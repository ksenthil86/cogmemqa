"""Tests for src/ontology.py — runtime loader over schema/cogmem-qa.yaml."""
from __future__ import annotations

from app.ontology import load_ontology


def test_loads_and_caches():
    a = load_ontology()
    b = load_ontology()
    assert a is b  # lru_cache


def test_every_entity_label_has_a_color():
    ont = load_ontology()
    assert len(ont.entity_labels) == 15
    missing = [l for l in ont.entity_labels if l not in ont.node_colors]
    assert not missing, f"labels without colors: {missing}"


def test_known_colors():
    ont = load_ontology()
    assert ont.node_colors["Requirement"] == "#2563EB"
    assert ont.node_colors["Project"] == "#F43F5E"


def test_demo_scenarios_shape():
    ont = load_ontology()
    assert len(ont.demo_scenarios) == 3
    for sc in ont.demo_scenarios:
        assert sc["name"]
        assert len(sc["prompts"]) >= 1


def test_system_prompt_nonempty():
    ont = load_ontology()
    assert "CoGMEM-QA" in ont.system_prompt
    assert "read-only" in ont.system_prompt
