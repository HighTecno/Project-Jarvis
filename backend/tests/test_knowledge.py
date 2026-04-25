"""Tests for knowledge embedding endpoint compatibility and failure behavior."""
import pytest

from backend import knowledge


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _FakeRequests:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def post(self, url, json, timeout):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        return self._responses.pop(0)


def test_knowledge_get_embedding_uses_modern_embed_endpoint(monkeypatch):
    monkeypatch.setattr(knowledge, "_embedding_api_unavailable", False)
    monkeypatch.setattr(knowledge, "OLLAMA_MODEL", knowledge.EMBED_MODEL)
    fake_requests = _FakeRequests([
        _FakeResponse(200, {"embeddings": [[0.1, 0.2, 0.3]]}),
    ])
    monkeypatch.setattr(knowledge, "_requests", fake_requests)

    result = knowledge._get_embedding("hello")

    assert result is not None
    assert result.tolist() == pytest.approx([0.1, 0.2, 0.3])
    assert len(fake_requests.calls) == 1
    assert fake_requests.calls[0]["url"].endswith("/api/embed")
    assert fake_requests.calls[0]["json"]["input"] == "hello"


def test_knowledge_get_embedding_falls_back_to_legacy_endpoint_on_404(monkeypatch):
    monkeypatch.setattr(knowledge, "_embedding_api_unavailable", False)
    monkeypatch.setattr(knowledge, "OLLAMA_MODEL", knowledge.EMBED_MODEL)
    fake_requests = _FakeRequests([
        _FakeResponse(404, {"error": "not found"}),
        _FakeResponse(200, {"embedding": [0.4, 0.5]}),
    ])
    monkeypatch.setattr(knowledge, "_requests", fake_requests)

    result = knowledge._get_embedding("world")

    assert result is not None
    assert result.tolist() == pytest.approx([0.4, 0.5])
    assert len(fake_requests.calls) == 2
    assert fake_requests.calls[0]["url"].endswith("/api/embed")
    assert fake_requests.calls[1]["url"].endswith("/api/embeddings")


def test_knowledge_get_embedding_disables_on_persistent_404(monkeypatch):
    monkeypatch.setattr(knowledge, "_embedding_api_unavailable", False)
    monkeypatch.setattr(knowledge, "OLLAMA_MODEL", knowledge.EMBED_MODEL)
    fake_requests = _FakeRequests([
        _FakeResponse(404, {"error": "not found"}),
        _FakeResponse(404, {"error": "not found"}),
    ])
    monkeypatch.setattr(knowledge, "_requests", fake_requests)

    first = knowledge._get_embedding("first")
    second = knowledge._get_embedding("second")

    assert first is None
    assert second is None
    assert knowledge._embedding_api_unavailable is True
    assert len(fake_requests.calls) == 2


def test_knowledge_get_embedding_falls_back_to_primary_llm_model_when_embed_model_missing(monkeypatch):
    monkeypatch.setattr(knowledge, "_embedding_api_unavailable", False)
    monkeypatch.setattr(knowledge, "EMBED_MODEL", "nomic-embed-text")
    monkeypatch.setattr(knowledge, "OLLAMA_MODEL", "qwen2.5-coder:7b")
    fake_requests = _FakeRequests([
        _FakeResponse(404, {"error": 'model "nomic-embed-text" not found, try pulling it first'}),
        _FakeResponse(200, {"embeddings": [[0.9, 0.8]]}),
    ])
    monkeypatch.setattr(knowledge, "_requests", fake_requests)

    result = knowledge._get_embedding("fallback")

    assert result is not None
    assert result.tolist() == pytest.approx([0.9, 0.8])
    assert len(fake_requests.calls) == 2
    assert fake_requests.calls[0]["url"].endswith("/api/embed")
    assert fake_requests.calls[0]["json"]["model"] == "nomic-embed-text"
    assert fake_requests.calls[1]["url"].endswith("/api/embed")
    assert fake_requests.calls[1]["json"]["model"] == "qwen2.5-coder:7b"


def test_knowledge_get_embedding_disables_on_unsupported_embed_endpoints(monkeypatch):
    monkeypatch.setattr(knowledge, "_embedding_api_unavailable", False)
    monkeypatch.setattr(knowledge, "EMBED_MODEL", "nomic-embed-text")
    monkeypatch.setattr(knowledge, "OLLAMA_MODEL", "qwen2.5-coder:7b")
    fake_requests = _FakeRequests([
        _FakeResponse(404, {"error": 'model "nomic-embed-text" not found, try pulling it first'}),
        _FakeResponse(501, {"error": "not implemented"}),
        _FakeResponse(501, {"error": "not implemented"}),
    ])
    monkeypatch.setattr(knowledge, "_requests", fake_requests)

    first = knowledge._get_embedding("first")
    second = knowledge._get_embedding("second")

    assert first is None
    assert second is None
    assert knowledge._embedding_api_unavailable is True
    assert len(fake_requests.calls) == 3
