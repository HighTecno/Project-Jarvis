import os
import re
import select
import subprocess
import threading
import time
import uuid

from ..config import MAX_TOOL_OUTPUT_CHARS, SERVICE_ROOT, TERMINAL_TIMEOUT_SECONDS, WORKSPACE_PATH


DANGEROUS_PATTERNS = [
    r"\brm\s+-rf\b",
    r"\bdd\b",
    r"\bmkfs\b",
    r":\(\)\{:\|:&\};:",
    r"\bshutdown\b",
    r"\breboot\b",
]


def _success(output):
    return {"status": "success", "output": output}


def _error(message):
    return {"status": "error", "error": message}


def _is_dangerous(command):
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command, flags=re.IGNORECASE):
            return True
    return False


def _inside_root(path, root):
    return os.path.commonpath([os.path.realpath(path), root]) == root


def _inside_any_root(path, roots):
    resolved = os.path.realpath(path)
    for root in roots:
        if _inside_root(resolved, root):
            return True
    return False


def _extract_cd_targets(command):
    matches = re.finditer(r"(?:^|[;&|]\s*)cd\s+([^;&|\n]+)", command)
    targets = []
    for m in matches:
        target = m.group(1).strip().strip('"').strip("'")
        targets.append(target)
    return targets


class _PersistentBash:
    _instance = None
    _instance_lock = threading.Lock()

    def __init__(self):
        self._lock = threading.Lock()
        self._process = None
        self._start_shell()

    @classmethod
    def get(cls):
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def _start_shell(self):
        cwd = os.path.realpath(WORKSPACE_PATH)
        self._process = subprocess.Popen(
            ["/bin/bash", "--noprofile", "--norc"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=cwd,
        )

    def _ensure_alive(self):
        if self._process is None or self._process.poll() is not None:
            self._start_shell()

    def run(self, command, timeout_seconds, max_output_chars, cwd=None):
        with self._lock:
            self._ensure_alive()
            workspace_root = os.path.realpath(WORKSPACE_PATH)
            service_root = os.path.realpath(SERVICE_ROOT)

            if not command or not command.strip():
                return _success("")

            if not os.path.isdir(workspace_root):
                return _error("Workspace root does not exist")

            effective_cwd = workspace_root
            allowed_roots = [workspace_root]

            if cwd is not None:
                if not isinstance(cwd, str) or not cwd.strip():
                    return _error("cwd must be a non-empty string")
                requested = os.path.realpath(cwd)
                if not os.path.isdir(requested):
                    return _error("cwd does not exist or is not a directory")
                if not (_inside_root(requested, workspace_root) or _inside_root(requested, service_root)):
                    return _error("cwd is outside allowed roots")
                effective_cwd = requested
                if _inside_root(requested, service_root):
                    allowed_roots.append(service_root)

            if _is_dangerous(command):
                return _error("Blocked dangerous command")

            for cd_target in _extract_cd_targets(command):
                if not cd_target or cd_target == "~":
                    return _error("Blocked directory change outside workspace")

                candidate = cd_target
                if not os.path.isabs(candidate):
                    candidate = os.path.join(effective_cwd, candidate)
                resolved = os.path.realpath(candidate)
                if not _inside_any_root(resolved, allowed_roots):
                    return _error("Blocked directory change outside workspace")

            token = uuid.uuid4().hex
            wrapped = (
                f"cd {effective_cwd!r} || exit 1\n"
                "export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH\n"
                f"{command}\n"
                f"printf '\\n__JARVIS_DONE__{token}__%s\\n' \"$?\"\n"
            )

            self._process.stdin.write(wrapped.encode("utf-8"))
            self._process.stdin.flush()

            end_time = time.time() + timeout_seconds
            chunks = []
            marker = f"__JARVIS_DONE__{token}__"
            raw_text = ""

            while True:
                now = time.time()
                if now >= end_time:
                    return _error(f"Command timed out after {timeout_seconds} seconds")

                wait = min(0.1, end_time - now)
                readable, _, _ = select.select([self._process.stdout], [], [], wait)
                if not readable:
                    continue

                data = os.read(self._process.stdout.fileno(), 4096)
                if not data:
                    break

                chunks.append(data.decode("utf-8", errors="replace"))
                raw_text = "".join(chunks)
                if marker in raw_text:
                    break

                if len(raw_text) > (max_output_chars * 3):
                    break

            if marker in raw_text:
                before_marker, _, after_marker = raw_text.partition(marker)
                output = before_marker.strip("\n")
                exit_line = after_marker.splitlines()[0].strip() if after_marker else ""
            else:
                output = raw_text.strip("\n")
                exit_line = ""

            if len(output) > max_output_chars:
                output = output[:max_output_chars] + "\n...[truncated]"

            if not output:
                if exit_line.isdigit():
                    return _success(f"(exit code {exit_line})")
                return _success("(no output)")

            return _success(output)


def run(command, timeout_seconds=TERMINAL_TIMEOUT_SECONDS, cwd=None):
    try:
        shell = _PersistentBash.get()
        return shell.run(
            command=command,
            timeout_seconds=timeout_seconds,
            max_output_chars=MAX_TOOL_OUTPUT_CHARS,
            cwd=cwd,
        )
    except Exception as exc:
        return _error(str(exc))