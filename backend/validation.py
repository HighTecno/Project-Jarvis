"""Input validation schemas for tool arguments"""
import os
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator
import re


# Terminal tool validation
class TerminalRunArgs(BaseModel):
    command: str = Field(..., min_length=1, max_length=10000)
    cwd: Optional[str] = Field(None, max_length=1000)
    
    @field_validator("command")
    @classmethod
    def validate_command(cls, v: str) -> str:
        # Remove null bytes
        if "\x00" in v:
            raise ValueError("Command contains null bytes")
        return v
    
    @field_validator("cwd")
    @classmethod
    def validate_cwd(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if "\x00" in v:
            raise ValueError("Path contains null bytes")
        # Prevent path traversal attempts in obvious cases
        if ".." in v.split("/"):
            raise ValueError("Path traversal detected")
        return v


# Filesystem tool validation
class FilePathArgs(BaseModel):
    file_path: str = Field(..., min_length=1, max_length=4096)
    
    @field_validator("file_path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        if "\x00" in v:
            raise ValueError("Path contains null bytes")
        if not v.startswith("/"):
            raise ValueError("Path must be absolute")
        return v


class FileWriteArgs(BaseModel):
    file_path: str = Field(..., min_length=1, max_length=4096)
    content: str = Field(..., max_length=10_000_000)  # 10MB max
    
    @field_validator("file_path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        if "\x00" in v:
            raise ValueError("Path contains null bytes")
        if not v.startswith("/"):
            raise ValueError("Path must be absolute")
        return v


class DirectoryArgs(BaseModel):
    path: str = Field(..., min_length=1, max_length=4096)
    
    @field_validator("path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        if "\x00" in v:
            raise ValueError("Path contains null bytes")
        if not v.startswith("/"):
            raise ValueError("Path must be absolute")
        return v


class FileSearchArgs(BaseModel):
    pattern: str = Field(..., min_length=1, max_length=500)
    base_path: str = Field(..., min_length=1, max_length=4096)
    
    @field_validator("base_path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        if "\x00" in v:
            raise ValueError("Path contains null bytes")
        if not v.startswith("/"):
            raise ValueError("Path must be absolute")
        return v


# Homelab tool validation
class ServiceNameArgs(BaseModel):
    service_name: str = Field(..., min_length=1, max_length=100)
    
    @field_validator("service_name")
    @classmethod
    def validate_service_name(cls, v: str) -> str:
        # Only allow alphanumeric, dash, underscore
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("Service name contains invalid characters")
        return v


class DockerLogsArgs(BaseModel):
    service_name: str = Field(..., min_length=1, max_length=100)
    lines: int = Field(50, ge=1, le=10000)
    
    @field_validator("service_name")
    @classmethod
    def validate_service_name(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("Service name contains invalid characters")
        return v


class SystemdUnitArgs(BaseModel):
    unit: str = Field(..., min_length=1, max_length=200)
    
    @field_validator("unit")
    @classmethod
    def validate_unit(cls, v: str) -> str:
        # Systemd units should end with .service, .socket, etc.
        if not re.match(r"^[a-zA-Z0-9_@.-]+$", v):
            raise ValueError("Unit name contains invalid characters")
        return v


class SystemdLogsArgs(BaseModel):
    unit: str = Field(..., min_length=1, max_length=200)
    lines: int = Field(50, ge=1, le=10000)
    
    @field_validator("unit")
    @classmethod
    def validate_unit(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_@.-]+$", v):
            raise ValueError("Unit name contains invalid characters")
        return v


class WebFetchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(..., min_length=1, max_length=4096)
    timeout: int = Field(30, ge=1, le=120)

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not re.match(r"^https?://", v, re.IGNORECASE):
            raise ValueError("URL must start with http:// or https://")
        return v


class WebExtractTextArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(..., min_length=1, max_length=4096)
    selector: Optional[str] = Field(None, min_length=1, max_length=200)

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not re.match(r"^https?://", v, re.IGNORECASE):
            raise ValueError("URL must start with http:// or https://")
        return v


class WebExtractRecipeArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(..., min_length=1, max_length=4096)

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not re.match(r"^https?://", v, re.IGNORECASE):
            raise ValueError("URL must start with http:// or https://")
        return v


class MealieSearchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(..., min_length=1, max_length=300)
    language: str = Field("de", min_length=2, max_length=10)


class MealieAddFromUrlArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(..., min_length=1, max_length=4096)
    tags: Optional[list[str]] = Field(None, max_length=50)

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not re.match(r"^https?://", v, re.IGNORECASE):
            raise ValueError("URL must start with http:// or https://")
        return v


class MealieListArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tags: Optional[list[str]] = Field(None, max_length=50)
    search: Optional[str] = Field(None, min_length=1, max_length=200)


class MealieTranslateArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(..., min_length=1, max_length=4000)
    source_lang: str = Field("de", min_length=2, max_length=10)
    target_lang: str = Field("en", min_length=2, max_length=10)


class SkillNameArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., min_length=2, max_length=64, pattern=r"^[a-z0-9][a-z0-9._-]{1,63}$")


class SkillAddArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., min_length=2, max_length=64, pattern=r"^[a-z0-9][a-z0-9._-]{1,63}$")
    description: str = Field(..., min_length=3, max_length=240)
    instructions: str = Field(..., min_length=10, max_length=20000)
    tags: Optional[list[str]] = Field(None, max_length=20)


# Mapping of tool names to their validation schemas
VALIDATION_SCHEMAS: Dict[str, type[BaseModel]] = {
    "terminal.run": TerminalRunArgs,
    "filesystem.read": FilePathArgs,
    "filesystem.write": FileWriteArgs,
    "filesystem.list": DirectoryArgs,
    "filesystem.search": FileSearchArgs,
    "filesystem.info": FilePathArgs,
    "homelab.docker_logs": DockerLogsArgs,
    "homelab.docker_status": ServiceNameArgs,
    "homelab.docker_restart": ServiceNameArgs,
    "homelab.caddy_reload": ServiceNameArgs,
    "homelab.systemd_status": SystemdUnitArgs,
    "homelab.systemd_logs": SystemdLogsArgs,
    "web.fetch": WebFetchArgs,
    "web.extract_text": WebExtractTextArgs,
    "web.extract_recipe": WebExtractRecipeArgs,
    "mealie.search": MealieSearchArgs,
    "mealie.add_from_url": MealieAddFromUrlArgs,
    "mealie.list": MealieListArgs,
    "mealie.translate": MealieTranslateArgs,
    "skills.get": SkillNameArgs,
    "skills.add": SkillAddArgs,
    "skills.delete": SkillNameArgs,
}


_ARG_ALIASES: Dict[str, Dict[str, str]] = {
    "telegram.send": {"text": "message"},
    "debug.summarize_error": {"error": "error_text"},
    "config.get": {"config_name": "key", "config_key": "key"},
    "config.set": {"config_name": "key", "config_key": "key"},
    "config.delete": {"config_name": "key", "config_key": "key"},
    "homelab.docker_logs": {"service": "service_name"},
    "homelab.docker_status": {"service": "service_name"},
    "homelab.docker_restart": {"service": "service_name"},
    "homelab.caddy_reload": {"service": "service_name"},
    "debug.analyze_logs": {"service": "service_name", "log_file": "service_name"},
    "telegram.forward_logs": {"service": "service_name"},
}


def _normalize_alias_args(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(args or {})
    alias_map = _ARG_ALIASES.get(tool_name, {})
    for alias, canonical in alias_map.items():
        if canonical in normalized or alias not in normalized:
            continue
        alias_value = normalized.pop(alias)
        if tool_name == "debug.analyze_logs" and alias == "log_file" and isinstance(alias_value, str):
            base_name = os.path.basename(alias_value.strip())
            if base_name.endswith(".log"):
                base_name = base_name[:-4]
            if base_name:
                normalized[canonical] = base_name
                continue
        normalized[canonical] = alias_value
    return normalized


def validate_tool_args(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate tool arguments against schema
    
    Args:
        tool_name: Name of the tool
        args: Dictionary of arguments
    
    Returns:
        Validated and sanitized arguments
    
    Raises:
        ValueError: If validation fails
    """
    normalized_args = _normalize_alias_args(tool_name, args)

    if tool_name not in VALIDATION_SCHEMAS:
        # No schema defined, pass through (but log warning)
        return normalized_args
    
    schema = VALIDATION_SCHEMAS[tool_name]
    try:
        validated = schema(**normalized_args)
        return validated.model_dump()
    except Exception as e:
        raise ValueError(f"Invalid arguments for {tool_name}: {str(e)}")
