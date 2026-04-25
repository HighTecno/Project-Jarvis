import json

try:
    from backend.agent.llm import call_llm
    from backend.env.context import environment_constraints_text
    from backend.agent.parser import extract_tool_call
    from backend.agent.schema import validate_tool_call
    from backend.tools.registry import execute_tool
    from backend.config import (
        LLM_TIMEOUT_ENABLED,
        LLM_TIMEOUT_SECONDS,
        MAX_STEPS,
        MAX_TOOL_CALLS,
        MEMORY_TOP_K,
    )
    from backend.logger import get_logger
    from backend.validation import validate_tool_args
    from backend.sanitize import sanitize_tool_output
    from backend.memory import retrieve_memories
except ImportError:
    try:
        from agent.llm import call_llm
        from env.context import environment_constraints_text
        from agent.parser import extract_tool_call
        from agent.schema import validate_tool_call
        from tools.registry import execute_tool
        from config import (
            LLM_TIMEOUT_ENABLED,
            LLM_TIMEOUT_SECONDS,
            MAX_STEPS,
            MAX_TOOL_CALLS,
            MEMORY_TOP_K,
        )
        from logger import get_logger
        from validation import validate_tool_args
        from sanitize import sanitize_tool_output
        from memory import retrieve_memories
    except ImportError:
        from .llm import call_llm
        from ..env.context import environment_constraints_text
        from .parser import extract_tool_call
        from .schema import validate_tool_call
        from ..tools.registry import execute_tool
        from ..config import (
            LLM_TIMEOUT_ENABLED,
            LLM_TIMEOUT_SECONDS,
            MAX_STEPS,
            MAX_TOOL_CALLS,
            MEMORY_TOP_K,
        )
        from ..logger import get_logger
        from ..validation import validate_tool_args
        from ..sanitize import sanitize_tool_output
        from ..memory import retrieve_memories

logger = get_logger("agent.core")


def _format_tool_result(result):
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, ensure_ascii=True)
    except TypeError:
        return str(result)

def _emit_event(on_event, event_type, data):
    if on_event is None:
        return
    try:
        on_event(event_type, data)
    except Exception as exc:
        logger.warning(f"Event callback error: {exc}", extra={"event_type": event_type})


def _normalize_history(history):
    if not isinstance(history, list):
        return []
    normalized = []
    for item in history:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role not in {"user", "assistant"}:
            continue
        if not isinstance(content, str):
            continue
        normalized.append({"role": role, "content": content})
    return normalized


def run_agent(
    user_input,
    system_prompt,
    on_event=None,
    history=None,
    thread_id=None,
    include_global_memory=True,
):
    logger.info("Starting agent run", extra={"user_input_len": len(user_input)})
    
    # Retrieve relevant memories before building context
    try:
        memories = retrieve_memories(
            user_input,
            top_k=MEMORY_TOP_K,
            thread_id=thread_id,
            include_global=include_global_memory,
        )
        if memories:
            memory_section = "\n\nRELEVANT MEMORY:\n" + "\n\n".join(memories)
            logger.info(f"Injected {len(memories)} relevant memories into context")
        else:
            memory_section = ""
    except Exception as e:
        logger.warning(f"Failed to retrieve memories: {e}")
        memory_section = ""

    # Retrieve relevant knowledge chunks
    try:
        try:
            from backend.knowledge import search_knowledge
            from backend.config import KNOWLEDGE_TOP_K
        except ImportError:
            try:
                from knowledge import search_knowledge
                from config import KNOWLEDGE_TOP_K
            except ImportError:
                from ..knowledge import search_knowledge
                from ..config import KNOWLEDGE_TOP_K
        knowledge_chunks = search_knowledge(user_input, top_k=KNOWLEDGE_TOP_K)
        if knowledge_chunks:
            knowledge_section = "\n\nRELEVANT KNOWLEDGE:\n" + "\n\n---\n".join(knowledge_chunks)
            logger.info(f"Injected {len(knowledge_chunks)} knowledge chunks into context")
        else:
            knowledge_section = ""
    except Exception as e:
        logger.warning(f"Failed to retrieve knowledge: {e}")
        knowledge_section = ""
    
    constraints = environment_constraints_text()
    system_content = f"{system_prompt.rstrip()}\n\n{constraints}{memory_section}{knowledge_section}\n"
    messages = [{"role": "system", "content": system_content}]
    messages.extend(_normalize_history(history))
    messages.append({"role": "user", "content": user_input})

    tool_calls = 0
    parse_failures = 0
    repeated_failed_tool_key = None
    repeated_failed_tool_count = 0
    for step in range(MAX_STEPS):
        logger.debug(f"Agent step {step}")
        _emit_event(on_event, "thinking", {"step": step + 1})

        try:
            llm_timeout = LLM_TIMEOUT_SECONDS if LLM_TIMEOUT_ENABLED else None
            response = call_llm(messages, stream=False, timeout_seconds=llm_timeout)
            logger.debug(f"LLM response received", extra={"response_len": len(response), "step": step})
            
            # Log the actual LLM thinking/reasoning
            logger.info(f"💭 LLM Response (Step {step}): {response[:500]}")
            if len(response) > 500:
                logger.debug(f"Full LLM response: {response}")
        except Exception as exc:
            message = f"LLM error: {str(exc)}"
            logger.error(f"LLM error at step {step}", extra={"error": str(exc), "step": step})
            _emit_event(on_event, "error", {"message": message})
            return message

        tool_call, parse_error = extract_tool_call(response)
        if parse_error:
            logger.warning("Tool call parse error", extra={"error": parse_error, "step": step})
            parse_failures += 1
            if parse_failures >= 2:
                message = f"Tool call rejected: {parse_error}"
                _emit_event(on_event, "error", {"message": message})
                return message
            messages.append({"role": "assistant", "content": response})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Format error: if you need a tool, output ONLY one raw JSON object "
                        "like {\"tool\":\"name\",\"args\":{...}} with no markdown fences or extra text. "
                        "If no tool is needed, output only the final plain-text answer."
                    ),
                }
            )
            continue

        if tool_call is not None:
            parse_failures = 0
            if tool_calls >= MAX_TOOL_CALLS:
                message = f"Tool call limit reached ({MAX_TOOL_CALLS})."
                logger.warning("Tool call limit reached", extra={"step": step, "limit": MAX_TOOL_CALLS})
                _emit_event(on_event, "error", {"message": message})
                return message
            tool_calls += 1
            tool_name = tool_call["tool"]
            logger.info("Executing tool", extra={"tool": tool_name, "step": step})
            
            # Validate tool arguments
            try:
                validated_args = validate_tool_args(tool_name, tool_call["args"])
                tool_call["args"] = validated_args
            except ValueError as e:
                error_msg = f"Tool argument validation failed: {str(e)}"
                logger.error("Tool validation error", extra={"tool": tool_name, "error": str(e)})
                _emit_event(on_event, "error", {"message": error_msg})
                messages.append({"role": "assistant", "content": response})
                messages.append({"role": "user", "content": error_msg})
                continue
            
            _emit_event(
                on_event,
                "tool_call",
                {"tool": tool_name, "args": tool_call["args"]},
            )

            try:
                result = execute_tool(tool_name, tool_call["args"])
                # Sanitize tool output to prevent XSS attacks
                result = sanitize_tool_output(result)
                result_preview = _format_tool_result(result)
                _emit_event(
                    on_event,
                    "tool_result",
                    {"tool": tool_name, "output": result_preview},
                )
                if isinstance(result, dict) and result.get("status") in {"error", "blocked"}:
                    logger.warning("Tool execution failed", extra={
                        "tool": tool_name,
                        "status": result.get("status"),
                        "error": result.get("error") or result.get("reason")
                    })
                    tool_key = (
                        tool_name,
                        json.dumps(tool_call["args"], sort_keys=True, ensure_ascii=True),
                    )
                    if repeated_failed_tool_key == tool_key:
                        repeated_failed_tool_count += 1
                    else:
                        repeated_failed_tool_key = tool_key
                        repeated_failed_tool_count = 1
                    if repeated_failed_tool_count >= 2:
                        message = (
                            f"Stopped after repeated failures for {tool_name} with the same arguments. "
                            "Adjust the arguments or choose a different tool."
                        )
                        _emit_event(on_event, "error", {"message": message})
                        return message
                    _emit_event(
                        on_event,
                        "error",
                        {"message": result.get("error") or result.get("reason") or "Tool execution failed"},
                    )
                else:
                    repeated_failed_tool_key = None
                    repeated_failed_tool_count = 0
                if len(result_preview) > 500:
                    result_preview = result_preview[:500] + "...[truncated]"
                logger.debug("Tool result", extra={"tool": tool_name, "preview": result_preview[:100]})
                messages.append({"role": "assistant", "content": response})
                messages.append(
                    {
                        "role": "user",
                        "content": f"Tool result ({tool_call['tool']}):\n{_format_tool_result(result)}",
                    }
                )
            except Exception as e:
                error_msg = f"Tool error: {str(e)}"
                logger.error("Tool execution exception", extra={"tool": tool_name, "error": str(e)})
                _emit_event(on_event, "error", {"message": error_msg})
                messages.append({"role": "assistant", "content": response})
                messages.append(
                    {
                        "role": "user",
                        "content": f"Tool result ({tool_call['tool']}):\n{error_msg}",
                    }
                )
            continue

        else:
            if isinstance(response, str):
                text = response.strip()
                if text.startswith("{"):
                    try:
                        parsed = json.loads(text)
                    except json.JSONDecodeError:
                        parsed = None
                    if parsed is not None and validate_tool_call(parsed) is None:
                        message = "Final answer rejected: looks like a tool call."
                        logger.warning("Response looks like tool call", extra={"step": step})
                        _emit_event(on_event, "error", {"message": message})
                        return message
                # Return any plain text response as the final answer
                logger.info("Agent run completed successfully", extra={"step": step, "tool_calls": tool_calls})
                _emit_event(on_event, "final", {"response": response})
                return response

    message = f"Stopped after {MAX_STEPS} steps without a final response."
    logger.warning("Max steps reached", extra={"max_steps": MAX_STEPS})
    _emit_event(on_event, "error", {"message": message})
    return message
