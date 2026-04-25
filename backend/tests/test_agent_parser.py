"""Tests for agent tool-call parser strictness."""
from backend.agent.parser import extract_tool_call


def test_extract_tool_call_accepts_raw_json_object():
    tool_call, parse_error = extract_tool_call('{"tool":"web.fetch","args":{"url":"https://example.com"}}')
    assert parse_error is None
    assert tool_call["tool"] == "web.fetch"


def test_extract_tool_call_rejects_narrative_with_fenced_json():
    response = (
        "I'll fetch the recipe now.\n\n"
        "```json\n"
        '{"tool":"web.fetch","args":{"url":"https://example.com"}}\n'
        "```"
    )
    tool_call, parse_error = extract_tool_call(response)
    assert parse_error is None
    assert tool_call["tool"] == "web.fetch"


def test_extract_tool_call_rejects_trailing_text_after_json():
    tool_call, parse_error = extract_tool_call(
        '{"tool":"web.fetch","args":{"url":"https://example.com"}} extra'
    )
    assert tool_call is None
    assert "Invalid tool call format" in parse_error


def test_extract_tool_call_accepts_tool_fence_with_tool_colon_args():
    response = (
        "```tool\n"
        'tool: "mealie.search",\n'
        'args: {"query": "Schokoladenkekse", "language": "de"}\n'
        "```"
    )
    tool_call, parse_error = extract_tool_call(response)
    assert parse_error is None
    assert tool_call["tool"] == "mealie.search"
    assert tool_call["args"]["query"] == "Schokoladenkekse"
