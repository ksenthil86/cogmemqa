import os
from functools import lru_cache

from dotenv import load_dotenv
from neo4j import GraphDatabase, Driver

load_dotenv()


@lru_cache(maxsize=1)
def get_driver() -> Driver:
    uri = os.environ["NEO4J_URI"]
    user = os.environ["NEO4J_USER"]
    password = os.environ["NEO4J_PASSWORD"]
    return GraphDatabase.driver(uri, auth=(user, password))
