# Backend Agent

Jarvis backend is a FastAPI service that runs a local tool-using coding and homelab assistant.

## What This Backend Does

- Serves the chat UI from /static/
- Exposes API endpoints for query and streaming responses
- Runs an agent loop with tool calling
- Integrates with Ollama or Google for model inference
- Persists recent conversation exchanges to disk
- Supports coding + homelab operations through a unified tool registry

## Quick Start

1. Install dependencies:

    pip install -r requirements.txt

2. Optional environment variables:

    - LLM_PROVIDER: default ollama (ollama or google)
    - OLLAMA_HOST: default localhost
    - OLLAMA_PORT: default 11434
    - OLLAMA_MODEL: default qwen2.5-coder:7b
    - GOOGLE_API_KEY: required when LLM_PROVIDER=google
    - GOOGLE_MODEL: default gemma-4-26b-it
    - GOOGLE_API_ENDPOINT: default https://generativelanguage.googleapis.com/v1beta
    - MAX_STEPS: default 8
    - MAX_TOOL_CALLS: default 6
    - LLM_TIMEOUT_SECONDS: default 120
    - TERMINAL_TIMEOUT_SECONDS: default 10
    - MAX_TOOL_OUTPUT_CHARS: default 12000
    - WORKSPACE_PATH: root path for workspace command safety
    - SAFE_FILESYSTEM_ROOT: default /workspace for write operations
    - HOST: default 0.0.0.0
    - PORT: default 8000
    - USE_SSL: default false
    - SSL_CERTFILE: TLS certificate path
    - SSL_KEYFILE: TLS key path
    - ENABLE_STT: default false
    - SKILLS_ENABLED: default true
    - SKILLS_FILE: default ~/.jarvis/skills.json
    - JARVIS_BASE_URL: default http://127.0.0.1:8000 (TUI mode)
    - JARVIS_API_KEY: optional API key for TUI mode
    - DEFAULT_THREAD_ID: default legacy-default
    - MEMORY_SUMMARIZE_EVERY_EXCHANGES: default 10
    - MEMORY_SUMMARY_WINDOW_EXCHANGES: default 10
    - MEMORY_MAX_CONTEXT_MESSAGES: default 100

3. Run backend:

    python run.py

   Or launch terminal UI mode:

    python run.py --tui --url http://127.0.0.1:8000

4. Open UI:

    http://localhost:8000/static/

## Tailscale HTTPS Setup (Optional)

1. Install and connect Tailscale:

    curl -fsSL https://tailscale.com/install.sh | sh
    sudo tailscale up

2. Find cert paths under /var/lib/tailscale/certs/

3. Start backend with TLS:

    export USE_SSL=true
    export SSL_CERTFILE=/var/lib/tailscale/certs/your-hostname.crt
    export SSL_KEYFILE=/var/lib/tailscale/certs/your-hostname.key
    python run.py

4. Access via your Tailscale IP over HTTPS.

## Runtime System Prompt Behavior

The runtime prompt is built in `system_prompt.py` and is intentionally strict:

- Execution-first behavior (discover -> implement -> validate)
- Strong tool-first policy and JSON-only tool call format
- Explicit quality bar for coding changes and debugging
- Safety guardrails for destructive actions, shell use, and secret handling
- Homelab-specific operational rules (service discovery, targeted restarts)

Runtime environment context is appended at execution time:

- /workspace is writable/executable
- /hostroot mirrors host filesystem read-only
- Host file reads should be prefixed with /hostroot
- Writes are restricted to /workspace

## API Endpoints

- GET / : health-style root message
- GET /static/ : serves chat UI
- POST /query : synchronous full response
- POST /stream : server-sent event stream with thought/tool/final events
- POST /stt : speech-to-text endpoint when ENABLE_STT=true
- GET /threads : list known chat threads
- GET /threads/{thread_id}/history : fetch persisted history for a thread
- GET /memory : list stored memory items
- POST /memory/{memory_id}/pin : pin/unpin memory item
- DELETE /memory/{memory_id} : delete memory item
- POST /memory/prune : prune oldest unpinned memory items

## Conversation + Memory Persistence

Jarvis now uses a thread-aware SQLite model for cross-chat memory reuse:

- DB path: `MEMORY_DB_PATH` (default `~/.jarvis/memory.db`)
- Core tables:
  - `chat_threads`: thread metadata
  - `chat_messages`: per-thread role/content history
  - `memory_items`: summarized long-term memory with scope + embeddings
  - `knowledge_chunks`: document chunks for semantic knowledge search
- `/query` and `/stream` accept optional `thread_id`:
  - if omitted, requests are routed to `DEFAULT_THREAD_ID` (`legacy-default`)
  - backward compatibility is preserved for existing clients
- `include_global_memory` (default true) controls whether cross-chat global memory is injected.

Legacy JSON history is still maintained at `~/.jarvis/history.json` for compatibility and is backfilled into the default thread on startup.

## Tooling Overview

Tool registration is in tools/registry.py and currently includes:

- terminal.run
- filesystem.read
- filesystem.write
- filesystem.list
- filesystem.search
- filesystem.info
- homelab.docker_logs
- homelab.docker_status
- homelab.docker_restart
- homelab.docker_list
- homelab.caddy_reload
- homelab.systemd_status
- homelab.systemd_logs
- skills.list
- skills.get
- skills.add
- skills.delete

## Skills System

Jarvis supports configurable "skills" (reusable task playbooks), similar to Claude Code skills.

- Skills are stored in JSON at `SKILLS_FILE` (default: `~/.jarvis/skills.json`)
- The system prompt includes currently configured skills automatically
- The assistant can manage skills through tools:
  - `skills.list`
  - `skills.get`
  - `skills.add`
  - `skills.delete`

Example tool calls:

- `{"tool":"skills.add","args":{"name":"python.debug","description":"Debug Python failures","instructions":"Reproduce, isolate stack trace, patch minimal root cause, verify tests","tags":["python","debug"]}}`
- `{"tool":"skills.get","args":{"name":"python.debug"}}`

## TUI (Terminal Client) Highlights

The `python run.py --tui` client supports:

- Split chat/tools layout with wrapping and focus control
- Streaming telemetry (status, elapsed time, tool counts, errors)
- Slash commands for workflow acceleration:
  - `/help`, `/status`, `/toggletools`, `/focus <chat|tools>`
  - `/history <count>`, `/new`, `/retry`, `/stop`
  - `/savechat <file>`, `/loadchat <file>`, `/export <file.md>`, `/search <text>`

## Homelab Tool Details

All homelab tools are implemented in tools/homelab.py and call terminal.run internally.

- docker_logs(service_name, lines=50)
   - Executes docker compose logs --tail={lines} in /root/{service_name}
- docker_status(service_name)
   - Executes docker compose ps in /root/{service_name}
- docker_restart(service_name)
   - Executes docker compose restart in /root/{service_name}
- docker_list()
   - Executes docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
- caddy_reload(service_name)
   - Executes docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile in /root/{service_name}
- systemd_status(unit)
   - Executes systemctl status {unit}
- systemd_logs(unit, lines=50)
   - Executes journalctl -u {unit} -n {lines} --no-pager

## Terminal Safety Model

terminal.run supports:

- Dangerous pattern blocking (rm -rf, mkfs, reboot, etc.)
- Execution timeout and output truncation
- Optional cwd override for approved roots
- Allowed roots:
   - WORKSPACE_PATH
   - SERVICE_ROOT (for homelab service stacks)
- cd target validation to prevent escaping allowed roots

## Parser Hardening

agent/parser.py supports extracting tool JSON from:

- Plain JSON objects
- Generic fenced blocks
- json fenced blocks

It also:

- Strips trailing commas before JSON decode
- Extracts only the first complete JSON object if extra text follows
- Validates shape via schema.validate_tool_call

## Project Layout

backend/
   main.py              FastAPI app + prompt + history persistence
   run.py               entry point
   config.py            env configuration defaults
   agent/
      core.py            agent loop
      llm.py             LLM provider wrapper (Ollama/Google)
      parser.py          resilient tool-call parser
      schema.py          tool-call schema validation
   tools/
      terminal.py        shell execution with safety + cwd policy
      filesystem.py      read/write/list/search/info tools
      homelab.py         docker/tailscale/systemd/caddy tools
      registry.py        tool name to callable mapping
      README.md          tool development guide
   static/
      index.html         web UI
