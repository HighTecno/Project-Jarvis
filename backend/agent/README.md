# Agent Module Guide

This folder contains the model interaction loop, parser, and schema validation.

## Components

- core.py: orchestrates the think-call-tool loop
- llm.py: sends chat messages to Ollama or Google and returns model output
- parser.py: extracts tool calls from model output
- schema.py: validates tool call shape and required fields

## Agent Loop Summary

core.run_agent executes a bounded loop:

1. Build message stack with system prompt + history + latest user message.
2. Ask model for the next response.
3. Try to parse a tool call.
4. If tool call is valid, execute via tools registry and feed tool result back.
5. If plain text response, return as final answer.
6. Stop on max steps or max tool calls.

Key limits are controlled by config:

- MAX_STEPS
- MAX_TOOL_CALLS
- LLM_TIMEOUT_SECONDS (per LLM call timeout)

## Parser Hardening

parser.extract_tool_call handles:

- direct JSON object tool calls
- fenced code blocks with or without explicit json language tag
- trailing commas in JSON objects and arrays
- extra text after a valid JSON object by extracting the first complete object

The parser then validates with schema.validate_tool_call.

## Streaming Events

When run_agent is called with on_event callback, it emits:

- thinking
- tool_call
- tool_result
- final
- error

These events are forwarded by main.py through the /stream endpoint as server-sent events.

## History Interaction

main.py handles persistent chat history. The agent receives history as a list of:

- role: user or assistant
- content: string

Invalid history entries are filtered before use.
