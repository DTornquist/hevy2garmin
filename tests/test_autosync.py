"""Tests for auto-sync helpers in server.py."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest

from hevy2garmin import server
from hevy2garmin.server import (
    _acquire_sync_lock,
    _build_sync_workflow_yaml,
    _format_interval_label,
    _minutes_to_cron,
    _sync_executing,
)


class TestMinutesToCron:
    @pytest.mark.parametrize(
        "minutes,expected",
        [
            (30, "*/30 * * * *"),
            (60, "0 * * * *"),
            (120, "0 */2 * * *"),
            (240, "0 */4 * * *"),
            (360, "0 */6 * * *"),
            (720, "0 */12 * * *"),
            (1440, "0 0 * * *"),
        ],
    )
    def test_supported_intervals(self, minutes: int, expected: str) -> None:
        assert _minutes_to_cron(minutes) == expected

    def test_fallback_for_unexpected_value(self) -> None:
        # Anything not on the supported list falls back to every-2-hours
        assert _minutes_to_cron(45) == "0 */2 * * *"
        assert _minutes_to_cron(0) == "0 */2 * * *"


class TestFormatIntervalLabel:
    @pytest.mark.parametrize(
        "minutes,expected",
        [
            (30, "30 minutes"),
            (60, "1 hour"),
            (120, "2 hours"),
            (240, "4 hours"),
            (1440, "24 hours"),
        ],
    )
    def test_label(self, minutes: int, expected: str) -> None:
        assert _format_interval_label(minutes) == expected


class TestBuildSyncWorkflowYaml:
    def test_cron_reflects_interval(self) -> None:
        yml = _build_sync_workflow_yaml(30)
        assert "cron: '*/30 * * * *'" in yml

    def test_default_2h(self) -> None:
        yml = _build_sync_workflow_yaml(120)
        assert "cron: '0 */2 * * *'" in yml

    def test_24h(self) -> None:
        yml = _build_sync_workflow_yaml(1440)
        assert "cron: '0 0 * * *'" in yml

class TestSyncLock:
    def test_acquire_and_release(self) -> None:
        """Lock can be acquired and released without crashing (verifies time module is imported)."""
        assert _acquire_sync_lock() is True
        _sync_executing.release()

    def test_acquire_blocks_second(self) -> None:
        """Second acquire returns False when lock is held."""
        assert _acquire_sync_lock() is True
        assert _acquire_sync_lock() is False  # Already held
        _sync_executing.release()


class TestCronGraceDeferral:
    def test_all_fresh_workouts_are_deferred_without_calling_sync_helper(self) -> None:
        """Cron returns a useful response when every candidate is in grace."""
        workout = {"id": "fresh-1", "title": "Fresh", "exercises": []}
        hevy = MagicMock()
        hevy.get_workout_count.return_value = 1
        database = MagicMock()

        with (
            patch.object(
                server,
                "load_config",
                return_value={
                    "hevy_api_key": "test-key",
                    "sync": {"grace_period_minutes": 120},
                },
            ),
            patch("hevy2garmin.hevy.HevyClient", return_value=hevy),
            patch.object(server.db, "get_db", return_value=database),
            patch.object(server.db, "get_synced_count", return_value=0),
            patch.object(
                server,
                "_scan_for_unsynced",
                side_effect=[(workout, {}), (None, {})],
            ),
            patch("hevy2garmin.sync._workout_within_grace", return_value=True),
            patch("hevy2garmin.sync.sync_one_workout") as sync_one,
        ):
            response = asyncio.run(server._do_sync_one(respect_grace=True))

        assert json.loads(response.body) == {
            "synced": 0,
            "deferred": 1,
            "remaining": 1,
            "done": False,
        }
        sync_one.assert_not_called()


class TestBuildSyncWorkflowYaml:
    def test_workflow_structure_intact(self) -> None:
        """Make sure essential workflow pieces survive any cron change."""
        yml = _build_sync_workflow_yaml(60)
        assert "name: Sync Workouts" in yml
        assert "workflow_dispatch:" in yml
        assert "repository_dispatch:" in yml
        assert "DATABASE_URL: ${{ secrets.DATABASE_URL }}" in yml
        assert "hevy2garmin sync" in yml

    def test_actions_run_on_node_24(self) -> None:
        """Pin the generated workflow to Node-24 action majors so it doesn't
        regress to the deprecated Node-20 versions (checkout@v4, setup-python@v5)."""
        yml = _build_sync_workflow_yaml(120)
        assert "actions/checkout@v5" in yml
        assert "actions/setup-python@v6" in yml
        assert "actions/checkout@v4" not in yml
        assert "actions/setup-python@v5" not in yml
