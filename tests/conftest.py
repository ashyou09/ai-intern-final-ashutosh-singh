"""Shared test fixtures. Tests never call real search engines or AI models."""

import pytest
from fastapi.testclient import TestClient

import backend.agent as agent
from backend.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def empty_source_cache():
    """Each test starts with an empty source cache."""
    agent.source_cache.clear()
    yield
    agent.source_cache.clear()
