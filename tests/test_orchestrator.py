"""
Tests for run_build_cycle() orchestrator — Sprint v5 Task 4.

Uses stub agents with call-tracking flags; no Neo4j driver required.
"""
from __future__ import annotations


# ── Stub agents ───────────────────────────────────────────────────────────────

class _StubB5:
    def __init__(self):
        self.call_count = 0

    def run(self, driver):
        self.call_count += 1
        return ["run-stub-1"]


class _StubB6:
    def __init__(self):
        self.call_count = 0
        self.last_scan_path: str | None = None

    def run(self, driver, scan_path: str):
        self.call_count += 1
        self.last_scan_path = scan_path
        return ["finding-stub-1"]


class _StubB7:
    def __init__(self, report_id: str = "report-stub-abc123"):
        self.call_count = 0
        self._report_id = report_id

    def run(self, driver):
        self.call_count += 1
        return self._report_id


# ══════════════════════════════════════════════════════════════════════════════
# run_build_cycle() tests  (driver=None — stubs never use it)
# ══════════════════════════════════════════════════════════════════════════════

def test_run_build_cycle_importable():
    from src.orchestrator import run_build_cycle
    assert callable(run_build_cycle)


def test_run_build_cycle_returns_report_id():
    from src.orchestrator import run_build_cycle
    b5, b6, b7 = _StubB5(), _StubB6(), _StubB7("report-expected-42")
    result = run_build_cycle(None, b5, b6, b7)
    assert result == "report-expected-42"


def test_run_build_cycle_calls_each_agent_once():
    from src.orchestrator import run_build_cycle
    b5, b6, b7 = _StubB5(), _StubB6(), _StubB7()
    run_build_cycle(None, b5, b6, b7)
    assert b5.call_count == 1, f"b5.run() called {b5.call_count} times, expected 1"
    assert b6.call_count == 1, f"b6.run() called {b6.call_count} times, expected 1"
    assert b7.call_count == 1, f"b7.run() called {b7.call_count} times, expected 1"


def test_run_build_cycle_result_starts_with_report():
    from src.orchestrator import run_build_cycle
    b5, b6, b7 = _StubB5(), _StubB6(), _StubB7("report-xyz")
    result = run_build_cycle(None, b5, b6, b7)
    assert isinstance(result, str) and result.startswith("report-")


def test_run_build_cycle_passes_scan_path_to_b6():
    from src.orchestrator import run_build_cycle
    b5, b6, b7 = _StubB5(), _StubB6(), _StubB7()
    run_build_cycle(None, b5, b6, b7, scan_path="src/account")
    assert b6.last_scan_path == "src/account"


def test_run_build_cycle_default_scan_path_is_src():
    from src.orchestrator import run_build_cycle
    b5, b6, b7 = _StubB5(), _StubB6(), _StubB7()
    run_build_cycle(None, b5, b6, b7)
    assert b6.last_scan_path == "src"
