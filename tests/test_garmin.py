"""Tests for Garmin upload module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hevy2garmin.garmin import (
    _sanitize_activity_id,
    find_activity_by_start_time,
    generate_description,
    upload_fit,
)


class TestSanitizeActivityId:
    """Garmin sometimes returns internalId as a quoted string → must coerce to int (#153)."""

    def test_quoted_string(self) -> None:
        assert _sanitize_activity_id("'23126363872'") == 23126363872

    def test_double_quoted_string(self) -> None:
        assert _sanitize_activity_id('"23126363872"') == 23126363872

    def test_plain_int(self) -> None:
        assert _sanitize_activity_id(23126363872) == 23126363872

    def test_plain_numeric_string(self) -> None:
        assert _sanitize_activity_id("23126363872") == 23126363872

    def test_none(self) -> None:
        assert _sanitize_activity_id(None) is None

    def test_garbage_returns_none(self) -> None:
        assert _sanitize_activity_id("not-an-id") is None

    def test_empty_string_returns_none(self) -> None:
        assert _sanitize_activity_id("") is None


class TestFindActivityByStartTime:
    def _make_activities(self, *start_times: str) -> list[dict]:
        return [
            {"activityId": i + 1, "startTimeLocal": t}
            for i, t in enumerate(start_times)
        ]

    def test_exact_match(self) -> None:
        client = MagicMock()
        acts = self._make_activities("2026-04-01 20:00:00")
        with patch("hevy2garmin.garmin._limiter") as mock_limiter:
            mock_limiter.call.return_value = acts
            result = find_activity_by_start_time(client, "2026-04-01T20:00:00+00:00")
            assert result == 1

    def test_within_window(self) -> None:
        client = MagicMock()
        acts = self._make_activities("2026-04-01 20:05:00")
        with patch("hevy2garmin.garmin._limiter") as mock_limiter:
            mock_limiter.call.return_value = acts
            result = find_activity_by_start_time(client, "2026-04-01T20:00:00+00:00", window_minutes=10)
            assert result == 1

    def test_outside_window(self) -> None:
        client = MagicMock()
        acts = self._make_activities("2026-04-01 21:00:00")
        with patch("hevy2garmin.garmin._limiter") as mock_limiter:
            mock_limiter.call.return_value = acts
            result = find_activity_by_start_time(client, "2026-04-01T20:00:00+00:00", window_minutes=10)
            assert result is None

    def test_no_activities(self) -> None:
        client = MagicMock()
        with patch("hevy2garmin.garmin._limiter") as mock_limiter:
            mock_limiter.call.return_value = []
            result = find_activity_by_start_time(client, "2026-04-01T20:00:00+00:00")
            assert result is None

    def test_picks_closest(self) -> None:
        client = MagicMock()
        acts = self._make_activities("2026-04-01 21:00:00", "2026-04-01 20:02:00")
        with patch("hevy2garmin.garmin._limiter") as mock_limiter:
            mock_limiter.call.return_value = acts
            result = find_activity_by_start_time(client, "2026-04-01T20:00:00+00:00", window_minutes=10)
            assert result == 2  # the 20:02 one

    def test_invalid_target_time(self) -> None:
        client = MagicMock()
        result = find_activity_by_start_time(client, "not-a-date")
        assert result is None

    def test_api_error_returns_none(self) -> None:
        client = MagicMock()
        with patch("hevy2garmin.garmin._limiter") as mock_limiter:
            mock_limiter.call.side_effect = Exception("API error")
            result = find_activity_by_start_time(client, "2026-04-01T20:00:00+00:00")
            assert result is None

    def test_excludes_pre_upload_activity(self) -> None:
        client = MagicMock()
        acts = self._make_activities(
            "2026-04-01 20:00:00",
            "2026-04-01 20:00:02",
        )
        with patch("hevy2garmin.garmin._limiter") as mock_limiter:
            mock_limiter.call.return_value = acts
            result = find_activity_by_start_time(
                client,
                "2026-04-01T20:00:00+00:00",
                exclude_activity_ids=["1"],
            )
            assert result == 2


class TestUploadFit:
    def test_post_upload_lookup_excludes_snapshot_ids(self, tmp_path: Path) -> None:
        fit_path = tmp_path / "workout.fit"
        fit_path.write_bytes(b"fit")
        client = MagicMock()
        client.upload_activity.return_value = {"detailedImportResult": {"uploadId": "u1"}}

        with patch("hevy2garmin.garmin._limiter") as limiter, patch(
            "hevy2garmin.garmin.time.sleep"
        ), patch(
            "hevy2garmin.garmin.find_activity_by_start_time", return_value=2
        ) as finder:
            limiter.call.side_effect = lambda func, *args: func(*args)
            result = upload_fit(
                client,
                fit_path,
                workout_start="2026-04-01T20:00:00+00:00",
                exclude_activity_ids=["1"],
            )

        assert result == {"upload_id": "u1", "activity_id": 2}
        assert finder.call_args.kwargs["exclude_activity_ids"] == ["1"]


class TestGenerateDescription:
    def test_basic_description(self, sample_workout: dict) -> None:
        desc = generate_description(sample_workout, calories=200, avg_hr=95)
        assert "🏋️ Push" in desc
        assert "200 kcal" in desc
        assert "avg 95 bpm" in desc
        assert "hevy2garmin" in desc

    def test_includes_exercises(self, sample_workout: dict) -> None:
        desc = generate_description(sample_workout)
        assert "Bench Press" in desc
        assert "Shoulder Press" in desc

    def test_shows_sets_and_weight(self, sample_workout: dict) -> None:
        desc = generate_description(sample_workout)
        assert "3 sets" in desc  # 3 normal bench sets
        assert "60.0kg" in desc

    def test_no_calories(self, sample_workout: dict) -> None:
        desc = generate_description(sample_workout, calories=None, avg_hr=None)
        assert "kcal" not in desc
        assert "bpm" not in desc

    def test_duration(self, sample_workout: dict) -> None:
        desc = generate_description(sample_workout)
        assert "45 min" in desc

    def test_empty_workout(self) -> None:
        workout = {"title": "Empty", "exercises": []}
        desc = generate_description(workout)
        assert "Empty" in desc

    def test_warmup_only_singular(self) -> None:
        workout = {"title": "W", "exercises": [
            {"title": "Bench", "sets": [{"type": "warmup", "weight_kg": 20, "reps": 5}]}
        ]}
        desc = generate_description(workout)
        assert "1 warmup set" in desc
        assert "1 warmup sets" not in desc

    def test_warmup_only_plural(self) -> None:
        workout = {"title": "W", "exercises": [
            {"title": "Bench", "sets": [
                {"type": "warmup", "weight_kg": 20, "reps": 5},
                {"type": "warmup", "weight_kg": 30, "reps": 5},
            ]}
        ]}
        desc = generate_description(workout)
        assert "2 warmup sets" in desc

    def test_cardio_exercise_description(self) -> None:
        workout = {"title": "Cardio", "exercises": [
            {"title": "Treadmill", "sets": [
                {"type": "normal", "distance_meters": 5000, "duration_seconds": 1800, "weight_kg": None, "reps": None}
            ]}
        ]}
        desc = generate_description(workout)
        assert "5.0km" in desc
        assert "30min" in desc
        assert "1 set" in desc
        assert "1 sets" not in desc

    def test_singular_set_grammar(self) -> None:
        """1 normal set should say 'set' not 'sets'."""
        workout = {"title": "T", "exercises": [
            {"title": "Curl", "sets": [{"type": "normal", "weight_kg": 10, "reps": 12}]}
        ]}
        desc = generate_description(workout)
        assert "1 set" in desc
        assert "1 sets" not in desc

    def test_plural_sets_grammar(self) -> None:
        """3 normal sets should say 'sets'."""
        workout = {"title": "T", "exercises": [
            {"title": "Curl", "sets": [
                {"type": "normal", "weight_kg": 10, "reps": 12},
                {"type": "normal", "weight_kg": 10, "reps": 10},
                {"type": "normal", "weight_kg": 10, "reps": 8},
            ]}
        ]}
        desc = generate_description(workout)
        assert "3 sets" in desc

    def test_singular_set_with_warmup_prefix(self) -> None:
        """Exercise with warmup + 1 working set shows working set in singular."""
        workout = {"title": "T", "exercises": [
            {"title": "Bench", "sets": [
                {"type": "warmup", "weight_kg": 20, "reps": 5},
                {"type": "normal", "weight_kg": 80, "reps": 5},
            ]}
        ]}
        desc = generate_description(workout)
        assert "1 set" in desc
        assert "1 sets" not in desc

    def test_mixed_strength_and_cardio(self) -> None:
        workout = {"title": "Mixed", "exercises": [
            {"title": "Bench", "sets": [{"type": "normal", "weight_kg": 80, "reps": 8}]},
            {"title": "Treadmill", "sets": [
                {"type": "normal", "distance_meters": 3000, "duration_seconds": 900, "weight_kg": None, "reps": None}
            ]},
        ]}
        desc = generate_description(workout)
        assert "80.0kg" in desc
        assert "3.0km" in desc


def test_list_workouts_raises_on_non_list_body():
    """A 2xx response with a non-list body (an error envelope or shape drift) must
    raise, not be read as an empty library. Reading it as ``[]`` would make routine
    reconciliation flag every synced routine as deleted on Garmin."""
    from hevy2garmin.garmin import list_workouts
    client = MagicMock()
    resp = MagicMock()
    resp.json.return_value = {"error": "temporarily unavailable"}  # dict, not a list
    client.client.request.return_value = resp
    with patch("hevy2garmin.garmin.time.sleep"):
        with pytest.raises(RuntimeError, match="not a list"):
            list_workouts(client)


def test_list_workouts_returns_well_formed_list():
    """A well-formed list body passes through unchanged."""
    from hevy2garmin.garmin import list_workouts
    client = MagicMock()
    resp = MagicMock()
    resp.json.return_value = [{"workoutId": 1}, {"workoutId": 2}]
    client.client.request.return_value = resp
    with patch("hevy2garmin.garmin.time.sleep"):
        assert list_workouts(client) == [{"workoutId": 1}, {"workoutId": 2}]
