"""
Tests for the /health endpoint.

These tests only verify the API's own liveness response and do not require
a running database or Ollama server.
"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_200():
    response = client.get("/health")
    assert response.status_code == 200


def test_health_returns_ok_status():
    response = client.get("/health")
    data = response.json()
    assert data == {"status": "ok"}
