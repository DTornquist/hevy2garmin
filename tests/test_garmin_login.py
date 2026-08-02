"""Tests for the in-memory two-step Garmin login."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
from garmin_auth.auth import NEEDS_MFA
from garminconnect import (
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

from hevy2garmin import garmin_login
from hevy2garmin.garmin_login import _PendingStore


@pytest.fixture(autouse=True)
def fresh_store():
    """Each test gets an empty pending store."""
    garmin_login._store = _PendingStore()
    yield


def _client(name="Jane Athlete"):
    c = MagicMock()
    c.display_name = name
    return c


def test_begin_clean_success():
    with patch("hevy2garmin.garmin_login.GarminAuth") as GA:
        GA.return_value.login.return_value = _client()
        out = garmin_login.begin("e@x.com", "pw")
    assert out == {"status": "success", "display_name": "Jane Athlete"}


def test_begin_needs_mfa_stores_session():
    with patch("hevy2garmin.garmin_login.GarminAuth") as GA:
        GA.return_value.login.return_value = NEEDS_MFA
        out = garmin_login.begin("e@x.com", "pw")
    assert out["status"] == "needs_mfa"
    assert out["session_id"]
    assert garmin_login._store.get(out["session_id"], 0.0) is not None


@pytest.mark.parametrize("exc,status", [
    (GarminConnectAuthenticationError("bad"), "invalid_credentials"),
    (GarminConnectTooManyRequestsError("429"), "rate_limited"),
    (GarminConnectConnectionError("down"), "error"),
])
def test_begin_exception_mapping(exc, status):
    with patch("hevy2garmin.garmin_login.GarminAuth") as GA:
        GA.return_value.login.side_effect = exc
        out = garmin_login.begin("e@x.com", "pw")
    assert out["status"] == status


def test_complete_success_evicts():
    auth = MagicMock()
    auth.resume_login.return_value = _client()
    sid = garmin_login._store.put(auth, time.time())  # stored "now"; complete() reads now+epsilon
    out = garmin_login.complete(sid, "123456")
    assert out == {"status": "success", "display_name": "Jane Athlete"}
    assert garmin_login._store.get(sid, 0.0) is None


def test_complete_unknown_session():
    assert garmin_login.complete("nope", "123456") == {"status": "session_expired"}


def test_complete_wrong_code_keeps_entry():
    auth = MagicMock()
    auth.resume_login.side_effect = GarminConnectAuthenticationError("bad code")
    sid = garmin_login._store.put(auth, time.time())  # stored "now"; complete() reads now+epsilon
    out = garmin_login.complete(sid, "000000")
    assert out["status"] == "mfa_failed"
    assert garmin_login._store.get(sid, 0.0) is not None  # retained for retry


def test_pending_store_ttl_eviction():
    store = _PendingStore(ttl=600)
    sid = store.put(MagicMock(), now=1000.0)
    assert store.get(sid, now=1500.0) is not None       # within TTL
    assert store.get(sid, now=1000.0 + 601) is None      # expired


def test_complete_empty_code_is_mfa_failed():
    auth = MagicMock()
    auth.resume_login.side_effect = ValueError("mfa_code must be a non-empty string")
    sid = garmin_login._store.put(auth, time.time())
    out = garmin_login.complete(sid, "")
    assert out["status"] == "mfa_failed"
    assert garmin_login._store.get(sid, 0.0) is not None  # retained for retry
