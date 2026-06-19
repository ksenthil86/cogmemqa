import os
import pytest
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), override=False)
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env.test"), override=True)


@pytest.fixture(scope="session")
def neo4j_driver():
    """Session-scoped Neo4j driver connected to the test instance."""
    from src.db import get_driver

    driver = get_driver()
    driver.verify_connectivity()
    yield driver
    driver.close()
