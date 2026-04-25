"""Tests for memory embedding endpoint compatibility."""
from pathlib import Path

from backend import memory


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


def test_get_embedding_uses_modern_embed_endpoint(monkeypatch):
    monkeypatch.setattr(memory, "OLLAMA_MODEL", memory.EMBED_MODEL)
    fake_requests = _FakeRequests([
        _FakeResponse(200, {"embeddings": [[0.1, 0.2, 0.3]]}),
    ])
    monkeypatch.setattr(memory, "_requests", fake_requests)

    result = memory.get_embedding("hello")

    assert result == [0.1, 0.2, 0.3]
    assert len(fake_requests.calls) == 1
    assert fake_requests.calls[0]["url"].endswith("/api/embed")
    assert fake_requests.calls[0]["json"]["input"] == "hello"


def test_get_embedding_falls_back_to_legacy_endpoint_on_404(monkeypatch):
    monkeypatch.setattr(memory, "OLLAMA_MODEL", memory.EMBED_MODEL)
    fake_requests = _FakeRequests([
        _FakeResponse(404, {"error": "not found"}),
        _FakeResponse(200, {"embedding": [0.4, 0.5]}),
    ])
    monkeypatch.setattr(memory, "_requests", fake_requests)

    result = memory.get_embedding("world")

    assert result == [0.4, 0.5]
    assert len(fake_requests.calls) == 2
    assert fake_requests.calls[0]["url"].endswith("/api/embed")
    assert fake_requests.calls[1]["url"].endswith("/api/embeddings")


def test_get_embedding_falls_back_to_primary_llm_model_when_embed_model_missing(monkeypatch):
    monkeypatch.setattr(memory, "EMBED_MODEL", "nomic-embed-text")
    monkeypatch.setattr(memory, "OLLAMA_MODEL", "qwen2.5-coder:7b")
    fake_requests = _FakeRequests([
        _FakeResponse(404, {"error": 'model "nomic-embed-text" not found, try pulling it first'}),
        _FakeResponse(200, {"embeddings": [[0.9, 0.8]]}),
    ])
    monkeypatch.setattr(memory, "_requests", fake_requests)

    result = memory.get_embedding("fallback")

    assert result == [0.9, 0.8]
    assert len(fake_requests.calls) == 2
    assert fake_requests.calls[0]["url"].endswith("/api/embed")
    assert fake_requests.calls[0]["json"]["model"] == "nomic-embed-text"
    assert fake_requests.calls[1]["url"].endswith("/api/embed")
    assert fake_requests.calls[1]["json"]["model"] == "qwen2.5-coder:7b"


def test_get_embedding_returns_none_when_embed_endpoints_unsupported(monkeypatch):
    monkeypatch.setattr(memory, "EMBED_MODEL", "nomic-embed-text")
    monkeypatch.setattr(memory, "OLLAMA_MODEL", "qwen2.5-coder:7b")
    fake_requests = _FakeRequests([
        _FakeResponse(404, {"error": 'model "nomic-embed-text" not found, try pulling it first'}),
        _FakeResponse(501, {"error": "not implemented"}),
        _FakeResponse(501, {"error": "not implemented"}),
    ])
    monkeypatch.setattr(memory, "_requests", fake_requests)

    result = memory.get_embedding("unsupported")

    assert result is None
    assert len(fake_requests.calls) == 3
    assert fake_requests.calls[0]["url"].endswith("/api/embed")
    assert fake_requests.calls[1]["url"].endswith("/api/embed")
    assert fake_requests.calls[2]["url"].endswith("/api/embeddings")


def test_thread_history_round_trip(tmp_path, monkeypatch):
    db_path = str(Path(tmp_path) / "memory.db")
    monkeypatch.setattr(memory, "MEMORY_ENABLED", True)
    monkeypatch.setattr(memory, "MEMORY_DB_PATH", db_path)
    monkeypatch.setattr(memory, "DEFAULT_THREAD_ID", "legacy-default")
    memory.init_memory_schema()

    ok = memory.append_thread_exchange("thread-a", "hello", "world")
    assert ok is True

    history = memory.get_thread_history("thread-a", limit_messages=10)
    assert history == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "world"},
    ]


def test_retrieve_memories_scopes_global_and_thread(tmp_path, monkeypatch):
    db_path = str(Path(tmp_path) / "memory.db")
    monkeypatch.setattr(memory, "MEMORY_ENABLED", True)
    monkeypatch.setattr(memory, "MEMORY_DB_PATH", db_path)
    monkeypatch.setattr(memory, "DEFAULT_THREAD_ID", "legacy-default")
    monkeypatch.setattr(memory, "MEMORY_TOP_K", 5)
    monkeypatch.setattr(memory, "get_embedding", lambda _: [1.0, 0.0, 0.0])
    memory.init_memory_schema()

    assert memory.store_memory(
        summary="global summary",
        content="global content",
        thread_id="thread-a",
        scope="global",
    )
    assert memory.store_memory(
        summary="thread summary",
        content="thread content",
        thread_id="thread-a",
        scope="thread",
    )

    with_global = memory.retrieve_memories("query", top_k=5, thread_id="thread-a", include_global=True)
    thread_only = memory.retrieve_memories("query", top_k=5, thread_id="thread-a", include_global=False)

    assert any("global summary" in item for item in with_global)
    assert any("thread summary" in item for item in with_global)
    assert any("thread summary" in item for item in thread_only)
    assert all("global summary" not in item for item in thread_only)


def test_memory_list_pin_delete_and_prune(tmp_path, monkeypatch):
    db_path = str(Path(tmp_path) / "memory.db")
    monkeypatch.setattr(memory, "MEMORY_ENABLED", True)
    monkeypatch.setattr(memory, "MEMORY_DB_PATH", db_path)
    monkeypatch.setattr(memory, "DEFAULT_THREAD_ID", "legacy-default")
    monkeypatch.setattr(memory, "get_embedding", lambda _: [1.0, 0.0, 0.0])
    memory.init_memory_schema()

    assert memory.store_memory("m1", "c1", thread_id="thread-a", scope="global")
    assert memory.store_memory("m2", "c2", thread_id="thread-a", scope="global")

    items = memory.list_memory_items(limit=10)
    assert len(items) >= 2
    target_id = items[0]["id"]

    assert memory.set_memory_pinned(target_id, True) is True
    refreshed = memory.list_memory_items(limit=10)
    target = next(item for item in refreshed if item["id"] == target_id)
    assert target["pinned"] is True

    deleted = memory.prune_unpinned_memories(max_items=0)
    assert deleted >= 1

    assert memory.delete_memory_item(target_id) is True
