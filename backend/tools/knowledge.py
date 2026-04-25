try:
    from backend.config import KNOWLEDGE_ROOT
    from backend.knowledge import ingest_directory, ingest_file as ingest_knowledge_file, search_knowledge
    from backend.logger import get_logger
except ImportError:
    try:
        from config import KNOWLEDGE_ROOT
        from knowledge import ingest_directory, ingest_file as ingest_knowledge_file, search_knowledge
        from logger import get_logger
    except ImportError:
        from ..config import KNOWLEDGE_ROOT
        from ..knowledge import ingest_directory, ingest_file as ingest_knowledge_file, search_knowledge
        from ..logger import get_logger

logger = get_logger("tools.knowledge")


def _success(output):
    return {"status": "success", "output": output}


def _error(message):
    return {"status": "error", "error": message}


def search(query: str, top_k: int = 5):
    try:
        if not isinstance(query, str) or not query.strip():
            return _error("query must be a non-empty string")
        results = search_knowledge(query=query.strip(), top_k=top_k)
        if not results:
            return _success("No relevant knowledge found.")

        formatted = []
        for i, chunk in enumerate(results, start=1):
            if isinstance(chunk, str) and "\n" in chunk:
                first_line, rest = chunk.split("\n", 1)
                if first_line.startswith("Source: "):
                    formatted.append(f"[{i}] {first_line}\n{rest.strip()}")
                    continue
            formatted.append(f"[{i}] Source: unknown\n{str(chunk).strip()}")

        return _success("\n\n".join(formatted))
    except Exception as exc:
        return _error(str(exc))


def ingest_file(path: str):
    try:
        return _success(ingest_knowledge_file(path))
    except Exception as exc:
        return _error(str(exc))


def init(root: str = KNOWLEDGE_ROOT):
    try:
        target_root = root or KNOWLEDGE_ROOT
        logger.info(f"Starting full knowledge base initialization from {target_root}")
        result = ingest_directory(target_root)
        if result.get("status") == "error":
            return _error(result.get("error", "Knowledge initialization failed"))

        summary = {
            "root": target_root,
            "files_ingested": result.get("files_ingested", 0),
            "chunks_total": result.get("chunks_total", 0),
            "errors": result.get("errors", []),
        }
        return _success(summary)
    except Exception as exc:
        return _error(str(exc))
