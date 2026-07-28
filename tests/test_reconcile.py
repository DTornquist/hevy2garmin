from __future__ import annotations
from unittest.mock import MagicMock


def _act(aid, manufacturer, start="2026-03-15 18:02:00", dur=2580, type_key="strength_training"):
    return {"activityId": aid, "manufacturer": manufacturer,
            "startTimeGMT": start, "startTimeLocal": start,
            "duration": dur, "activityType": {"typeKey": type_key}}


WORKOUT = {"id": "w1", "title": "Push",
           "start_time": "2026-03-15T18:00:00+00:00",
           "end_time": "2026-03-15T18:45:00+00:00"}


def test_detects_tool_plus_watch_pair():
    from hevy2garmin.reconcile import detect_duplicates
    client = MagicMock()
    client.get_activities_by_date.return_value = [
        _act(1, "DEVELOPMENT"), _act(2, "GARMIN"),
    ]
    dups = detect_duplicates(client, [WORKOUT])
    assert len(dups) == 1
    d = dups[0]
    assert d["workout_id"] == "w1"
    assert {d["tool_activity_id"], d["watch_activity_id"]} == {1, 2}


def test_single_activity_is_not_a_duplicate():
    from hevy2garmin.reconcile import detect_duplicates
    client = MagicMock()
    client.get_activities_by_date.return_value = [_act(1, "DEVELOPMENT")]
    assert detect_duplicates(client, [WORKOUT]) == []


def test_never_raises_on_garmin_error():
    from hevy2garmin.reconcile import detect_duplicates
    client = MagicMock()
    client.get_activities_by_date.side_effect = RuntimeError("boom")
    assert detect_duplicates(client, [WORKOUT]) == []


# ── reconcile_missing_routine_workouts ──────────────────────────────────────


def _routine_store(tmp_path):
    from hevy2garmin.db_sqlite import SQLiteDatabase
    return SQLiteDatabase(tmp_path / "reconcile.db")


def test_marks_routine_missing_when_workout_gone(tmp_path):
    from hevy2garmin.reconcile import reconcile_missing_routine_workouts
    store = _routine_store(tmp_path)
    store.mark_routine_synced("r1", garmin_workout_id="555", title="Push",
                              content_hash="h1")
    changed = reconcile_missing_routine_workouts(store, [{"workoutId": 999}])
    assert changed == ["r1"]
    record = store.get_synced_routine("r1")
    assert record["status"] == "missing_on_garmin"
    # Only the status flips — the hash and workout id stay for the re-sync.
    assert record["content_hash"] == "h1"
    assert record["garmin_workout_id"] == "555"


def test_none_listing_is_a_noop(tmp_path):
    # A failed listing (auth/rate limit) must not be read as "everything deleted".
    from hevy2garmin.reconcile import reconcile_missing_routine_workouts
    store = _routine_store(tmp_path)
    store.mark_routine_synced("r1", garmin_workout_id="555")
    assert reconcile_missing_routine_workouts(store, None) == []
    assert store.get_synced_routine("r1")["status"] == "success"


def test_missing_self_heals_when_workout_reappears(tmp_path):
    # A false positive (e.g. truncated listing) recovers on the next reconcile.
    from hevy2garmin.reconcile import reconcile_missing_routine_workouts
    store = _routine_store(tmp_path)
    store.mark_routine_synced("r1", garmin_workout_id="555")
    store.set_routine_status("r1", "missing_on_garmin")
    changed = reconcile_missing_routine_workouts(store, [{"workoutId": 555}])
    assert changed == ["r1"]
    assert store.get_synced_routine("r1")["status"] == "success"


def test_schedule_pending_is_not_promoted_to_success(tmp_path):
    # Promoting a present-but-pending row would cancel its schedule retry.
    from hevy2garmin.reconcile import reconcile_missing_routine_workouts
    store = _routine_store(tmp_path)
    store.mark_routine_synced("r1", garmin_workout_id="555", status="schedule_pending")
    assert reconcile_missing_routine_workouts(store, [{"workoutId": 555}]) == []
    assert store.get_synced_routine("r1")["status"] == "schedule_pending"


def test_schedule_pending_can_go_missing(tmp_path):
    from hevy2garmin.reconcile import reconcile_missing_routine_workouts
    store = _routine_store(tmp_path)
    store.mark_routine_synced("r1", garmin_workout_id="555", status="schedule_pending")
    assert reconcile_missing_routine_workouts(store, []) == ["r1"]
    assert store.get_synced_routine("r1")["status"] == "missing_on_garmin"


def test_rows_without_workout_id_are_ignored(tmp_path):
    from hevy2garmin.reconcile import reconcile_missing_routine_workouts
    store = _routine_store(tmp_path)
    store.mark_routine_synced("r1")  # no garmin_workout_id
    assert reconcile_missing_routine_workouts(store, []) == []
    assert store.get_synced_routine("r1")["status"] == "success"


def test_routine_reconcile_never_raises_on_broken_store():
    from hevy2garmin.reconcile import reconcile_missing_routine_workouts
    store = MagicMock()
    store.list_synced_routines.side_effect = RuntimeError("db down")
    assert reconcile_missing_routine_workouts(store, []) == []
