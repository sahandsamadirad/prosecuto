"""Phase 0 smoke tests: the app boots and /api/health responds."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_config_singleton_loads():
    from app.config import settings

    # Defaults from ARCHITECTURE.md section 15 are present even with no .env.
    assert settings.nim_llm_model == "nvidia/llama-3.3-nemotron-super-49b-v1"
    assert settings.max_rag_retries == 2
    assert settings.tavily_max_sources == 5
