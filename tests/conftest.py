"""Shared test fixtures. Tests never call real search engines or AI models."""

import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
