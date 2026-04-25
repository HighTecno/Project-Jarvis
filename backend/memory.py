"""Long-term memory system using SQLite with vector similarity search"""
import json
import os
import sqlite3
import threading
from typing import List, Dict, Any, Optional
from datetime import datetime

try:
    from backend.config import (
        MEMORY_ENABLED,
        MEMORY_TOP_K,
        MEMORY_DB_PATH,
        DEFAULT_THREAD_ID,
        EMBED_MODEL,
        OLLAMA_ENDPOINT,
        OLLAMA_MODEL,
    )
    from backend.logger import get_logger
except ImportError:
    try:
        from config import (
            MEMORY_ENABLED,
            MEMORY_TOP_K,
            MEMORY_DB_PATH,
            DEFAULT_THREAD_ID,
            EMBED_MODEL,
            OLLAMA_ENDPOINT,
            OLLAMA_MODEL,
        )
        from logger import get_logger
    except ImportError:
        from .config import (
            MEMORY_ENABLED,
            MEMORY_TOP_K,
            MEMORY_DB_PATH,
            DEFAULT_THREAD_ID,
            EMBED_MODEL,
            OLLAMA_ENDPOINT,
            OLLAMA_MODEL,
        )
        from .logger import get_logger

logger = get_logger("memory")

# Lazy imports for graceful degradation
_requests = None
_db_lock = threading.Lock()


def _init_requests():
    """Lazy initialization of requests library"""
    global _requests
    
    if _requests is None:
        try:
            import requests
            _requests = requests
        except ImportError:
            logger.warning("requests not available - memory system disabled")
            return False
    
    return True


def _get_connection():
    """Get a database connection"""
    if not MEMORY_ENABLED:
        return None
    
    try:
        # Ensure directory exists
        db_dir = os.path.dirname(MEMORY_DB_PATH)
        os.makedirs(db_dir, exist_ok=True)
        
        # Connect to SQLite
        conn = sqlite3.connect(MEMORY_DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to SQLite: {e}")
        return None


def _normalize_thread_id(thread_id: Optional[str]) -> str:
    if isinstance(thread_id, str) and thread_id.strip():
        return thread_id.strip()
    return DEFAULT_THREAD_ID


def init_memory_schema():
    """Initialize the database schema if it doesn't exist"""
    if not MEMORY_ENABLED:
        logger.info("Memory system disabled by config")
        return
    
    conn = _get_connection()
    if not conn:
        logger.warning("Could not initialize memory schema - no database connection")
        return
    
    try:
        with _db_lock:
            cursor = conn.cursor()
            
            # Create memory table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS jarvis_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT DEFAULT (datetime('now')),
                    type TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    content TEXT NOT NULL,
                    embedding TEXT,
                    tags TEXT
                )
            """)

            # New unified chat-aware memory tables.
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_threads (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY(thread_id) REFERENCES chat_threads(id)
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_messages_thread_created
                ON chat_messages (thread_id, created_at DESC, id DESC)
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS memory_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    legacy_memory_id INTEGER UNIQUE,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                    type TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    content TEXT NOT NULL,
                    embedding TEXT,
                    tags TEXT,
                    scope TEXT NOT NULL DEFAULT 'global',
                    thread_id TEXT,
                    source TEXT NOT NULL DEFAULT 'conversation',
                    pinned INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY(thread_id) REFERENCES chat_threads(id)
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_memory_items_scope_thread
                ON memory_items (scope, thread_id, created_at DESC)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_memory_items_type_created
                ON memory_items (type, created_at DESC)
            """)
            
            # Create indexes
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_memory_type 
                ON jarvis_memory (type)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_memory_created 
                ON jarvis_memory (created_at DESC)
            """)

            # Ensure default legacy thread exists for compatibility.
            cursor.execute(
                """
                INSERT OR IGNORE INTO chat_threads (id, title, created_at, updated_at)
                VALUES (?, ?, datetime('now'), datetime('now'))
                """,
                (DEFAULT_THREAD_ID, "Legacy default thread"),
            )

            # One-time, idempotent migration from legacy jarvis_memory table.
            cursor.execute(
                """
                INSERT INTO memory_items (
                    legacy_memory_id, created_at, updated_at, type, summary, content,
                    embedding, tags, scope, thread_id, source, pinned
                )
                SELECT
                    jm.id,
                    jm.created_at,
                    jm.created_at,
                    jm.type,
                    jm.summary,
                    jm.content,
                    jm.embedding,
                    jm.tags,
                    'global',
                    ?,
                    'legacy_jarvis_memory',
                    0
                FROM jarvis_memory jm
                LEFT JOIN memory_items mi ON mi.legacy_memory_id = jm.id
                WHERE mi.legacy_memory_id IS NULL
                """,
                (DEFAULT_THREAD_ID,),
            )
            
            conn.commit()
            logger.info(f"Memory schema initialized at {MEMORY_DB_PATH}")
    except Exception as e:
        logger.error(f"Failed to initialize memory schema: {e}")
        conn.rollback()
    finally:
        conn.close()


def ensure_thread(thread_id: Optional[str], title: Optional[str] = None) -> str:
    normalized = _normalize_thread_id(thread_id)
    conn = _get_connection()
    if not conn:
        return normalized

    try:
        with _db_lock:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR IGNORE INTO chat_threads (id, title, created_at, updated_at)
                VALUES (?, ?, datetime('now'), datetime('now'))
                """,
                (normalized, title or normalized),
            )
            cursor.execute(
                "UPDATE chat_threads SET updated_at = datetime('now') WHERE id = ?",
                (normalized,),
            )
            conn.commit()
    except Exception as e:
        logger.warning(f"Failed to ensure thread {normalized}: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        conn.close()
    return normalized


def append_thread_exchange(thread_id: Optional[str], user_message: str, assistant_message: str) -> bool:
    normalized = ensure_thread(thread_id)
    conn = _get_connection()
    if not conn:
        return False

    try:
        with _db_lock:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO chat_messages (thread_id, role, content, created_at) VALUES (?, 'user', ?, datetime('now'))",
                (normalized, user_message),
            )
            cursor.execute(
                "INSERT INTO chat_messages (thread_id, role, content, created_at) VALUES (?, 'assistant', ?, datetime('now'))",
                (normalized, assistant_message),
            )
            cursor.execute(
                "UPDATE chat_threads SET updated_at = datetime('now') WHERE id = ?",
                (normalized,),
            )
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Failed to append thread exchange for {normalized}: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        return False
    finally:
        conn.close()


def get_thread_history(thread_id: Optional[str], limit_messages: int = 100) -> List[Dict[str, str]]:
    normalized = _normalize_thread_id(thread_id)
    conn = _get_connection()
    if not conn:
        return []

    try:
        with _db_lock:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT role, content
                FROM (
                    SELECT role, content, id
                    FROM chat_messages
                    WHERE thread_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                ) recent
                ORDER BY id ASC
                """,
                (normalized, max(1, int(limit_messages))),
            )
            rows = cursor.fetchall()
        return [{"role": row["role"], "content": row["content"]} for row in rows]
    except Exception as e:
        logger.error(f"Failed to get thread history for {normalized}: {e}")
        return []
    finally:
        conn.close()


def list_threads(limit: int = 50) -> List[Dict[str, Any]]:
    conn = _get_connection()
    if not conn:
        return []
    try:
        with _db_lock:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, title, created_at, updated_at
                FROM chat_threads
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (max(1, int(limit)),),
            )
            rows = cursor.fetchall()
        return [
            {
                "id": row["id"],
                "title": row["title"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]
    except Exception as e:
        logger.warning(f"Failed to list threads: {e}")
        return []
    finally:
        conn.close()


def migrate_history_file(history: List[Dict[str, str]], thread_id: Optional[str] = None) -> int:
    """Backfill normalized role/content history into thread storage once."""
    normalized = _normalize_thread_id(thread_id)
    if not isinstance(history, list) or not history:
        ensure_thread(normalized)
        return 0

    conn = _get_connection()
    if not conn:
        return 0

    inserted = 0
    try:
        with _db_lock:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) AS count FROM chat_messages WHERE thread_id = ?", (normalized,))
            row = cursor.fetchone()
            if row and int(row["count"]) > 0:
                return 0

            cursor.execute(
                """
                INSERT OR IGNORE INTO chat_threads (id, title, created_at, updated_at)
                VALUES (?, ?, datetime('now'), datetime('now'))
                """,
                (normalized, normalized),
            )
            for item in history:
                role = item.get("role") if isinstance(item, dict) else None
                content = item.get("content") if isinstance(item, dict) else None
                if role not in {"user", "assistant"} or not isinstance(content, str):
                    continue
                cursor.execute(
                    "INSERT INTO chat_messages (thread_id, role, content, created_at) VALUES (?, ?, ?, datetime('now'))",
                    (normalized, role, content),
                )
                inserted += 1

            cursor.execute(
                "UPDATE chat_threads SET updated_at = datetime('now') WHERE id = ?",
                (normalized,),
            )
            conn.commit()
    except Exception as e:
        logger.warning(f"Failed to migrate history file to thread {normalized}: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        return 0
    finally:
        conn.close()
    return inserted


def list_memory_items(
    limit: int = 50,
    thread_id: Optional[str] = None,
    scope: Optional[str] = None,
) -> List[Dict[str, Any]]:
    conn = _get_connection()
    if not conn:
        return []
    try:
        with _db_lock:
            cursor = conn.cursor()
            query = """
                SELECT id, created_at, updated_at, type, summary, tags, scope, thread_id, source, pinned
                FROM memory_items
                WHERE 1=1
            """
            params: List[Any] = []
            if scope in {"global", "thread"}:
                query += " AND scope = ?"
                params.append(scope)
            if thread_id:
                query += " AND thread_id = ?"
                params.append(_normalize_thread_id(thread_id))
            query += " ORDER BY pinned DESC, created_at DESC LIMIT ?"
            params.append(max(1, int(limit)))
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
        return [
            {
                "id": int(row["id"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "type": row["type"],
                "summary": row["summary"],
                "tags": row["tags"],
                "scope": row["scope"],
                "thread_id": row["thread_id"],
                "source": row["source"],
                "pinned": bool(row["pinned"]),
            }
            for row in rows
        ]
    except Exception as e:
        logger.warning(f"Failed to list memory items: {e}")
        return []
    finally:
        conn.close()


def set_memory_pinned(memory_id: int, pinned: bool) -> bool:
    conn = _get_connection()
    if not conn:
        return False
    try:
        with _db_lock:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE memory_items SET pinned = ?, updated_at = datetime('now') WHERE id = ?",
                (1 if pinned else 0, int(memory_id)),
            )
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        logger.warning(f"Failed to set pin for memory {memory_id}: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        return False
    finally:
        conn.close()


def delete_memory_item(memory_id: int) -> bool:
    conn = _get_connection()
    if not conn:
        return False
    try:
        with _db_lock:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM memory_items WHERE id = ?", (int(memory_id),))
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        logger.warning(f"Failed to delete memory item {memory_id}: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        return False
    finally:
        conn.close()


def prune_unpinned_memories(max_items: int = 1000) -> int:
    """Keep newest max_items memories, preserving pinned rows."""
    conn = _get_connection()
    if not conn:
        return 0
    try:
        with _db_lock:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) AS count FROM memory_items WHERE pinned = 0")
            row = cursor.fetchone()
            total_unpinned = int(row["count"]) if row else 0
            overflow = total_unpinned - max(0, int(max_items))
            if overflow <= 0:
                return 0
            cursor.execute(
                """
                DELETE FROM memory_items
                WHERE id IN (
                    SELECT id FROM memory_items
                    WHERE pinned = 0
                    ORDER BY created_at ASC
                    LIMIT ?
                )
                """,
                (overflow,),
            )
            deleted = cursor.rowcount
            conn.commit()
            return max(0, int(deleted))
    except Exception as e:
        logger.warning(f"Failed to prune memories: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        return 0
    finally:
        conn.close()


def get_embedding(text: str) -> Optional[List[float]]:
    """
    Get embedding vector for text using Ollama's embedding endpoint.
    
    Args:
        text: Text to embed
    
    Returns:
        List of floats representing the embedding vector, or None on error
    """
    if not _init_requests():
        return None
    
    def _extract_embedding(data: Dict[str, Any]) -> Optional[List[float]]:
        embedding = data.get("embedding")
        if isinstance(embedding, list) and embedding:
            return embedding

        embeddings = data.get("embeddings")
        if isinstance(embeddings, list) and embeddings:
            first = embeddings[0]
            if isinstance(first, list) and first:
                return first

        logger.error("No embedding vector in Ollama response")
        return None

    def _is_missing_model_404(response: Any) -> bool:
        if getattr(response, "status_code", None) != 404:
            return False

        try:
            error = response.json().get("error", "")
        except Exception:
            return False

        return isinstance(error, str) and "model" in error.lower() and "not found" in error.lower()

    def _is_endpoint_unavailable_status(status_code: Any) -> bool:
        return status_code in {404, 405, 501}

    def _request_embedding_api(path: str, model: str, payload_key: str) -> Any:
        return _requests.post(
            f"{OLLAMA_ENDPOINT}{path}",
            json={
                "model": model,
                payload_key: text
            },
            timeout=30
        )

    try:
        models_to_try = [EMBED_MODEL]
        if OLLAMA_MODEL and OLLAMA_MODEL != EMBED_MODEL:
            models_to_try.append(OLLAMA_MODEL)

        modern_endpoint_missing = False
        for model in models_to_try:
            response = _request_embedding_api("/api/embed", model, "input")

            if _is_endpoint_unavailable_status(response.status_code):
                if response.status_code == 404 and _is_missing_model_404(response):
                    if model == EMBED_MODEL and OLLAMA_MODEL and OLLAMA_MODEL != EMBED_MODEL:
                        logger.warning(
                            f"Embedding model '{EMBED_MODEL}' not found; falling back to '{OLLAMA_MODEL}'"
                        )
                    continue

                modern_endpoint_missing = True
                break

            response.raise_for_status()
            return _extract_embedding(response.json())

        if not modern_endpoint_missing:
            return None

        # Backward compatibility for older Ollama versions.
        for model in models_to_try:
            legacy_response = _request_embedding_api("/api/embeddings", model, "prompt")

            if legacy_response.status_code == 404 and _is_missing_model_404(legacy_response):
                continue

            if _is_endpoint_unavailable_status(legacy_response.status_code):
                return None

            legacy_response.raise_for_status()
            return _extract_embedding(legacy_response.json())

        return None
    except Exception as e:
        logger.error(f"Failed to get embedding: {e}")
        return None


def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Calculate cosine similarity between two vectors"""
    try:
        import math
        
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = math.sqrt(sum(a * a for a in vec1))
        magnitude2 = math.sqrt(sum(b * b for b in vec2))
        
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        
        return dot_product / (magnitude1 * magnitude2)
    except Exception as e:
        logger.error(f"Failed to calculate similarity: {e}")
        return 0.0


def store_memory(
    summary: str,
    content: str,
    mem_type: str = "conversation",
    tags: Optional[List[str]] = None,
    thread_id: Optional[str] = None,
    scope: str = "global",
    source: str = "conversation",
) -> bool:
    """
    Store a memory with its embedding in the database.
    
    Args:
        summary: Brief summary of the memory
        content: Full content to store
        mem_type: Type of memory (conversation, decision, incident, etc.)
        tags: Optional list of tags for categorization
    
    Returns:
        True if successful, False otherwise
    """
    if not MEMORY_ENABLED:
        return False
    
    conn = _get_connection()
    if not conn:
        logger.warning("Cannot store memory - no database connection")
        return False
    
    try:
        normalized_scope = scope if scope in {"global", "thread"} else "global"
        normalized_thread_id = _normalize_thread_id(thread_id)
        if normalized_scope == "thread" or thread_id:
            ensure_thread(normalized_thread_id)

        # Get embedding for the summary (used for retrieval)
        embedding = get_embedding(summary)
        if embedding is None:
            logger.warning("Failed to get embedding, storing without it")
            embedding_json = None
        else:
            embedding_json = json.dumps(embedding)
        
        # Store in database
        with _db_lock:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO memory_items (
                    type, summary, content, embedding, tags, scope, thread_id, source, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    mem_type,
                    summary,
                    content,
                    embedding_json,
                    json.dumps(tags or []),
                    normalized_scope,
                    normalized_thread_id,
                    source,
                ),
            )
            memory_id = cursor.lastrowid
            conn.commit()
            
        logger.info(f"Stored memory {memory_id}: {summary[:50]}...")
        return True
        
    except Exception as e:
        logger.error(f"Failed to store memory: {e}")
        try:
            conn.rollback()
        except:
            pass
        return False
    finally:
        conn.close()


def retrieve_memories(
    query_text: str,
    top_k: Optional[int] = None,
    mem_type: Optional[str] = None,
    thread_id: Optional[str] = None,
    include_global: bool = True,
) -> List[str]:
    """
    Retrieve the most semantically similar memories.
    
    Args:
        query_text: Query to search for
        top_k: Number of results to return (defaults to MEMORY_TOP_K)
        mem_type: Optional filter by memory type
    
    Returns:
        List of memory content strings, or empty list on error
    """
    if not MEMORY_ENABLED:
        return []
    
    if top_k is None:
        top_k = MEMORY_TOP_K
    
    conn = _get_connection()
    if not conn:
        logger.warning("Cannot retrieve memories - no database connection")
        return []
    
    try:
        # Get embedding for query
        query_embedding = get_embedding(query_text)
        if query_embedding is None:
            logger.warning("Failed to get query embedding")
            return []
        
        # Fetch all memories with embeddings
        with _db_lock:
            cursor = conn.cursor()
            normalized_thread = _normalize_thread_id(thread_id)
            if mem_type and thread_id and include_global:
                cursor.execute(
                    """
                    SELECT id, content, summary, created_at, embedding
                    FROM memory_items
                    WHERE type = ? AND embedding IS NOT NULL
                      AND (scope = 'global' OR thread_id = ?)
                    ORDER BY created_at DESC
                    LIMIT 500
                    """,
                    (mem_type, normalized_thread),
                )
            elif mem_type and thread_id and not include_global:
                cursor.execute(
                    """
                    SELECT id, content, summary, created_at, embedding
                    FROM memory_items
                    WHERE type = ? AND embedding IS NOT NULL
                      AND scope = 'thread' AND thread_id = ?
                    ORDER BY created_at DESC
                    LIMIT 500
                    """,
                    (mem_type, normalized_thread),
                )
            elif mem_type and not thread_id:
                cursor.execute(
                    """
                    SELECT id, content, summary, created_at, embedding
                    FROM memory_items
                    WHERE type = ? AND embedding IS NOT NULL AND scope = 'global'
                    ORDER BY created_at DESC
                    LIMIT 500
                    """,
                    (mem_type,),
                )
            elif thread_id and include_global:
                cursor.execute(
                    """
                    SELECT id, content, summary, created_at, embedding
                    FROM memory_items
                    WHERE embedding IS NOT NULL
                      AND (scope = 'global' OR thread_id = ?)
                    ORDER BY created_at DESC
                    LIMIT 500
                    """,
                    (normalized_thread,),
                )
            elif thread_id and not include_global:
                cursor.execute(
                    """
                    SELECT id, content, summary, created_at, embedding
                    FROM memory_items
                    WHERE embedding IS NOT NULL
                      AND scope = 'thread' AND thread_id = ?
                    ORDER BY created_at DESC
                    LIMIT 500
                    """,
                    (normalized_thread,),
                )
            else:
                cursor.execute(
                    """
                    SELECT id, content, summary, created_at, embedding
                    FROM memory_items
                    WHERE embedding IS NOT NULL AND scope = 'global'
                    ORDER BY created_at DESC
                    LIMIT 500
                    """
                )
            
            rows = cursor.fetchall()
        
        # Calculate similarities
        similarities = []
        for row in rows:
            try:
                stored_embedding = json.loads(row['embedding'])
                similarity = _cosine_similarity(query_embedding, stored_embedding)
                
                # Only include if similarity is reasonable (> 0.5 is fairly similar)
                if similarity > 0.5:
                    similarities.append({
                        'content': row['content'],
                        'summary': row['summary'],
                        'created_at': row['created_at'],
                        'similarity': similarity
                    })
            except Exception as e:
                logger.debug(f"Error processing memory {row['id']}: {e}")
                continue
        
        # Sort by similarity and take top_k
        similarities.sort(key=lambda x: x['similarity'], reverse=True)
        similarities = similarities[:top_k]
        
        # Format results
        memories = []
        for item in similarities:
            timestamp = item['created_at'][:16]  # YYYY-MM-DD HH:MM
            memories.append(f"[{timestamp}] {item['summary']}\n{item['content']}")
        
        logger.info(f"Retrieved {len(memories)} memories for query: {query_text[:50]}...")
        return memories
        
    except Exception as e:
        logger.error(f"Failed to retrieve memories: {e}")
        return []
    finally:
        conn.close()


def summarize_and_store(
    conversation: List[Dict[str, str]],
    thread_id: Optional[str] = None,
    scope: str = "global",
) -> bool:
    """
    Summarize a conversation and store it in memory.
    
    Args:
        conversation: List of {role, content} message dicts
    
    Returns:
        True if successful, False otherwise
    """
    if not MEMORY_ENABLED:
        return False
    
    if not conversation or len(conversation) < 2:
        return False
    
    if not _init_requests():
        return False
    
    try:
        # Build conversation text
        convo_text = "\n".join([
            f"{msg['role'].title()}: {msg['content'][:500]}"
            for msg in conversation
        ])
        
        # Call LLM to generate summary
        # Use a simple prompt to get concise summary
        summary_prompt = f"""Summarize this conversation in 1-2 sentences, focusing on the key topic and outcome:

{convo_text}

Summary:"""
        
        response = _requests.post(
            f"{OLLAMA_ENDPOINT}/api/generate",
            json={
                "model": "qwen2.5-coder:7b",  # Use same model as agent
                "prompt": summary_prompt,
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "num_predict": 100
                }
            },
            timeout=30
        )
        response.raise_for_status()
        summary = response.json().get("response", "").strip()
        
        if not summary:
            # Fallback: use first user message as summary
            user_msgs = [m['content'] for m in conversation if m['role'] == 'user']
            summary = user_msgs[0][:200] if user_msgs else "Conversation"
        
        # Store in memory
        return store_memory(
            summary=summary,
            content=convo_text,
            mem_type="conversation",
            tags=[],
            thread_id=thread_id,
            scope=scope,
            source="conversation_summary",
        )
        
    except Exception as e:
        logger.error(f"Failed to summarize and store: {e}")
        return False


# Initialize schema on module import (if enabled)
try:
    init_memory_schema()
except Exception as e:
    logger.warning(f"Memory initialization skipped: {e}")
