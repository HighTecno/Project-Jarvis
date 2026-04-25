"""Tests for system prompt generation."""
from backend import system_prompt


def test_system_prompt_includes_skills_and_tools(monkeypatch):
    monkeypatch.setattr(
        system_prompt,
        "skills_prompt_section",
        lambda: "SKILLS:\n- test.skill: A reusable workflow",
    )
    monkeypatch.setattr(system_prompt, "list_tool_names", lambda: ["filesystem.read", "skills.add"])

    prompt = system_prompt.build_system_prompt()

    assert "SKILLS:" in prompt
    assert "test.skill" in prompt
    assert '{"tool": "filesystem.read", "args": {...}}' in prompt
    assert '{"tool": "skills.add", "args": {...}}' in prompt
    assert "OPERATING MODES" in prompt
    assert "CODE QUALITY BAR" in prompt
    assert "STRICT TOOL OUTPUT PROTOCOL" in prompt
