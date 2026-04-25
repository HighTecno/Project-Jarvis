"""Debug and troubleshooting tools for homelab services"""
import re
import json
import yaml
from typing import Dict, Any, List

try:
    from backend.tools import terminal, homelab
except ImportError:
    try:
        from tools import terminal, homelab
    except ImportError:
        from . import terminal, homelab


def _success(output):
    return {"status": "success", "output": output}


def _error(message):
    return {"status": "error", "error": message}


def analyze_logs(service_name: str, lines: int = 100) -> Dict[str, Any]:
    """
    Analyze service logs for errors, warnings, and patterns.
    
    Args:
        service_name: Service directory name
        lines: Number of log lines to analyze (default: 100)
    
    Returns:
        Dict with error analysis, patterns, and suggestions
    """
    try:
        # Get logs using existing homelab tool
        log_result = homelab.docker_logs(service_name, lines)
        
        if log_result.get("status") != "success":
            return log_result
        
        log_text = log_result.get("output", "")
        
        # Parse logs for issues
        errors = []
        warnings = []
        patterns = {}
        
        # Error patterns
        error_patterns = [
            (r'(?i)error:?\s+(.+)', 'ERROR'),
            (r'(?i)exception:?\s+(.+)', 'EXCEPTION'),
            (r'(?i)failed:?\s+(.+)', 'FAILURE'),
            (r'(?i)fatal:?\s+(.+)', 'FATAL'),
            (r'(?i)panic:?\s+(.+)', 'PANIC'),
        ]
        
        # Warning patterns
        warning_patterns = [
            (r'(?i)warning:?\s+(.+)', 'WARNING'),
            (r'(?i)warn:?\s+(.+)', 'WARN'),
            (r'(?i)deprecated:?\s+(.+)', 'DEPRECATED'),
        ]
        
        # Parse line by line
        for line in log_text.split('\n'):
            # Check for errors
            for pattern, level in error_patterns:
                match = re.search(pattern, line)
                if match:
                    errors.append({
                        "level": level,
                        "message": match.group(1).strip()[:200],
                        "line": line[:300]
                    })
                    break
            
            # Check for warnings
            for pattern, level in warning_patterns:
                match = re.search(pattern, line)
                if match:
                    warnings.append({
                        "level": level,
                        "message": match.group(1).strip()[:200],
                        "line": line[:300]
                    })
                    break
            
            # Track common patterns
            # Connection issues
            if re.search(r'connection (refused|reset|timeout|closed)', line, re.I):
                patterns['connection_issues'] = patterns.get('connection_issues', 0) + 1
            
            # Permission issues
            if re.search(r'permission denied|access denied|forbidden', line, re.I):
                patterns['permission_issues'] = patterns.get('permission_issues', 0) + 1
            
            # Resource issues
            if re.search(r'out of memory|disk full|no space', line, re.I):
                patterns['resource_issues'] = patterns.get('resource_issues', 0) + 1
            
            # Configuration issues
            if re.search(r'invalid config|config error|missing (env|variable)', line, re.I):
                patterns['config_issues'] = patterns.get('config_issues', 0) + 1
        
        # Generate summary
        summary = {
            "service": service_name,
            "lines_analyzed": lines,
            "error_count": len(errors),
            "warning_count": len(warnings),
            "errors": errors[:10],  # Limit to 10 most recent
            "warnings": warnings[:5],
            "patterns": patterns,
            "suggestions": _generate_suggestions(errors, warnings, patterns)
        }
        
        return _success(summary)
        
    except Exception as e:
        return _error(f"Log analysis failed: {str(e)}")


def _generate_suggestions(errors: List, warnings: List, patterns: Dict) -> List[str]:
    """Generate actionable suggestions based on log analysis"""
    suggestions = []
    
    if patterns.get('connection_issues', 0) > 0:
        suggestions.append("Connection issues detected. Check network connectivity and service dependencies.")
    
    if patterns.get('permission_issues', 0) > 0:
        suggestions.append("Permission issues found. Verify file permissions and user ownership.")
    
    if patterns.get('resource_issues', 0) > 0:
        suggestions.append("Resource constraints detected. Check disk space and memory allocation.")
    
    if patterns.get('config_issues', 0) > 0:
        suggestions.append("Configuration problems found. Review .env files and environment variables.")
    
    if len(errors) > 10:
        suggestions.append(f"High error rate ({len(errors)} errors). Consider restarting the service.")
    
    if not suggestions:
        suggestions.append("No critical issues detected in recent logs.")
    
    return suggestions


def validate_compose(file_path: str) -> Dict[str, Any]:
    """
    Validate docker-compose.yaml file for syntax and best practices.
    
    Args:
        file_path: Path to docker-compose.yaml
    
    Returns:
        Dict with validation results, errors, and warnings
    """
    try:
        # Read file
        read_result = terminal.run(f"cat {file_path}", timeout_seconds=5)
        
        if read_result.get("status") != "success":
            return _error(f"Failed to read file: {file_path}")
        
        compose_content = read_result.get("output", "")
        
        # Try to parse YAML
        try:
            compose_data = yaml.safe_load(compose_content)
        except yaml.YAMLError as e:
            return _error(f"Invalid YAML syntax: {str(e)}")
        
        if not isinstance(compose_data, dict):
            return _error("docker-compose.yaml must be a dictionary")
        
        issues = []
        warnings = []
        
        # Check version
        version = compose_data.get('version')
        if not version:
            warnings.append("No version specified. Modern docker-compose doesn't require it, but it's recommended for clarity.")
        
        # Check services
        services = compose_data.get('services', {})
        if not services:
            issues.append("No services defined in docker-compose.yaml")
        
        for service_name, service_config in services.items():
            if not isinstance(service_config, dict):
                issues.append(f"Service '{service_name}' configuration must be a dictionary")
                continue
            
            # Check for image or build
            if 'image' not in service_config and 'build' not in service_config:
                issues.append(f"Service '{service_name}' must have either 'image' or 'build' specified")
            
            # Check restart policy
            if 'restart' not in service_config:
                warnings.append(f"Service '{service_name}' has no restart policy. Consider adding 'restart: unless-stopped'")
            
            # Check for exposed environment variables
            env_vars = service_config.get('environment', [])
            if isinstance(env_vars, list):
                for var in env_vars:
                    if isinstance(var, str) and ('PASSWORD' in var.upper() or 'SECRET' in var.upper() or 'KEY' in var.upper()):
                        if '=' in var and not var.endswith('=${...}'):
                            warnings.append(f"Service '{service_name}' may have hardcoded secrets. Use env_file or variables instead.")
            
            # Check volumes
            volumes = service_config.get('volumes', [])
            for volume in volumes:
                if isinstance(volume, str) and volume.startswith('/var/run/docker.sock'):
                    warnings.append(f"Service '{service_name}' has Docker socket access. This grants root-equivalent privileges.")
        
        # Check networks
        networks = compose_data.get('networks', {})
        if networks and isinstance(networks, dict):
            for network_name in networks:
                if network_name == 'default':
                    warnings.append("Explicitly defining 'default' network is usually unnecessary")
        
        # Compile results
        result = {
            "valid": len(issues) == 0,
            "file": file_path,
            "services_count": len(services),
            "issues": issues,
            "warnings": warnings,
            "services": list(services.keys())
        }
        
        return _success(result)
        
    except Exception as e:
        return _error(f"Validation failed: {str(e)}")


def summarize_error(error_text: str) -> Dict[str, Any]:
    """
    Parse and summarize error messages and stack traces.
    
    Args:
        error_text: Error message or stack trace
    
    Returns:
        Dict with error type, cause, and suggested fixes
    """
    try:
        # Detect error type
        error_type = "Unknown"
        cause = None
        suggestions = []
        
        error_lower = error_text.lower()
        
        # Python errors
        if 'traceback' in error_lower:
            error_type = "Python Exception"
            # Extract exception type
            match = re.search(r'(\w+Error|Exception):\s*(.+)', error_text)
            if match:
                cause = f"{match.group(1)}: {match.group(2)}"
        
        # Connection errors
        elif 'connection refused' in error_lower:
            error_type = "Connection Refused"
            cause = "Target service is not running or not accepting connections"
            suggestions.append("Check if the target service is running")
            suggestions.append("Verify the port number is correct")
            suggestions.append("Check firewall rules")
        
        elif 'timeout' in error_lower:
            error_type = "Timeout"
            cause = "Operation took too long to complete"
            suggestions.append("Check network connectivity")
            suggestions.append("Increase timeout value if appropriate")
            suggestions.append("Verify target service is responsive")
        
        # Permission errors
        elif 'permission denied' in error_lower or 'forbidden' in error_lower:
            error_type = "Permission Error"
            cause = "Insufficient permissions to access resource"
            suggestions.append("Check file/directory permissions")
            suggestions.append("Verify user/group ownership")
            suggestions.append("Check if service needs elevated privileges")
        
        # File not found
        elif 'no such file' in error_lower or 'not found' in error_lower:
            error_type = "File Not Found"
            cause = "Required file or directory does not exist"
            suggestions.append("Verify the file path is correct")
            suggestions.append("Check if file was deleted or moved")
            suggestions.append("Ensure volume mounts are configured correctly")
        
        # Port in use
        elif 'address already in use' in error_lower:
            error_type = "Port Already in Use"
            cause = "Another service is using the required port"
            suggestions.append("Check which service is using the port")
            suggestions.append("Stop the conflicting service or change port")
        
        # Docker errors
        elif 'docker' in error_lower and ('pull' in error_lower or 'image' in error_lower):
            error_type = "Docker Image Error"
            cause = "Failed to pull or find Docker image"
            suggestions.append("Check image name and tag")
            suggestions.append("Verify Docker registry is accessible")
            suggestions.append("Check Docker Hub rate limits")
        
        # Environment variable missing
        elif 'env' in error_lower or 'environment' in error_lower:
            error_type = "Environment Variable Error"
            cause = "Required environment variable is missing or invalid"
            suggestions.append("Check .env file exists and is loaded")
            suggestions.append("Verify variable names are correct")
            suggestions.append("Restart service after updating environment")
        
        if not suggestions:
            suggestions.append("Review the full error message for context")
            suggestions.append("Check service logs for additional details")
        
        result = {
            "error_type": error_type,
            "cause": cause or "Unable to determine specific cause",
            "suggestions": suggestions,
            "original_error": error_text[:500]  # Truncate for readability
        }
        
        return _success(result)
        
    except Exception as e:
        return _error(f"Error summarization failed: {str(e)}")
