"""
Build-cycle orchestrator — Sprint v5 B8.

run_build_cycle() sequences the three downstream agents (B5 → B6 → B7) for
a single commit cycle and returns the health report_id produced by B7.
"""
from __future__ import annotations

from typing import Any


def run_build_cycle(
    driver: Any,
    b5: Any,
    b6: Any,
    b7: Any,
    scan_path: str = "src",
) -> str:
    """
    Orchestrate one build-cycle after a commit is ingested.

    Steps:
      1. b5.run(driver)            — re-execute all functional tests
      2. b6.run(driver, scan_path) — re-scan for security findings
      3. b7.run(driver)            — compute new health report snapshot

    Returns the report_id string from B7.
    """
    b5.run(driver)
    b6.run(driver, scan_path)
    return b7.run(driver)
