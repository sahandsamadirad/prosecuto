"""Smoke tests: the app boots and /api/health reports dependency checks."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_reports_status_and_checks():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in ("ok", "degraded")
    assert "checks" in body
    # NIM config is surfaced (not a live call).
    assert "nim" in body["checks"]
    assert body["checks"]["nim"]["llm_model"] == "nvidia/llama-3.3-nemotron-super-49b-v1"


def test_config_singleton_loads():
    from app.config import settings

    assert settings.nim_llm_model == "nvidia/llama-3.3-nemotron-super-49b-v1"
    assert settings.max_rag_retries == 2
    assert settings.tavily_max_sources == 5
