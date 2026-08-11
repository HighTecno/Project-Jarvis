"""Long-term memory system using PostgreSQL+pgvector ONLY. SQLite is not supported. This module will not start unless backend/memory_pg.py is present and importable."""
import json
import os
from typing import List, Dict, Any, Optional
from datetime import datetime

try:
    from backend.config import (
        MEMORY_ENABLED,
        MEMORY_TOP_K,
        DEFAULT_THREAD_ID,
        EMBED_MODEL,
        OLLAMA_ENDPOINT,
        OLLAMA_MODEL,
        POSTGRES_URL,
    )
    from backend.logger import get_logger
except ImportError:
    try:
        from config import (
            MEMORY_ENABLED,
            MEMORY_TOP_K,
            DEFAULT_THREAD_ID,
            EMBED_MODEL,
            OLLAMA_ENDPOINT,
            OLLAMA_MODEL,
            POSTGRES_URL,
        )
        from logger import get_logger
    except ImportError:
        from .config import (
            MEMORY_ENABLED,
            MEMORY_TOP_K,
            DEFAULT_THREAD_ID,
            EMBED_MODEL,
            OLLAMA_ENDPOINT,
            OLLAMA_MODEL,
            POSTGRES_URL,
        )
        from .logger import get_logger

logger = get_logger("memory")

# --- Provider dispatch ---
# FORCE: Only allow PostgreSQL + pgvector. Abort if unavailable.
try:
    from backend.memory_pg import (
        init_memory_schema,
        ensure_thread,
        append_thread_exchange,
        get_thread_history,
        list_threads,
        migrate_history_file,
        store_memory,
        retrieve_memories,
        summarize_and_store,
        list_memory_items,
        set_memory_pinned,
        delete_memory_item,
        prune_unpinned_memories,
        get_embedding,
    )
    logger.info("Memory provider: PostgreSQL + pgvector (forced, no SQLite fallback)")
except ImportError as e:
    logger.critical("FATAL: memory_pg (Postgres/pgvector) not found! Cannot start memory system.")
    raise SystemExit("Project-Jarvis requires backend/memory_pg.py for Postgres+pgvector -- aborting.")

# Initialize schema on module import (if enabled)
try:
    init_memory_schema()
except Exception as e:
    logger.critical(f"FATAL: Could not initialize Postgres/pgvector memory schema: {e}")
    raise SystemExit(str(e))
