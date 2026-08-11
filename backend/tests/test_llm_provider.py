from backend.agent import llm


class _PassThroughBreaker:
    @staticmethod
    def call(func):
        return func()


def test_call_llm_routes_to_google_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "google")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_MODEL", "gemma-4-26b-it")
    monkeypatch.setattr(llm, "LLM_TIMEOUT_ENABLED", False)
    monkeypatch.setattr(llm, "llm_circuit_breaker", _PassThroughBreaker())

    captured = {}

    def fake_chat_once(provider, selected_model, messages, stream, timeout_seconds):
        captured["provider"] = provider
        captured["model"] = selected_model
        captured["messages"] = messages
        captured["stream"] = stream
        captured["timeout_seconds"] = timeout_seconds
        return "google-response"

    monkeypatch.setattr(llm, "_chat_once", fake_chat_once)

    result = llm.call_llm([{"role": "user", "content": "hello"}], stream=False)

    assert result == "google-response"
    assert captured["provider"] == "google"
    assert captured["model"] == "gemma-4-26b-it"
    assert captured["stream"] is False


def test_google_payload_uses_system_instruction():
    payload = llm._google_payload(
        [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello"},
        ]
    )

    assert payload["systemInstruction"]["parts"][0]["text"] == "You are helpful."
    assert payload["contents"][0]["role"] == "user"
    assert payload["contents"][1]["role"] == "model"

