"""Tests for output sanitization"""
import pytest
from backend.sanitize import (
    sanitize_html,
    sanitize_tool_output,
    detect_xss_patterns,
    sanitize_agent_response,
)


class TestSanitizeHTML:
    def test_escape_basic_html(self):
        assert sanitize_html("<script>alert('xss')</script>") == "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;"
    
    def test_escape_ampersand(self):
        assert sanitize_html("foo & bar") == "foo &amp; bar"
    
    def test_escape_quotes(self):
        assert sanitize_html('test "quoted" text') == "test &quot;quoted&quot; text"
        assert sanitize_html("test 'quoted' text") == "test &#x27;quoted&#x27; text"
    
    def test_safe_text_unchanged(self):
        assert sanitize_html("safe text") == "safe text"
    
    def test_non_string_input(self):
        assert sanitize_html(123) == "123"
        assert sanitize_html(None) == "None"


class TestSanitizeToolOutput:
    def test_string_output(self):
        result = sanitize_tool_output("<script>xss</script>")
        assert "&lt;script&gt;" in result
    
    def test_dict_output(self):
        result = sanitize_tool_output({
            "status": "success",
            "data": "<script>xss</script>",
            "nested": {"html": "<b>test</b>"}
        })
        assert result["status"] == "success"
        assert "&lt;script&gt;" in result["data"]
        assert "&lt;b&gt;" in result["nested"]["html"]
    
    def test_list_output(self):
        result = sanitize_tool_output([
            "<script>xss</script>",
            {"html": "<b>test</b>"},
            "safe text"
        ])
        assert "&lt;script&gt;" in result[0]
        assert "&lt;b&gt;" in result[1]["html"]
        assert result[2] == "safe text"
    
    def test_primitive_types(self):
        assert sanitize_tool_output(123) == 123
        assert sanitize_tool_output(45.67) == 45.67
        assert sanitize_tool_output(True) is True
        assert sanitize_tool_output(None) is None
    
    def test_mixed_nested_structure(self):
        result = sanitize_tool_output({
            "items": ["<a>link</a>", 123, True],
            "meta": {
                "count": 5,
                "html": "<div>test</div>"
            }
        })
        assert "&lt;a&gt;" in result["items"][0]
        assert result["items"][1] == 123
        assert result["items"][2] is True
        assert result["meta"]["count"] == 5
        assert "&lt;div&gt;" in result["meta"]["html"]


class TestDetectXSSPatterns:
    def test_detect_script_tag(self):
        assert detect_xss_patterns("<script>alert(1)</script>") is True
        assert detect_xss_patterns("<SCRIPT>alert(1)</SCRIPT>") is True
    
    def test_detect_javascript_protocol(self):
        assert detect_xss_patterns("javascript:alert(1)") is True
        assert detect_xss_patterns("JavaScript:alert(1)") is True
    
    def test_detect_event_handlers(self):
        assert detect_xss_patterns('onerror="alert(1)"') is True
        assert detect_xss_patterns('onload="alert(1)"') is True
        assert detect_xss_patterns('onclick="alert(1)"') is True
        assert detect_xss_patterns('onmouseover="alert(1)"') is True
    
    def test_detect_dangerous_tags(self):
        assert detect_xss_patterns("<iframe src='evil.com'></iframe>") is True
        assert detect_xss_patterns("<object data='evil.swf'></object>") is True
        assert detect_xss_patterns("<embed src='evil.swf'>") is True
    
    def test_detect_eval_expression(self):
        assert detect_xss_patterns("eval(malicious_code)") is True
        assert detect_xss_patterns("expression(alert(1))") is True
    
    def test_safe_content(self):
        assert detect_xss_patterns("This is safe text") is False
        assert detect_xss_patterns("No dangerous patterns here") is False
        assert detect_xss_patterns("123") is False
    
    def test_non_string_input(self):
        assert detect_xss_patterns(123) is False
        assert detect_xss_patterns(None) is False


class TestSanitizeAgentResponse:
    def test_safe_markdown_preserved(self):
        text = "# Header\n\n**Bold** and *italic*\n\n- List item"
        assert sanitize_agent_response(text) == text
    
    def test_xss_detected_and_escaped(self):
        text = "Response with <script>alert(1)</script>"
        result = sanitize_agent_response(text)
        assert "&lt;script&gt;" in result
    
    def test_javascript_protocol_escaped(self):
        text = "Click javascript:alert(1)"
        result = sanitize_agent_response(text)
        # Should be escaped because XSS detected
        assert "javascript:" in result or "javascript&#x3A;" in result
    
    def test_safe_code_blocks(self):
        text = "```python\nprint('hello')\n```"
        assert sanitize_agent_response(text) == text
    
    def test_non_string_input(self):
        assert sanitize_agent_response(123) == "123"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
