# Copyright (c) 2026, Stéphane Brunner

"""Pytest suite for the main entry point of python-version-hook."""

import sys

import tomlkit

from python_versions_hook import main


def test_main_processes_root_pyproject(tmp_path, monkeypatch):
    """Test that the root pyproject.toml is processed (regression: the root directory was excluded)."""
    monkeypatch.setattr(sys, "argv", ["python-versions-hook"])
    (tmp_path / "pyproject.toml").write_text(
        """
[tool.poetry.dependencies]
python = ">=3.10,<4.0"
core-dep = "1.2.3"
optional-dep = { version = "4.5.6", optional = true }

[tool.poetry.extras]
my-extra = ["optional-dep"]

[tool.poetry-plugin-tweak-dependencies-version]
default = "major"

[project]
classifiers = [
    'Programming Language :: Python :: 3',
    'Programming Language :: Python :: 3.10',
]
requires-python = ">=3.10"
dependencies = ["core-dep<2,>=1"]
"""
    )
    monkeypatch.chdir(tmp_path)

    main()

    pyproject = tomlkit.parse((tmp_path / "pyproject.toml").read_text())
    # The required dependencies are kept in project.dependencies...
    assert list(pyproject["project"]["dependencies"]) == ["core-dep<2,>=1"]
    # ...and project.optional-dependencies is generated from tool.poetry.extras.
    assert dict(pyproject["project"]["optional-dependencies"]) == {"my-extra": ["optional-dep<5,>=4"]}
