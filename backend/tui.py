"""Terminal UI client for Jarvis streaming API."""

from __future__ import annotations

import curses
import json
import os
import queue
import textwrap
import threading
import time
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Tuple
from uuid import uuid4

import requests


DisplayLine = Tuple[str, str]
SPINNER_FRAMES = ("|", "/", "-", "\\")
MIN_TUI_WIDTH = 40
MIN_TUI_HEIGHT = 10
DEFAULT_HISTORY_LIMIT = 100


def _iter_sse_events(chunks: Iterable[str]):
    buffer = ""
    for chunk in chunks:
        if not chunk:
            continue
        buffer += chunk
        while "\n\n" in buffer:
            raw, buffer = buffer.split("\n\n", 1)
            data_lines = [line[5:].strip() for line in raw.splitlines() if line.startswith("data:")]
            if not data_lines:
                continue
            try:
                yield json.loads("\n".join(data_lines))
            except json.JSONDecodeError:
                continue


def _utc_time_label() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def _truncate_text(value: str, limit: int = 280) -> str:
    text = str(value).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def _format_elapsed(started_at: Optional[float]) -> str:
    if not started_at:
        return "0.0s"
    elapsed = max(0.0, time.time() - started_at)
    if elapsed < 60:
        return f"{elapsed:.1f}s"
    minutes = int(elapsed // 60)
    seconds = elapsed % 60
    return f"{minutes}m {seconds:.1f}s"


def _parse_positive_int(raw: str) -> Optional[int]:
    text = raw.strip()
    if not text:
        return None
    if not text.isdigit():
        return None
    value = int(text)
    if value <= 0:
        return None
    return value


def fetch_csrf_token(base_url: str, api_key: Optional[str], timeout: int = 10) -> Optional[str]:
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        response = requests.get(f"{base_url.rstrip('/')}/csrf-token", headers=headers, timeout=timeout)
        if response.status_code != 200:
            return None
        body = response.json()
    except (requests.RequestException, ValueError, TypeError):
        return None
    token = body.get("csrf_token")
    if isinstance(token, str) and token:
        return token
    return None


def stream_query(
    base_url: str,
    prompt: str,
    history: List[Dict[str, str]],
    api_key: Optional[str],
    csrf_token: Optional[str],
    timeout: int = 300,
    stop_event: Optional[threading.Event] = None,
    thread_id: Optional[str] = None,
    include_global_memory: bool = True,
):
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if csrf_token:
        headers["X-CSRF-Token"] = csrf_token

    payload = {
        "prompt": prompt,
        "history": history,
        "thread_id": thread_id or "legacy-default",
        "include_global_memory": include_global_memory,
    }
    response = requests.post(
        f"{base_url.rstrip('/')}/stream",
        headers=headers,
        json=payload,
        stream=True,
        timeout=timeout,
    )
    response.raise_for_status()
    for event in _iter_sse_events(response.iter_content(chunk_size=1024, decode_unicode=True)):
        if stop_event and stop_event.is_set():
            break
        yield event


def parse_slash_command(raw: str) -> Tuple[Optional[str], str]:
    text = raw.strip()
    if not text.startswith("/"):
        return None, ""
    body = text[1:].strip()
    if not body:
        return "", ""
    if " " in body:
        cmd, arg = body.split(" ", 1)
        return cmd.lower().strip(), arg.strip()
    return body.lower(), ""


def generate_followup_suggestions(response: str, limit: int = 3) -> List[str]:
    text = response.strip().lower()
    suggestions: List[str] = []
    if any(word in text for word in ("error", "failed", "issue", "problem")):
        suggestions.append("Want me to diagnose the likely root cause?")
    if any(word in text for word in ("plan", "steps", "approach", "roadmap")):
        suggestions.append("Want a concise checklist from this?")
    if any(word in text for word in ("code", "function", "api", "endpoint", "implementation")):
        suggestions.append("Should I draft an implementation snippet next?")

    defaults = [
        "Can you summarize this in 3 bullets?",
        "What should I do next?",
        "What are the trade-offs or risks?",
    ]
    for item in defaults:
        if len(suggestions) >= max(1, limit):
            break
        if item not in suggestions:
            suggestions.append(item)
    return suggestions[: max(1, limit)]


class JarvisTUI:
    def __init__(self, stdscr, base_url: str, api_key: Optional[str]):
        self.stdscr = stdscr
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.csrf_token = None
        self.current_thread_id = f"tui-{uuid4()}"

        self.history: List[Dict[str, str]] = []
        self.chat_lines: List[DisplayLine] = []
        self.tool_lines: List[DisplayLine] = []

        self.input_buffer = ""
        self.input_cursor = 0
        self.input_history: List[str] = []
        self.input_history_index: Optional[int] = None

        self.status = "Ready"
        self.focus = "chat"
        self.chat_scroll = 0
        self.tool_scroll = 0
        self.tools_visible = True

        self.running = True
        self.streaming = False
        self.stop_event = threading.Event()
        self.event_queue: queue.Queue = queue.Queue()
        self.stream_thread: Optional[threading.Thread] = None
        self.last_prompt = ""
        self.current_request_started_at: Optional[float] = None

        self.message_count = 0
        self.tool_call_count = 0
        self.error_count = 0
        self.history_limit = DEFAULT_HISTORY_LIMIT
        self.spinner_index = 0

        self.colors = {name: 0 for name in ["header", "status", "hint", "user", "assistant", "tool", "error", "title"]}

    @staticmethod
    def command_help_lines() -> List[str]:
        return [
            "Core: /help /quit /stop /retry /status /toggletools /focus <chat|tools>",
            "Session: /clear /cleartools /new /thread /apikey <token> /history <count>",
            "Data: /savechat <file> /loadchat <file> /export <file.md> /search <text>",
        ]

    def _init_colors(self):
        try:
            if not curses.has_colors():
                return
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_CYAN, -1)
            curses.init_pair(2, curses.COLOR_MAGENTA, -1)
            curses.init_pair(3, curses.COLOR_BLUE, -1)
            curses.init_pair(4, curses.COLOR_GREEN, -1)
            curses.init_pair(5, curses.COLOR_WHITE, -1)
            curses.init_pair(6, curses.COLOR_YELLOW, -1)
            curses.init_pair(7, curses.COLOR_RED, -1)
            self.colors["header"] = curses.color_pair(1) | curses.A_BOLD
            self.colors["status"] = curses.color_pair(2) | curses.A_BOLD
            self.colors["hint"] = curses.color_pair(3)
            self.colors["user"] = curses.color_pair(4) | curses.A_BOLD
            self.colors["assistant"] = curses.color_pair(5)
            self.colors["tool"] = curses.color_pair(6)
            self.colors["error"] = curses.color_pair(7) | curses.A_BOLD
            self.colors["title"] = curses.color_pair(1) | curses.A_BOLD
        except curses.error:
            return

    def _append_lines(self, target: List[DisplayLine], text: str, style: str = "assistant"):
        for line in str(text).splitlines() or [""]:
            target.append((line, style))
        if len(target) > 3000:
            del target[:-3000]

    def _append_chat(self, text: str, style: str = "assistant"):
        self._append_lines(self.chat_lines, f"[{_utc_time_label()}] {text}", style)

    def _append_tool(self, text: str, style: str = "tool"):
        self._append_lines(self.tool_lines, f"[{_utc_time_label()}] {text}", style)

    def _safe_addnstr(self, y: int, x: int, text: str, width: int, attr: int = 0):
        if width <= 0:
            return
        try:
            self.stdscr.addnstr(y, x, text, max(0, width), attr)
        except curses.error:
            return

    def _safe_hline(self, y: int, x: int, ch: int, width: int):
        if width <= 0:
            return
        try:
            self.stdscr.hline(y, x, ch, width)
        except curses.error:
            return

    def _wrapped_lines(self, lines: List[DisplayLine], width: int) -> List[DisplayLine]:
        wrapped: List[DisplayLine] = []
        wrap_width = max(1, width)
        for text, style in lines:
            if not text:
                wrapped.append(("", style))
                continue
            for segment in textwrap.wrap(
                text,
                width=wrap_width,
                replace_whitespace=False,
                drop_whitespace=False,
                break_long_words=True,
                break_on_hyphens=False,
            ) or [""]:
                wrapped.append((segment, style))
        return wrapped

    def _visible_lines(self, lines: List[DisplayLine], pane_height: int, scroll: int, width: int) -> List[DisplayLine]:
        if pane_height <= 0:
            return []
        expanded = self._wrapped_lines(lines, max(1, width - 1))
        max_scroll = max(0, len(expanded) - 1)
        bounded_scroll = max(0, min(scroll, max_scroll))
        end = max(0, len(expanded) - bounded_scroll)
        start = max(0, end - pane_height)
        return expanded[start:end]

    def _draw_pane(self, top: int, left: int, height: int, width: int, title: str, lines: List[DisplayLine], focus: bool, scroll: int):
        if height < 2 or width < 4:
            return
        title_attr = self.colors["title"] if focus else curses.A_BOLD
        self._safe_addnstr(top, left, f"[{title}]", width - 1, title_attr)
        self._safe_hline(top + 1, left, ord("-"), width)

        visible = self._visible_lines(lines, height - 2, scroll, width)
        y = top + 2
        for text, style in visible:
            if y >= top + height:
                break
            attr = self.colors.get(style, 0)
            self._safe_addnstr(y, left, text, width - 1, attr)
            y += 1

    def _draw(self):
        self.stdscr.erase()
        h, w = self.stdscr.getmaxyx()
        if h < MIN_TUI_HEIGHT or w < MIN_TUI_WIDTH:
            self._safe_addnstr(
                0,
                0,
                f"Terminal too small. Resize to at least {MIN_TUI_WIDTH}x{MIN_TUI_HEIGHT}.",
                max(1, w - 1),
                self.colors["error"],
            )
            self.stdscr.refresh()
            return

        spinner = SPINNER_FRAMES[self.spinner_index % len(SPINNER_FRAMES)] if self.streaming else "-"
        state = f"{spinner} {'Streaming' if self.streaming else 'Idle'} {_format_elapsed(self.current_request_started_at if self.streaming else None)}"
        counters = f"Msgs:{self.message_count} Tools:{self.tool_call_count} Errors:{self.error_count} Hist:{len(self.history)}"

        self._safe_addnstr(0, 0, "Jarvis TUI Pro", w - 1, self.colors["header"])
        self._safe_addnstr(0, max(0, w - len(counters) - 1), counters, len(counters), self.colors["hint"])
        endpoint_text = f"Endpoint: {self.base_url}   Auth: {'set' if self.api_key else 'none'}"
        self._safe_addnstr(1, 0, endpoint_text, w - 1)
        self._safe_addnstr(1, max(0, w - len(state) - 1), state, len(state), self.colors["status"])
        self._safe_hline(2, 0, ord("="), w)

        pane_top = 3
        footer_top = h - 3
        pane_height = max(2, footer_top - pane_top)

        if self.tools_visible and w >= 70:
            chat_w = int(w * 0.67)
            tool_w = max(22, w - chat_w - 1)
            self._draw_pane(
                pane_top,
                0,
                pane_height,
                chat_w,
                f"Chat {'*' if self.focus == 'chat' else ''}",
                self.chat_lines,
                self.focus == "chat",
                self.chat_scroll,
            )
            self._draw_pane(
                pane_top,
                chat_w + 1,
                pane_height,
                tool_w,
                f"Tools {'*' if self.focus == 'tools' else ''}",
                self.tool_lines,
                self.focus == "tools",
                self.tool_scroll,
            )
        else:
            self._draw_pane(
                pane_top,
                0,
                pane_height,
                w,
                f"Chat {'*' if self.focus == 'chat' else ''}",
                self.chat_lines,
                self.focus == "chat",
                self.chat_scroll,
            )

        self._safe_hline(footer_top, 0, ord("="), w)
        footer = f"{self.status} | Tab:focus PgUp/PgDn:scroll Ctrl+L:clear Ctrl+T:tools /help"
        self._safe_addnstr(footer_top + 1, 0, footer, w - 1, self.colors["hint"])

        prompt_prefix = "> "
        render_input = prompt_prefix + self.input_buffer
        self._safe_addnstr(footer_top + 2, 0, render_input, w - 1)
        cursor_x = min(w - 1, len(prompt_prefix) + self.input_cursor)
        try:
            self.stdscr.move(footer_top + 2, max(0, cursor_x))
        except curses.error:
            pass
        self.stdscr.refresh()

    def _handle_event(self, event: Dict[str, object]) -> Optional[str]:
        event_type = event.get("type")
        if event_type == "thinking":
            step = event.get("step", "?")
            thought = str(event.get("thought", "")).strip()
            suffix = f": {thought}" if thought else ""
            self.status = f"Thinking step {step}"
            self._append_tool(f"[thinking] step {step}{suffix}")
        elif event_type == "tool_call":
            tool = str(event.get("tool", "unknown"))
            args = json.dumps(event.get("args", {}), ensure_ascii=True)
            self._append_tool(f"[call] {tool} {_truncate_text(args, limit=220)}")
            self.tool_call_count += 1
            self.status = f"Running {tool}"
        elif event_type == "tool_result":
            tool = str(event.get("tool", "tool"))
            self._append_tool(f"[result] {tool}")
            self._append_tool(_truncate_text(str(event.get("output", "")), limit=1000))
            self.status = "Tool result received"
        elif event_type == "error":
            msg = str(event.get("message", "Unknown error"))
            self._append_chat(f"[error] {msg}", "error")
            self._append_tool(f"[error] {msg}", "error")
            self.error_count += 1
            self.status = "Error"
        elif event_type == "final":
            text = str(event.get("response", ""))
            self._append_chat(f"Jarvis: {text}", "assistant")
            self._append_chat("Follow-up suggestions:", "hint")
            for item in generate_followup_suggestions(text):
                self._append_chat(f"  - {item}", "hint")
            self.status = "Ready"
            return text
        return None

    def _start_stream(self, prompt: str):
        if self.streaming:
            self._append_chat("[system] A request is already in progress. Use /stop first.", "error")
            return
        self.last_prompt = prompt
        self._append_chat(f"You: {prompt}", "user")
        if self.csrf_token is None:
            self.csrf_token = fetch_csrf_token(self.base_url, self.api_key)

        self.stop_event = threading.Event()
        self.streaming = True
        self.current_request_started_at = time.time()
        self.status = "Streaming response"

        def worker():
            assistant_text = ""
            try:
                for event in stream_query(
                    base_url=self.base_url,
                    prompt=prompt,
                    history=self.history,
                    api_key=self.api_key,
                    csrf_token=self.csrf_token,
                    stop_event=self.stop_event,
                    thread_id=self.current_thread_id,
                    include_global_memory=True,
                ):
                    if self.stop_event.is_set():
                        break
                    self.event_queue.put(("event", event))
                    if event.get("type") == "final":
                        assistant_text = str(event.get("response", ""))
            except requests.HTTPError as exc:
                self.event_queue.put(("error", f"[http-error] {exc}"))
            except requests.RequestException as exc:
                self.event_queue.put(("error", f"[network-error] {exc}"))
            except Exception as exc:
                self.event_queue.put(("error", f"[error] {exc}"))
            finally:
                self.event_queue.put(("done", assistant_text))

        self.stream_thread = threading.Thread(target=worker, daemon=True)
        self.stream_thread.start()

    def _process_event_queue(self):
        while True:
            try:
                kind, payload = self.event_queue.get_nowait()
            except queue.Empty:
                return
            if kind == "event":
                self._handle_event(payload)
            elif kind == "error":
                self._append_chat(str(payload), "error")
                self.error_count += 1
                self.status = "Error"
            elif kind == "done":
                assistant_text = str(payload or "")
                if not self.stop_event.is_set() and assistant_text:
                    self.history.append({"role": "user", "content": self.last_prompt})
                    self.history.append({"role": "assistant", "content": assistant_text})
                    self.history = self.history[-self.history_limit :]
                    self.message_count += 1
                elif self.stop_event.is_set():
                    self._append_chat("[system] Request stopped.", "hint")
                    self.status = "Stopped"
                self.streaming = False
                self.current_request_started_at = None

    def _set_input(self, text: str):
        self.input_buffer = text
        self.input_cursor = len(text)

    def _history_up(self):
        if not self.input_history:
            return
        if self.input_history_index is None:
            self.input_history_index = len(self.input_history) - 1
        else:
            self.input_history_index = max(0, self.input_history_index - 1)
        self._set_input(self.input_history[self.input_history_index])

    def _history_down(self):
        if self.input_history_index is None:
            return
        self.input_history_index += 1
        if self.input_history_index >= len(self.input_history):
            self.input_history_index = None
            self._set_input("")
            return
        self._set_input(self.input_history[self.input_history_index])

    def _scroll(self, amount: int):
        if self.focus == "tools":
            self.tool_scroll = max(0, self.tool_scroll + amount)
        else:
            self.chat_scroll = max(0, self.chat_scroll + amount)

    def _reset_session(self):
        self.history.clear()
        self.chat_lines.clear()
        self.tool_lines.clear()
        self.current_thread_id = f"tui-{uuid4()}"
        self.chat_scroll = 0
        self.tool_scroll = 0
        self.status = "New session"
        self._append_chat(f"Started a clean session ({self.current_thread_id}).", "hint")

    def _save_chat(self, file_path: str) -> bool:
        path = file_path.strip()
        if not path:
            self._append_chat("Usage: /savechat <file_path>", "error")
            return True
        payload = {"history": self.history, "saved_at": datetime.now(timezone.utc).isoformat()}
        try:
            directory = os.path.dirname(path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=True, indent=2)
            self._append_chat(f"Saved session to {path}", "hint")
        except Exception as exc:
            self._append_chat(f"Failed to save session: {exc}", "error")
        return True

    def _load_chat(self, file_path: str) -> bool:
        path = file_path.strip()
        if not path:
            self._append_chat("Usage: /loadchat <file_path>", "error")
            return True
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            loaded_history = payload.get("history", [])
            normalized = []
            if isinstance(loaded_history, list):
                for item in loaded_history:
                    if not isinstance(item, dict):
                        continue
                    role = item.get("role")
                    content = item.get("content")
                    if role not in {"user", "assistant"} or not isinstance(content, str):
                        continue
                    normalized.append({"role": role, "content": content})
            self.history = normalized[-self.history_limit :]
            self._append_chat(f"Loaded {len(self.history)} history messages from {path}", "hint")
        except Exception as exc:
            self._append_chat(f"Failed to load session: {exc}", "error")
        return True

    def _export_markdown(self, file_path: str) -> bool:
        path = file_path.strip()
        if not path:
            self._append_chat("Usage: /export <file_path>", "error")
            return True
        try:
            directory = os.path.dirname(path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write("# Jarvis TUI Export\n\n")
                for role_item in self.history:
                    role = str(role_item.get("role", "unknown")).capitalize()
                    content = str(role_item.get("content", ""))
                    f.write(f"## {role}\n\n{content}\n\n")
            self._append_chat(f"Exported markdown transcript to {path}", "hint")
        except Exception as exc:
            self._append_chat(f"Failed to export markdown: {exc}", "error")
        return True

    def _search_chat(self, text: str) -> bool:
        query = text.strip().lower()
        if not query:
            self._append_chat("Usage: /search <text>", "error")
            return True
        matches = [line for line, _ in self.chat_lines if query in line.lower()]
        self._append_chat(f"Found {len(matches)} chat lines matching '{query}'", "hint")
        for item in matches[:5]:
            self._append_chat(f"  {item}", "hint")
        return True

    def _run_command(self, cmd: str, arg: str) -> bool:
        if cmd in {"quit", "q", "exit"}:
            self.running = False
            return True
        if cmd == "help":
            for line in self.command_help_lines():
                self._append_chat(line, "hint")
            return True
        if cmd == "clear":
            self.chat_lines.clear()
            self.status = "Chat cleared"
            return True
        if cmd == "cleartools":
            self.tool_lines.clear()
            self.status = "Tool pane cleared"
            return True
        if cmd == "new":
            self._reset_session()
            return True
        if cmd == "thread":
            self._append_chat(f"Current thread: {self.current_thread_id}", "hint")
            return True
        if cmd == "toggletools":
            self.tools_visible = not self.tools_visible
            self.status = "Tools visible" if self.tools_visible else "Tools hidden"
            return True
        if cmd == "focus":
            target = arg.lower()
            if target in {"chat", "tools"}:
                self.focus = target
                self.status = f"Focus: {target}"
            else:
                self._append_chat("Usage: /focus <chat|tools>", "error")
            return True
        if cmd in {"status", "stats"}:
            self._append_chat(
                (
                    f"status={self.status} streaming={self.streaming} history={len(self.history)} "
                    f"chat_lines={len(self.chat_lines)} tool_lines={len(self.tool_lines)}"
                ),
                "hint",
            )
            return True
        if cmd == "apikey":
            self.api_key = arg or None
            self.csrf_token = None
            masked = "(cleared)" if not self.api_key else f"...{self.api_key[-4:]}"
            self._append_chat(f"API key updated {masked}", "hint")
            return True
        if cmd == "stop":
            if self.streaming:
                self.stop_event.set()
                self.status = "Stopping..."
            else:
                self._append_chat("No active request.", "hint")
            return True
        if cmd == "retry":
            if self.last_prompt:
                self._start_stream(self.last_prompt)
            else:
                self._append_chat("No previous prompt to retry.", "hint")
            return True
        if cmd == "history":
            value = _parse_positive_int(arg)
            if value is None:
                self._append_chat("Usage: /history <positive_number>", "error")
            else:
                self.history_limit = max(20, min(400, value))
                self.history = self.history[-self.history_limit :]
                self._append_chat(f"History cap set to {self.history_limit} messages", "hint")
            return True
        if cmd == "savechat":
            return self._save_chat(arg)
        if cmd == "loadchat":
            return self._load_chat(arg)
        if cmd == "export":
            return self._export_markdown(arg)
        if cmd == "search":
            return self._search_chat(arg)
        if cmd == "":
            self._append_chat("Empty slash command. Use /help.", "hint")
            return True
        self._append_chat(f"Unknown command: /{cmd}. Use /help.", "error")
        return True

    def _submit_input(self):
        prompt = self.input_buffer.strip()
        self._set_input("")
        self.input_history_index = None
        if not prompt:
            return

        cmd, arg = parse_slash_command(prompt)
        if cmd is not None:
            self._run_command(cmd, arg)
            return

        self.input_history.append(prompt)
        if len(self.input_history) > 200:
            self.input_history = self.input_history[-200:]
        self._start_stream(prompt)

    def _handle_key(self, ch):
        if ch in ("\n", "\r", curses.KEY_ENTER):
            self._submit_input()
            return
        if ch == "\t" or ch == curses.KEY_BTAB:
            self.focus = "tools" if self.focus == "chat" else "chat"
            return
        if ch == curses.KEY_PPAGE:
            self._scroll(10)
            return
        if ch == curses.KEY_NPAGE:
            self._scroll(-10)
            return
        if ch == "\x0c":  # Ctrl+L
            self.chat_lines.clear()
            self.status = "Chat cleared"
            return
        if ch == "\x14":  # Ctrl+T
            self.tools_visible = not self.tools_visible
            self.status = "Tools visible" if self.tools_visible else "Tools hidden"
            return
        if ch == "\x0b":  # Ctrl+K
            self._set_input("")
            return
        if ch in (curses.KEY_UP,):
            self._history_up()
            return
        if ch in (curses.KEY_DOWN,):
            self._history_down()
            return
        if ch in (curses.KEY_LEFT,):
            self.input_cursor = max(0, self.input_cursor - 1)
            return
        if ch in (curses.KEY_RIGHT,):
            self.input_cursor = min(len(self.input_buffer), self.input_cursor + 1)
            return
        if ch in (curses.KEY_HOME,):
            self.input_cursor = 0
            return
        if ch in (curses.KEY_END,):
            self.input_cursor = len(self.input_buffer)
            return
        if ch in ("\b", "\x7f", curses.KEY_BACKSPACE):
            if self.input_cursor > 0:
                self.input_buffer = self.input_buffer[: self.input_cursor - 1] + self.input_buffer[self.input_cursor :]
                self.input_cursor -= 1
            return
        if ch in (curses.KEY_DC,):
            if self.input_cursor < len(self.input_buffer):
                self.input_buffer = self.input_buffer[: self.input_cursor] + self.input_buffer[self.input_cursor + 1 :]
            return
        if ch == "\x1b":
            return
        if isinstance(ch, str) and ch.isprintable():
            self.input_buffer = self.input_buffer[: self.input_cursor] + ch + self.input_buffer[self.input_cursor :]
            self.input_cursor += 1

    def run(self):
        try:
            curses.curs_set(1)
        except curses.error:
            pass
        self.stdscr.timeout(50)
        self._init_colors()
        self._append_chat("Welcome to Jarvis TUI Pro. Type your prompt and press Enter.", "hint")
        self._append_chat("Use /help for commands.", "hint")

        while self.running:
            self._process_event_queue()
            if self.streaming:
                self.spinner_index += 1
            self._draw()
            try:
                ch = self.stdscr.get_wch()
            except curses.error:
                continue
            self._handle_key(ch)


def launch_tui(base_url: str, api_key: Optional[str] = None):
    resolved_key = api_key or os.getenv("JARVIS_API_KEY")
    curses.wrapper(lambda stdscr: JarvisTUI(stdscr, base_url=base_url, api_key=resolved_key).run())
