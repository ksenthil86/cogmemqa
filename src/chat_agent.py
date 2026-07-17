"""
Chat agent — Gemini function-calling loop over the CoGMEM-QA graph.

run_chat_agent() drives a bounded tool-use loop: each iteration sends the
conversation to Gemini with the CHAT_TOOLS declarations; returned function
calls are executed against Neo4j and fed back as function responses until
the model produces a final text answer.

The Gemini call is injectable (generate_fn) following the project's llm_fn
pattern, so tests run without an API key.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Awaitable, Callable

from google.genai import types
from neo4j import Driver

from src.chat_tools import CHAT_TOOLS, run_tool
from src.graph_serialization import _merge_graph

_MODEL = "gemini-flash-latest"
_MAX_ITERATIONS = 10
_OUTPUT_PREVIEW_CHARS = 600

_SYSTEM_PROMPT = """\
You are the CoGMEM-QA assistant: an auditable QA agent operating on a \
memory-grounded knowledge graph for the Meridian Bank software delivery \
pipeline. You answer questions about requirements, test coverage, security \
findings, commits, and agent decisions by querying a shared Neo4j graph.

You MUST use the available tools to query the knowledge graph before \
answering any question about its contents. Prefer the predefined tools; use \
execute_cypher only when no predefined tool fits. Never attempt to modify \
the graph — you only have read access.

Graph schema (node labels by layer):
- Requirements: Requirement(id, title, priority, reg_control), \
AcceptanceCriterion(id, statement, status), Actor(id, name, role)
- Capability: Functionality(id, name, status), Component(id, name, status)
- Implementation: File(id, path, language, module), Commit(id, sha, message, \
author, timestamp), Contract, Endpoint, UIElement
- Evidence: Test(id, name, type, status), TestRun(id, outcome, duration, \
timestamp), SecurityFinding(id, severity, status, title, tool), \
Report(id, summary, coverage_pct, open_findings_count, created_at), \
Failure, Artifact, Scan
- Reasoning: Judgment(id, agent_role, label, confidence, reasoning), \
ReasoningTrace(id, agent_role, decision, timestamp)

Relationships: (Requirement)-[:REALIZED_BY]->(Functionality), \
(Functionality)-[:COMPOSED_OF]->(Component), \
(Component)-[:IMPLEMENTED_BY]->(File), (Commit)-[:MODIFIES]->(File), \
(Test)-[:VERIFIES]->(Functionality), \
(Test)-[:COVERS_CRITERION]->(AcceptanceCriterion), \
(TestRun)-[:INSTANCE_OF]->(Test), (SecurityFinding)-[:AFFECTS]->(Component), \
(Judgment)-[:INFORMED_BY]->(Requirement|AcceptanceCriterion|Functionality|\
Component|File), (Judgment)-[:HAS_STEP]->(ReasoningTrace), \
(AcceptanceCriterion)-[:JUDGED]->(Judgment)

Answer concisely with concrete ids, titles, and numbers from the graph. \
When the user asks a follow-up, reuse ids already established in the \
conversation instead of re-listing everything.\
"""

GenerateFn = Callable[[list[types.Content], types.GenerateContentConfig], Awaitable[Any]]


def _default_generate_fn() -> GenerateFn:
    from src.llm import get_gemini_client

    client = get_gemini_client()

    async def _generate(contents: list[types.Content], config: types.GenerateContentConfig) -> Any:
        return await client.aio.models.generate_content(
            model=_MODEL, contents=contents, config=config,
        )

    return _generate


def _history_to_contents(history: list[dict]) -> list[types.Content]:
    """Map client-held turns [{role: 'user'|'model', text}] to Content objects."""
    contents: list[types.Content] = []
    for turn in history:
        role = "model" if turn.get("role") == "model" else "user"
        text = turn.get("text") or ""
        if text:
            contents.append(types.Content(role=role, parts=[types.Part.from_text(text=text)]))
    return contents


def _preview(data: Any) -> str:
    text = json.dumps(data, default=str)
    if len(text) > _OUTPUT_PREVIEW_CHARS:
        text = text[:_OUTPUT_PREVIEW_CHARS] + "…"
    return text


async def _execute_function_calls(
    driver: Driver,
    function_calls: list,
    tool_calls: list[dict],
    graph_data: dict,
) -> list[types.Part]:
    """Run each requested tool; record telemetry and merge graphs in place."""
    response_parts: list[types.Part] = []
    for call in function_calls:
        name = call.name or ""
        args = dict(call.args or {})
        started = time.monotonic()
        result = await asyncio.to_thread(run_tool, driver, name, args)
        duration_ms = int((time.monotonic() - started) * 1000)

        record: dict = {
            "name": name,
            "inputs": args,
            "duration_ms": duration_ms,
            "output_preview": _preview(result.data),
        }
        if isinstance(result.data, dict) and "error" in result.data:
            record["error"] = result.data["error"]
        tool_calls.append(record)

        if result.graph and result.graph.get("nodes"):
            _merge_graph(graph_data, result.graph)

        response_parts.append(types.Part.from_function_response(
            name=name, response={"result": result.data},
        ))
    return response_parts


async def run_chat_agent(
    driver: Driver,
    message: str,
    history: list[dict] | None = None,
    generate_fn: GenerateFn | None = None,
    max_iterations: int = _MAX_ITERATIONS,
) -> dict:
    """
    Run the tool loop and return:

        {
            "response": str,
            "tool_calls": [{name, inputs, duration_ms, output_preview, error?}],
            "graph_data": {"nodes": [...], "relationships": [...]},
        }
    """
    if generate_fn is None:
        generate_fn = _default_generate_fn()

    config = types.GenerateContentConfig(
        system_instruction=_SYSTEM_PROMPT,
        tools=[types.Tool(function_declarations=[
            spec.declaration for spec in CHAT_TOOLS.values()
        ])],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )

    contents = _history_to_contents(history or [])
    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=message)]))

    tool_calls: list[dict] = []
    graph_data: dict = {"nodes": [], "relationships": []}

    for _iteration in range(max_iterations):
        response = await generate_fn(contents, config)

        function_calls = response.function_calls
        if not function_calls:
            # Final answer. response.text is None when no text parts exist.
            text = response.text or "I could not produce an answer for that question."
            return {"response": text, "tool_calls": tool_calls, "graph_data": graph_data}

        # Echo the model's function-call content back into the conversation.
        contents.append(response.candidates[0].content)

        response_parts = await _execute_function_calls(
            driver, function_calls, tool_calls, graph_data,
        )
        contents.append(types.Content(role="user", parts=response_parts))

    return {
        "response": (
            "I hit the tool-call limit before finishing. "
            "Here is what I gathered so far — try narrowing the question."
        ),
        "tool_calls": tool_calls,
        "graph_data": graph_data,
    }
