"""Optional intervals.icu cleanup: delete a Garmin-sourced activity after merge.

Called from merge.py when an original watch activity is deleted from Garmin.
Prevents the original from appearing as a duplicate in intervals.icu after the
merged FIT is uploaded and synced.

Only runs when INTERVALS_API_KEY and INTERVALS_ATHLETE_ID env vars are set.
All errors are swallowed — never breaks the merge flow.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger("hevy2garmin")

_BASE_URL = "https://intervals.icu"


def try_delete_icu_activity(garmin_activity_id: int, workout_start: str) -> bool:
    """Delete the intervals.icu activity that corresponds to garmin_activity_id.

    Intervals.icu stores Garmin activities with the plain numeric activity id
    as external_id (a legacy "G{garminId}" form is matched too, just in case).
    Searches a ±2-hour window around workout_start to locate the activity,
    then deletes it.

    Returns True if deleted, False if not found or env vars not configured.
    Never raises.
    """
    api_key = os.environ.get("INTERVALS_API_KEY", "")
    athlete_id = os.environ.get("INTERVALS_ATHLETE_ID", "")
    if not api_key or not athlete_id:
        return False

    base_url = os.environ.get("INTERVALS_BASE_URL", _BASE_URL).rstrip("/")
    auth = ("API_KEY", api_key)
    target_external_ids = {str(garmin_activity_id), f"G{garmin_activity_id}"}

    try:
        start = datetime.fromisoformat(workout_start.replace("Z", "+00:00"))
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        logger.warning("ICU cleanup: invalid workout_start %r", workout_start)
        return False

    oldest = (start - timedelta(hours=2)).date().isoformat()
    newest = (start + timedelta(hours=2)).date().isoformat()

    try:
        resp = requests.get(
            f"{base_url}/api/v1/athlete/{athlete_id}/activities",
            auth=auth,
            params={"oldest": oldest, "newest": newest},
            timeout=15,
        )
        resp.raise_for_status()
        activities = resp.json()
    except Exception as e:
        logger.warning("ICU cleanup: failed to list activities: %s", e)
        return False

    icu_id = None
    for act in activities:
        if str(act.get("external_id")) in target_external_ids:
            icu_id = act.get("id")
            break

    if icu_id is None:
        logger.warning(
            "ICU cleanup: no activity with external_id=%s in window %s–%s — a stale duplicate may remain on intervals.icu",
            garmin_activity_id, oldest, newest,
        )
        return False

    try:
        # Single-activity operations live under /api/v1/activity/{id} —
        # the athlete-scoped path only supports listing (DELETE there is a 405).
        resp = requests.delete(
            f"{base_url}/api/v1/activity/{icu_id}",
            auth=auth,
            timeout=15,
        )
        resp.raise_for_status()
        logger.info("  ICU cleanup: deleted activity %s (garmin_id=%s)", icu_id, garmin_activity_id)
        return True
    except Exception as e:
        logger.warning("ICU cleanup: failed to delete activity %s: %s", icu_id, e)
        return False
