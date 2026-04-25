"""Tests for input validation"""
import pytest
from backend.validation import (
    validate_tool_args,
    TerminalRunArgs,
    FilePathArgs,
    FileWriteArgs,
    ServiceNameArgs,
)


def test_terminal_run_validation():
    """Test terminal command validation"""
    # Valid command
    result = validate_tool_args("terminal.run", {"command": "ls -la"})
    assert result["command"] == "ls -la"
    
    # Null byte attack
    with pytest.raises(ValueError, match="null bytes"):
        validate_tool_args("terminal.run", {"command": "ls\x00rm -rf /"})


def test_filepath_validation():
    """Test file path validation"""
    # Valid absolute path
    result = validate_tool_args("filesystem.read", {"file_path": "/tmp/test.txt"})
    assert result["file_path"] == "/tmp/test.txt"
    
    # Relative path should fail
    with pytest.raises(ValueError, match="must be absolute"):
        validate_tool_args("filesystem.read", {"file_path": "test.txt"})
    
    # Null byte attack
    with pytest.raises(ValueError, match="null bytes"):
        validate_tool_args("filesystem.read", {"file_path": "/tmp/test\x00.txt"})


def test_service_name_validation():
    """Test service name validation"""
    # Valid service name
    result = validate_tool_args("homelab.docker_status", {"service_name": "my-service"})
    assert result["service_name"] == "my-service"
    
    # Invalid characters
    with pytest.raises(ValueError, match="invalid characters"):
        validate_tool_args("homelab.docker_status", {"service_name": "my service"})
    
    with pytest.raises(ValueError, match="invalid characters"):
        validate_tool_args("homelab.docker_status", {"service_name": "my;service"})


def test_service_name_alias_normalization():
    """Accept common alias used by LLM outputs."""
    result = validate_tool_args("homelab.docker_status", {"service": "my-service"})
    assert result["service_name"] == "my-service"


def test_debug_summarize_error_alias_normalization():
    """Map 'error' alias to expected 'error_text'."""
    result = validate_tool_args("debug.summarize_error", {"error": "boom"})
    assert result["error_text"] == "boom"


def test_debug_analyze_logs_log_file_alias_normalization():
    """Allow log_file path and infer service name."""
    result = validate_tool_args("debug.analyze_logs", {"log_file": "/workspace/logs/telegram.log"})
    assert result["service_name"] == "telegram"


def test_telegram_send_text_alias_normalization():
    """Map Telegram 'text' field to tool's 'message' argument."""
    result = validate_tool_args("telegram.send", {"chat_id": "123", "text": "hello"})
    assert result["message"] == "hello"
    assert result["chat_id"] == "123"


def test_file_write_size_limit():
    """Test file write size limits"""
    # Under limit
    result = validate_tool_args("filesystem.write", {
        "file_path": "/workspace/test.txt",
        "content": "x" * 1000
    })
    assert len(result["content"]) == 1000
    
    # Over limit should fail
    with pytest.raises(ValueError):
        validate_tool_args("filesystem.write", {
            "file_path": "/workspace/test.txt",
            "content": "x" * 11_000_000  # Over 10MB
        })


def test_path_traversal_basic():
    """Test basic path traversal detection"""
    with pytest.raises(ValueError, match="traversal"):
        validate_tool_args("terminal.run", {
            "command": "ls",
            "cwd": "/workspace/../root"
        })


def test_mealie_add_from_url_requires_full_url():
    """Reject placeholder or partial URLs for mealie.add_from_url."""
    with pytest.raises(ValueError, match="http:// or https://"):
        validate_tool_args("mealie.add_from_url", {"url": "recipe-url"})


def test_mealie_add_from_url_rejects_unknown_args():
    """Reject unsupported arguments like api_token."""
    with pytest.raises(ValueError, match="extra_forbidden"):
        validate_tool_args(
            "mealie.add_from_url",
            {"url": "https://example.com/recipe", "api_token": "secret"},
        )


def test_skills_add_validation():
    result = validate_tool_args(
        "skills.add",
        {
            "name": "python.debug",
            "description": "Debug Python issues safely",
            "instructions": "1. Reproduce issue\n2. Capture traceback\n3. Propose targeted fix",
            "tags": ["python", "debug"],
        },
    )
    assert result["name"] == "python.debug"


def test_skills_add_rejects_invalid_name():
    with pytest.raises(ValueError, match="Invalid arguments for skills.add"):
        validate_tool_args(
            "skills.add",
            {
                "name": "Bad Name",
                "description": "desc",
                "instructions": "long enough instructions text",
            },
        )
