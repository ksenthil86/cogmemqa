"""
Runtime loader for the CoGMEM-QA domain ontology (schema/cogmem-qa.yaml).

The YAML follows the create-context-graph custom-domain contract and is the
single source of truth for presentation + agent configuration: node colors,
node sizes, demo scenarios, and the agent system prompt. Loading it at
runtime (the scaffold only code-generates from it) keeps those from being
hardcoded in chat_agent.py / GraphCanvas.tsx / scenarios.ts.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

import yaml

_ONTOLOGY_PATH = os.path.join(
    os.path.dirname(__file__), "..", "schema", "cogmem-qa.yaml"
)


@dataclass(frozen=True)
class Ontology:
    node_colors: dict[str, str]
    node_sizes: dict[str, int]
    demo_scenarios: list[dict] = field(default_factory=list)
    system_prompt: str = ""
    entity_labels: list[str] = field(default_factory=list)


@lru_cache(maxsize=1)
def load_ontology() -> Ontology:
    """Parse schema/cogmem-qa.yaml once and expose the runtime-relevant bits."""
    with open(_ONTOLOGY_PATH) as f:
        doc = yaml.safe_load(f)

    viz = doc.get("visualization", {})
    return Ontology(
        node_colors=dict(viz.get("node_colors", {})),
        node_sizes=dict(viz.get("node_sizes", {})),
        demo_scenarios=list(doc.get("demo_scenarios", [])),
        system_prompt=str(doc.get("system_prompt", "")).strip(),
        entity_labels=[e["label"] for e in doc.get("entity_types", [])],
    )
