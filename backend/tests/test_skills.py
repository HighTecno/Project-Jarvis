"""Tests for persistent skills storage and retrieval."""
import pytest
from backend import skills


def test_upsert_and_get_skill(tmp_path, monkeypatch):
    store_path = tmp_path / "skills.json"
    monkeypatch.setattr(skills, "SKILLS_FILE", str(store_path))
    monkeypatch.setattr(skills, "SKILLS_ENABLED", True)

    saved = skills.upsert_skill(
        name="python.debug",
        description="Debug Python runtime issues",
        instructions="Reproduce, isolate, patch, and verify.",
        tags=["python", "debug"],
    )
    assert saved["name"] == "python.debug"

    loaded = skills.get_skill("python.debug")
    assert loaded is not None
    assert loaded["description"] == "Debug Python runtime issues"
    assert "python" in loaded["tags"]


def test_list_and_delete_skill(tmp_path, monkeypatch):
    store_path = tmp_path / "skills.json"
    monkeypatch.setattr(skills, "SKILLS_FILE", str(store_path))
    monkeypatch.setattr(skills, "SKILLS_ENABLED", True)

    skills.upsert_skill(
        name="ops.logs",
        description="Analyze service logs first",
        instructions="Open logs, identify first failure, then trace dependencies.",
        tags=["ops"],
    )

    items = skills.list_skills()
    assert any(item["name"] == "ops.logs" for item in items)

    assert skills.delete_skill("ops.logs") is True
    assert skills.get_skill("ops.logs") is None


def test_invalid_skill_definition_rejected(tmp_path, monkeypatch):
    store_path = tmp_path / "skills.json"
    monkeypatch.setattr(skills, "SKILLS_FILE", str(store_path))
    monkeypatch.setattr(skills, "SKILLS_ENABLED", True)

    with pytest.raises(ValueError):
        skills.upsert_skill(
            name="Bad Name",
            description="invalid",
            instructions="This is sufficiently long but name is invalid",
            tags=[],
        )
