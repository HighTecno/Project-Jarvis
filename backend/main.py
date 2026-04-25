import asyncio
import json
import os
import queue
import threading
import time
from typing import Dict, List, Optional

from fastapi import FastAPI, Depends, Request
from fastapi import File, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

try:
    # package mode
    from backend.agent.core import run_agent
except ImportError:
    try:
        # script mode from backend folder
        from agent.core import run_agent
    except ImportError:
        # fallback for direct root invocation
        from .agent.core import run_agent

try:
    from backend.config import (
        ENABLE_STT,
        CORS_ORIGINS,
        HISTORY_DIR,
        HISTORY_FILE,
        DEFAULT_THREAD_ID,
        MEMORY_SUMMARIZE_EVERY_EXCHANGES,
        MEMORY_SUMMARY_WINDOW_EXCHANGES,
        MEMORY_MAX_CONTEXT_MESSAGES,
    )
    from backend.logger import setup_logging, get_logger
    from backend.system_prompt import build_system_prompt
    from backend.auth import verify_auth, init_auth
    from backend.rate_limit import check_rate_limit, get_rate_limit_status
    from backend.csrf import generate_csrf_token, validate_csrf_token
    from backend.request_id import RequestIDMiddleware
    from backend.metrics import get_metrics, get_metrics_summary
    from backend.metrics_middleware import MetricsMiddleware
    from backend.health import shallow_health_check, deep_health_check
    from backend.timeout_middleware import TimeoutMiddleware
    from backend.memory import (
        summarize_and_store,
        ensure_thread,
        append_thread_exchange,
        get_thread_history,
        list_threads,
        list_memory_items,
        set_memory_pinned,
        delete_memory_item,
        prune_unpinned_memories,
        migrate_history_file,
    )
except ImportError:
    try:
        from config import (
            ENABLE_STT,
            CORS_ORIGINS,
            HISTORY_DIR,
            HISTORY_FILE,
            DEFAULT_THREAD_ID,
            MEMORY_SUMMARIZE_EVERY_EXCHANGES,
            MEMORY_SUMMARY_WINDOW_EXCHANGES,
            MEMORY_MAX_CONTEXT_MESSAGES,
        )
        from logger import setup_logging, get_logger
        from system_prompt import build_system_prompt
        from auth import verify_auth, init_auth
        from rate_limit import check_rate_limit, get_rate_limit_status
        from csrf import generate_csrf_token, validate_csrf_token
        from request_id import RequestIDMiddleware
        from metrics import get_metrics, get_metrics_summary
        from metrics_middleware import MetricsMiddleware
        from health import shallow_health_check, deep_health_check
        from timeout_middleware import TimeoutMiddleware
        from memory import (
            summarize_and_store,
            ensure_thread,
            append_thread_exchange,
            get_thread_history,
            list_threads,
            list_memory_items,
            set_memory_pinned,
            delete_memory_item,
            prune_unpinned_memories,
            migrate_history_file,
        )
    except ImportError:
        from .config import (
            ENABLE_STT,
            CORS_ORIGINS,
            HISTORY_DIR,
            HISTORY_FILE,
            DEFAULT_THREAD_ID,
            MEMORY_SUMMARIZE_EVERY_EXCHANGES,
            MEMORY_SUMMARY_WINDOW_EXCHANGES,
            MEMORY_MAX_CONTEXT_MESSAGES,
        )
        from .logger import setup_logging, get_logger
        from .system_prompt import build_system_prompt
        from .auth import verify_auth, init_auth
        from .rate_limit import check_rate_limit, get_rate_limit_status
        from .csrf import generate_csrf_token, validate_csrf_token
        from .request_id import RequestIDMiddleware
        from .metrics import get_metrics, get_metrics_summary
        from .metrics_middleware import MetricsMiddleware
        from .health import shallow_health_check, deep_health_check
        from .timeout_middleware import TimeoutMiddleware
        from .memory import (
            summarize_and_store,
            ensure_thread,
            append_thread_exchange,
            get_thread_history,
            list_threads,
            list_memory_items,
            set_memory_pinned,
            delete_memory_item,
            prune_unpinned_memories,
            migrate_history_file,
        )

# Initialize logging
setup_logging()
logger = get_logger("main")

app = FastAPI(title="Jarvis AI Assistant", version="1.0.0")

# Add timeout middleware (first, to wrap everything)
app.add_middleware(TimeoutMiddleware, timeout=300.0)  # 5 minutes

# Add metrics middleware (second, to track all requests)
app.add_middleware(MetricsMiddleware)

# Add request ID middleware (third, so it wraps remaining middleware)
app.add_middleware(RequestIDMiddleware)

# Add CORS middleware
# Note: allow_credentials=True requires specific origins, not wildcard
if CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    logger.info(f"CORS configured for origins: {CORS_ORIGINS}")
else:
    # Wildcard origin with no credentials for development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    logger.warning("CORS configured with allow_origins=['*'] and allow_credentials=False - set CORS_ORIGINS env var for production")

# Get the directory where main.py is located
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BACKEND_DIR, "static")
INDEX_FILE = os.path.join(STATIC_DIR, "index.html")
MAX_HISTORY_EXCHANGES = 50
MAX_HISTORY_AGE_DAYS = 90  # Delete history files older than this
_HISTORY_LOCK = threading.Lock()
_history_cleanup_thread = None
_history_cleanup_stop_event = threading.Event()


def _normalize_thread_id(thread_id: Optional[str]) -> str:
    if isinstance(thread_id, str) and thread_id.strip():
        return thread_id.strip()
    return DEFAULT_THREAD_ID

SYSTEM_PROMPT = """
You are Jarvis, a personal AI assistant for a homelab server running Debian.
You assist with two things: coding tasks and homelab infrastructure management.

ENVIRONMENT:
- Services live at /hostroot/root/<service-name>/
    each with docker-compose.yaml, .env, Caddyfile
- Each service runs its own Caddy instance with caddy-tailscale plugin
- Tailscale state persisted via TS_STATE volume
- Ollama runs bare on the host at port 11434, reachable via host.docker.internal
Service directories are named after the service (e.g. nextcloud, mealie, n8n) 
NOT after container names (e.g. nextcloud-tailscale-1). 
To find Tailscale hostnames, read the Caddyfile inside /hostroot/root/<service>/

CODING CONVENTIONS:
- Shell scripts use bash
- Python projects use venv or pipx
- Config files follow existing patterns in the repo before inventing new ones
- Always read existing files before writing new ones

BEHAVIOR:
- Before any destructive action (restart, delete, overwrite), state what you are
  about to do and why
- Prefer targeted reads over broad searches
- When diagnosing an issue, check logs first
- Never guess at file paths - use filesystem.list or filesystem.search to confirm
- Present information directly. 
- Do not end responses with offers to do more unless the user's request was genuinely ambiguous.

MEMORY:
- Relevant long-term memories may be appended as a `RELEVANT MEMORY` section.
- This memory comes from semantic retrieval over summarized prior conversations.
- Memory is best-effort context, not guaranteed fact. If it conflicts with current
  evidence, trust current tool output and explain the conflict.
- If no `RELEVANT MEMORY` section is present, continue normally without referring
  to memory.

FILESYSTEM:
- /workspace is your sandbox - read, write, and execute freely here
- /hostroot mirrors the entire host filesystem read-only
- Host service files are at /hostroot/root/<service-name>/
- Never write outside /workspace
SERVICES: 
- List the actual directory names under /hostroot/root when 
referring to services. 
- Always use filesystem.list on /hostroot/root 
first if unsure of the exact directory name before calling homelab tools.

TOOL USE:
You have access to tools. You MUST use tools to answer questions about files,
directories, and the system. Never say you cannot access the file system.

To use a tool, output ONLY a raw JSON object on its own, with no other text before or after it:
{"tool": "tool_name", "args": {"arg1": "value1"}}

Hard requirements:
- Never wrap tool calls in markdown/code fences (no ```json and no ```tool).
- Never include explanatory text before or after a tool call JSON.
- Never invent tool names or argument names; use only what is listed below.
- For URL arguments, always use a full absolute URL with scheme and host
  (e.g. https://example.com/path). Never use placeholders, wildcards, or
  partial URLs.
- If no tool is needed, respond with plain text only and do not include JSON.

Available tools:
- {"tool": "terminal.run", "args": {"command": "bash command here"}}
- {"tool": "filesystem.read", "args": {"file_path": "/path/to/file"}}
- {"tool": "filesystem.write", "args": {"file_path": "/path/to/file", "content": "text"}}
- {"tool": "filesystem.list", "args": {"path": "/path/to/dir"}}
- {"tool": "filesystem.search", "args": {"pattern": "*.py", "base_path": "/root"}}
- {"tool": "filesystem.info", "args": {"file_path": "/path/to/file"}}
- {"tool": "homelab.docker_logs", "args": {"service_name": "service", "lines": 50}}
- {"tool": "homelab.docker_status", "args": {"service_name": "service"}}
- {"tool": "homelab.docker_restart", "args": {"service_name": "service"}}
- {"tool": "homelab.docker_list", "args": {}}
- {"tool": "homelab.caddy_reload", "args": {"service_name": "service"}}
- {"tool": "homelab.systemd_status", "args": {"unit": "docker.service"}}
- {"tool": "homelab.systemd_logs", "args": {"unit": "docker.service", "lines": 50}}
- {"tool": "debug.analyze_logs", "args": {"service_name": "service", "lines": 100}}
- {"tool": "debug.validate_compose", "args": {"file_path": "/path/to/docker-compose.yaml"}}
- {"tool": "debug.summarize_error", "args": {"error_text": "error message or stack trace"}}
- {"tool": "git.status", "args": {"repo_path": "/path/to/repo"}}
- {"tool": "git.commit", "args": {"message": "commit message", "add_all": false}}
- {"tool": "git.push", "args": {"remote": "origin", "branch": "main"}}
- {"tool": "git.pull", "args": {"remote": "origin", "branch": "main"}}
- {"tool": "git.branch_list", "args": {"repo_path": "/path/to/repo"}}
- {"tool": "git.create_branch", "args": {"name": "feature-branch", "checkout": true}}
- {"tool": "config.set", "args": {"key": "service.api_token", "value": "secret", "description": "optional"}}
- {"tool": "config.get", "args": {"key": "service.api_token"}}
- {"tool": "config.list", "args": {}}
- {"tool": "config.delete", "args": {"key": "service.api_token"}}
- {"tool": "web.fetch", "args": {"url": "https://example.com", "timeout": 20}}
- {"tool": "web.extract_recipe", "args": {"url": "https://chefkoch.de/recipe-url"}}
- {"tool": "web.extract_text", "args": {"url": "https://example.com", "selector": "article"}}
- {"tool": "mealie.search", "args": {"query": "Käsekuchen", "language": "de"}}
- {"tool": "mealie.add_from_url", "args": {"url": "https://www.allrecipes.com/recipe/12683/chocolate-chip-cookies/", "tags": ["dessert"]}}
- {"tool": "mealie.list", "args": {"tags": ["dinner"], "search": "pasta"}}
- {"tool": "mealie.translate", "args": {"text": "Mehl", "source_lang": "de", "target_lang": "en"}}
- {"tool": "n8n.draft_workflow", "args": {"description": "workflow description", "trigger_type": "webhook"}}
- {"tool": "n8n.validate_workflow", "args": {"workflow_json": "json string"}}
- {"tool": "n8n.trigger_workflow", "args": {"workflow_id": "webhook-path", "data": {"key": "value"}}}
- {"tool": "telegram.send", "args": {"message": "text", "chat_id": "optional"}}
- {"tool": "telegram.alert", "args": {"title": "Alert", "body": "message", "level": "info"}}
- {"tool": "telegram.forward_logs", "args": {"service_name": "service", "lines": 20}}
- {"tool": "telegram.get_updates", "args": {"offset": 123}}
- {"tool": "network.ping", "args": {"host": "example.com", "count": 4}}
- {"tool": "network.port_check", "args": {"host": "localhost", "port": 8000}}
- {"tool": "network.dns_lookup", "args": {"hostname": "example.com"}}
- {"tool": "system.info", "args": {}}
- {"tool": "system.disk_usage", "args": {"path": "/"}}
- {"tool": "system.process_list", "args": {"filter_name": "python"}}
- {"tool": "knowledge.search", "args": {"query": "question", "top_k": 5}}
- {"tool": "knowledge.ingest_file", "args": {"path": "/nextcloud/user/files/notes.md"}}
- {"tool": "knowledge.init", "args": {"root": "/nextcloud"}}

Description for tools

- homelab.docker_logs / docker_status / docker_restart / caddy_reload — these 
    require a service_name matching a directory under /hostroot/root/
    
- debug.analyze_logs — analyzes service logs for errors, warnings, and patterns.
    Returns error count, common issues, and actionable suggestions.
    
- debug.validate_compose — validates docker-compose.yaml syntax and best practices.
    Checks for common issues like missing restart policies, exposed secrets, etc.
    
- debug.summarize_error — parses error messages and stack traces.
    Identifies error type, probable cause, and suggests fixes.
    
- git.status — shows repository status including branch, uncommitted changes,
    staged files, and remote sync status.
    
- git.commit — creates a commit with the given message. Set add_all=true to
    stage all modified files first.
    
- git.push / git.pull — sync with remote repository.

- git.branch_list — lists all local and remote branches.

- git.create_branch — creates a new branch. Set checkout=true to switch to it.

- config.set / get / list / delete — secure storage for API keys and secrets.
    Stored at ~/.jarvis/config/secrets.json with 0600 permissions.
    Use dot notation for keys (e.g., "telegram.bot_token").
    
- web.fetch — fetches content from URLs with timeout support.

- web.extract_recipe — extracts structured recipe data from German cooking sites
    (Chefkoch.de supported). Returns ingredients, instructions, servings, etc.
    
- web.extract_text — extracts clean text from URLs with optional CSS selectors.

- mealie.search — searches for recipes online (currently supports language="de").
    Returns list of recipe URLs matching the query.
    
- mealie.add_from_url — extracts recipe from URL and adds to Mealie via API.
    Requires mealie.url and mealie.api_token in config.
    
- mealie.list — lists recipes from Mealie with optional tag/search filters.

- mealie.translate — basic translation of cooking terms (German ↔ English).

- n8n.draft_workflow — generates n8n workflow JSON from natural language.
    Supports webhook, schedule, and manual triggers.
    
- n8n.validate_workflow — validates n8n workflow JSON structure.

- n8n.trigger_workflow — triggers n8n workflow execution via webhook.
    Requires n8n.url in config.
    
- telegram.send — sends message to Telegram chat.
    Requires telegram.bot_token and telegram.default_chat_id in config.
    
- telegram.alert — sends formatted alert with title, body, and severity level.

- telegram.forward_logs — forwards service logs to Telegram.

- telegram.get_updates — retrieves messages sent to the bot.

- knowledge.search — semantically searches ingested local knowledge files.

- knowledge.ingest_file — ingests one file into the knowledge base.

- knowledge.init — recursively ingests all supported files under a root path.
    This can take several minutes on large directories.

Tailscale is not a standalone service — it runs as a sidecar container 
inside each service stack. To check Tailscale status for a service, 
check that service's tailscale container logs instead.

When you receive a tool result, summarize it clearly for the user. Always use tools when the user asks about files, directories, or system information. Never claim you don't have access to the file system or terminal. Always use the tools to get the information you need to help the user.
"""

# Overwrite with the prompt builder so skills and tool lists are reflected.
SYSTEM_PROMPT = build_system_prompt()


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


def _load_history():
    os.makedirs(HISTORY_DIR, exist_ok=True)
    if not os.path.exists(HISTORY_FILE):
        return []
    
    # Try to load the main file
    try:
        with open(HISTORY_FILE, "r") as f:
            data = json.load(f)
        return _normalize_history(data)
    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"Failed to load history from {HISTORY_FILE}: {e}")
        
        # Try to recover from backup if main file is corrupted
        backup_file = HISTORY_FILE + ".backup"
        if os.path.exists(backup_file):
            try:
                logger.info("Attempting to recover from backup")
                with open(backup_file, "r") as f:
                    data = json.load(f)
                logger.info("Successfully recovered from backup")
                return _normalize_history(data)
            except Exception as backup_error:
                logger.error(f"Backup recovery also failed: {backup_error}")
        
        return []


def _save_history(history):
    """
    Save history using atomic write-then-rename pattern.
    This prevents corruption if the process is interrupted during write.
    """
    os.makedirs(HISTORY_DIR, exist_ok=True)
    
    # Write to temporary file first
    temp_file = HISTORY_FILE + ".tmp"
    try:
        with open(temp_file, "w") as f:
            json.dump(history, f, ensure_ascii=True, indent=2)
        
        # Create backup of current file before replacing
        if os.path.exists(HISTORY_FILE):
            backup_file = HISTORY_FILE + ".backup"
            try:
                import shutil
                shutil.copy2(HISTORY_FILE, backup_file)
            except Exception as e:
                logger.warning(f"Failed to create backup: {e}")
        
        # Atomically rename temp file to actual file
        os.replace(temp_file, HISTORY_FILE)
    except Exception as e:
        logger.error(f"Failed to save history: {e}")
        # Clean up temp file if it exists
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception:
                pass


def _append_exchange(user_message, assistant_message, thread_id: Optional[str] = None):
    if not isinstance(user_message, str):
        return
    if not isinstance(assistant_message, str):
        assistant_message = str(assistant_message)

    normalized_thread_id = _normalize_thread_id(thread_id)
    ensure_thread(normalized_thread_id)
    append_thread_exchange(normalized_thread_id, user_message, assistant_message)

    with _HISTORY_LOCK:
        global CONVERSATION_HISTORY
        if normalized_thread_id == DEFAULT_THREAD_ID:
            CONVERSATION_HISTORY.append({"role": "user", "content": user_message})
            CONVERSATION_HISTORY.append({"role": "assistant", "content": assistant_message})

            max_messages = MAX_HISTORY_EXCHANGES * 2
            if len(CONVERSATION_HISTORY) > max_messages:
                CONVERSATION_HISTORY = CONVERSATION_HISTORY[-max_messages:]

            _save_history(CONVERSATION_HISTORY)
        
        # Policy-driven memory summarization cadence.
        summarize_every = max(1, int(MEMORY_SUMMARIZE_EVERY_EXCHANGES))
        summary_window_exchanges = max(1, int(MEMORY_SUMMARY_WINDOW_EXCHANGES))
        history_for_thread = get_thread_history(
            normalized_thread_id,
            limit_messages=max(
                summary_window_exchanges * 2,
                MEMORY_MAX_CONTEXT_MESSAGES,
            ),
        )
        if len(history_for_thread) >= summary_window_exchanges * 2 and (
            (len(history_for_thread) // 2) % summarize_every == 0
        ):
            recent_conversation = history_for_thread[-(summary_window_exchanges * 2) :]

            # Store asynchronously to avoid blocking the response
            def _async_store():
                try:
                    summarize_and_store(
                        recent_conversation,
                        thread_id=normalized_thread_id,
                        scope="global",
                    )
                except Exception as e:
                    logger.warning(f"Failed to store memory: {e}")
            
            threading.Thread(target=_async_store, daemon=True).start()
            logger.info(
                "Triggered async memory storage",
                extra={"thread_id": normalized_thread_id, "messages": len(recent_conversation)},
            )


def _get_history_snapshot(thread_id: Optional[str] = None):
    normalized_thread_id = _normalize_thread_id(thread_id)
    db_history = get_thread_history(normalized_thread_id, limit_messages=MEMORY_MAX_CONTEXT_MESSAGES)
    if db_history:
        return db_history
    with _HISTORY_LOCK:
        return [dict(item) for item in CONVERSATION_HISTORY]


def _cleanup_old_history_files():
    """Remove old backup and temp files from history directory"""
    try:
        cutoff_time = time.time() - (MAX_HISTORY_AGE_DAYS * 24 * 3600)
        for filename in os.listdir(HISTORY_DIR):
            if filename.startswith("history.json") and filename != "history.json":
                filepath = os.path.join(HISTORY_DIR, filename)
                try:
                    if os.path.getmtime(filepath) < cutoff_time:
                        os.remove(filepath)
                        logger.info(f"Removed old history file: {filename}")
                except Exception as e:
                    logger.warning(f"Failed to remove old file {filename}: {e}")
    except Exception as e:
        logger.error(f"History cleanup failed: {e}")


def _background_history_cleanup():
    """Background thread to periodically clean up old history files"""
    while not _history_cleanup_stop_event.wait(timeout=86400):  # Run daily
        try:
            _cleanup_old_history_files()
        except Exception:
            pass


def start_history_cleanup_thread():
    """Start the background history cleanup thread"""
    global _history_cleanup_thread
    if _history_cleanup_thread is None or not _history_cleanup_thread.is_alive():
        _history_cleanup_stop_event.clear()
        _history_cleanup_thread = threading.Thread(target=_background_history_cleanup, daemon=True)
        _history_cleanup_thread.start()


def stop_history_cleanup_thread():
    """Stop the background history cleanup thread"""
    _history_cleanup_stop_event.set()
    if _history_cleanup_thread is not None:
        _history_cleanup_thread.join(timeout=5)


CONVERSATION_HISTORY = _load_history()

# Initialize auth on startup
@app.on_event("startup")
async def startup_event():
    try:
        from backend.memory import init_memory_schema
        from backend.knowledge import init_knowledge_schema
    except ImportError:
        try:
            from memory import init_memory_schema
            from knowledge import init_knowledge_schema
        except ImportError:
            from .memory import init_memory_schema
            from .knowledge import init_knowledge_schema

    init_memory_schema()
    init_knowledge_schema()
    ensure_thread(DEFAULT_THREAD_ID)
    migrated = migrate_history_file(CONVERSATION_HISTORY, thread_id=DEFAULT_THREAD_ID)
    if migrated:
        logger.info("Migrated legacy history into thread store", extra={"messages": migrated})
    init_auth()
    start_history_cleanup_thread()
    
    # Import and start rate limit cleanup
    try:
        from backend.rate_limit import start_cleanup_thread as start_rate_limit_cleanup
    except ImportError:
        try:
            from rate_limit import start_cleanup_thread as start_rate_limit_cleanup
        except ImportError:
            from .rate_limit import start_cleanup_thread as start_rate_limit_cleanup
    start_rate_limit_cleanup()
    
    # Redis disabled — using in-memory rate limiting only
    logger.info("Rate limiting: in-memory mode (Redis disabled)")
    
    logger.info("Jarvis backend started")


@app.on_event("shutdown")
async def shutdown_event():
    """Handle graceful shutdown"""
    logger.info("Jarvis backend shutting down gracefully...")
    
    # Stop background cleanup threads
    logger.info("Stopping cleanup threads...")
    stop_history_cleanup_thread()
    
    # Import and stop rate limit cleanup
    try:
        from backend.rate_limit import stop_cleanup_thread as stop_rate_limit_cleanup
    except ImportError:
        try:
            from rate_limit import stop_cleanup_thread as stop_rate_limit_cleanup
        except ImportError:
            from .rate_limit import stop_cleanup_thread as stop_rate_limit_cleanup
    stop_rate_limit_cleanup()
    
    # Import and stop auth cleanup
    try:
        from backend.auth import stop_cleanup_thread as stop_auth_cleanup
    except ImportError:
        try:
            from auth import stop_cleanup_thread as stop_auth_cleanup
        except ImportError:
            from .auth import stop_cleanup_thread as stop_auth_cleanup
    stop_auth_cleanup()
    
    # Give a small window for in-flight requests to complete
    logger.info("Waiting for in-flight requests to complete...")
    await asyncio.sleep(2)
    
    logger.info("Jarvis backend shutdown complete")


class Query(BaseModel):
    prompt: str
    history: Optional[List[Dict[str, str]]] = None
    thread_id: Optional[str] = None
    include_global_memory: bool = True


class PinMemoryRequest(BaseModel):
    pinned: bool = True

@app.get("/")
def root():
    return {
        "message": "Jarvis AI Assistant API",
        "version": "1.0.0",
        "endpoints": {
            "ui": "/static/",
            "query": "/query",
            "stream": "/stream",
            "health": "/health"
        }
    }

@app.get("/health")
def health(deep: bool = False):
    """
    Health check endpoint.
    
    Args:
        deep: If True, performs deep health check (slower but comprehensive)
              If False, performs shallow health check (fast, for load balancers)
    
    Returns:
        Health status with appropriate HTTP status code
    """
    if deep:
        result = deep_health_check()
    else:
        result = shallow_health_check()
    
    # Set HTTP status code based on health status
    status_code = 200
    if result.get("status") == "unhealthy":
        status_code = 503  # Service Unavailable
    elif result.get("status") == "degraded":
        status_code = 200  # Still OK, but with warnings
    
    from fastapi.responses import JSONResponse
    return JSONResponse(content=result, status_code=status_code)

@app.get("/metrics")
async def metrics_endpoint():
    """
    Prometheus metrics endpoint.
    Returns metrics in Prometheus text format.
    """
    return get_metrics()

@app.get("/csrf-token")
async def get_csrf_token(authenticated: bool = Depends(verify_auth)):
    """
    Get a CSRF token for making state-changing requests.
    Requires authentication.
    """
    token = generate_csrf_token()
    return {
        "csrf_token": token,
        "expires_in": 3600  # 1 hour
    }


@app.get("/threads")
async def get_threads(
    limit: int = 50,
    authenticated: bool = Depends(verify_auth),
):
    """List known chat threads for UI/TUI selection."""
    return {"threads": list_threads(limit=limit)}


@app.get("/threads/{thread_id}/history")
async def get_thread_messages(
    thread_id: str,
    limit: int = MEMORY_MAX_CONTEXT_MESSAGES,
    authenticated: bool = Depends(verify_auth),
):
    normalized = _normalize_thread_id(thread_id)
    return {
        "thread_id": normalized,
        "history": get_thread_history(normalized, limit_messages=limit),
    }


@app.get("/memory")
async def get_memory_items(
    limit: int = 50,
    thread_id: Optional[str] = None,
    scope: Optional[str] = None,
    authenticated: bool = Depends(verify_auth),
):
    return {
        "items": list_memory_items(limit=limit, thread_id=thread_id, scope=scope),
    }


@app.post("/memory/{memory_id}/pin")
async def pin_memory_item(
    memory_id: int,
    request: PinMemoryRequest,
    authenticated: bool = Depends(verify_auth),
    csrf_valid: bool = Depends(validate_csrf_token),
):
    ok = set_memory_pinned(memory_id, request.pinned)
    return {"ok": ok, "memory_id": memory_id, "pinned": request.pinned}


@app.delete("/memory/{memory_id}")
async def remove_memory_item(
    memory_id: int,
    authenticated: bool = Depends(verify_auth),
    csrf_valid: bool = Depends(validate_csrf_token),
):
    ok = delete_memory_item(memory_id)
    return {"ok": ok, "memory_id": memory_id}


@app.post("/memory/prune")
async def prune_memory_items(
    max_items: int = 1000,
    authenticated: bool = Depends(verify_auth),
    csrf_valid: bool = Depends(validate_csrf_token),
):
    deleted = prune_unpinned_memories(max_items=max_items)
    return {"deleted": deleted, "max_items": max_items}

@app.get("/static/")
async def serve_ui():
    if not os.path.exists(INDEX_FILE):
        return HTMLResponse("<h1>Error: UI not found</h1>")
    with open(INDEX_FILE, 'r') as f:
        return HTMLResponse(content=f.read())

@app.post("/query")
async def query_agent(
    query: Query,
    request: Request,
    authenticated: bool = Depends(verify_auth),
    csrf_valid: bool = Depends(validate_csrf_token)
):
    """Asynchronous query endpoint with authentication, rate limiting, and CSRF protection"""
    await check_rate_limit(request)
    
    logger.info("Query received", extra={"prompt_len": len(query.prompt)})
    system_prompt = build_system_prompt()
    thread_id = _normalize_thread_id(query.thread_id)
    request_history = (
        _normalize_history(query.history)
        if query.history is not None
        else _get_history_snapshot(thread_id=thread_id)
    )
    
    try:
        # Run agent in thread to avoid blocking the event loop
        response = await asyncio.to_thread(
            run_agent,
            query.prompt,
            system_prompt,
            history=request_history,
            thread_id=thread_id,
            include_global_memory=query.include_global_memory,
        )
        _append_exchange(query.prompt, response, thread_id=thread_id)
        
        # Add rate limit headers
        requests_made, remaining, reset_in = get_rate_limit_status(request)
        
        return {
            "response": response,
            "thread_id": thread_id,
            "rate_limit": {
                "remaining": remaining,
                "reset_in": reset_in
            }
        }
    except Exception as e:
        logger.error("Query error", extra={"error": str(e)})
        raise


@app.post("/stream")
async def stream_agent(
    query: Query,
    request: Request,
    authenticated: bool = Depends(verify_auth),
    csrf_valid: bool = Depends(validate_csrf_token)
):
    """Streaming query endpoint with authentication, rate limiting, and CSRF protection"""
    await check_rate_limit(request)
    
    logger.info("Stream query received", extra={"prompt_len": len(query.prompt)})
    system_prompt = build_system_prompt()
    event_queue = queue.Queue()
    thread_id = _normalize_thread_id(query.thread_id)
    request_history = (
        _normalize_history(query.history)
        if query.history is not None
        else _get_history_snapshot(thread_id=thread_id)
    )
    result_holder = {"response": ""}

    def on_event(event_type: str, data: dict):
        event = {"type": event_type}
        if isinstance(data, dict):
            event.update(data)
        event_queue.put(event)

    def run_agent_thread():
        try:
            result_holder["response"] = run_agent(
                query.prompt,
                system_prompt,
                on_event=on_event,
                history=request_history,
                thread_id=thread_id,
                include_global_memory=query.include_global_memory,
            )
        except Exception as exc:
            logger.error("Agent error", extra={"error": str(exc)})
            result_holder["response"] = f"LLM error: {str(exc)}"
            on_event("error", {"message": str(exc)})
        finally:
            _append_exchange(query.prompt, result_holder["response"], thread_id=thread_id)
            event_queue.put(None)

    async def event_generator():
        worker_task = asyncio.create_task(asyncio.to_thread(run_agent_thread))
        try:
            while True:
                event = await asyncio.to_thread(event_queue.get)
                if event is None:
                    break
                yield f"data: {json.dumps(event, ensure_ascii=True)}\n\n"
        finally:
            await worker_task

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )

@app.post("/stt")
async def speech_to_text(file: UploadFile = File(...)):
    """Transcribe audio file to text using local Whisper model"""
    if not ENABLE_STT:
        return {"text": "", "success": False, "error": "STT is disabled"}

    try:
        import whisper
        import tempfile
        
        logger.info(f"[STT] Received file: {file.filename}")
        
        # Read audio file
        contents = await file.read()
        logger.info(f"[STT] Read {len(contents)} bytes from file")
        
        # Write to temporary file (Whisper accepts various formats)
        suffix = os.path.splitext(file.filename)[1] if file.filename else ".wav"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(contents)
            tmp_path = tmp.name
        
        logger.info(f"[STT] Saved to temp file: {tmp_path}")
        
        try:
            # Load Whisper model (base model is a good balance of speed/accuracy)
            # Model is cached after first load
            model = whisper.load_model("base")
            logger.info("[STT] Whisper model loaded")
            
            # Transcribe using local inference
            result = model.transcribe(tmp_path, fp16=False)
            text = result["text"].strip()
            
            logger.info(f"[STT] Transcription successful: {text}")
            return {"text": text, "success": True}
        except Exception as e:
            logger.error(f"[STT] Transcription failed: {str(e)}")
            return {"text": "", "success": False, "error": f"Transcription error: {str(e)}"}
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
                logger.info("[STT] Cleaned up temp file")
    except ImportError as e:
        logger.error(f"[STT] ImportError: {str(e)}")
        return {"text": "", "success": False, "error": "Whisper library not installed"}
    except Exception as e:
        logger.error(f"[STT] Exception: {str(e)}")
        return {"text": "", "success": False, "error": str(e)}
