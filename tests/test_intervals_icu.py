"""Tests for the optional intervals.icu cleanup after a merge."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from hevy2garmin.intervals_icu import try_delete_icu_activity

ENV = {"INTERVALS_API_KEY": "secret", "INTERVALS_ATHLETE_ID": "i12345"}
START = "2026-03-15T18:00:00+00:00"


@pytest.fixture
def icu_env(monkeypatch):
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    # Pin the base URL so assertions don't depend on a real default.
    monkeypatch.setenv("INTERVALS_BASE_URL", "https://intervals.icu")


def _resp(json_data=None, raise_exc=None):
    resp = MagicMock()
    if raise_exc is not None:
        resp.raise_for_status.side_effect = raise_exc
    else:
        resp.raise_for_status.return_value = None
    resp.json.return_value = json_data
    return resp


def test_no_env_vars_is_noop(monkeypatch):
    monkeypatch.delenv("INTERVALS_API_KEY", raising=False)
    monkeypatch.delenv("INTERVALS_ATHLETE_ID", raising=False)
    with patch("hevy2garmin.intervals_icu.requests") as req:
        assert try_delete_icu_activity(999, START) is False
        req.get.assert_not_called()
        req.delete.assert_not_called()


def test_found_activity_is_deleted(icu_env):
    activities = [
        {"id": 111, "external_id": "Gnope"},
        {"id": 222, "external_id": "G999"},
    ]
    with patch("hevy2garmin.intervals_icu.requests") as req:
        req.get.return_value = _resp(json_data=activities)
        req.delete.return_value = _resp()

        assert try_delete_icu_activity(999, START) is True

        # GET hit the activities list with a ±2h date window.
        get_args, get_kwargs = req.get.call_args
        assert get_args[0] == "https://intervals.icu/api/v1/athlete/i12345/activities"
        assert get_kwargs["auth"] == ("API_KEY", "secret")
        assert get_kwargs["params"] == {"oldest": "2026-03-15", "newest": "2026-03-15"}

        # DELETE targeted the matched ICU id (222), not the Garmin id, on the
        # single-activity endpoint (the athlete-scoped path 405s on DELETE).
        del_args, _ = req.delete.call_args
        assert del_args[0] == "https://intervals.icu/api/v1/activity/222"


def test_plain_numeric_external_id_is_deleted(icu_env):
    # intervals.icu reports Garmin activities with a plain numeric external_id
    # (no "G" prefix) — observed live 2026-07: {"external_id": "23633234350",
    # "source": "GARMIN_CONNECT"}. The cleanup must match that form too.
    activities = [
        {"id": "i166661330", "external_id": "23632538775", "source": "GARMIN_CONNECT"},
        {"id": "i166677402", "external_id": "23633234350", "source": "GARMIN_CONNECT"},
    ]
    with patch("hevy2garmin.intervals_icu.requests") as req:
        req.get.return_value = _resp(json_data=activities)
        req.delete.return_value = _resp()

        assert try_delete_icu_activity(23633234350, START) is True

        del_args, _ = req.delete.call_args
        assert del_args[0] == "https://intervals.icu/api/v1/activity/i166677402"


def test_not_found_does_not_delete(icu_env):
    with patch("hevy2garmin.intervals_icu.requests") as req:
        req.get.return_value = _resp(json_data=[{"id": 1, "external_id": "Gother"}])
        assert try_delete_icu_activity(999, START) is False
        req.delete.assert_not_called()


def test_invalid_workout_start_is_noop(icu_env):
    with patch("hevy2garmin.intervals_icu.requests") as req:
        assert try_delete_icu_activity(999, "not-a-date") is False
        req.get.assert_not_called()
        req.delete.assert_not_called()


def test_list_failure_never_raises(icu_env):
    with patch("hevy2garmin.intervals_icu.requests") as req:
        req.get.side_effect = RuntimeError("network down")
        assert try_delete_icu_activity(999, START) is False
        req.delete.assert_not_called()


def test_delete_failure_never_raises(icu_env):
    with patch("hevy2garmin.intervals_icu.requests") as req:
        req.get.return_value = _resp(json_data=[{"id": 222, "external_id": "G999"}])
        req.delete.return_value = _resp(raise_exc=RuntimeError("403"))
        assert try_delete_icu_activity(999, START) is False


@pytest.mark.parametrize(
    "body", [{"error": "nope"}, "a string", 42, None], ids=["dict", "str", "int", "null"]
)
def test_non_list_200_body_never_raises(icu_env, body):
    """A 200 whose body is not a list must not escape into the sync.

    The match loop runs outside the request try/except, so an unexpected shape
    used to raise from here (a dict iterates to str keys → AttributeError on
    .get; an int → TypeError). This helper sits inside finalize_pending before
    next_step="commit", so a raise reverts to phase="finalizing", retries the
    delete on the already-deleted watch id, and after the retry cap files a
    fully-successful merge as needs_review.
    """
    with patch("hevy2garmin.intervals_icu.requests") as req:
        req.get.return_value = _resp(json_data=body)
        assert try_delete_icu_activity(999, START) is False
        req.delete.assert_not_called()


@pytest.mark.parametrize(
    "workout_start", [1773763200, {"start_time": START}, [START], None], ids=["int", "dict", "list", "none"]
)
def test_non_string_workout_start_never_raises(icu_env, workout_start):
    """A non-str start has no .replace — AttributeError, not ValueError/TypeError."""
    with patch("hevy2garmin.intervals_icu.requests") as req:
        assert try_delete_icu_activity(999, workout_start) is False
        req.get.assert_not_called()
        req.delete.assert_not_called()


def test_zero_icu_id_is_deleted(icu_env):
    # An ICU activity id of 0 is valid and must be deleted, not treated as "not found".
    with patch("hevy2garmin.intervals_icu.requests") as req:
        req.get.return_value = _resp(json_data=[{"id": 0, "external_id": "G999"}])
        req.delete.return_value = _resp()
        assert try_delete_icu_activity(999, START) is True
        del_args, _ = req.delete.call_args
        assert del_args[0] == "https://intervals.icu/api/v1/activity/0"
