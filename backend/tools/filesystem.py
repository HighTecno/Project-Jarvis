import os
from ..config import SAFE_FILESYSTEM_ROOT


def _success(output):
    return {"status": "success", "output": output}


def _error(message):
    return {"status": "error", "error": message}


def _check_symlink_safety(path, allow_symlinks=False):
    """
    Check if a path is safe to use, detecting and validating symlinks.
    
    Args:
        path: The path to check
        allow_symlinks: If False, reject any symlinks in the path
    
    Returns:
        tuple: (is_safe, error_message)
    """
    # Check if the path itself is a symlink
    if os.path.islink(path):
        if not allow_symlinks:
            return False, f"Path is a symbolic link: {path}"
        
        # If symlinks are allowed, ensure the target stays within bounds
        target = os.readlink(path)
        if os.path.isabs(target):
            # Absolute symlink - needs to be validated
            real_target = os.path.realpath(path)
            root = os.path.realpath(SAFE_FILESYSTEM_ROOT)
            try:
                common = os.path.commonpath([real_target, root])
                if common != root:
                    return False, f"Symlink target escapes safe root: {target}"
            except ValueError:
                return False, f"Invalid symlink target: {target}"
    
    # Check if any parent directories are symlinks
    current = path
    while current != '/':
        parent = os.path.dirname(current)
        if parent == current:  # Reached root
            break
        if os.path.islink(parent):
            if not allow_symlinks:
                return False, f"Path contains symbolic link in parent: {parent}"
        current = parent
    
    return True, None


def _validate_read_path(path, allow_symlinks=False):
    if not isinstance(path, str) or not path.strip():
        raise ValueError("Path must be a non-empty string")
    
    # Check for symlinks before resolving
    safe, error = _check_symlink_safety(path, allow_symlinks)
    if not safe:
        raise ValueError(error)
    
    return os.path.realpath(path)


def _validate_write_path(path, allow_symlinks=False):
    if not isinstance(path, str) or not path.strip():
        raise ValueError("Path must be a non-empty string")

    root = os.path.realpath(SAFE_FILESYSTEM_ROOT)
    candidate = path
    if not os.path.isabs(candidate):
        candidate = os.path.join(root, candidate)

    # Check for symlinks before resolving
    if os.path.exists(candidate):
        safe, error = _check_symlink_safety(candidate, allow_symlinks)
        if not safe:
            raise ValueError(error)

    resolved = os.path.realpath(candidate)

    try:
        common = os.path.commonpath([resolved, root])
    except ValueError:
        raise ValueError("Invalid path")

    if common != root:
        raise ValueError("Path escapes allowed root /workspace")

    return resolved

def read(file_path):
    try:
        path = _validate_read_path(file_path)
        with open(path, 'r') as f:
            return _success(f.read())
    except Exception as exc:
        return _error(str(exc))

def write(file_path, content):
    try:
        path = _validate_write_path(file_path)
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, 'w') as f:
            f.write(content)
        return _success(f"Wrote {len(content)} bytes to {path}")
    except Exception as exc:
        return _error(str(exc))

def list_dir(path="."):
    try:
        validated_path = _validate_read_path(path)
        if not os.path.isdir(validated_path):
            raise ValueError("Path is not a directory")
        return _success(os.listdir(validated_path))
    except Exception as exc:
        return _error(str(exc))


def search(pattern, base_path="/"):
    try:
        base = _validate_read_path(base_path)
        if not os.path.isdir(base):
            return _error("base_path is not a directory")
        import glob
        results = glob.glob(os.path.join(base, "**", pattern), recursive=True)
        return _success(results[:100])
    except Exception as exc:
        return _error(str(exc))


def info(file_path):
    try:
        path = _validate_read_path(file_path)
        s = os.stat(path)
        return _success({
            "path": path,
            "size_bytes": s.st_size,
            "is_dir": os.path.isdir(path),
            "is_file": os.path.isfile(path),
            "modified": s.st_mtime,
        })
    except Exception as exc:
        return _error(str(exc))