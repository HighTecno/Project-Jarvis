"""Network and system diagnostic tools for homelab management"""
import subprocess
import re
import socket
from typing import Dict, Any

def _success(output):
    return {"status": "success", "output": output}

def _error(message):
    return {"status": "error", "error": message}


def ping(host: str, count: int = 4) -> Dict[str, Any]:
    """
    Ping a host to check connectivity and measure latency.
    
    Args:
        host: Hostname or IP address to ping
        count: Number of ping packets (default: 4)
    
    Returns:
        Dict with status and ping statistics
    """
    try:
        # Limit count to prevent abuse
        count = min(max(1, count), 10)
        
        result = subprocess.run(
            ["ping", "-c", str(count), "-W", "2", host],
            capture_output=True,
            text=True,
            timeout=15
        )
        
        output = result.stdout + result.stderr
        
        # Parse statistics
        stats = {}
        if "packets transmitted" in output:
            # Extract packet loss
            match = re.search(r'(\d+)% packet loss', output)
            if match:
                stats['packet_loss_percent'] = int(match.group(1))
            
            # Extract RTT statistics
            match = re.search(r'rtt min/avg/max/mdev = ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)', output)
            if match:
                stats['rtt_min_ms'] = float(match.group(1))
                stats['rtt_avg_ms'] = float(match.group(2))
                stats['rtt_max_ms'] = float(match.group(3))
                stats['rtt_mdev_ms'] = float(match.group(4))
        
        return _success({
            "host": host,
            "reachable": result.returncode == 0,
            "statistics": stats,
            "output": output[:500]  # Limit output size
        })
    except subprocess.TimeoutExpired:
        return _error(f"Ping timeout for {host}")
    except Exception as e:
        return _error(str(e))


def port_check(host: str, port: int, timeout: float = 3.0) -> Dict[str, Any]:
    """
    Check if a TCP port is open on a host.
    
    Args:
        host: Hostname or IP address
        port: Port number to check
        timeout: Connection timeout in seconds (default: 3.0)
    
    Returns:
        Dict with status and port state
    """
    try:
        # Validate port
        if not 1 <= port <= 65535:
            return _error(f"Invalid port number: {port}")
        
        # Limit timeout
        timeout = min(max(0.5, timeout), 10.0)
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        
        result = sock.connect_ex((host, port))
        sock.close()
        
        is_open = (result == 0)
        
        return _success({
            "host": host,
            "port": port,
            "open": is_open,
            "state": "open" if is_open else "closed/filtered"
        })
    except socket.gaierror:
        return _error(f"Could not resolve hostname: {host}")
    except Exception as e:
        return _error(str(e))


def dns_lookup(hostname: str) -> Dict[str, Any]:
    """
    Perform DNS lookup for a hostname.
    
    Args:
        hostname: Hostname to resolve
    
    Returns:
        Dict with resolved IP addresses
    """
    try:
        # Get all addresses
        addr_info = socket.getaddrinfo(hostname, None)
        
        ipv4_addresses = []
        ipv6_addresses = []
        
        for info in addr_info:
            family, _, _, _, sockaddr = info
            ip = sockaddr[0]
            
            if family == socket.AF_INET:
                if ip not in ipv4_addresses:
                    ipv4_addresses.append(ip)
            elif family == socket.AF_INET6:
                if ip not in ipv6_addresses:
                    ipv6_addresses.append(ip)
        
        return _success({
            "hostname": hostname,
            "ipv4": ipv4_addresses,
            "ipv6": ipv6_addresses
        })
    except socket.gaierror as e:
        return _error(f"DNS lookup failed: {e}")
    except Exception as e:
        return _error(str(e))


def system_info() -> Dict[str, Any]:
    """
    Get system information (hostname, uptime, load average).
    
    Returns:
        Dict with system information
    """
    try:
        info = {}
        
        # Hostname
        info['hostname'] = socket.gethostname()
        
        # Uptime
        try:
            with open('/proc/uptime', 'r') as f:
                uptime_seconds = float(f.readline().split()[0])
                days = int(uptime_seconds // 86400)
                hours = int((uptime_seconds % 86400) // 3600)
                minutes = int((uptime_seconds % 3600) // 60)
                info['uptime'] = f"{days}d {hours}h {minutes}m"
                info['uptime_seconds'] = int(uptime_seconds)
        except:
            pass
        
        # Load average
        try:
            with open('/proc/loadavg', 'r') as f:
                load = f.readline().split()[:3]
                info['load_average'] = {
                    '1min': float(load[0]),
                    '5min': float(load[1]),
                    '15min': float(load[2])
                }
        except:
            pass
        
        # Memory info
        try:
            with open('/proc/meminfo', 'r') as f:
                meminfo = {}
                for line in f:
                    parts = line.split(':')
                    if len(parts) == 2:
                        key = parts[0].strip()
                        value = parts[1].strip().split()[0]  # Get numeric value
                        if key in ['MemTotal', 'MemFree', 'MemAvailable']:
                            meminfo[key] = int(value)
                
                if 'MemTotal' in meminfo and 'MemAvailable' in meminfo:
                    total_mb = meminfo['MemTotal'] / 1024
                    available_mb = meminfo['MemAvailable'] / 1024
                    used_mb = total_mb - available_mb
                    percent_used = (used_mb / total_mb) * 100
                    
                    info['memory'] = {
                        'total_mb': round(total_mb, 1),
                        'used_mb': round(used_mb, 1),
                        'available_mb': round(available_mb, 1),
                        'percent_used': round(percent_used, 1)
                    }
        except:
            pass
        
        return _success(info)
    except Exception as e:
        return _error(str(e))


def disk_usage(path: str = "/") -> Dict[str, Any]:
    """
    Get disk usage for a path.
    
    Args:
        path: Path to check (default: /)
    
    Returns:
        Dict with disk usage statistics
    """
    try:
        result = subprocess.run(
            ["df", "-h", path],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode != 0:
            return _error(f"df command failed: {result.stderr}")
        
        lines = result.stdout.strip().split('\n')
        if len(lines) < 2:
            return _error("Unexpected df output")
        
        # Parse df output
        header = lines[0].split()
        data = lines[1].split()
        
        if len(data) >= 5:
            return _success({
                "path": path,
                "filesystem": data[0],
                "size": data[1],
                "used": data[2],
                "available": data[3],
                "use_percent": data[4],
                "mounted_on": data[5] if len(data) > 5 else path
            })
        
        return _error("Could not parse df output")
    except subprocess.TimeoutExpired:
        return _error("df command timeout")
    except Exception as e:
        return _error(str(e))


def process_list(filter_name: str = None) -> Dict[str, Any]:
    """
    List running processes (optionally filtered by name).
    
    Args:
        filter_name: Optional process name filter
    
    Returns:
        Dict with process list
    """
    try:
        cmd = ["ps", "aux"]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode != 0:
            return _error(f"ps command failed: {result.stderr}")
        
        lines = result.stdout.strip().split('\n')
        processes = []
        
        for line in lines[1:]:  # Skip header
            if filter_name and filter_name.lower() not in line.lower():
                continue
            
            parts = line.split(None, 10)
            if len(parts) >= 11:
                processes.append({
                    "user": parts[0],
                    "pid": parts[1],
                    "cpu": parts[2],
                    "mem": parts[3],
                    "command": parts[10][:100]  # Limit command length
                })
        
        # Limit number of processes returned
        processes = processes[:50]
        
        return _success({
            "count": len(processes),
            "filter": filter_name,
            "processes": processes
        })
    except subprocess.TimeoutExpired:
        return _error("ps command timeout")
    except Exception as e:
        return _error(str(e))
