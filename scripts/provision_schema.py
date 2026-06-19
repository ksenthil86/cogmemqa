#!/usr/bin/env python3
"""
CLI entry point for the Neo4j schema provisioner.

Usage:
  python scripts/provision_schema.py [--schema PATH]

Reads schema/schema.yaml (or --schema override) and applies all UNIQUENESS
constraints and RANGE indexes to the Neo4j instance in .env.
"""
import argparse
import sys
import os

# Allow running from the project root without installing the package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
from src.db import get_driver
from src.provisioner import provision_schema


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Provision CoGMEM-QA Neo4j schema")
    parser.add_argument(
        "--schema",
        default=None,
        help="Path to schema YAML (default: schema/schema.yaml)",
    )
    args = parser.parse_args()

    driver = get_driver()
    try:
        driver.verify_connectivity()
    except Exception as exc:
        print(f"Cannot connect to Neo4j: {exc}", file=sys.stderr)
        sys.exit(1)

    provision_schema(driver, schema_path=args.schema)

    # Report what was applied
    with driver.session() as session:
        constraint_count = len(session.run("SHOW CONSTRAINTS").data())
        index_count = len(session.run("SHOW INDEXES").data())

    print(
        f"Schema provisioned ✓  "
        f"({constraint_count} constraints, {index_count} indexes in Neo4j)"
    )


if __name__ == "__main__":
    main()
