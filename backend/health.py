"""Health check utilities for Jarvis"""
import os
import shutil
import time
from typing import Dict, Any
import httpx

try:
    from backend.config import GOOGLE_API_KEY, LLM_PROVIDER, OLLAMA_ENDPOINT, HISTORY_DIR
    from backend.metrics import get_metrics_summary
except ImportError:
    try:
        from config import GOOGLE_API_KEY, LLM_PROVIDER, OLLAMA_ENDPOINT, HISTORY_DIR
        from metrics import get_metrics_summary
    except ImportError:
        from .config import GOOGLE_API_KEY, LLM_PROVIDER, OLLAMA_ENDPOINT, HISTORY_DIR
        from .metrics import get_metrics_summary


def check_ollama() -> Dict[str, Any]:
    """Check Ollama connectivity and health"""
    try:
        start_time = time.time()
        response = httpx.get(f"{OLLAMA_ENDPOINT}/api/tags", timeout=5.0)
        duration = time.time() - start_time
        
        if response.status_code == 200:
            return {
                "status": "healthy",
                "response_time_ms": round(duration * 1000, 2),
                "endpoint": OLLAMA_ENDPOINT
            }
        else:
            return {
                "status": "unhealthy",
                "error": f"HTTP {response.status_code}",
                "endpoint": OLLAMA_ENDPOINT
            }
    except httpx.TimeoutException:
        return {
            "status": "unhealthy",
            "error": "Connection timeout",
            "endpoint": OLLAMA_ENDPOINT
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "endpoint": OLLAMA_ENDPOINT
        }


def check_disk_space() -> Dict[str, Any]:
    """Check available disk space"""
    try:
        # Check history directory
        if os.path.exists(HISTORY_DIR):
            stat = shutil.disk_usage(HISTORY_DIR)
            total_gb = stat.total / (1024**3)
            used_gb = stat.used / (1024**3)
            free_gb = stat.free / (1024**3)
            percent_used = (stat.used / stat.total) * 100
            
            status = "healthy"
            if percent_used > 90:
                status = "critical"
            elif percent_used > 80:
                status = "warning"
            
            return {
                "status": status,
                "path": HISTORY_DIR,
                "total_gb": round(total_gb, 2),
                "used_gb": round(used_gb, 2),
                "free_gb": round(free_gb, 2),
                "percent_used": round(percent_used, 1)
            }
        else:
            return {
                "status": "unknown",
                "error": "History directory does not exist",
                "path": HISTORY_DIR
            }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


def check_session_store() -> Dict[str, Any]:
    """Check session store health"""
    try:
        # Check if history directory is writable
        test_file = os.path.join(HISTORY_DIR, ".health_check")
        try:
            with open(test_file, 'w') as f:
                f.write("test")
            os.remove(test_file)
            writable = True
        except Exception:
            writable = False
        
        # Count history files
        history_files = 0
        if os.path.exists(HISTORY_DIR):
            history_files = len([f for f in os.listdir(HISTORY_DIR) if f.startswith('history')])
        
        return {
            "status": "healthy" if writable else "unhealthy",
            "writable": writable,
            "history_files": history_files,
            "path": HISTORY_DIR
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


def shallow_health_check() -> Dict[str, Any]:
    """
    Shallow health check - quick check that returns immediately.
    Used for load balancer health checks.
    """
    return {
        "status": "healthy",
        "service": "jarvis",
        "timestamp": time.time()
    }


def deep_health_check() -> Dict[str, Any]:
    """
    Deep health check - comprehensive check of all dependencies.
    May take several seconds to complete.
    """
    provider = os.getenv("LLM_PROVIDER", LLM_PROVIDER).strip().lower()
    llm_check = (
        {"status": "healthy", "provider": "google"}
        if provider == "google" and os.getenv("GOOGLE_API_KEY", GOOGLE_API_KEY)
        else (
            {"status": "unhealthy", "provider": "google", "error": "GOOGLE_API_KEY is not set"}
            if provider == "google"
            else check_ollama()
        )
    )
    checks = {
        "llm": llm_check,
        "disk": check_disk_space(),
        "session_store": check_session_store(),
    }
    
    # Add metrics summary
    try:
        checks["metrics"] = get_metrics_summary()
    except Exception as e:
        checks["metrics"] = {"status": "error", "error": str(e)}
    
    # Determine overall status
    statuses = [check.get("status", "unknown") for check in checks.values() if isinstance(check, dict)]
    
    if "critical" in statuses or "unhealthy" in statuses:
        overall_status = "unhealthy"
    elif "warning" in statuses:
        overall_status = "degraded"
    else:
        overall_status = "healthy"
    
    return {
        "status": overall_status,
        "service": "jarvis",
        "timestamp": time.time(),
        "checks": checks
    }
