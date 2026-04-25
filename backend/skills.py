"""Persistent skill management for Jarvis."""
import json
import os
import re
import threading
from typing import Any, Dict, List, Optional

try:
    from backend.config import SKILLS_ENABLED, SKILLS_FILE
except ImportError:
    try:
        from config import SKILLS_ENABLED, SKILLS_FILE
    except ImportError:
        from .config import SKILLS_ENABLED, SKILLS_FILE


_SKILL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")
_file_lock = threading.Lock()


def _default_store() -> Dict[str, Any]:
    return {"skills": []}


def _ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def _normalize_skill(skill: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    name = skill.get("name")
    description = skill.get("description")
    instructions = skill.get("instructions")
    tags = skill.get("tags", [])

    if not isinstance(name, str) or not _SKILL_NAME_RE.match(name.strip().lower()):
        return None
    if not isinstance(description, str) or not description.strip():
        return None
    if not isinstance(instructions, str) or not instructions.strip():
        return None
    if tags is None:
        tags = []
    if not isinstance(tags, list):
        return None

    normalized_tags: List[str] = []
    for tag in tags:
        if isinstance(tag, str) and tag.strip():
            normalized_tags.append(tag.strip())

    return {
        "name": name.strip().lower(),
        "description": description.strip(),
        "instructions": instructions.strip(),
        "tags": normalized_tags[:20],
    }


def _read_store() -> Dict[str, Any]:
    if not SKILLS_ENABLED:
        return _default_store()

    with _file_lock:
        if not os.path.exists(SKILLS_FILE):
            return _default_store()
        try:
            with open(SKILLS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return _default_store()
            raw_skills = data.get("skills", [])
            if not isinstance(raw_skills, list):
                return _default_store()
            normalized = []
            for item in raw_skills:
                if isinstance(item, dict):
                    skill = _normalize_skill(item)
                    if skill is not None:
                        normalized.append(skill)
            return {"skills": normalized}
        except Exception:
            return _default_store()


def _write_store(store: Dict[str, Any]) -> None:
    _ensure_parent_dir(SKILLS_FILE)
    temp_file = f"{SKILLS_FILE}.tmp"
    with _file_lock:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(store, f, ensure_ascii=True, indent=2)
        os.replace(temp_file, SKILLS_FILE)


def list_skills() -> List[Dict[str, Any]]:
    data = _read_store()
    result = []
    for skill in data.get("skills", []):
        result.append(
            {
                "name": skill["name"],
                "description": skill["description"],
                "tags": skill.get("tags", []),
            }
        )
    return result


def get_skill(name: str) -> Optional[Dict[str, Any]]:
    if not isinstance(name, str):
        return None
    lookup = name.strip().lower()
    for skill in _read_store().get("skills", []):
        if skill.get("name") == lookup:
            return dict(skill)
    return None


def upsert_skill(name: str, description: str, instructions: str, tags: Optional[List[str]] = None) -> Dict[str, Any]:
    if not SKILLS_ENABLED:
        raise ValueError("Skills are disabled")

    skill = _normalize_skill(
        {
            "name": name,
            "description": description,
            "instructions": instructions,
            "tags": tags or [],
        }
    )
    if skill is None:
        raise ValueError("Invalid skill definition")

    store = _read_store()
    existing = [s for s in store.get("skills", []) if s.get("name") != skill["name"]]
    existing.append(skill)
    store["skills"] = sorted(existing, key=lambda s: s["name"])
    _write_store(store)
    return {
        "name": skill["name"],
        "description": skill["description"],
        "tags": skill["tags"],
    }


def delete_skill(name: str) -> bool:
    if not SKILLS_ENABLED:
        raise ValueError("Skills are disabled")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("name must be a non-empty string")
    target = name.strip().lower()
    store = _read_store()
    before = len(store.get("skills", []))
    store["skills"] = [s for s in store.get("skills", []) if s.get("name") != target]
    if len(store["skills"]) == before:
        return False
    _write_store(store)
    return True


def skills_prompt_section() -> str:
    available = list_skills()
    lines = [
        "SKILLS:",
        "- Skills are reusable playbooks that guide how to solve a task.",
        "- Use skills.list to discover skills, skills.get to load one, and follow its instructions exactly.",
        "- Use skills.add to create/update a custom skill and skills.delete to remove one.",
        "- Do not invent a skill; always check with skills.list first.",
        "",
        "Configured skills:",
    ]
    if not available:
        lines.append("- (none configured)")
    else:
        for skill in available:
            lines.append(f"- {skill['name']}: {skill['description']}")
    return "\n".join(lines)
