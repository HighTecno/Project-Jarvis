"""Tool wrappers for skill management."""
try:
    from backend.skills import list_skills, get_skill, upsert_skill, delete_skill
except ImportError:
    try:
        from skills import list_skills, get_skill, upsert_skill, delete_skill
    except ImportError:
        from ..skills import list_skills, get_skill, upsert_skill, delete_skill


def _success(output):
    return {"status": "success", "output": output}


def _error(message):
    return {"status": "error", "error": message}


def list():
    try:
        return _success({"skills": list_skills()})
    except Exception as exc:
        return _error(str(exc))


def get(name: str):
    try:
        skill = get_skill(name)
        if skill is None:
            return _error(f"Skill not found: {name}")
        return _success(skill)
    except Exception as exc:
        return _error(str(exc))


def add(name: str, description: str, instructions: str, tags=None):
    try:
        skill = upsert_skill(name=name, description=description, instructions=instructions, tags=tags or [])
        return _success({"saved": True, "skill": skill})
    except Exception as exc:
        return _error(str(exc))


def delete(name: str):
    try:
        deleted = delete_skill(name)
        if not deleted:
            return _error(f"Skill not found: {name}")
        return _success({"deleted": True, "name": name})
    except Exception as exc:
        return _error(str(exc))
