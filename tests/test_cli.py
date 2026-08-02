"""Tests for CLI commands."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch


def run_cli(*args: str) -> subprocess.CompletedProcess:
    """Run hevy2garmin CLI and capture output."""
    return subprocess.run(
        [sys.executable, "-m", "hevy2garmin.cli", *args],
        capture_output=True,
        text=True,
        timeout=10,
    )


class TestNoArgs:
    def test_shows_help(self) -> None:
        result = run_cli()
        assert result.returncode == 0
        assert "hevy2garmin" in result.stdout
        assert "sync" in result.stdout
        assert "init" in result.stdout
        assert "list" in result.stdout


class TestStatus:
    def test_without_config(self, tmp_path: Path) -> None:
        """Status with no config should show 'not configured' — but subprocess reads real config.
        Test the function directly instead."""
        with patch("hevy2garmin.config.CONFIG_FILE", tmp_path / "nonexistent.json"):
            from hevy2garmin.config import is_configured
            assert is_configured() is False


class TestMap:
    def test_map_command_in_memory(self) -> None:
        from hevy2garmin.mapper import _custom_mappings, lookup_exercise

        _custom_mappings["CLI Test Exercise"] = (10, 20)
        cat, subcat, _ = lookup_exercise("CLI Test Exercise")
        assert cat == 10
        assert subcat == 20
        _custom_mappings.clear()


class TestSyncDryRun:
    def test_dry_run_flag(self) -> None:
        # Just verify the flag is accepted
        result = run_cli("sync", "--dry-run", "--help")
        assert result.returncode == 0
        assert "dry-run" in result.stdout

    def test_all_flag(self) -> None:
        result = run_cli("sync", "--all", "--help")
        assert result.returncode == 0

    def test_since_flag(self) -> None:
        result = run_cli("sync", "--since", "2026-01-01", "--help")
        assert result.returncode == 0


from hevy2garmin.cli import _garmin_interactive_login


class TestGarminInteractiveLogin:
    def test_clean_success(self, capsys) -> None:
        with patch("hevy2garmin.garmin_login.begin",
                   return_value={"status": "success", "display_name": "Jane"}):
            _garmin_interactive_login("e@x.com", "pw")
        assert "Authenticated as Jane" in capsys.readouterr().out

    def test_mfa_flow(self, capsys) -> None:
        with patch("hevy2garmin.garmin_login.begin",
                   return_value={"status": "needs_mfa", "session_id": "sid-1"}), \
             patch("hevy2garmin.garmin_login.complete",
                   return_value={"status": "success", "display_name": "Jane"}) as comp, \
             patch("builtins.input", return_value="123456"):
            _garmin_interactive_login("e@x.com", "pw")
        comp.assert_called_once_with("sid-1", "123456")
        assert "Authenticated as Jane" in capsys.readouterr().out

    def test_invalid_credentials_prints_and_returns(self, capsys) -> None:
        with patch("hevy2garmin.garmin_login.begin",
                   return_value={"status": "invalid_credentials", "message": "bad"}):
            _garmin_interactive_login("e@x.com", "pw")
        assert "email" in capsys.readouterr().out.lower()

    def test_rate_limited(self, capsys) -> None:
        with patch("hevy2garmin.garmin_login.begin",
                   return_value={"status": "rate_limited", "message": "429"}):
            _garmin_interactive_login("e@x.com", "pw")
        assert "rate-limit" in capsys.readouterr().out.lower()

    def test_mfa_failed(self, capsys) -> None:
        with patch("hevy2garmin.garmin_login.begin",
                   return_value={"status": "needs_mfa", "session_id": "sid-1"}), \
             patch("hevy2garmin.garmin_login.complete",
                   return_value={"status": "mfa_failed", "message": "Code rejected, try again"}), \
             patch("builtins.input", return_value="000000"):
            _garmin_interactive_login("e@x.com", "pw")
        assert "rejected" in capsys.readouterr().out.lower()

    def test_mfa_eof_is_handled(self, capsys) -> None:
        with patch("hevy2garmin.garmin_login.begin",
                   return_value={"status": "needs_mfa", "session_id": "sid-1"}), \
             patch("builtins.input", side_effect=EOFError):
            _garmin_interactive_login("e@x.com", "pw")  # must not raise
        assert "no input" in capsys.readouterr().out.lower()
