from backend import health


def test_deep_health_check_google_requires_api_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "google")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(health, "check_disk_space", lambda: {"status": "healthy"})
    monkeypatch.setattr(health, "check_session_store", lambda: {"status": "healthy"})
    monkeypatch.setattr(health, "get_metrics_summary", lambda: {"status": "healthy"})

    result = health.deep_health_check()

    assert result["status"] == "unhealthy"
    assert result["checks"]["llm"]["provider"] == "google"
    assert "GOOGLE_API_KEY" in result["checks"]["llm"]["error"]

