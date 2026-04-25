import os
import shlex
import json

try:
    from backend.tools import terminal
except ImportError:
    try:
        from tools import terminal
    except ImportError:
        from . import terminal


def _success(output):
    return {"status": "success", "output": output}


def _error(message):
    return {"status": "error", "error": message}


SERVICE_ROOT = os.path.realpath(os.getenv("SERVICE_ROOT", "/hostroot/root"))


def _service_dir(service_name):
    if not isinstance(service_name, str) or not service_name.strip():
        raise ValueError("service_name must be a non-empty string")
    candidate = os.path.realpath(os.path.join(SERVICE_ROOT, service_name.strip()))
    if os.path.commonpath([candidate, SERVICE_ROOT]) != SERVICE_ROOT:
        raise ValueError("service_name resolves outside service root")
    return candidate


def _normalize_lines(lines):
    try:
        value = int(lines)
    except (TypeError, ValueError):
        raise ValueError("lines must be an integer")
    if value <= 0:
        raise ValueError("lines must be greater than 0")
    return value


def _normalize_terminal_result(result):
    if isinstance(result, dict) and result.get("status") in {"success", "error"}:
        return result
    return _success(result)


def _resolve_executable(command_name):
    candidates = [
        command_name,
        f"/usr/bin/{command_name}",
        f"/usr/sbin/{command_name}",
        f"/bin/{command_name}",
        f"/sbin/{command_name}",
        f"/hostroot/usr/bin/{command_name}",
        f"/hostroot/usr/sbin/{command_name}",
        f"/hostroot/bin/{command_name}",
        f"/hostroot/sbin/{command_name}",
    ]
    for path in candidates:
        if path == command_name:
            return path
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return command_name


def _parse_docker_ps_json_lines(output_text):
    containers = []
    for raw_line in (output_text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        containers.append(
            {
                "name": item.get("Names", ""),
                "image": item.get("Image", ""),
                "status": item.get("Status", ""),
                "ports": item.get("Ports", ""),
            }
        )
    return containers


def docker_logs(service_name, lines=50):
    try:
        tail = _normalize_lines(lines)
        directory = _service_dir(service_name)
        if os.path.isdir(directory):
            command = f"docker compose logs --tail={tail}"
            return _normalize_terminal_result(terminal.run(command, cwd=directory))
        container = shlex.quote(service_name.strip())
        return _normalize_terminal_result(terminal.run(f"docker logs --tail={tail} {container}"))
    except Exception as exc:
        return _error(str(exc))


def docker_status(service_name):
    try:
        directory = _service_dir(service_name)
        if os.path.isdir(directory):
            result = terminal.run("docker compose ps --format json", cwd=directory)
            if not isinstance(result, dict):
                return _error("Unexpected docker_status response format")
            if result.get("status") != "success":
                return result
            try:
                parsed = json.loads(result.get("output", "[]") or "[]")
                if isinstance(parsed, dict):
                    parsed = [parsed]
                containers = []
                for item in parsed:
                    if not isinstance(item, dict):
                        continue
                    containers.append(
                        {
                            "name": item.get("Name", "") or item.get("name", ""),
                            "image": item.get("Image", "") or item.get("image", ""),
                            "status": item.get("State", "") or item.get("Status", "") or item.get("state", ""),
                            "ports": item.get("Publishers", "") or item.get("Ports", "") or item.get("ports", ""),
                        }
                    )
                return {"status": "success", "containers": containers}
            except json.JSONDecodeError:
                # Fallback to raw output if compose JSON formatting is unsupported.
                return _success({"containers": [], "raw": result.get("output", "")})
        container = shlex.quote(service_name.strip())
        cmd = f"docker ps -a --filter name={container} --format '{{{{json .}}}}'"
        result = terminal.run(cmd)
        if not isinstance(result, dict):
            return _error("Unexpected docker_status response format")
        if result.get("status") != "success":
            return result
        return {
            "status": "success",
            "containers": _parse_docker_ps_json_lines(result.get("output", "")),
        }
    except Exception as exc:
        return _error(str(exc))


def docker_restart(service_name):
    try:
        directory = _service_dir(service_name)
        if os.path.isdir(directory):
            return _normalize_terminal_result(terminal.run("docker compose restart", cwd=directory))
        container = shlex.quote(service_name.strip())
        return _normalize_terminal_result(terminal.run(f"docker restart {container}"))
    except Exception as exc:
        return _error(str(exc))


def docker_list():
    try:
        command = "docker ps --format '{{json .}}'"
        result = terminal.run(command)
        if not isinstance(result, dict):
            return _error("Unexpected docker_list response format")
        if result.get("status") != "success":
            return result
        return {
            "status": "success",
            "containers": _parse_docker_ps_json_lines(result.get("output", "")),
        }
    except Exception as exc:
        return _error(str(exc))





def caddy_reload(service_name):
    try:
        directory = _service_dir(service_name)
        command = "docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile"
        return _normalize_terminal_result(terminal.run(command, cwd=directory))
    except Exception as exc:
        return _error(str(exc))


def systemd_status(unit):
    try:
        if not isinstance(unit, str) or not unit.strip():
            raise ValueError("unit must be a non-empty string")
        safe_unit = shlex.quote(unit.strip())
        systemctl_bin = _resolve_executable("systemctl")
        return _normalize_terminal_result(terminal.run(f"{systemctl_bin} status {safe_unit}"))
    except Exception as exc:
        return _error(str(exc))


def systemd_logs(unit, lines=50):
    try:
        if not isinstance(unit, str) or not unit.strip():
            raise ValueError("unit must be a non-empty string")
        safe_unit = shlex.quote(unit.strip())
        tail = _normalize_lines(lines)
        journalctl_bin = _resolve_executable("journalctl")
        command = f"{journalctl_bin} -u {safe_unit} -n {tail} --no-pager"
        return _normalize_terminal_result(terminal.run(command))
    except Exception as exc:
        return _error(str(exc))
