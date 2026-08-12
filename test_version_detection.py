#!/usr/bin/env python3

"""
Test script for Python version detection in python-version-hook.

Usage:
    python test_version_detection.py
"""

import os
import shutil
import tempfile
from pathlib import Path

import packaging.specifiers
import packaging.version

from python_versions_hook import _detect_python_version, _get_python_version_from_file


def create_test_structure() -> Path:
    """Create a temporary directory structure for testing."""
    test_dir = Path(tempfile.mkdtemp(prefix="python_version_hook_test_"))
    
    # Root directory with pyproject.toml
    (test_dir / "pyproject.toml").write_text("""
[tool.poetry.dependencies]
python = "^3.8"
""")
    
    # Subdirectory with .python-version
    subdir1 = test_dir / "subdir1"
    subdir1.mkdir()
    (subdir1 / ".python-version").write_text("3.9")
    
    # Subdirectory with pyproject.toml
    subdir2 = test_dir / "subdir2"
    subdir2.mkdir()
    (subdir2 / "pyproject.toml").write_text("""
[project]
requires-python = ">=3.10"
""")
    
    # Subdirectory without version files (should inherit from parent)
    subdir3 = subdir2 / "subdir3"
    subdir3.mkdir()
    
    # Subdirectory with both files (pyproject.toml should take precedence)
    subdir4 = test_dir / "subdir4"
    subdir4.mkdir()
    (subdir4 / "pyproject.toml").write_text("""
[tool.poetry.dependencies]
python = ">=3.11"
""")
    (subdir4 / ".python-version").write_text("3.7")
    
    return test_dir


def test_version_detection(test_dir: Path) -> None:
    """Test version detection for all directories."""
    test_cases = [
        (test_dir, "<4.0,>=3.8"),  # Root: pyproject.toml (Poetry ^3.8 → <4.0,>=3.8)
        (test_dir / "subdir1", "3.9"),  # subdir1: .python-version
        (test_dir / "subdir2", ">=3.10"),  # subdir2: pyproject.toml (PEP 621)
        (test_dir / "subdir2" / "subdir3", ">=3.10"),  # subdir3: inherits from subdir2
        (test_dir / "subdir4", ">=3.11"),  # subdir4: pyproject.toml (Poetry ^3.11 → >=3.11,<4.0 mais <4.0 est ignoré car déjà couvert par >=3.11)
    ]
    
    for directory, expected in test_cases:
        print(f"\nTesting directory: {directory.relative_to(test_dir)}")
        version = _detect_python_version(directory)
        
        if version is None:
            print(f"  ❌ FAIL: No version detected (expected: {expected})")
            continue
        
        if isinstance(version, packaging.specifiers.SpecifierSet):
            version_str = ",".join(sorted(str(s) for s in version))
        else:
            version_str = str(version)
        
        if version_str == expected:
            print(f"  ✅ PASS: Detected version = {version_str}")
        else:
            print(f"  ❌ FAIL: Detected version = {version_str} (expected: {expected})")


def test_get_python_version_from_file(test_dir: Path) -> None:
    """Test reading .python-version from a directory."""
    print("\nTesting _get_python_version_from_file():")
    
    # Test with existing .python-version
    version = _get_python_version_from_file(test_dir / "subdir1")
    if version and str(version) == "3.9":
        print("  ✅ PASS: Read .python-version correctly")
    else:
        print(f"  ❌ FAIL: Expected 3.9, got {version}")
    
    # Test with non-existing .python-version
    version = _get_python_version_from_file(test_dir / "subdir2")
    if version is None:
        print("  ✅ PASS: Returned None for missing .python-version")
    else:
        print(f"  ❌ FAIL: Expected None, got {version}")


def main() -> None:
    """Run all tests."""
    print("Creating test directory structure...")
    test_dir = create_test_structure()
    
    try:
        print(f"Test directory: {test_dir}")
        test_version_detection(test_dir)
        test_get_python_version_from_file(test_dir)
    finally:
        # Cleanup
        shutil.rmtree(test_dir)
        print(f"\nCleanup: Removed test directory {test_dir}")


if __name__ == "__main__":
    main()