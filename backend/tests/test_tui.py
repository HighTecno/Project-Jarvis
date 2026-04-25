"""Tests for TUI helpers."""
from backend import tui
from backend.run import parse_args


def test_iter_sse_events_parses_multiple_events():
    chunks = [
        'data: {"type":"thinking","step":1}\n\n',
        'data: {"type":"final","response":"done"}\n\n',
    ]
    events = list(tui._iter_sse_events(chunks))
    assert events[0]["type"] == "thinking"
    assert events[1]["type"] == "final"
    assert events[1]["response"] == "done"


def test_iter_sse_events_handles_chunked_payload():
    chunks = ['data: {"type":"final"', ',"response":"ok"}\n\n']
    events = list(tui._iter_sse_events(chunks))
    assert len(events) == 1
    assert events[0]["response"] == "ok"


def test_parse_args_tui_mode():
    args = parse_args(["--tui", "--url", "http://localhost:9000", "--api-key", "abc"])
    assert args.tui is True
    assert args.url == "http://localhost:9000"
    assert args.api_key == "abc"


def test_parse_slash_command():
    cmd, arg = tui.parse_slash_command("/apikey   secret-token ")
    assert cmd == "apikey"
    assert arg == "secret-token"


def test_parse_slash_command_non_command():
    cmd, arg = tui.parse_slash_command("hello")
    assert cmd is None
    assert arg == ""


def test_generate_followup_suggestions_defaults_and_limit():
    suggestions = tui.generate_followup_suggestions("Simple response", limit=2)
    assert len(suggestions) == 2
    assert all(isinstance(item, str) and item for item in suggestions)


def test_generate_followup_suggestions_contextual():
    suggestions = tui.generate_followup_suggestions("This API code failed with an error")
    assert any("diagnose" in item.lower() for item in suggestions)


def test_parse_positive_int_accepts_and_rejects_values():
    assert tui._parse_positive_int("42") == 42
    assert tui._parse_positive_int("0") is None
    assert tui._parse_positive_int("-3") is None
    assert tui._parse_positive_int("abc") is None


def test_command_help_lines_include_core_commands():
    lines = tui.JarvisTUI.command_help_lines()
    joined = " ".join(lines)
    assert "/help" in joined
    assert "/savechat" in joined
    assert "/history" in joined
