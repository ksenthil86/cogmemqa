"""
Intentional Bandit finding for SecurityTesterAgent Phase 3 e2e test.

The filename contains "account" so _map_file_to_component maps this file
to comp-account-opening, producing an AFFECTS edge in the graph.

Bandit B105 finding below is intentional — do not add nosec.
"""

# Intentional B105 — hardcoded credential for Bandit e2e demo
ACCOUNT_PASSWORD = "account-dev-password-2024"
