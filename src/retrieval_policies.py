"""
Retrieval policies — maps each agent role to the graph layers it may read.

Layers defined in schema/schema.yaml:
  requirements | capability | implementation | evidence | reasoning
"""

# Maps agent_role → list of layers the role is permitted to retrieve.
# These drive the label-filter in memory_api.retrieve().
RETRIEVAL_POLICIES: dict[str, list[str]] = {
    # Sees everything — used for health reports and audit queries
    "supervisor": [
        "requirements", "capability", "implementation", "evidence", "reasoning",
    ],
    # Runs and triages functional tests; does not need raw requirements
    "functional_tester": [
        "capability", "implementation", "evidence",
    ],
    # Proposes test cases from acceptance criteria; needs requirement context
    "test_case_generator": [
        "requirements", "capability", "evidence",
    ],
    # Runs security scans; maps findings to components and requirements
    "security_tester": [
        "capability", "implementation", "reasoning",
    ],
    # Parses PRD into the requirements + capability skeleton
    "requirements_parser": [
        "requirements", "capability",
    ],
}
