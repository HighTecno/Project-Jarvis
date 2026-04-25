# Tool Development Guide

This folder contains all tool functions callable by the agent.

## Current Tool Set

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

## Files in This Folder

- terminal.py: shell execution with safety checks and output limits
- filesystem.py: read/write/list/search/info helpers
- homelab.py: docker, tailscale, caddy, and systemd helpers
- skills.py: manage reusable skill playbooks
- registry.py: central tool registration map and dispatch

## Return Contract

Tool functions should return one of:

- {"status": "success", "output": ...}
- {"status": "error", "error": "..."}

The registry keeps this pattern consistent for all tools.

## Registration Pattern

Register tool names in registry.py using dot-scoped keys:

- module.action naming style
- key must exactly match the name expected by the system prompt
- value must be a callable compatible with func(**args)

## terminal.run Behavior

terminal.run(command, timeout_seconds=..., cwd=None) supports:

- persistent bash shell reuse
- timeout enforcement
- output truncation to MAX_TOOL_OUTPUT_CHARS
- dangerous command blocking via regex patterns
- cd path validation against allowed roots

Allowed execution roots:

- WORKSPACE_PATH
- SERVICE_ROOT (defaults to /root inside host namespace, e.g. /hostroot/root)

The optional cwd argument is validated and used by homelab tools that must run inside service directories.

## filesystem Tool Behavior

- read(file_path): read file content
- write(file_path, content): write only under SAFE_FILESYSTEM_ROOT
- list_dir(path): list directory entries
- search(pattern, base_path): glob recursive search, max 100 results
- info(file_path): stat-style metadata

Notes:

- read/list/search/info currently validate path format and existence
- write is root-restricted to prevent escaping configured safe root

## homelab Tool Behavior

All homelab functions call terminal.run internally and follow the same status contract.

- docker_logs(service_name, lines=50)
    - docker compose logs --tail={lines}
    - cwd: /root/{service_name}
- docker_status(service_name)
    - docker compose ps
    - cwd: /root/{service_name}
- docker_restart(service_name)
    - docker compose restart
    - cwd: /root/{service_name}
- docker_list()
    - docker ps --format table with names, status, ports
- caddy_reload(service_name)
    - docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile
    - cwd: /root/{service_name}
- systemd_status(unit)
    - systemctl status {unit}
- systemd_logs(unit, lines=50)
    - journalctl -u {unit} -n {lines} --no-pager

Input hardening in homelab.py:

- service_name and unit must be non-empty strings
- lines is coerced to positive integer
- systemd unit names are shell-quoted

## Safe Tool Authoring Checklist

- Validate every argument type and value range
- Keep output JSON-serializable
- Set strict execution boundaries (paths, timeouts, output limits)
- Avoid spawning unrestricted subprocesses in new tools when shared wrappers exist
- Prefer shared helpers for consistent policy enforcement
- Ensure registry key and prompt documentation stay in sync

## Adding a New Tool

1. Implement function in this folder.
2. Use explicit keyword-friendly signature.
3. Validate inputs and enforce safety boundaries.
4. Return status-formatted result.
5. Register in registry.py.
6. Update backend main prompt tool list to keep names in sync.
7. Update docs in this file and backend README.
