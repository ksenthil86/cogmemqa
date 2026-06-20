"""
Tests for scripts/demo_summary.py — Sprint v5 Task 6.

Only verifies CLI behaviour that doesn't require Neo4j.
Full output is validated by running the script after replay_meridian.py.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_SCRIPT = Path(__file__).parent.parent / "scripts" / "demo_summary.py"


def test_demo_summary_script_exists():
    assert _SCRIPT.exists(), f"Script not found: {_SCRIPT}"


def test_demo_summary_help_exits_zero():
    result = subprocess.run(  # nosec B603
        [sys.executable, str(_SCRIPT), "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"--help exited {result.returncode}\nstderr: {result.stderr}"
    )


def test_demo_summary_help_mentions_req_flag():
    result = subprocess.run(  # nosec B603
        [sys.executable, str(_SCRIPT), "--help"],
        capture_output=True,
        text=True,
    )
    assert "--req" in result.stdout, (
        f"Expected '--req' in help output:\n{result.stdout}"
    )
