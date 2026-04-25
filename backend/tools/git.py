"""Git operations and repository management tools"""
import os
import re
from typing import Dict, Any, Optional

try:
    from backend.tools import terminal
except ImportError:
    try:
        from tools import terminal
    except ImportError:
        from . import terminal


def _success(output):
    return {"status": "success", "output": output}


def _error(message):
    return {"status": "error", "error": message}


def status(repo_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Get git repository status including branch, uncommitted changes, and remote status.
    
    Args:
        repo_path: Path to git repository (optional, defaults to current directory)
    
    Returns:
        Dict with repository status information
    """
    try:
        cwd = repo_path if repo_path else None
        
        # Check if we're in a git repo
        check_result = terminal.run("git rev-parse --is-inside-work-tree", timeout_seconds=5, cwd=cwd)
        if check_result.get("status") != "success":
            return _error("Not a git repository")
        
        # Get branch name
        branch_result = terminal.run("git branch --show-current", timeout_seconds=5, cwd=cwd)
        branch = branch_result.get("output", "").strip() if branch_result.get("status") == "success" else "unknown"
        
        # Get status
        status_result = terminal.run("git status --porcelain", timeout_seconds=10, cwd=cwd)
        status_output = status_result.get("output", "") if status_result.get("status") == "success" else ""
        
        # Parse status
        modified_files = []
        staged_files = []
        untracked_files = []
        
        for line in status_output.split('\n'):
            if not line.strip():
                continue
            
            status_code = line[:2]
            file_path = line[3:].strip()
            
            if status_code[0] in ['M', 'A', 'D', 'R', 'C']:
                staged_files.append(file_path)
            elif status_code[1] in ['M', 'D']:
                modified_files.append(file_path)
            elif status_code == '??':
                untracked_files.append(file_path)
        
        # Get remote status
        remote_result = terminal.run("git remote -v", timeout_seconds=5, cwd=cwd)
        remote_output = remote_result.get("output", "") if remote_result.get("status") == "success" else ""
        
        remotes = []
        for line in remote_output.split('\n'):
            if '(fetch)' in line:
                parts = line.split()
                if len(parts) >= 2:
                    remotes.append({"name": parts[0], "url": parts[1]})
        
        # Check if ahead/behind remote
        ahead_behind = None
        if branch and remotes:
            ahead_behind_result = terminal.run(f"git rev-list --left-right --count origin/{branch}...HEAD", timeout_seconds=5, cwd=cwd)
            if ahead_behind_result.get("status") == "success":
                output = ahead_behind_result.get("output", "").strip()
                if output:
                    parts = output.split()
                    if len(parts) == 2:
                        behind, ahead = parts
                        ahead_behind = {"ahead": int(ahead), "behind": int(behind)}
        
        # Get last commit
        last_commit_result = terminal.run('git log -1 --pretty=format:"%h - %s (%cr by %an)"', timeout_seconds=5, cwd=cwd)
        last_commit = last_commit_result.get("output", "").strip() if last_commit_result.get("status") == "success" else None
        
        result = {
            "branch": branch,
            "clean": len(modified_files) == 0 and len(staged_files) == 0 and len(untracked_files) == 0,
            "modified_files": modified_files,
            "staged_files": staged_files,
            "untracked_files": untracked_files,
            "remotes": remotes,
            "ahead_behind": ahead_behind,
            "last_commit": last_commit
        }
        
        return _success(result)
        
    except Exception as e:
        return _error(f"Failed to get git status: {str(e)}")


def commit(message: str, repo_path: Optional[str] = None, add_all: bool = False) -> Dict[str, Any]:
    """
    Create a git commit with the given message.
    
    Args:
        message: Commit message
        repo_path: Path to git repository (optional)
        add_all: If True, stage all modified files before committing
    
    Returns:
        Dict with commit result
    """
    try:
        if not message or not message.strip():
            return _error("Commit message cannot be empty")
        
        cwd = repo_path if repo_path else None
        
        # Add files if requested
        if add_all:
            add_result = terminal.run("git add -A", timeout_seconds=10, cwd=cwd)
            if add_result.get("status") != "success":
                return _error(f"Failed to stage files: {add_result.get('error', 'Unknown error')}")
        
        # Check if there's anything to commit
        status_result = terminal.run("git status --porcelain", timeout_seconds=5, cwd=cwd)
        if status_result.get("status") == "success":
            status_output = status_result.get("output", "")
            if not any(line.startswith(('M', 'A', 'D', 'R', 'C')) for line in status_output.split('\n')):
                return _error("No staged changes to commit")
        
        # Escape commit message for shell
        escaped_message = message.replace('"', '\\"').replace('$', '\\$').replace('`', '\\`')
        
        # Commit
        commit_result = terminal.run(f'git commit -m "{escaped_message}"', timeout_seconds=15, cwd=cwd)
        
        if commit_result.get("status") != "success":
            return commit_result
        
        # Get commit hash
        hash_result = terminal.run("git rev-parse HEAD", timeout_seconds=5, cwd=cwd)
        commit_hash = hash_result.get("output", "").strip()[:8] if hash_result.get("status") == "success" else "unknown"
        
        result = {
            "committed": True,
            "commit_hash": commit_hash,
            "message": message,
            "output": commit_result.get("output", "")
        }
        
        return _success(result)
        
    except Exception as e:
        return _error(f"Commit failed: {str(e)}")


def push(repo_path: Optional[str] = None, remote: str = "origin", branch: Optional[str] = None) -> Dict[str, Any]:
    """
    Push commits to remote repository.
    
    Args:
        repo_path: Path to git repository (optional)
        remote: Remote name (default: origin)
        branch: Branch to push (optional, uses current branch if not specified)
    
    Returns:
        Dict with push result
    """
    try:
        cwd = repo_path if repo_path else None
        
        # Get current branch if not specified
        if not branch:
            branch_result = terminal.run("git branch --show-current", timeout_seconds=5, cwd=cwd)
            if branch_result.get("status") != "success":
                return _error("Failed to determine current branch")
            branch = branch_result.get("output", "").strip()
            if not branch:
                return _error("Not on any branch")
        
        # Check if there are commits to push
        ahead_result = terminal.run(f"git rev-list --count {remote}/{branch}..HEAD", timeout_seconds=5, cwd=cwd)
        if ahead_result.get("status") == "success":
            ahead_count = ahead_result.get("output", "").strip()
            if ahead_count == "0":
                return _error("No commits to push (already up to date)")
        
        # Push
        push_result = terminal.run(f"git push {remote} {branch}", timeout_seconds=30, cwd=cwd)
        
        if push_result.get("status") != "success":
            error_msg = push_result.get("error", "Unknown error")
            if "rejected" in error_msg.lower():
                return _error(f"Push rejected. Pull remote changes first: {error_msg}")
            return push_result
        
        result = {
            "pushed": True,
            "remote": remote,
            "branch": branch,
            "output": push_result.get("output", "")
        }
        
        return _success(result)
        
    except Exception as e:
        return _error(f"Push failed: {str(e)}")


def pull(repo_path: Optional[str] = None, remote: str = "origin", branch: Optional[str] = None) -> Dict[str, Any]:
    """
    Pull updates from remote repository.
    
    Args:
        repo_path: Path to git repository (optional)
        remote: Remote name (default: origin)
        branch: Branch to pull (optional, uses current branch if not specified)
    
    Returns:
        Dict with pull result
    """
    try:
        cwd = repo_path if repo_path else None
        
        # Get current branch if not specified
        if not branch:
            branch_result = terminal.run("git branch --show-current", timeout_seconds=5, cwd=cwd)
            if branch_result.get("status") != "success":
                return _error("Failed to determine current branch")
            branch = branch_result.get("output", "").strip()
            if not branch:
                return _error("Not on any branch")
        
        # Pull
        pull_result = terminal.run(f"git pull {remote} {branch}", timeout_seconds=30, cwd=cwd)
        
        if pull_result.get("status") != "success":
            error_msg = pull_result.get("error", "Unknown error")
            if "conflict" in error_msg.lower():
                return _error(f"Merge conflict detected: {error_msg}")
            return pull_result
        
        output = pull_result.get("output", "")
        already_up_to_date = "already up to date" in output.lower() or "already up-to-date" in output.lower()
        
        result = {
            "pulled": True,
            "remote": remote,
            "branch": branch,
            "up_to_date": already_up_to_date,
            "output": output
        }
        
        return _success(result)
        
    except Exception as e:
        return _error(f"Pull failed: {str(e)}")


def branch_list(repo_path: Optional[str] = None) -> Dict[str, Any]:
    """
    List all branches in the repository.
    
    Args:
        repo_path: Path to git repository (optional)
    
    Returns:
        Dict with list of branches
    """
    try:
        cwd = repo_path if repo_path else None
        
        # Get local branches
        local_result = terminal.run("git branch", timeout_seconds=5, cwd=cwd)
        if local_result.get("status") != "success":
            return local_result
        
        local_branches = []
        current_branch = None
        
        for line in local_result.get("output", "").split('\n'):
            line = line.strip()
            if not line:
                continue
            
            if line.startswith('* '):
                current_branch = line[2:].strip()
                local_branches.append(current_branch)
            else:
                local_branches.append(line)
        
        # Get remote branches
        remote_result = terminal.run("git branch -r", timeout_seconds=5, cwd=cwd)
        remote_branches = []
        
        if remote_result.get("status") == "success":
            for line in remote_result.get("output", "").split('\n'):
                line = line.strip()
                if line and not 'HEAD ->' in line:
                    remote_branches.append(line)
        
        result = {
            "current_branch": current_branch,
            "local_branches": local_branches,
            "remote_branches": remote_branches
        }
        
        return _success(result)
        
    except Exception as e:
        return _error(f"Failed to list branches: {str(e)}")


def create_branch(name: str, repo_path: Optional[str] = None, checkout: bool = True) -> Dict[str, Any]:
    """
    Create a new git branch.
    
    Args:
        name: Branch name
        repo_path: Path to git repository (optional)
        checkout: If True, switch to the new branch (default: True)
    
    Returns:
        Dict with branch creation result
    """
    try:
        if not name or not name.strip():
            return _error("Branch name cannot be empty")
        
        # Validate branch name
        if not re.match(r'^[a-zA-Z0-9/_-]+$', name):
            return _error("Invalid branch name. Use only letters, numbers, hyphens, underscores, and slashes.")
        
        cwd = repo_path if repo_path else None
        
        # Create branch
        if checkout:
            create_result = terminal.run(f"git checkout -b {name}", timeout_seconds=10, cwd=cwd)
        else:
            create_result = terminal.run(f"git branch {name}", timeout_seconds=10, cwd=cwd)
        
        if create_result.get("status") != "success":
            error_msg = create_result.get("error", "Unknown error")
            if "already exists" in error_msg.lower():
                return _error(f"Branch '{name}' already exists")
            return create_result
        
        result = {
            "created": True,
            "branch_name": name,
            "checked_out": checkout,
            "output": create_result.get("output", "")
        }
        
        return _success(result)
        
    except Exception as e:
        return _error(f"Failed to create branch: {str(e)}")
