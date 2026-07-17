"""
Chat agent tools — predefined Cypher retrievals + read-only fallback.

Each tool is a plain function (driver, **params) -> ToolResult.  ToolResult
carries a JSON-safe `data` payload (returned to the LLM) and an optional
`graph` dict in the /api/graph shape (streamed to the NVL canvas).

Tool names/descriptions are adapted from schema/cogmem_ontology.yaml
`agent_tools`.  The graph schema itself is embedded in the agent's system
prompt (src/chat_agent.py), so no schema tool is needed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from google.genai import types
from neo4j import Driver

from src import memory_api
from src.graph_serialization import extract_graph_from_records, _sanitize


@dataclass
class ToolResult:
    data: Any
    graph: dict | None = None


# ── Read-only Cypher guard ────────────────────────────────────────────────────

class CypherWriteError(ValueError):
    """Raised when a query contains write/procedure clauses."""


_FORBIDDEN = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|FOREACH|CALL|LOAD)\b"
    r"|apoc\.|dbms\.",
    re.IGNORECASE,
)

_COMMENT_LINE = re.compile(r"//[^\n]*")
_COMMENT_BLOCK = re.compile(r"/\*.*?\*/", re.DOTALL)
_STRING_LITERAL = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"")


def assert_read_only(query: str) -> None:
    """
    Raise CypherWriteError unless *query* looks strictly read-only.

    Comments and string literals are stripped before scanning so keywords
    can't be smuggled inside them (and legit string contents can't cause
    false rejections).  CALL is rejected entirely (blocks apoc/dbms procs);
    this also blocks CALL {} subqueries — acceptable for the chat use case.

    NOTE: Neo4j READ routing is advisory on a single community instance,
    so this blocklist is the primary write guard, not defense-in-depth.
    """
    stripped = _COMMENT_BLOCK.sub(" ", query)
    stripped = _COMMENT_LINE.sub(" ", stripped)
    stripped = _STRING_LITERAL.sub("''", stripped)
    match = _FORBIDDEN.search(stripped)
    if match:
        raise CypherWriteError(
            f"Query rejected: {match.group(0)!r} is not allowed. "
            "Only read-only Cypher (MATCH/RETURN/WHERE/WITH/UNWIND/ORDER BY) is permitted."
        )


# ── Tool implementations ──────────────────────────────────────────────────────

def get_health(driver: Driver) -> ToolResult:
    cov = memory_api.coverage_summary(driver)
    sec = memory_api.security_summary(driver)
    with driver.session() as s:
        report_count = s.run("MATCH (r:Report) RETURN count(r) AS n").single()["n"]
    return ToolResult(data={
        "coverage_pct":        cov["coverage_pct"],
        "covered_ac":          cov["covered_ac"],
        "total_ac":            cov["total_ac"],
        "open_findings_count": sec["total_open"],
        "by_severity":         sec["by_severity"],
        "report_count":        report_count,
    })


def list_requirements(driver: Driver, search: str | None = None) -> ToolResult:
    with driver.session() as s:
        total = s.run("MATCH (r:Requirement) RETURN count(r) AS n").single()["n"]
        cypher = "MATCH (r:Requirement) "
        params: dict[str, Any] = {}
        if search:
            cypher += (
                "WHERE toLower(r.title) CONTAINS toLower($search) "
                "OR toLower(r.id) CONTAINS toLower($search) "
            )
            params["search"] = search
        # Curated Meridian ids (req-account-opening) are human-named; bulk-seeded
        # ids are hex (req-00055b1d). Sort non-hex ids first (false < true).
        cypher += "RETURN r ORDER BY r.id =~ 'req-[0-9a-f]{8}', r.id LIMIT 25"
        records = list(s.run(cypher, **params))
    graph = extract_graph_from_records(records)
    rows = [
        {k: n["properties"].get(k) for k in ("id", "title", "priority", "reg_control")}
        for n in graph["nodes"]
    ]
    return ToolResult(
        data={"total_requirements": total, "showing": len(rows), "requirements": rows},
        graph=graph,
    )


def get_audit_chain(driver: Driver, requirement_id: str) -> ToolResult:
    data = memory_api.audit_trail(driver, requirement_id)
    with driver.session() as s:
        records = list(s.run(
            "MATCH p = (r:Requirement {id: $req_id})"
            "-[:REALIZED_BY]->(:Functionality)"
            "-[:COMPOSED_OF]->(:Component)"
            "-[:IMPLEMENTED_BY]->(f:File) "
            "OPTIONAL MATCH p2 = (:Commit)-[:MODIFIES]->(f) "
            "RETURN p, p2 LIMIT 25",
            req_id=requirement_id,
        ))
    graph = extract_graph_from_records(records)
    if not data and not graph["nodes"]:
        return ToolResult(data={
            "error": f"No requirement found with id {requirement_id!r}. "
                     "Use list_requirements to see valid ids."
        })
    return ToolResult(data=data, graph=graph)


def get_open_security_findings(driver: Driver, severity: str | None = None) -> ToolResult:
    cypher = (
        "MATCH p = (sf:SecurityFinding {status: 'open'})-[:AFFECTS]->(:Component)"
        "<-[:COMPOSED_OF]-(:Functionality)<-[:REALIZED_BY]-(r:Requirement) "
    )
    params: dict[str, Any] = {}
    if severity:
        cypher += "WHERE toUpper(sf.severity) = toUpper($severity) "
        params["severity"] = severity
    cypher += (
        "RETURN p, r.title AS requirement_title, r.priority AS requirement_priority, "
        "sf.id AS finding_id, sf.severity AS severity, sf.title AS finding_title "
        "LIMIT 50"
    )
    with driver.session() as s:
        records = list(s.run(cypher, **params))
    graph = extract_graph_from_records(records)
    data = [
        {
            "finding_id":           rec["finding_id"],
            "severity":             rec["severity"],
            "finding_title":        rec["finding_title"],
            "requirement_title":    rec["requirement_title"],
            "requirement_priority": rec["requirement_priority"],
        }
        for rec in records
    ]
    return ToolResult(data=data, graph=graph)


def execute_cypher(driver: Driver, query: str) -> ToolResult:
    try:
        assert_read_only(query)
    except CypherWriteError as exc:
        return ToolResult(data={"error": str(exc)})

    with driver.session() as s:
        records = list(s.run(query))[:100]

    graph = extract_graph_from_records(records)

    def _render(value: Any) -> Any:
        from neo4j.graph import Node, Relationship, Path
        if isinstance(value, Node):
            return {"labels": list(value.labels), "properties": _sanitize(dict(value))}
        if isinstance(value, Relationship):
            return {"type": value.type, "properties": _sanitize(dict(value))}
        if isinstance(value, Path):
            return {"path_length": len(value.relationships)}
        if isinstance(value, (list, tuple)):
            return [_render(v) for v in value]
        return _sanitize(value)

    data = [{k: _render(v) for k, v in rec.items()} for rec in records]
    return ToolResult(data=data, graph=graph if graph["nodes"] else None)


# ── Gemini function declarations + registry ───────────────────────────────────

@dataclass
class ToolSpec:
    fn: Callable[..., ToolResult]
    declaration: types.FunctionDeclaration


CHAT_TOOLS: dict[str, ToolSpec] = {
    "get_health": ToolSpec(
        fn=get_health,
        declaration=types.FunctionDeclaration(
            name="get_health",
            description=(
                "Retrieve the current QA health snapshot: test coverage percentage, "
                "covered/total acceptance criteria, open security finding counts by "
                "severity, and health report count."
            ),
            parameters=types.Schema(type=types.Type.OBJECT, properties={}),
        ),
    ),
    "list_requirements": ToolSpec(
        fn=list_requirements,
        declaration=types.FunctionDeclaration(
            name="list_requirements",
            description=(
                "List business Requirements (up to 25) with their ids, titles, "
                "priorities, and regulatory controls, plus the total count. "
                "Call this first when you need a requirement id for other tools. "
                "Pass `search` to filter by title or id substring."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "search": types.Schema(
                        type=types.Type.STRING,
                        description="Optional case-insensitive substring to match against title or id",
                    ),
                },
            ),
        ),
    ),
    "get_audit_chain": ToolSpec(
        fn=get_audit_chain,
        declaration=types.FunctionDeclaration(
            name="get_audit_chain",
            description=(
                "Retrieve the full provenance chain for a requirement: "
                "Requirement → Functionality → Component → File ← Commit, plus the "
                "tests and judgments attached to it."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "requirement_id": types.Schema(
                        type=types.Type.STRING,
                        description="Logical requirement id, e.g. 'req-account-opening'",
                    ),
                },
                required=["requirement_id"],
            ),
        ),
    ),
    "get_open_security_findings": ToolSpec(
        fn=get_open_security_findings,
        declaration=types.FunctionDeclaration(
            name="get_open_security_findings",
            description=(
                "List open security findings and the requirements they affect "
                "(via Component → Functionality → Requirement). Optionally filter "
                "by severity."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "severity": types.Schema(
                        type=types.Type.STRING,
                        description="Optional severity filter: LOW, MEDIUM, HIGH or CRITICAL",
                    ),
                },
            ),
        ),
    ),
    "execute_cypher": ToolSpec(
        fn=execute_cypher,
        declaration=types.FunctionDeclaration(
            name="execute_cypher",
            description=(
                "Execute a read-only Cypher query against the knowledge graph. "
                "Use only when no predefined tool answers the question. "
                "Write clauses (CREATE/MERGE/DELETE/SET/...) and CALL are rejected. "
                "Return nodes/relationships where possible so they can be visualised."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "query": types.Schema(
                        type=types.Type.STRING,
                        description="A read-only Cypher query (MATCH ... RETURN ...)",
                    ),
                },
                required=["query"],
            ),
        ),
    ),
}


def run_tool(driver: Driver, name: str, args: dict) -> ToolResult:
    """Execute a registered tool by name; unknown names return an error payload."""
    spec = CHAT_TOOLS.get(name)
    if spec is None:
        return ToolResult(data={"error": f"Unknown tool: {name!r}"})
    try:
        return spec.fn(driver, **args)
    except TypeError as exc:
        return ToolResult(data={"error": f"Bad arguments for {name}: {exc}"})
    except Exception as exc:  # tool errors go back to the model, never crash the loop
        return ToolResult(data={"error": f"{type(exc).__name__}: {exc}"})
