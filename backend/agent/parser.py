import json
import re
from .schema import validate_tool_call


def _strip_trailing_commas(text):
    # Remove trailing commas before object/array close: {"a":1,} or [1,2,]
    return re.sub(r",\s*([}\]])", r"\1", text)


def _parse_tool_colon_args_format(text):
    """Parse tool-call blocks formatted like: tool: "name" args: {...}"""
    match = re.match(
        r'^\s*tool\s*:\s*("([^"]+)"|\'([^\']+)\')\s*,?\s*args\s*:\s*(\{.*\})\s*$',
        text,
        re.DOTALL,
    )
    if not match:
        return None

    tool_name = match.group(2) or match.group(3)
    args_text = _strip_trailing_commas(match.group(4))
    try:
        args = json.loads(args_text)
    except json.JSONDecodeError:
        return None
    if not isinstance(args, dict):
        return None
    return {"tool": tool_name, "args": args}


def _extract_candidate_text(text):
    if text.startswith("{"):
        return text

    # Prefer explicit tool/json fenced blocks even when surrounded by narrative text.
    for match in re.finditer(r"```(?:tool|json)?\s*\n(.*?)\n```", text, re.DOTALL | re.IGNORECASE):
        candidate = match.group(1).strip()
        if candidate.startswith("{") or candidate.lower().startswith("tool"):
            return candidate

    # Fallback for unfenced tool-call style output.
    if text.lower().lstrip().startswith("tool"):
        return text

    return None


def extract_tool_call(response):
    text = (response or "").strip()
    if not text:
        return None, None

    candidate = _extract_candidate_text(text)
    if candidate is None:
        return None, None

    if not candidate.startswith("{"):
        parsed_tool = _parse_tool_colon_args_format(candidate)
        if parsed_tool is None:
            return None, "Invalid tool call format."
        validation_error = validate_tool_call(parsed_tool)
        if validation_error:
            return None, validation_error
        return parsed_tool, None

    try:
        normalized = _strip_trailing_commas(candidate)
        decoder = json.JSONDecoder()
        data, end_idx = decoder.raw_decode(normalized)
    except json.JSONDecodeError:
        return None, "Invalid JSON tool call."
    if normalized[end_idx:].strip():
        return None, "Invalid tool call format."

    if isinstance(data, dict):
        data.setdefault("args", {})

    validation_error = validate_tool_call(data)
    if validation_error:
        return None, validation_error

    return data, None
