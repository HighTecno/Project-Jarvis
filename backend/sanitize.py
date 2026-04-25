"""Output sanitization utilities for preventing XSS attacks"""
import html
import re
from typing import Any, Dict


def sanitize_html(text: str) -> str:
    """
    HTML-escape text to prevent XSS attacks.
    Converts <, >, &, ", ' to their HTML entities.
    """
    if not isinstance(text, str):
        text = str(text)
    return html.escape(text, quote=True)


def sanitize_tool_output(output: Any) -> Any:
    """
    Sanitize tool output to prevent XSS attacks.
    
    - If output is a string, HTML-escape it
    - If output is a dict, recursively sanitize all string values
    - If output is a list, recursively sanitize all items
    - For other types, convert to string and escape
    """
    if isinstance(output, str):
        return sanitize_html(output)
    elif isinstance(output, dict):
        return {key: sanitize_tool_output(value) for key, value in output.items()}
    elif isinstance(output, list):
        return [sanitize_tool_output(item) for item in output]
    elif isinstance(output, (int, float, bool, type(None))):
        # Safe primitive types, no escaping needed
        return output
    else:
        # For other types, convert to string and escape
        return sanitize_html(str(output))


def detect_xss_patterns(text: str) -> bool:
    """
    Detect common XSS patterns in text.
    Returns True if suspicious patterns are found.
    """
    if not isinstance(text, str):
        return False
    
    # Common XSS patterns (case-insensitive)
    xss_patterns = [
        r'<script[^>]*>',
        r'javascript:',
        r'onerror\s*=',
        r'onload\s*=',
        r'onclick\s*=',
        r'onmouseover\s*=',
        r'<iframe[^>]*>',
        r'<object[^>]*>',
        r'<embed[^>]*>',
        r'eval\s*\(',
        r'expression\s*\(',
    ]
    
    text_lower = text.lower()
    for pattern in xss_patterns:
        if re.search(pattern, text_lower):
            return True
    
    return False


def sanitize_agent_response(response: str) -> str:
    """
    Sanitize final agent response.
    Less aggressive than tool output sanitization - preserves markdown.
    Only escapes dangerous patterns.
    """
    if not isinstance(response, str):
        response = str(response)
    
    # Check for XSS patterns
    if detect_xss_patterns(response):
        # If XSS detected, escape the entire response
        return sanitize_html(response)
    
    # Otherwise, return as-is to preserve markdown formatting
    return response
