TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "tool": {"type": "string"},
        "args": {"type": "object"}
    },
    "required": ["tool"]
}


def validate_tool_call(data):
    if not isinstance(data, dict):
        return "Tool call must be a JSON object."

    expected_keys = {"tool", "args"}
    data_keys = set(data.keys())
    if not data_keys.issubset(expected_keys):
        return "Tool call must contain only 'tool' and optional 'args'."

    if "tool" not in data:
        return "Tool call must contain 'tool' key."
    if "args" not in data:
        data["args"] = {}

    tool = data.get("tool")
    if not isinstance(tool, str) or not tool.strip():
        return "Field 'tool' must be a non-empty string."

    if not isinstance(data.get("args"), dict):
        return "Field 'args' must be a JSON object."

    return None