"""Secure configuration and API key management"""
import os
import json
from typing import Dict, Any, Optional

def _success(output):
    return {"status": "success", "output": output}

def _error(message):
    return {"status": "error", "error": message}


# Config directory
CONFIG_DIR = os.path.expanduser("~/.jarvis/config")
SECRETS_FILE = os.path.join(CONFIG_DIR, "secrets.json")


def _ensure_config_dir():
    """Ensure config directory exists"""
    os.makedirs(CONFIG_DIR, exist_ok=True)


def _load_secrets() -> Dict[str, str]:
    """Load secrets from file"""
    if not os.path.exists(SECRETS_FILE):
        return {}
    
    try:
        with open(SECRETS_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        return {}


def _save_secrets(secrets: Dict[str, str]):
    """Save secrets to file"""
    _ensure_config_dir()
    
    try:
        with open(SECRETS_FILE, "w") as f:
            json.dump(secrets, f, indent=2)
        
        # Set restrictive permissions (owner read/write only)
        os.chmod(SECRETS_FILE, 0o600)
    except Exception as e:
        raise Exception(f"Failed to save secrets: {str(e)}")


def set_config(key: str, value: str, description: Optional[str] = None) -> Dict[str, Any]:
    """
    Store a configuration value securely.
    
    Args:
        key: Configuration key (e.g., "telegram.bot_token")
        value: Configuration value
        description: Optional description of what this config is for
    
    Returns:
        Dict with success status
    """
    try:
        if not key or not key.strip():
            return _error("Key cannot be empty")
        
        if not value:
            return _error("Value cannot be empty")
        
        secrets = _load_secrets()
        
        # Store with metadata
        secrets[key] = {
            "value": value,
            "description": description or "",
            "updated_at": None  # Will be set by JSON serialization
        }
        
        _save_secrets(secrets)
        
        return _success({
            "key": key,
            "set": True,
            "message": f"Configuration '{key}' stored securely"
        })
        
    except Exception as e:
        return _error(f"Failed to set config: {str(e)}")


def get_config(key: str) -> Dict[str, Any]:
    """
    Retrieve a configuration value.
    
    Args:
        key: Configuration key to retrieve
    
    Returns:
        Dict with configuration value or error
    """
    try:
        if not key or not key.strip():
            return _error("Key cannot be empty")
        
        secrets = _load_secrets()
        
        if key not in secrets:
            return _error(f"Configuration '{key}' not found. Use config.list to see available configs.")
        
        config_data = secrets[key]
        
        # Return value and metadata
        return _success({
            "key": key,
            "value": config_data.get("value", ""),
            "description": config_data.get("description", "")
        })
        
    except Exception as e:
        return _error(f"Failed to get config: {str(e)}")


def list_configs() -> Dict[str, Any]:
    """
    List all stored configuration keys (without values for security).
    
    Returns:
        Dict with list of configuration keys and descriptions
    """
    try:
        secrets = _load_secrets()
        
        configs = []
        for key, data in secrets.items():
            configs.append({
                "key": key,
                "description": data.get("description", ""),
                "has_value": bool(data.get("value"))
            })
        
        return _success({
            "count": len(configs),
            "configs": configs
        })
        
    except Exception as e:
        return _error(f"Failed to list configs: {str(e)}")


def delete_config(key: str) -> Dict[str, Any]:
    """
    Delete a configuration value.
    
    Args:
        key: Configuration key to delete
    
    Returns:
        Dict with deletion status
    """
    try:
        if not key or not key.strip():
            return _error("Key cannot be empty")
        
        secrets = _load_secrets()
        
        if key not in secrets:
            return _error(f"Configuration '{key}' not found")
        
        del secrets[key]
        _save_secrets(secrets)
        
        return _success({
            "key": key,
            "deleted": True,
            "message": f"Configuration '{key}' deleted"
        })
        
    except Exception as e:
        return _error(f"Failed to delete config: {str(e)}")


def validate_required(required_keys: list) -> Dict[str, Any]:
    """
    Validate that required configuration keys are present.
    
    Args:
        required_keys: List of required configuration keys
    
    Returns:
        Dict with validation status and missing keys
    """
    try:
        secrets = _load_secrets()
        
        missing = []
        for key in required_keys:
            if key not in secrets or not secrets[key].get("value"):
                missing.append(key)
        
        if missing:
            return _error(f"Missing required configurations: {', '.join(missing)}")
        
        return _success({
            "valid": True,
            "message": "All required configurations are present"
        })
        
    except Exception as e:
        return _error(f"Validation failed: {str(e)}")
