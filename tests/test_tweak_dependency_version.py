import tempfile
from pathlib import Path

import multi_repo_automation as mra

from python_versions_hook import _tweak_dependency_version


def test_tweak_dependency_version_add():
    with mra.EditTOML(Path(__file__).parent / "test_data" / "test_pyproject_no_project.toml") as edit:
        _tweak_dependency_version(edit)

        assert edit["project"]["optional-dependencies"]["extra"] == ["pkg_in_extra==1.2.3"]
        assert set(edit["project"]["dependencies"]) == set(
            [
                "pkg_major<2,>=1",
                "pkg_minor<1.3,>=1.2",
                "pkg_patch<1.2.4,>=1.2.3",
                "pkg_patch_error==1.2",
                "pkg_present",
                "pkg_no==1.2.3",
                "pkg_extra[extra]==1.2.3",
                "pkg_set<3.0.0,>=1.0.0",
            ]
        )


def test_tweak_dependency_version_replace():
    with mra.EditTOML(Path(__file__).parent / "test_data" / "test_pyproject.toml") as edit:
        _tweak_dependency_version(edit)

        assert edit["project"]["optional-dependencies"]["extra"] == ["pkg_in_extra==1.2.3"]
        assert set(edit["project"]["dependencies"]) == set(
            [
                "pkg_only==2.3.4",
                "pkg_major<2,>=1",
                "pkg_minor<1.3,>=1.2",
                "pkg_patch<1.2.4,>=1.2.3",
                "pkg_patch_error==1.2",
                "pkg_present",
                "pkg_no==1.2.3",
                "pkg_extra[extra]==1.2.3",
                "pkg_set<3.0.0,>=1.0.0",
            ]
        )


def test_tweak_dependency_version_poetry_add():
    """Test that function does nothing when no configuration is present."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml") as f:
        f.write("""
[project]
dependencies = ["requests==2.25.1", "beaker (>=1.13.0,<2.0.0)"]

[tool.poetry.dependencies]
requests = "2.25.1"

[tool.poetry-plugin-tweak-dependencies-version]
default = "present"
""")
        f.flush()

        with mra.EditTOML(Path(f.name)) as edit:
            _tweak_dependency_version(edit)
            assert "beaker" in edit["tool"]["poetry"]["dependencies"]


def test_tweak_dependency_version_no_config():
    """Test that function does nothing when no configuration is present."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml") as f:
        f.write("""
[project]
dependencies = ["requests==2.25.1"]

[tool.poetry.dependencies]
requests = "2.25.1"
""")
        f.flush()

        with mra.EditTOML(Path(f.name)) as edit:
            original_deps = edit.get("project", {}).get("dependencies", [])[:]
            _tweak_dependency_version(edit)
            # Should remain unchanged
            assert edit.get("project", {}).get("dependencies", []) == original_deps


def test_tweak_dependency_version_legacy_config_name():
    """Test that function works with legacy configuration name."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml") as f:
        f.write("""
[project]
dependencies = ["requests==2.25.1"]

[tool.poetry.dependencies]
requests = "2.25.1"

[tool.poetry-plugin-tweak-dependencies-version]
requests = "major"
""")
        f.flush()

        with mra.EditTOML(Path(f.name)) as edit:
            _tweak_dependency_version(edit)
            assert "requests<3,>=2" in edit["project"]["dependencies"]


def test_tweak_dependency_version_major_modifier():
    """Test major version modifier."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml") as f:
        f.write("""
[project]
dependencies = []

[tool.poetry.dependencies]
test_pkg = "2.5.3"

[tool.tweak-poetry-dependencies-versions]
test_pkg = "major"
""")
        f.flush()

        with mra.EditTOML(Path(f.name)) as edit:
            _tweak_dependency_version(edit)
            assert "test_pkg<3,>=2" in edit["project"]["dependencies"]


def test_tweak_dependency_version_minor_modifier():
    """Test minor version modifier."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml") as f:
        f.write("""
[project]
dependencies = []

[tool.poetry.dependencies]
test_pkg = "2.5.3"

[tool.tweak-poetry-dependencies-versions]
test_pkg = "minor"
""")
        f.flush()

        with mra.EditTOML(Path(f.name)) as edit:
            _tweak_dependency_version(edit)
            assert "test_pkg<2.6,>=2.5" in edit["project"]["dependencies"]


def test_tweak_dependency_version_patch_modifier():
    """Test patch version modifier."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml") as f:
        f.write("""
[project]
dependencies = []

[tool.poetry.dependencies]
test_pkg = "2.5.3"

[tool.tweak-poetry-dependencies-versions]
test_pkg = "patch"
""")
        f.flush()

        with mra.EditTOML(Path(f.name)) as edit:
            _tweak_dependency_version(edit)
            assert "test_pkg<2.5.4,>=2.5.3" in edit["project"]["dependencies"]


def test_tweak_dependency_version_full_modifier():
    """Test full version modifier (exact version)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml") as f:
        f.write("""
[project]
dependencies = []

[tool.poetry.dependencies]
test_pkg = "2.5.3"

[tool.tweak-poetry-dependencies-versions]
test_pkg = "full"
""")
        f.flush()

        with mra.EditTOML(Path(f.name)) as edit:
            _tweak_dependency_version(edit)
            assert "test_pkg==2.5.3" in edit["project"]["dependencies"]


def test_tweak_dependency_version_present_modifier():
    """Test present modifier (no version constraint)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml") as f:
        f.write("""
[project]
dependencies = []

[tool.poetry.dependencies]
test_pkg = "2.5.3"

[tool.tweak-poetry-dependencies-versions]
test_pkg = "present"
""")
        f.flush()

        with mra.EditTOML(Path(f.name)) as edit:
            _tweak_dependency_version(edit)
            assert "test_pkg" in edit["project"]["dependencies"]
            # Should not have version constraints
            deps_without_constraints = [dep for dep in edit["project"]["dependencies"] if dep == "test_pkg"]
            assert len(deps_without_constraints) == 1


def test_tweak_dependency_version_custom_constraint():
    """Test custom version constraint."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml") as f:
        f.write("""
[project]
dependencies = []

[tool.poetry.dependencies]
test_pkg = "2.5.3"

[tool.tweak-poetry-dependencies-versions]
test_pkg = ">=2.0.0,<3.0.0"
""")
        f.flush()

        with mra.EditTOML(Path(f.name)) as edit:
            _tweak_dependency_version(edit)
            assert "test_pkg<3.0.0,>=2.0.0" in edit["project"]["dependencies"]


def test_tweak_dependency_version_with_extras():
    """Test dependency with extras."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml") as f:
        f.write("""
[project]
dependencies = []

[tool.poetry.dependencies]
test_pkg = { version = "2.5.3", extras = ["dev", "test"] }

[tool.tweak-poetry-dependencies-versions]
test_pkg = "major"
""")
        f.flush()

        with mra.EditTOML(Path(f.name)) as edit:
            _tweak_dependency_version(edit)
            # Should preserve extras
            deps_with_extras = [dep for dep in edit["project"]["dependencies"] if "[dev,test]" in dep]
            assert len(deps_with_extras) == 1
            assert "test_pkg[dev,test]<3,>=2" in edit["project"]["dependencies"]


def test_tweak_dependency_version_optional_dependency():
    """Test optional dependency handling."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml") as f:
        f.write("""
[project]
dependencies = []

[project.optional-dependencies]
dev = []

[tool.poetry.dependencies]
test_pkg = { version = "2.5.3", optional = true }

[tool.poetry.extras]
dev = ["test_pkg"]

[tool.tweak-poetry-dependencies-versions]
test_pkg = "major"
""")
        f.flush()

        with mra.EditTOML(Path(f.name)) as edit:
            _tweak_dependency_version(edit)
            # Should appear in optional dependencies, not main dependencies
            assert "test_pkg<3,>=2" in edit["project"]["optional-dependencies"]["dev"]
            assert "test_pkg<3,>=2" not in edit["project"]["dependencies"]


def test_tweak_dependency_version_default_modifier():
    """Test default modifier when none specified."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml") as f:
        f.write("""
[project]
dependencies = []

[tool.poetry.dependencies]
test_pkg = "2.5.3"

[tool.tweak-poetry-dependencies-versions]
default = "major"
""")
        f.flush()

        with mra.EditTOML(Path(f.name)) as edit:
            _tweak_dependency_version(edit)
            # Should use default modifier
            assert "test_pkg<3,>=2" in edit["project"]["dependencies"]


def test_tweak_dependency_version_invalid_version():
    """Test handling of invalid version strings."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml") as f:
        f.write("""
[project]
dependencies = []

[tool.poetry.dependencies]
test_pkg = "invalid.version.string"

[tool.tweak-poetry-dependencies-versions]
test_pkg = "major"
""")
        f.flush()

        with mra.EditTOML(Path(f.name)) as edit:
            _tweak_dependency_version(edit)
            # Should skip invalid versions
            assert edit["project"]["dependencies"] == []


def test_tweak_dependency_version_python_dependency_skipped():
    """Test that python dependency is skipped."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml") as f:
        f.write("""
[project]
dependencies = []

[tool.poetry.dependencies]
python = "^3.8"
test_pkg = "2.5.3"

[tool.tweak-poetry-dependencies-versions]
python = "major"
test_pkg = "major"
""")
        f.flush()

        with mra.EditTOML(Path(f.name)) as edit:
            _tweak_dependency_version(edit)
            # Python should be skipped, test_pkg should be processed
            assert "python" not in str(edit["project"]["dependencies"])
            assert "test_pkg<3,>=2" in edit["project"]["dependencies"]
