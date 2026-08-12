# Copyright (c) 2026, Stéphane Brunner

"""
Pytest suite for Python version detection in python-version-hook.
"""

import shutil
import tempfile
from pathlib import Path

import packaging.specifiers
import packaging.version
import pytest

from python_versions_hook import (
    _detect_python_version,
    _get_python_specifiers_version,
    _get_python_version_from_file,
)


@pytest.fixture
def test_dir():
    """Create a temporary directory structure for testing."""
    test_dir = Path(tempfile.mkdtemp(prefix="python_version_hook_test_"))

    # Root directory with pyproject.toml (Poetry)
    (test_dir / "pyproject.toml").write_text("""
[tool.poetry.dependencies]
python = "^3.8"
""")

    # Subdirectory with .python-version
    subdir1 = test_dir / "subdir1"
    subdir1.mkdir()
    (subdir1 / ".python-version").write_text("3.9")

    # Subdirectory with pyproject.toml (PEP 621)
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

    yield test_dir

    # Cleanup
    shutil.rmtree(test_dir)


def test_get_python_version_from_file(test_dir):
    """Test reading .python-version from a directory."""
    # Test with existing .python-version
    version = _get_python_version_from_file(test_dir / "subdir1")
    assert version == packaging.version.parse("3.9")

    # Test with non-existing .python-version
    version = _get_python_version_from_file(test_dir / "subdir2")
    assert version is None


def test_get_python_specifiers_version(test_dir):
    """Test reading Python version from pyproject.toml."""
    # Test Poetry syntax (^3.8 → >=3.8,<4.0)
    version_set = _get_python_specifiers_version(test_dir / "pyproject.toml")
    assert str(version_set) == "<4.0,>=3.8"

    # Test PEP 621 syntax (>=3.10)
    version_set = _get_python_specifiers_version(test_dir / "subdir2" / "pyproject.toml")
    assert str(version_set) == ">=3.10"


def test_detect_python_version(test_dir):
    """Test version detection for all directories."""
    test_cases = [
        (test_dir, "<4.0,>=3.8"),  # Root: pyproject.toml (Poetry)
        (test_dir / "subdir1", "3.9"),  # subdir1: .python-version
        (test_dir / "subdir2", ">=3.10"),  # subdir2: pyproject.toml (PEP 621)
        (test_dir / "subdir2" / "subdir3", ">=3.10"),  # subdir3: inherits from subdir2
        (test_dir / "subdir4", ">=3.11"),  # subdir4: pyproject.toml (Poetry)
    ]

    for directory, expected in test_cases:
        version = _detect_python_version(directory)

        if isinstance(version, packaging.specifiers.SpecifierSet):
            version_str = ",".join(sorted(str(s) for s in version))
        else:
            version_str = str(version)

        assert version_str == expected, (
            f"Failed for {directory.relative_to(test_dir)}: expected {expected}, got {version_str}"
        )
