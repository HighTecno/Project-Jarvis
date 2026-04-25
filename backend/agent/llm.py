import os
import asyncio
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from urllib.parse import quote

try:
    from backend.config import (
        GOOGLE_API_ENDPOINT,
        GOOGLE_API_KEY,
        GOOGLE_MODEL,
        LLM_PROVIDER,
        LLM_TIMEOUT_ENABLED,
        LLM_TIMEOUT_SECONDS,
        OLLAMA_ENDPOINT,
        OLLAMA_MODEL,
    )
    from backend.retry import retry_with_backoff
    from backend.circuit_breaker import llm_circuit_breaker
except ImportError:
    try:
        from config import (
            GOOGLE_API_ENDPOINT,
            GOOGLE_API_KEY,
            GOOGLE_MODEL,
            LLM_PROVIDER,
            LLM_TIMEOUT_ENABLED,
            LLM_TIMEOUT_SECONDS,
            OLLAMA_ENDPOINT,
            OLLAMA_MODEL,
        )
        from retry import retry_with_backoff
        from circuit_breaker import llm_circuit_breaker
    except ImportError:
        from ..config import (
            GOOGLE_API_ENDPOINT,
            GOOGLE_API_KEY,
            GOOGLE_MODEL,
            LLM_PROVIDER,
            LLM_TIMEOUT_ENABLED,
            LLM_TIMEOUT_SECONDS,
            OLLAMA_ENDPOINT,
            OLLAMA_MODEL,
        )
        from ..retry import retry_with_backoff
        from ..circuit_breaker import llm_circuit_breaker


def _ollama_client(timeout_seconds=None):
    try:
        import ollama
    except ImportError as exc:
        raise RuntimeError("ollama package is not installed") from exc

    endpoint = os.getenv("OLLAMA_ENDPOINT", OLLAMA_ENDPOINT)
    if timeout_seconds is not None:
        try:
            return ollama.Client(host=endpoint, timeout=timeout_seconds)
        except TypeError:
            pass
    return ollama.Client(host=endpoint)


def _resolve_provider():
    provider = os.getenv("LLM_PROVIDER", LLM_PROVIDER).strip().lower()
    if provider not in {"ollama", "google"}:
        raise ValueError(f"Unsupported LLM_PROVIDER '{provider}'. Use 'ollama' or 'google'.")
    return provider


def _google_payload(messages):
    system_parts = []
    contents = []
    for msg in messages:
        role = msg.get("role", "user")
        text = str(msg.get("content", ""))
        if role == "system":
            if text:
                system_parts.append({"text": text})
            continue
        google_role = "model" if role == "assistant" else "user"
        contents.append({"role": google_role, "parts": [{"text": text}]})

    if not contents:
        contents = [{"role": "user", "parts": [{"text": ""}]}]

    payload = {"contents": contents}
    if system_parts:
        payload["systemInstruction"] = {"parts": system_parts}
    return payload


def _google_response_text(data):
    candidates = data.get("candidates") or []
    if not candidates:
        raise RuntimeError("Google API returned no candidates")
    content = candidates[0].get("content", {})
    parts = content.get("parts") or []
    text_chunks = [part.get("text", "") for part in parts if isinstance(part, dict) and part.get("text")]
    if not text_chunks:
        raise RuntimeError("Google API candidate contained no text output")
    return "".join(text_chunks)


def _chat_once_google(selected_model, messages, timeout_seconds):
    try:
        import requests
    except ImportError as exc:
        raise RuntimeError("requests package is not installed") from exc

    api_key = os.getenv("GOOGLE_API_KEY", GOOGLE_API_KEY)
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is required when LLM_PROVIDER=google")

    endpoint = os.getenv("GOOGLE_API_ENDPOINT", GOOGLE_API_ENDPOINT).rstrip("/")
    url = f"{endpoint}/models/{quote(selected_model, safe='')}:generateContent?key={api_key}"
    payload = _google_payload(messages)

    try:
        response = requests.post(url, json=payload, timeout=timeout_seconds)
    except requests.Timeout as exc:
        raise TimeoutError("Google API request timed out") from exc
    except requests.RequestException as exc:
        raise ConnectionError(f"Google API request failed: {exc}") from exc

    if response.status_code >= 400:
        details = response.text.strip()
        raise RuntimeError(f"Google API error {response.status_code}: {details}")

    return _google_response_text(response.json())


@retry_with_backoff(max_retries=3, base_delay=1.0, retriable_exceptions=(ConnectionError, TimeoutError, OSError))
def _chat_once(provider, selected_model, messages, stream, timeout_seconds):
    """Chat with retry logic for transient failures."""
    if provider == "google":
        if stream:
            raise RuntimeError("Streaming is not supported for LLM_PROVIDER=google")
        return _chat_once_google(selected_model, messages, timeout_seconds)
    return _ollama_client(timeout_seconds=timeout_seconds).chat(
        model=selected_model,
        messages=messages,
        stream=stream,
    )


def call_llm(messages, stream=False, model=None, timeout_seconds=None):
    """Synchronous LLM call with circuit breaker and retry logic."""
    provider = _resolve_provider()
    selected_model = model or (
        os.getenv("GOOGLE_MODEL", GOOGLE_MODEL) if provider == "google" else os.getenv("OLLAMA_MODEL", OLLAMA_MODEL)
    )
    timeout_enabled = LLM_TIMEOUT_ENABLED

    def _call_with_timeout():
        if timeout_enabled:
            if timeout_seconds is None:
                actual_timeout = LLM_TIMEOUT_SECONDS
            else:
                actual_timeout = timeout_seconds
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_chat_once, provider, selected_model, messages, stream, actual_timeout)
                try:
                    response = future.result(timeout=actual_timeout)
                except FutureTimeoutError as exc:
                    raise TimeoutError(f"LLM call timed out after {actual_timeout} seconds") from exc
        else:
            response = _chat_once(provider, selected_model, messages, stream, timeout_seconds=None)
        return response

    # Use circuit breaker
    response = llm_circuit_breaker.call(_call_with_timeout)

    if provider == "google":
        return response

    if stream:
        full_response = ""
        for chunk in response:
            content = chunk.get("message", {}).get("content", "")
            if content:
                full_response += content
        return full_response

    return response.get("message", {}).get("content", "")


async def call_llm_async(messages, stream=False, model=None, timeout_seconds=None):
    """Async LLM call using asyncio.to_thread."""
    provider = _resolve_provider()
    selected_model = model or (
        os.getenv("GOOGLE_MODEL", GOOGLE_MODEL) if provider == "google" else os.getenv("OLLAMA_MODEL", OLLAMA_MODEL)
    )
    timeout_enabled = LLM_TIMEOUT_ENABLED

    if timeout_enabled:
        if timeout_seconds is None:
            timeout_seconds = LLM_TIMEOUT_SECONDS
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(_chat_once, provider, selected_model, messages, stream, timeout_seconds),
                timeout=timeout_seconds
            )
        except asyncio.TimeoutError as exc:
            raise TimeoutError(f"LLM call timed out after {timeout_seconds} seconds") from exc
    else:
        response = await asyncio.to_thread(_chat_once, provider, selected_model, messages, stream, timeout_seconds=None)

    if provider == "google":
        return response

    if stream:
        full_response = ""
        for chunk in response:
            content = chunk.get("message", {}).get("content", "")
            if content:
                full_response += content
        return full_response

    return response.get("message", {}).get("content", "")
