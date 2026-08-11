import os
import shutil


def _has_docker_socket() -> bool:
    return os.path.exists("/var/run/docker.sock")


def _has_systemd() -> bool:
    return os.path.isdir("/run/systemd/system")


def _has_journalctl() -> bool:
    return shutil.which("journalctl") is not None


ENV = {
    "paths": {
        "workspace": "/workspace",
        "hostroot": "/hostroot",
    },
    "has_docker_socket": _has_docker_socket(),
    "has_systemd": _has_systemd(),
    "has_journalctl": _has_journalctl(),
}


def environment_constraints_text() -> str:
    lines = [
        "ENVIRONMENT CONSTRAINTS:",
        "- /workspace is writable/executable",
        "- /hostroot mirrors host filesystem read-only",
        "- Host file reads should be prefixed with /hostroot",
        "- Writes are restricted to /workspace",
    ]
    return "\n".join(lines)
