"""
Tests for scripts/replay_meridian.py — Sprint v5 Task 5.

Only verifies the --dry-run path (no Neo4j required).
Full replay is covered by the Task 7 e2e test.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_SCRIPT = Path(__file__).parent.parent / "scripts" / "replay_meridian.py"


def test_replay_script_exists():
    assert _SCRIPT.exists(), f"Script not found: {_SCRIPT}"


def test_replay_dry_run_exits_zero():
    result = subprocess.run(  # nosec B603
        [sys.executable, str(_SCRIPT), "--dry-run"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"--dry-run exited {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_replay_dry_run_prints_commit_count():
    result = subprocess.run(  # nosec B603
        [sys.executable, str(_SCRIPT), "--dry-run"],
        capture_output=True,
        text=True,
    )
    assert "5 commits" in result.stdout, (
        f"Expected '5 commits' in stdout, got:\n{result.stdout}"
    )
