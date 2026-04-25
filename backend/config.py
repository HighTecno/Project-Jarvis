import os

# Ollama configuration
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "localhost")
OLLAMA_PORT = os.getenv("OLLAMA_PORT", "11434")
OLLAMA_ENDPOINT = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}"
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")

# LLM provider configuration
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GOOGLE_MODEL = os.getenv("GOOGLE_MODEL", "gemma-4-26b-it")
GOOGLE_API_ENDPOINT = os.getenv(
    "GOOGLE_API_ENDPOINT",
    "https://generativelanguage.googleapis.com/v1beta",
)

# Agent configuration
MAX_STEPS = int(os.getenv("MAX_STEPS", "8"))
MAX_TOOL_CALLS = int(os.getenv("MAX_TOOL_CALLS", "6"))
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "120"))
LLM_TIMEOUT_ENABLED = os.getenv("LLM_TIMEOUT_ENABLED", "false").lower() == "true"
TERMINAL_TIMEOUT_SECONDS = int(os.getenv("TERMINAL_TIMEOUT_SECONDS", "10"))
MAX_TOOL_OUTPUT_CHARS = int(os.getenv("MAX_TOOL_OUTPUT_CHARS", "12000"))

# Workspace path for file writes (defaults to current directory if not set)
WORKSPACE_PATH = os.getenv("WORKSPACE_PATH", os.getcwd())
SAFE_FILESYSTEM_ROOT = os.getenv("SAFE_FILESYSTEM_ROOT", "/workspace")
HOST_ROOT = os.getenv("HOST_ROOT", "/hostroot")
SERVICE_ROOT = os.getenv("SERVICE_ROOT", "/hostroot/root")

# Server configuration
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# SSL/HTTPS configuration (for Tailscale)
USE_SSL = os.getenv("USE_SSL", "false").lower() == "true"
SSL_CERTFILE = os.getenv("SSL_CERTFILE", None)
SSL_KEYFILE = os.getenv("SSL_KEYFILE", None)

# Optional feature flags
ENABLE_STT = os.getenv("ENABLE_STT", "false").lower() == "true"

# Logging configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_JSON_FORMAT = os.getenv("LOG_JSON_FORMAT", "true").lower() == "true"

# Authentication configuration
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "true").lower() == "true"
API_KEYS_FILE = os.getenv("API_KEYS_FILE", os.path.expanduser("~/.jarvis/api_keys.txt"))

# Rate limiting configuration
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "60"))
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))

# CORS configuration
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "").split(",") if os.getenv("CORS_ORIGINS") else []

# Memory system configuration
MEMORY_ENABLED = os.getenv("MEMORY_ENABLED", "true").lower() == "true"
MEMORY_TOP_K = int(os.getenv("MEMORY_TOP_K", "3"))
MEMORY_DB_PATH = os.getenv("MEMORY_DB_PATH", os.path.expanduser("~/.jarvis/memory.db"))
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
MEMORY_SUMMARIZE_EVERY_EXCHANGES = int(os.getenv("MEMORY_SUMMARIZE_EVERY_EXCHANGES", "10"))
MEMORY_SUMMARY_WINDOW_EXCHANGES = int(os.getenv("MEMORY_SUMMARY_WINDOW_EXCHANGES", "10"))
MEMORY_MAX_CONTEXT_MESSAGES = int(os.getenv("MEMORY_MAX_CONTEXT_MESSAGES", "100"))
DEFAULT_THREAD_ID = os.getenv("DEFAULT_THREAD_ID", "legacy-default")

# History file configuration
HISTORY_DIR = os.path.expanduser("~/.jarvis")
HISTORY_FILE = os.path.join(HISTORY_DIR, "history.json")

# Knowledge base configuration
KNOWLEDGE_ENABLED = os.getenv("KNOWLEDGE_ENABLED", "true").lower() == "true"
KNOWLEDGE_CHUNK_SIZE = int(os.getenv("KNOWLEDGE_CHUNK_SIZE", "800"))
KNOWLEDGE_CHUNK_OVERLAP = int(os.getenv("KNOWLEDGE_CHUNK_OVERLAP", "100"))
KNOWLEDGE_MAX_FILE_MB = float(os.getenv("KNOWLEDGE_MAX_FILE_MB", "5"))
KNOWLEDGE_TOP_K = int(os.getenv("KNOWLEDGE_TOP_K", "5"))
KNOWLEDGE_ROOT = os.getenv("KNOWLEDGE_ROOT", "/nextcloud")

# Skills configuration
SKILLS_ENABLED = os.getenv("SKILLS_ENABLED", "true").lower() == "true"
SKILLS_FILE = os.getenv("SKILLS_FILE", os.path.expanduser("~/.jarvis/skills.json"))
