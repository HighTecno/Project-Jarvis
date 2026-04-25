"""Telegram bot integration for notifications and commands"""
import json
from typing import Dict, Any, Optional

try:
    from backend.tools import terminal, config
except ImportError:
    try:
        from tools import terminal, config
    except ImportError:
        from . import terminal, config


def _success(output):
    return {"status": "success", "output": output}


def _error(message):
    return {"status": "error", "error": message}


def _get_telegram_config() -> tuple:
    """Get Telegram bot configuration"""
    # Get bot token
    token_result = config.get_config("telegram.bot_token")
    if token_result.get("status") != "success":
        return None, None, "Telegram bot token not configured. Use: config.set('telegram.bot_token', 'your-bot-token')"
    
    # Get default chat ID
    chat_result = config.get_config("telegram.default_chat_id")
    if chat_result.get("status") != "success":
        default_chat_id = None
    else:
        default_chat_id = chat_result.get("output", {}).get("value")
    
    token = token_result.get("output", {}).get("value", "")
    
    return token, default_chat_id, None


def send_message(message: str, chat_id: Optional[str] = None, parse_mode: str = "Markdown") -> Dict[str, Any]:
    """
    Send a message to Telegram.
    
    Args:
        message: Message text to send
        chat_id: Chat ID to send to (uses default if not provided)
        parse_mode: Message formatting (Markdown, HTML, or None)
    
    Returns:
        Dict with send status
    """
    try:
        if not message or not message.strip():
            return _error("Message cannot be empty")
        
        # Get Telegram configuration
        bot_token, default_chat_id, error = _get_telegram_config()
        if error:
            return _error(error)
        
        # Use provided chat_id or default
        target_chat_id = chat_id or default_chat_id
        if not target_chat_id:
            return _error("No chat_id provided and no default chat_id configured. Use: config.set('telegram.default_chat_id', 'your-chat-id')")
        
        # Prepare API request
        api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        
        # Escape message for JSON
        message_escaped = message.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        
        # Build JSON payload
        payload = {
            "chat_id": target_chat_id,
            "text": message_escaped,
        }
        
        if parse_mode and parse_mode.lower() != "none":
            payload["parse_mode"] = parse_mode
        
        payload_json = json.dumps(payload)
        
        # Send via curl
        curl_cmd = f'''curl -s -X POST "{api_url}" -H "Content-Type: application/json" -d '{payload_json}' '''
        
        result = terminal.run(curl_cmd, timeout_seconds=15)
        
        if result.get("status") != "success":
            return _error(f"Failed to send message: {result.get('error')}")
        
        # Parse response
        response_text = result.get("output", "")
        try:
            response = json.loads(response_text)
        except:
            return _error(f"Failed to parse Telegram API response: {response_text[:200]}")
        
        if not response.get("ok"):
            error_desc = response.get("description", "Unknown error")
            return _error(f"Telegram API error: {error_desc}")
        
        message_id = response.get("result", {}).get("message_id")
        
        return _success({
            "sent": True,
            "message_id": message_id,
            "chat_id": target_chat_id
        })
        
    except Exception as e:
        return _error(f"Failed to send message: {str(e)}")


def send_alert(title: str, body: str, level: str = "info", chat_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Send a formatted alert to Telegram.
    
    Args:
        title: Alert title
        body: Alert message body
        level: Alert level (info, warning, error, critical)
        chat_id: Chat ID to send to (uses default if not provided)
    
    Returns:
        Dict with send status
    """
    try:
        # Map levels to emojis
        level_emoji = {
            "info": "ℹ️",
            "warning": "⚠️",
            "error": "❌",
            "critical": "🚨"
        }
        
        emoji = level_emoji.get(level.lower(), "ℹ️")
        
        # Format message
        formatted_message = f"{emoji} *{title}*\n\n{body}"
        
        # Send
        return send_message(formatted_message, chat_id=chat_id, parse_mode="Markdown")
        
    except Exception as e:
        return _error(f"Failed to send alert: {str(e)}")


def forward_logs(service_name: str, lines: int = 20, chat_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Forward service logs to Telegram.
    
    Args:
        service_name: Docker service name
        lines: Number of log lines to forward
        chat_id: Chat ID to send to (uses default if not provided)
    
    Returns:
        Dict with send status
    """
    try:
        # Import homelab tools
        try:
            from backend.tools import homelab
        except ImportError:
            try:
                from tools import homelab
            except ImportError:
                from . import homelab
        
        # Get logs
        logs_result = homelab.docker_logs(service_name, lines=lines)
        
        if logs_result.get("status") != "success":
            return _error(f"Failed to get logs: {logs_result.get('error')}")
        
        logs = logs_result.get("output", "")
        
        # Truncate if too long (Telegram has 4096 char limit)
        if len(logs) > 3800:
            logs = logs[:3800] + "\n\n... (truncated)"
        
        # Format message
        message = f"📋 *Logs: {service_name}*\n```\n{logs}\n```"
        
        # Send
        return send_message(message, chat_id=chat_id, parse_mode="Markdown")
        
    except Exception as e:
        return _error(f"Failed to forward logs: {str(e)}")


def get_updates(offset: Optional[int] = None) -> Dict[str, Any]:
    """
    Get updates (messages) from Telegram bot.
    
    Args:
        offset: Update offset for pagination
    
    Returns:
        Dict with updates/messages
    """
    try:
        # Get Telegram configuration
        bot_token, _, error = _get_telegram_config()
        if error:
            return _error(error)
        
        # Prepare API request
        api_url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
        
        if offset:
            api_url += f"?offset={offset}"
        
        # Fetch via curl
        curl_cmd = f'curl -s -X GET "{api_url}"'
        
        result = terminal.run(curl_cmd, timeout_seconds=10)
        
        if result.get("status") != "success":
            return _error(f"Failed to get updates: {result.get('error')}")
        
        # Parse response
        response_text = result.get("output", "")
        try:
            response = json.loads(response_text)
        except:
            return _error(f"Failed to parse Telegram API response: {response_text[:200]}")
        
        if not response.get("ok"):
            error_desc = response.get("description", "Unknown error")
            return _error(f"Telegram API error: {error_desc}")
        
        updates = response.get("result", [])
        
        # Extract relevant info
        messages = []
        for update in updates:
            if "message" in update:
                msg = update["message"]
                messages.append({
                    "update_id": update.get("update_id"),
                    "message_id": msg.get("message_id"),
                    "from": msg.get("from", {}).get("username"),
                    "chat_id": msg.get("chat", {}).get("id"),
                    "text": msg.get("text"),
                    "date": msg.get("date")
                })
        
        return _success({
            "updates_count": len(updates),
            "messages": messages
        })
        
    except Exception as e:
        return _error(f"Failed to get updates: {str(e)}")
