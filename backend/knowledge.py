"""Document knowledge base using SQLite with vector similarity search."""
import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

try:
    from backend.config import (
        KNOWLEDGE_ENABLED,
        KNOWLEDGE_CHUNK_SIZE,
        KNOWLEDGE_CHUNK_OVERLAP,
        KNOWLEDGE_MAX_FILE_MB,
        EMBED_MODEL,
        OLLAMA_MODEL,
        OLLAMA_ENDPOINT,
        MEMORY_DB_PATH,
    )
    from backend.logger import get_logger
except ImportError:
    try:
        from config import (
            KNOWLEDGE_ENABLED,
            KNOWLEDGE_CHUNK_SIZE,
            KNOWLEDGE_CHUNK_OVERLAP,
            KNOWLEDGE_MAX_FILE_MB,
            EMBED_MODEL,
            OLLAMA_MODEL,
            OLLAMA_ENDPOINT,
            MEMORY_DB_PATH,
        )
        from logger import get_logger
    except ImportError:
        from .config import (
            KNOWLEDGE_ENABLED,
            KNOWLEDGE_CHUNK_SIZE,
            KNOWLEDGE_CHUNK_OVERLAP,
            KNOWLEDGE_MAX_FILE_MB,
            EMBED_MODEL,
            OLLAMA_MODEL,
            OLLAMA_ENDPOINT,
            MEMORY_DB_PATH,
        )
        from .logger import get_logger

logger = get_logger("knowledge")

_requests = None
_db_lock = threading.Lock()
_embedding_api_unavailable = False
_SUPPORTED_EXTENSIONS = {
    ".txt",
    ".md",
    ".py",
    ".yaml",
    ".yml",
    ".json",
    ".sh",
    ".conf",
    ".ini",
    ".toml",
}


def _init_requests() -> bool:
    """Lazy initialization of requests library."""
    global _requests
    if _requests is None:
        try:
            import requests

            _requests = requests
        except ImportError:
            logger.warning("requests not available - knowledge system disabled")
            return False
    return True


def _get_connection():
    """Get a database connection."""
    if not KNOWLEDGE_ENABLED:
        return None

    try:
        db_dir = os.path.dirname(MEMORY_DB_PATH)
        os.makedirs(db_dir, exist_ok=True)
        conn = sqlite3.connect(MEMORY_DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to SQLite: {e}")
        return None


def _is_supported_file(path: Path) -> bool:
    return path.suffix.lower() in _SUPPORTED_EXTENSIONS


def _is_file_too_large(path: Path) -> bool:
    max_bytes = int(KNOWLEDGE_MAX_FILE_MB * 1024 * 1024)
    return path.stat().st_size > max_bytes


def _is_binary(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            sample = f.read(4096)
        return b"\x00" in sample
    except Exception:
        return False


def _read_text_file(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"Skipping unreadable file {path}: {e}")
        return None


def _chunk_text(text: str) -> List[str]:
    if not text:
        return []

    chunk_size = max(1, KNOWLEDGE_CHUNK_SIZE)
    overlap = max(0, min(KNOWLEDGE_CHUNK_OVERLAP, chunk_size - 1))
    step = max(1, chunk_size - overlap)

    chunks = []
    index = 0
    while index < len(text):
        chunk = text[index : index + chunk_size].strip()
        if chunk:
            chunks.append(chunk)
        index += step
    return chunks


def _get_embedding(text: str) -> Optional[np.ndarray]:
    if not _init_requests():
        return None
    if _embedding_api_unavailable:
        return None

    def _extract_embedding(data: Dict[str, Any]) -> Optional[np.ndarray]:
        embedding = data.get("embedding")
        if isinstance(embedding, list) and embedding:
            return np.asarray(embedding, dtype=np.float32)

        embeddings = data.get("embeddings")
        if isinstance(embeddings, list) and embeddings:
            first = embeddings[0]
            if isinstance(first, list) and first:
                return np.asarray(first, dtype=np.float32)

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
            json={"model": model, payload_key: text},
            timeout=30,
        )

    def _disable_embedding_api(reason: str) -> None:
        global _embedding_api_unavailable
        if _embedding_api_unavailable:
            return
        _embedding_api_unavailable = True
        logger.error(f"Disabling knowledge embeddings: {reason}")

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
            _disable_embedding_api(
                f"No available embedding model on {OLLAMA_ENDPOINT}; tried {', '.join(models_to_try)}"
            )
            return None

        # Backward compatibility for older Ollama versions.
        for model in models_to_try:
            legacy_response = _request_embedding_api("/api/embeddings", model, "prompt")

            if legacy_response.status_code == 404 and _is_missing_model_404(legacy_response):
                continue

            if _is_endpoint_unavailable_status(legacy_response.status_code):
                _disable_embedding_api(
                    f"Neither /api/embed nor /api/embeddings is available on {OLLAMA_ENDPOINT}"
                )
                return None

            legacy_response.raise_for_status()
            return _extract_embedding(legacy_response.json())

        _disable_embedding_api(
            f"No available embedding model on {OLLAMA_ENDPOINT}; tried {', '.join(models_to_try)}"
        )
        return None
    except Exception as e:
        error_text = str(e)
        if "404" in error_text or "405" in error_text or "501" in error_text or "Not Implemented" in error_text:
            _disable_embedding_api(f"Received persistent HTTP error from Ollama embedding API: {e}")
        else:
            logger.error(f"Failed to get embedding: {e}")
        return None


def _cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    try:
        denom = float(np.linalg.norm(vec1) * np.linalg.norm(vec2))
        if denom == 0.0:
            return 0.0
        return float(np.dot(vec1, vec2) / denom)
    except Exception as e:
        logger.error(f"Failed to calculate similarity: {e}")
        return 0.0


def init_knowledge_schema():
    """Initialize the knowledge schema if it doesn't exist."""
    if not KNOWLEDGE_ENABLED:
        logger.info("Knowledge system disabled by config")
        return

    conn = _get_connection()
    if not conn:
        logger.warning("Could not initialize knowledge schema - no database connection")
        return

    try:
        with _db_lock:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS knowledge_chunks (
                    id INTEGER PRIMARY KEY,
                    source TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    ingested_at TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_knowledge_source_chunk
                ON knowledge_chunks (source, chunk_index)
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_knowledge_source
                ON knowledge_chunks (source)
                """
            )
            conn.commit()
            logger.info(f"Knowledge schema initialized at {MEMORY_DB_PATH}")
    except Exception as e:
        logger.error(f"Failed to initialize knowledge schema: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        conn.close()


def ingest_file(path: str) -> Dict[str, Any]:
    """Chunk, embed, and store a single file in the knowledge base."""
    if not KNOWLEDGE_ENABLED:
        return {"status": "ok", "chunks": 0, "source": path}

    try:
        source_path = str(Path(path).resolve())
        file_path = Path(source_path)
        if not file_path.exists() or not file_path.is_file():
            return {"status": "error", "error": f"File not found: {path}"}
        if not _is_supported_file(file_path):
            return {"status": "error", "error": f"Unsupported file type: {path}"}
        if _is_file_too_large(file_path):
            return {"status": "error", "error": f"File too large: {path}"}
        if _is_binary(file_path):
            return {"status": "error", "error": f"Binary file skipped: {path}"}

        content = _read_text_file(file_path)
        if content is None:
            return {"status": "error", "error": f"Unreadable file: {path}"}

        chunks = _chunk_text(content)
        if not chunks:
            return {"status": "ok", "chunks": 0, "source": source_path}

        rows_to_insert = []
        for chunk_index, chunk in enumerate(chunks):
            embedding = _get_embedding(chunk)
            if embedding is None:
                return {"status": "error", "error": f"Failed embedding for file: {path}"}
            rows_to_insert.append(
                (
                    source_path,
                    chunk_index,
                    chunk,
                    embedding.astype(np.float32).tobytes(),
                    datetime.utcnow().isoformat(),
                )
            )

        conn = _get_connection()
        if not conn:
            return {"status": "error", "error": "No database connection"}

        try:
            with _db_lock:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM knowledge_chunks WHERE source = ?", (source_path,))
                cursor.executemany(
                    """
                    INSERT INTO knowledge_chunks (source, chunk_index, content, embedding, ingested_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    rows_to_insert,
                )
                conn.commit()
            return {"status": "ok", "chunks": len(rows_to_insert), "source": source_path}
        except Exception as e:
            logger.error(f"Failed to persist knowledge chunks for {path}: {e}")
            try:
                conn.rollback()
            except Exception:
                pass
            return {"status": "error", "error": str(e)}
        finally:
            conn.close()

    except Exception as e:
        logger.error(f"Failed to ingest file {path}: {e}")
        return {"status": "error", "error": str(e)}


def ingest_directory(root: str, recursive: bool = True) -> Dict[str, Any]:
    """Walk a directory and ingest all supported files."""
    if not KNOWLEDGE_ENABLED:
        return {"status": "ok", "files_ingested": 0, "chunks_total": 0, "errors": []}

    try:
        root_path = Path(root).resolve()
        if not root_path.exists() or not root_path.is_dir():
            return {"status": "error", "error": f"Directory not found: {root}"}

        files_ingested = 0
        chunks_total = 0
        errors = []

        iterator = root_path.rglob("*") if recursive else root_path.glob("*")
        for item in iterator:
            if not item.is_file():
                continue
            if not _is_supported_file(item):
                continue
            try:
                if _is_file_too_large(item) or _is_binary(item):
                    continue
            except Exception as e:
                logger.warning(f"Skipping unreadable file {item}: {e}")
                continue

            result = ingest_file(str(item))
            if result.get("status") == "ok":
                files_ingested += 1
                chunks_total += int(result.get("chunks", 0))
            else:
                message = result.get("error", "unknown error")
                if isinstance(message, str) and message.startswith("Unreadable file:"):
                    logger.warning(f"Skipping unreadable file {item}")
                    continue
                errors.append({"source": str(item), "error": message})

        return {
            "status": "ok",
            "files_ingested": files_ingested,
            "chunks_total": chunks_total,
            "errors": errors,
        }
    except Exception as e:
        logger.error(f"Failed to ingest directory {root}: {e}")
        return {"status": "error", "error": str(e)}


def search_knowledge(query: str, top_k: int = 5) -> List[str]:
    """Search the knowledge base and return relevant chunks."""
    if not KNOWLEDGE_ENABLED:
        return []

    conn = _get_connection()
    if not conn:
        logger.warning("Cannot search knowledge - no database connection")
        return []

    try:
        query_embedding = _get_embedding(query)
        if query_embedding is None:
            logger.warning("Failed to get query embedding for knowledge search")
            return []

        with _db_lock:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT source, chunk_index, content, embedding
                FROM knowledge_chunks
                ORDER BY ingested_at DESC
                LIMIT 5000
                """
            )
            rows = cursor.fetchall()

        similarities = []
        for row in rows:
            try:
                stored_embedding = np.frombuffer(row["embedding"], dtype=np.float32)
                similarity = _cosine_similarity(query_embedding, stored_embedding)
                similarities.append(
                    {
                        "source": row["source"],
                        "content": row["content"],
                        "chunk_index": row["chunk_index"],
                        "similarity": similarity,
                    }
                )
            except Exception as e:
                logger.warning(f"Error processing knowledge chunk: {e}")
                continue

        similarities.sort(key=lambda x: x["similarity"], reverse=True)
        top_results = similarities[: max(1, int(top_k))]
        return [f"Source: {item['source']}\n{item['content']}" for item in top_results]
    except Exception as e:
        logger.error(f"Failed to search knowledge: {e}")
        return []
    finally:
        conn.close()


def knowledge_stats() -> Dict[str, Any]:
    """Return basic knowledge base stats."""
    if not KNOWLEDGE_ENABLED:
        return {"total_files": 0, "total_chunks": 0, "enabled": False}

    conn = _get_connection()
    if not conn:
        return {"total_files": 0, "total_chunks": 0, "enabled": True}

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(DISTINCT source) AS total_files FROM knowledge_chunks")
        files_row = cursor.fetchone()
        cursor.execute("SELECT COUNT(*) AS total_chunks FROM knowledge_chunks")
        chunks_row = cursor.fetchone()
        return {
            "total_files": int(files_row["total_files"]) if files_row else 0,
            "total_chunks": int(chunks_row["total_chunks"]) if chunks_row else 0,
            "enabled": True,
        }
    except Exception as e:
        logger.error(f"Failed to read knowledge stats: {e}")
        return {"total_files": 0, "total_chunks": 0, "enabled": True}
    finally:
        conn.close()


try:
    init_knowledge_schema()
except Exception as e:
    logger.warning(f"Knowledge initialization skipped: {e}")
