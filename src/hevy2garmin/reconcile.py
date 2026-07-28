"""Reconcile local sync state against Garmin's actual state.

Two concerns live here:

- :func:`detect_duplicates` — detect (log-only) duplicate Garmin activities left
  by past sync races: hevy2garmin uploaded a fresh activity before the watch copy
  landed, leaving two activities for one workout. Nothing is deleted — deletion
  is a separate, opt-in feature.
- :func:`reconcile_missing_routine_workouts` — flag routine planned workouts the
  user deleted on Garmin, so the dashboard stops showing them as synced.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from hevy2garmin.fit import _parse_timestamp

logger = logging.getLogger("hevy2garmin")


def detect_duplicates(client, workouts: list[dict], limiter=None) -> list[dict]:
    """Return a list of duplicate descriptors, one per workout window that holds
    both a tool-created (manufacturer DEVELOPMENT) and a watch (other
    manufacturer) activity. Best-effort: never raises."""
    dups: list[dict] = []
    for workout in workouts:
        try:
            start = _parse_timestamp(workout.get("start_time") or workout.get("startTime", ""))
            end = _parse_timestamp(workout.get("end_time") or workout.get("endTime", ""))
            if start is None or end is None:
                continue
            # Normalize to naive UTC for comparison so Garmin's naive GMT strings
            # (no offset) and workout's aware UTC strings can be compared safely.
            start_naive = start.replace(tzinfo=None)
            end_naive = end.replace(tzinfo=None)
            date_str = str(workout.get("start_time") or "")[:10]
            call = (limiter.call if limiter is not None else (lambda f, *a: f(*a)))
            acts = call(client.get_activities_by_date, date_str, date_str)
            tool_id = watch_id = None
            for act in acts or []:
                a_start = _parse_timestamp(act.get("startTimeGMT") or act.get("startTimeLocal", ""))
                a_dur = act.get("duration", 0) or 0
                if a_start is None or a_dur <= 0:
                    continue
                # Normalize activity timestamps to naive UTC as well.
                a_start_naive = a_start.replace(tzinfo=None)
                a_end_naive = a_start_naive + timedelta(seconds=a_dur)
                if a_start_naive > end_naive or a_end_naive < start_naive:
                    continue
                manufacturer = str(act.get("manufacturer") or "").upper()
                if manufacturer == "DEVELOPMENT":
                    tool_id = act.get("activityId")
                elif manufacturer:
                    watch_id = act.get("activityId")
            if tool_id is not None and watch_id is not None:
                dup = {"workout_id": workout.get("id"),
                       "workout_title": workout.get("title"),
                       "tool_activity_id": tool_id,
                       "watch_activity_id": watch_id}
                logger.warning(
                    "  ⚠ Duplicate for workout %s: tool activity %s + watch activity %s",
                    dup["workout_id"], tool_id, watch_id,
                )
                dups.append(dup)
        except Exception:
            logger.debug("duplicate detection skipped for a workout", exc_info=True)
            continue
    return dups


def reconcile_missing_routine_workouts(store, garmin_workouts: list[dict] | None) -> list[str]:
    """Flag synced routines whose Garmin planned workout no longer exists.

    ``garmin_workouts`` is a full ``list_workouts()`` result; ``None`` means the
    listing failed (auth, rate limit, network) — reconciliation is skipped entirely
    rather than treating an error as "everything was deleted". A tracked id absent
    from the listing flips the routine's status to ``missing_on_garmin``; an id
    that reappears flips it back to ``success`` (self-healing a false positive from
    a truncated listing). ``schedule_pending`` rows are never promoted to
    ``success`` — that would cancel their schedule retry. Best-effort: never raises.

    Returns the ``hevy_routine_id``s whose status changed.
    """
    if garmin_workouts is None:
        return []
    changed: list[str] = []
    try:
        present = {
            str(w["workoutId"]) for w in garmin_workouts if w.get("workoutId") is not None
        }
        for row in store.list_synced_routines():
            wid = row.get("garmin_workout_id")
            if not wid:
                continue
            status = row.get("status") or "success"
            if str(wid) not in present and status != "missing_on_garmin":
                store.set_routine_status(row["hevy_routine_id"], "missing_on_garmin")
                changed.append(row["hevy_routine_id"])
                logger.info(
                    "Routine %s (%s): Garmin workout %s is gone — marked missing",
                    row["hevy_routine_id"], row.get("title") or "?", wid,
                )
            elif str(wid) in present and status == "missing_on_garmin":
                store.set_routine_status(row["hevy_routine_id"], "success")
                changed.append(row["hevy_routine_id"])
    except Exception:
        logger.debug("routine reconcile skipped", exc_info=True)
    return changed
