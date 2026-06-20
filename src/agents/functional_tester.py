"""
B5 — Functional Tester Agent.

Reads Test nodes from the shared graph, executes HTTP calls via an injectable
run_fn, ingests TestRun nodes (INSTANCE_OF → Test), and for each failure
classifies it via LLM into one of six categories before writing a Failure node
and Judgment provenance record.
"""
from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Callable, Optional

import httpx
from neo4j import Driver

from src.agent_base import BaseAgent
from src import memory_api
from src.llm import call_llm
from src.models import Failure, Judgment, ReasoningTrace, TestRun, InstanceOfEdge

log = logging.getLogger(__name__)

_VALID_CATEGORIES = frozenset({
    "regression", "environment", "flaky", "spec_gap", "data_error", "blocker",
})

_CLASSIFY_PROMPT = """\
You are a QA triage engineer. A test has failed. Classify the failure into
exactly one category and return ONLY the category word — no explanation.

Valid categories:
  regression   — previously passed, now failing
  environment  — network/infra issue (timeout, connection refused)
  flaky        — intermittent with no deterministic signal
  spec_gap     — acceptance criterion too vague to derive a passing test
  data_error   — bad payload or test fixture data
  blocker      — app not running or hard dependency unavailable

Test acceptance criterion: {ac_statement}
Error signature         : {error_sig}
Recent outcomes (newest first): {recent_outcomes}

Return exactly one category word:"""

# ── Endpoint map ───────────────────────────────────────────────────────────────

_FUNC_TO_ENDPOINT: dict[str, tuple[str, str]] = {
    "func-account-opening":     ("POST", "/accounts"),
    "func-kyc":                 ("POST", "/kyc/verify"),
    "func-money-transfer":      ("POST", "/transfers"),
    "func-transaction-history": ("GET",  "/transactions"),
    "func-fraud-alerting":      ("GET",  "/fraud/alerts"),
}

# ── Default run_fn (real httpx caller) ────────────────────────────────────────

def _default_run_fn(spec: dict) -> dict:
    """Execute an HTTP request described by *spec* and return a result dict."""
    try:
        method = spec["method"].upper()
        url = spec["url"]
        payload = spec.get("payload") or {}
        with httpx.Client(timeout=10) as client:
            if method == "GET":
                resp = client.get(url, params=payload)
            else:
                resp = client.request(method, url, json=payload)
        return {"status_code": resp.status_code, "body": resp.json(), "error": None}
    except Exception as exc:
        return {"status_code": 0, "body": {}, "error": str(exc)}


# ── Agent ──────────────────────────────────────────────────────────────────────

class FunctionalTesterAgent(BaseAgent):
    """
    B5 — Functional Tester.

    Accepts an injectable run_fn so the test suite can pass deterministic
    stubs without needing a live server.
    """

    def __init__(
        self,
        role: str = "functional_tester",
        driver: Optional[Driver] = None,
        llm_fn: Callable[[str], str] = call_llm,
        run_fn: Callable[[dict], dict] = _default_run_fn,
    ) -> None:
        super().__init__(role=role, driver=driver, llm_fn=llm_fn)
        self.run_fn = run_fn

    def _derive_http_spec(self, subgraph: dict, base_url: str) -> dict:
        """
        Convert the retrieve() subgraph centred on a Test node into a run_fn
        input dict by following the VERIFIES edge to a Functionality node and
        looking up its endpoint in _FUNC_TO_ENDPOINT.

        Raises KeyError if the Functionality id is not in the endpoint map.
        Raises ValueError if no VERIFIES edge is found in the subgraph.
        """
        # Find the VERIFIES edge to get the functionality id
        func_id: Optional[str] = None
        for edge in subgraph.get("edges", []):
            if edge.get("type") == "VERIFIES":
                func_id = edge["to_id"]
                break

        if func_id is None:
            raise ValueError(
                "No VERIFIES edge found in subgraph — cannot derive HTTP spec"
            )

        # Raises KeyError for unknown func_id (intentional — caller should handle)
        method, path = _FUNC_TO_ENDPOINT[func_id]
        url = base_url.rstrip("/") + path
        return {"method": method, "url": url, "payload": {}}

    def _execute_http_test(
        self, driver: Driver, test_id: str
    ) -> tuple[str, bool, dict]:
        """
        Internal: execute HTTP test, ingest TestRun, return (test_run_id, passed, raw_result).

        Shared by run_http_test() (public API) and run() (orchestrator) so that
        run() can access the raw result for error signature extraction without
        a second HTTP call.
        """
        base_url = os.environ.get("MERIDIAN_APP_URL", "http://localhost:8000")
        subgraph = self.retrieve(test_id)
        spec = self._derive_http_spec(subgraph, base_url)
        result = self.run_fn(spec)

        status_code = result.get("status_code", 0)
        error = result.get("error")
        passed = status_code < 400 and error is None
        outcome = "pass" if passed else "fail"

        now = datetime.now(timezone.utc)
        timestamp_ms = int(now.timestamp() * 1000)
        test_run_id = f"{test_id}-run-{timestamp_ms}"

        memory_api.ingest_node(driver, TestRun(id=test_run_id, outcome=outcome, timestamp=now))
        memory_api.ingest_edge(driver, InstanceOfEdge(from_id=test_run_id, to_id=test_id, valid_from=now))

        return test_run_id, passed, result

    def run_http_test(self, driver: Driver, test_id: str) -> tuple[str, bool]:
        """
        Execute the HTTP test identified by *test_id*.

        Returns (test_run_id, passed) where passed is True iff status_code < 400
        and no transport error occurred.
        """
        test_run_id, passed, _ = self._execute_http_test(driver, test_id)
        return test_run_id, passed

    def classify_failure(self, driver: Driver, test_id: str, error_sig: str) -> str:
        """
        Ask the LLM to classify a test failure into one of six categories.

        Looks up the AC statement via a direct graph query (COVERS_CRITERION) and
        retrieves the last 3 TestRun outcomes for historical context.

        Writes Judgment(label="FAILURE_CLASSIFIED") + ReasoningTrace via
        write_provenance, informed_by test_id.

        Returns the category string; falls back to "blocker" for unrecognised LLM output.
        """
        # Fetch AC statement for the test
        with driver.session() as s:
            ac_row = s.run(
                "MATCH (t:Test {id: $tid})-[:COVERS_CRITERION]->(ac:AcceptanceCriterion) "
                "RETURN ac.statement AS statement LIMIT 1",
                tid=test_id,
            ).single()
        ac_statement = ac_row["statement"] if ac_row else "(no AC statement found)"

        # Fetch last 3 TestRun outcomes
        with driver.session() as s:
            outcome_rows = s.run(
                "MATCH (tr:TestRun)-[:INSTANCE_OF]->(t:Test {id: $tid}) "
                "RETURN tr.outcome AS outcome ORDER BY tr.timestamp DESC LIMIT 3",
                tid=test_id,
            ).data()
        recent_outcomes = ", ".join(r["outcome"] for r in outcome_rows) or "none"

        prompt = _CLASSIFY_PROMPT.format(
            ac_statement=ac_statement,
            error_sig=error_sig,
            recent_outcomes=recent_outcomes,
        )

        raw = self.llm_fn(prompt).strip().lower()
        category = raw if raw in _VALID_CATEGORIES else "blocker"
        if raw not in _VALID_CATEGORIES:
            log.warning("classify_failure: unrecognised LLM category %r — falling back to 'blocker'", raw)

        now = datetime.now(timezone.utc)
        sig_hash = hashlib.sha256(f"{test_id}:{error_sig}".encode()).hexdigest()[:10]
        judgment = Judgment(
            id=f"judgment-failure-classified-{sig_hash}",
            agent_role=self.role,
            label="FAILURE_CLASSIFIED",
        )
        trace = ReasoningTrace(
            id=f"trace-failure-classified-{sig_hash}",
            agent_role=self.role,
            decision=category,
            timestamp=now,
        )
        self.write_provenance(judgment, [trace], [test_id])

        return category

    def record_failure(
        self, driver: Driver, test_id: str, error_sig: str, category: str
    ) -> str:
        """
        Ingest a Failure node linked to *test_id*.

        The id is deterministic (`{test_id}-failure`) so repeat calls are
        idempotent — MERGE on the node means a second call with the same args
        is a no-op in Neo4j.

        Returns the Failure node id.
        """
        failure_id = f"{test_id}-failure"
        memory_api.ingest_node(
            driver,
            Failure(
                id=failure_id,
                error_signature=error_sig,
                label=category,
                confidence=0.9,
            ),
        )
        return failure_id

    def run(
        self,
        driver: Driver,
        test_ids: Optional[list[str]] = None,
    ) -> list[str]:
        """
        Full B5 pipeline: discover or accept test_ids → execute → triage failures.

        If test_ids is None, queries the graph for all Test nodes with type="api"
        that have no INSTANCE_OF ← TestRun edge yet (avoids re-running tests).

        Returns the list of TestRun node ids created in this run.
        """
        if test_ids is None:
            with driver.session() as s:
                rows = s.run(
                    "MATCH (t:Test {type: 'api'}) "
                    "WHERE NOT (:TestRun)-[:INSTANCE_OF]->(t) "
                    "RETURN t.id AS id"
                ).data()
            test_ids = [r["id"] for r in rows]

        test_run_ids: list[str] = []
        pass_count = 0
        fail_count = 0

        for test_id in test_ids:
            try:
                test_run_id, passed, raw_result = self._execute_http_test(driver, test_id)
            except (KeyError, ValueError) as exc:
                log.warning("run: skipping test %r — %s", test_id, exc)
                continue
            test_run_ids.append(test_run_id)
            if passed:
                pass_count += 1
            else:
                fail_count += 1
                status_code = raw_result.get("status_code", 0)
                transport_err = raw_result.get("error") or ""
                error_sig = transport_err if transport_err else f"HTTP {status_code}"
                category = self.classify_failure(driver, test_id, error_sig)
                self.record_failure(driver, test_id, error_sig, category)

        n = len(test_ids)
        now = datetime.now(timezone.utc)
        run_hash = hashlib.sha256(",".join(test_ids).encode()).hexdigest()[:10]
        judgment = Judgment(
            id=f"judgment-functional-run-complete-{run_hash}",
            agent_role=self.role,
            label="FUNCTIONAL_RUN_COMPLETE",
        )
        trace = ReasoningTrace(
            id=f"trace-functional-run-complete-{run_hash}",
            agent_role=self.role,
            decision=f"Ran {n} tests: {pass_count} passed, {fail_count} failed",
            timestamp=now,
        )
        self.write_provenance(judgment, [trace], test_ids)

        return test_run_ids
