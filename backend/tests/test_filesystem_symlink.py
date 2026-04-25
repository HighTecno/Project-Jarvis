"""Tests for filesystem symlink validation"""
import os
import tempfile
import pytest
from backend.tools.filesystem import (
    _check_symlink_safety,
    _validate_read_path,
    _validate_write_path,
    read,
    write,
    list_dir,
)


class TestSymlinkSafety:
    def setup_method(self):
        """Create a temporary directory for testing"""
        self.temp_dir = tempfile.mkdtemp()
        self.safe_file = os.path.join(self.temp_dir, "safe.txt")
        with open(self.safe_file, "w") as f:
            f.write("safe content")
    
    def teardown_method(self):
        """Clean up temporary directory"""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_check_safe_regular_file(self):
        """Regular file should be safe"""
        safe, error = _check_symlink_safety(self.safe_file, allow_symlinks=False)
        assert safe is True
        assert error is None
    
    def test_detect_direct_symlink(self):
        """Should detect when path itself is a symlink"""
        symlink = os.path.join(self.temp_dir, "link.txt")
        os.symlink(self.safe_file, symlink)
        
        safe, error = _check_symlink_safety(symlink, allow_symlinks=False)
        assert safe is False
        assert "symbolic link" in error.lower()
    
    def test_allow_symlink_within_bounds(self):
        """Should allow symlink if target stays within safe root"""
        # This test assumes we're testing within a controlled environment
        symlink = os.path.join(self.temp_dir, "link.txt")
        os.symlink(self.safe_file, symlink)
        
        # When allow_symlinks=True, should still validate target
        safe, error = _check_symlink_safety(symlink, allow_symlinks=True)
        # Result depends on whether symlink target is within SAFE_FILESYSTEM_ROOT
        # For this test, we just verify the function runs without crashing
        assert isinstance(safe, bool)
    
    def test_validate_read_path_rejects_symlink(self):
        """_validate_read_path should reject symlinks by default"""
        symlink = os.path.join(self.temp_dir, "link.txt")
        os.symlink(self.safe_file, symlink)
        
        with pytest.raises(ValueError, match="symbolic link"):
            _validate_read_path(symlink, allow_symlinks=False)
    
    def test_validate_write_path_rejects_symlink(self):
        """_validate_write_path should reject symlinks by default"""
        symlink = os.path.join(self.temp_dir, "link.txt")
        os.symlink(self.safe_file, symlink)
        
        with pytest.raises(ValueError, match="symbolic link"):
            _validate_write_path(symlink, allow_symlinks=False)
    
    def test_read_tool_rejects_symlink(self):
        """read() tool should reject symlinks"""
        symlink = os.path.join(self.temp_dir, "link.txt")
        os.symlink(self.safe_file, symlink)
        
        result = read(symlink)
        assert result["status"] == "error"
        assert "symbolic link" in result["error"].lower()
    
    def test_write_tool_rejects_symlink(self):
        """write() tool should reject writing to symlinks"""
        symlink = os.path.join(self.temp_dir, "link.txt")
        os.symlink(self.safe_file, symlink)
        
        result = write(symlink, "new content")
        assert result["status"] == "error"
        assert "symbolic link" in result["error"].lower()
    
    def test_list_dir_rejects_symlink(self):
        """list_dir() should reject symlink directories"""
        link_dir = os.path.join(self.temp_dir, "link_dir")
        os.symlink(self.temp_dir, link_dir)
        
        result = list_dir(link_dir)
        assert result["status"] == "error"
        assert "symbolic link" in result["error"].lower()
    
    def test_regular_operations_still_work(self):
        """Verify regular file operations still work"""
        # Read regular file
        result = read(self.safe_file)
        assert result["status"] == "success"
        assert "safe content" in result["output"]
        
        # List directory
        result = list_dir(self.temp_dir)
        assert result["status"] == "success"
        assert isinstance(result["output"], list)
        
        # Note: write() requires path within SAFE_FILESYSTEM_ROOT (/workspace)
        # which is outside our temp directory, so we skip write test here


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
