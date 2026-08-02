"""In-memory two-step Garmin login (password -> MFA) served from the Pi.

This is the only module that knows the MFA mechanics; the dashboard and CLI both
drive it through begin()/complete(). Login happens directly from this host (a
residential IP Garmin does not block), so the password never leaves the Pi.

Pending MFA logins are held in memory between the two HTTP requests; the ``serve``
daemon is a single long-lived process, so the pending GarminAuth object survives
from begin() to complete(). Assumes a single worker process (see spec, open risks).
"""

from __future__ import annotations

import logging
import secrets
import threading
import time

from garmin_auth import GarminAuth
from garmin_auth.auth import NEEDS_MFA
from garminconnect import (
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

logger = logging.getLogger("hevy2garmin")

_TTL = 600  # seconds a pending MFA session stays valid


class _PendingStore:
    """Thread-safe store of pending MFA logins, keyed by an opaque session id."""

    def __init__(self, ttl: int = _TTL) -> None:
        self._ttl = ttl
        self._lock = threading.Lock()
        self._pending: dict[str, tuple[GarminAuth, float]] = {}

    def _evict_expired(self, now: float) -> None:
        # caller holds the lock
        expired = [sid for sid, (_, ts) in self._pending.items() if now - ts > self._ttl]
        for sid in expired:
            del self._pending[sid]

    def put(self, auth: GarminAuth, now: float) -> str:
        sid = secrets.token_urlsafe(32)
        with self._lock:
            self._evict_expired(now)
            self._pending[sid] = (auth, now)
        return sid

    def get(self, sid: str, now: float) -> GarminAuth | None:
        with self._lock:
            self._evict_expired(now)
            entry = self._pending.get(sid)
            return entry[0] if entry else None

    def pop(self, sid: str, now: float) -> GarminAuth | None:
        with self._lock:
            self._evict_expired(now)
            entry = self._pending.pop(sid, None)
            return entry[0] if entry else None


_store = _PendingStore()


def begin(email: str, password: str) -> dict:
    """Start a Garmin login. Returns a status dict; never raises for auth errors."""
    try:
        auth = GarminAuth(email=email, password=password, return_on_mfa=True)
        result = auth.login()
    except GarminConnectAuthenticationError as e:
        return {"status": "invalid_credentials", "message": str(e)[:200]}
    except GarminConnectTooManyRequestsError as e:
        return {"status": "rate_limited", "message": str(e)[:200]}
    except GarminConnectConnectionError as e:
        return {"status": "error", "message": str(e)[:200]}
    except Exception as e:
        logger.warning("garmin_login.begin unexpected error: %s", e)
        return {"status": "error", "message": str(e)[:200]}

    if result == NEEDS_MFA:
        sid = _store.put(auth, time.time())
        return {"status": "needs_mfa", "session_id": sid}

    # result is an authenticated Garmin client; login() already persisted tokens.
    return {"status": "success", "display_name": getattr(result, "display_name", None)}


def complete(session_id: str, code: str) -> dict:
    """Finish a pending MFA login with the user's code."""
    # get-then-pop is two lock acquisitions; safe only because serve runs as a
    # single process (see module docstring). A multi-worker deployment would need
    # an atomic pop-if-present here.
    auth = _store.get(session_id, time.time())
    if auth is None:
        return {"status": "session_expired"}
    try:
        client = auth.resume_login(code)
    except (GarminConnectAuthenticationError, ValueError):
        # Wrong/empty code — keep the pending entry so the user can re-enter just the code.
        return {"status": "mfa_failed", "message": "Code rejected, try again"}
    except Exception as e:
        logger.warning("garmin_login.complete unexpected error: %s", e)
        return {"status": "error", "message": str(e)[:200]}
    _store.pop(session_id, time.time())
    return {"status": "success", "display_name": getattr(client, "display_name", None)}
