from dataclasses import dataclass, field
from typing import Callable, Dict, Tuple

try:
    from backend.env.context import ENV
except ImportError:
    try:
        from env.context import ENV
    except ImportError:
        from ..env.context import ENV

from . import filesystem, homelab, terminal, network, debug, git, config, web, mealie, n8n, telegram, knowledge, skills, pentest


@dataclass(frozen=True)
class Tool:
    name: str
    handler: Callable
    requires: Dict[str, object] = field(default_factory=dict)

TOOLS = {
    "terminal.run": Tool(name="terminal.run", handler=terminal.run),
    "filesystem.read": Tool(name="filesystem.read", handler=filesystem.read),
    "filesystem.write": Tool(name="filesystem.write", handler=filesystem.write),
    "filesystem.list": Tool(name="filesystem.list", handler=filesystem.list_dir),
    "filesystem.search": Tool(name="filesystem.search", handler=filesystem.search),
    "filesystem.info": Tool(name="filesystem.info", handler=filesystem.info),
    "homelab.docker_logs": Tool(
        name="homelab.docker_logs",
        handler=homelab.docker_logs,
        requires={"has_docker_socket": True},
    ),
    "homelab.docker_status": Tool(
        name="homelab.docker_status",
        handler=homelab.docker_status,
        requires={"has_docker_socket": True},
    ),
    "homelab.docker_restart": Tool(
        name="homelab.docker_restart",
        handler=homelab.docker_restart,
        requires={"has_docker_socket": True},
    ),
    "homelab.docker_list": Tool(
        name="homelab.docker_list",
        handler=homelab.docker_list,
        requires={"has_docker_socket": True},
    ),
    "homelab.caddy_reload": Tool(
        name="homelab.caddy_reload",
        handler=homelab.caddy_reload,
        requires={"has_docker_socket": True},
    ),
    "homelab.systemd_status": Tool(
        name="homelab.systemd_status",
        handler=homelab.systemd_status,
        requires={"has_systemd": True},
    ),
    "homelab.systemd_logs": Tool(
        name="homelab.systemd_logs",
        handler=homelab.systemd_logs,
        requires={"has_journalctl": True},
    ),
    "network.ping": Tool(name="network.ping", handler=network.ping),
    "network.port_check": Tool(name="network.port_check", handler=network.port_check),
    "network.dns_lookup": Tool(name="network.dns_lookup", handler=network.dns_lookup),
    "system.info": Tool(name="system.info", handler=network.system_info),
    "system.disk_usage": Tool(name="system.disk_usage", handler=network.disk_usage),
    "system.process_list": Tool(name="system.process_list", handler=network.process_list),
    # Debug tools
    "debug.analyze_logs": Tool(
        name="debug.analyze_logs",
        handler=debug.analyze_logs,
        requires={"has_docker_socket": True},
    ),
    "debug.validate_compose": Tool(name="debug.validate_compose", handler=debug.validate_compose),
    "debug.summarize_error": Tool(name="debug.summarize_error", handler=debug.summarize_error),
    # Git tools
    "git.status": Tool(name="git.status", handler=git.status),
    "git.commit": Tool(name="git.commit", handler=git.commit),
    "git.push": Tool(name="git.push", handler=git.push),
    "git.pull": Tool(name="git.pull", handler=git.pull),
    "git.branch_list": Tool(name="git.branch_list", handler=git.branch_list),
    "git.create_branch": Tool(name="git.create_branch", handler=git.create_branch),
    # Configuration tools
    "config.set": Tool(name="config.set", handler=config.set_config),
    "config.get": Tool(name="config.get", handler=config.get_config),
    "config.list": Tool(name="config.list", handler=config.list_configs),
    "config.delete": Tool(name="config.delete", handler=config.delete_config),
    # Web scraping tools
    "web.fetch": Tool(name="web.fetch", handler=web.fetch_url),
    "web.extract_recipe": Tool(name="web.extract_recipe", handler=web.extract_recipe),
    "web.extract_text": Tool(name="web.extract_text", handler=web.extract_text),
    # Mealie recipe tools
    "mealie.search": Tool(name="mealie.search", handler=mealie.search_recipe_online),
    "mealie.add_from_url": Tool(name="mealie.add_from_url", handler=mealie.add_recipe_from_url),
    "mealie.list": Tool(name="mealie.list", handler=mealie.list_recipes),
    "mealie.translate": Tool(name="mealie.translate", handler=mealie.translate_recipe),
    # n8n workflow tools
    "n8n.draft_workflow": Tool(name="n8n.draft_workflow", handler=n8n.draft_workflow),
    "n8n.validate_workflow": Tool(name="n8n.validate_workflow", handler=n8n.validate_workflow),
    "n8n.trigger_workflow": Tool(name="n8n.trigger_workflow", handler=n8n.trigger_workflow),
    # Telegram bot tools
    "telegram.send": Tool(name="telegram.send", handler=telegram.send_message),
    "telegram.alert": Tool(name="telegram.alert", handler=telegram.send_alert),
    "telegram.forward_logs": Tool(name="telegram.forward_logs", handler=telegram.forward_logs),
    "telegram.get_updates": Tool(name="telegram.get_updates", handler=telegram.get_updates),
    "knowledge.search": Tool(name="knowledge.search", handler=knowledge.search),
    "knowledge.ingest_file": Tool(name="knowledge.ingest_file", handler=knowledge.ingest_file),
    "knowledge.init": Tool(name="knowledge.init", handler=knowledge.init),
    "skills.list": Tool(name="skills.list", handler=skills.list),
    "skills.get": Tool(name="skills.get", handler=skills.get),
    "skills.add": Tool(name="skills.add", handler=skills.add),
    "skills.delete": Tool(name="skills.delete", handler=skills.delete),
    # Pentest tools (require Kali container + Docker socket)
    "pentest.shell_exec": Tool(
        name="pentest.shell_exec",
        handler=pentest.shell_exec,
        requires={"has_docker_socket": True},
    ),
    "pentest.shell_exec_confirmed": Tool(
        name="pentest.shell_exec_confirmed",
        handler=pentest.shell_exec_confirmed,
        requires={"has_docker_socket": True},
    ),
    "pentest.search_cve": Tool(name="pentest.search_cve", handler=pentest.search_cve),
    "pentest.save_finding": Tool(name="pentest.save_finding", handler=pentest.save_finding),
    "pentest.summarize_session": Tool(name="pentest.summarize_session", handler=pentest.summarize_session),
    "pentest.list_findings": Tool(name="pentest.list_findings", handler=pentest.list_findings),
}


def _success(output):
    return {"status": "success", "output": output}


def _error(message):
    return {"status": "error", "error": message}


def _blocked(reason):
    return {"status": "blocked", "reason": reason}


def _get_env_value(env, dotted_key):
    current = env
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def is_tool_allowed(tool: Tool, env: dict) -> Tuple[bool, str]:
    requires = tool.requires or {}
    for dotted_key, expected_value in requires.items():
        actual_value = _get_env_value(env, dotted_key)
        if actual_value != expected_value:
            reason = f"{dotted_key}={actual_value} does not satisfy required {expected_value}"
            if dotted_key == "has_systemd":
                reason = "systemd not available in container"
            elif dotted_key == "has_journalctl":
                reason = "journalctl not available in this environment"
            elif dotted_key == "has_docker_socket":
                reason = "docker socket not available"
            return False, reason
    return True, ""

def execute_tool(name, args):
    if name not in TOOLS:
        return _error(f"Invalid tool: {name}")
    tool = TOOLS[name]

    allowed, reason = is_tool_allowed(tool, ENV)
    if not allowed:
        return _blocked(reason)

    if args is None:
        args = {}
    if not isinstance(args, dict):
        return _error("Tool args must be a JSON object")
    try:
        result = tool.handler(**args)
    except Exception as exc:
        return _error(str(exc))

    if isinstance(result, dict) and result.get("status") in {"success", "error", "blocked"}:
        return result
    return _success(result)


def list_tool_names():
    return sorted(TOOLS.keys())
