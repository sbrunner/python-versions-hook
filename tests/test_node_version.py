# Copyright (c) 2026, Stéphane Brunner

"""
Pytest suite for Node.js version detection and .pre-commit-config.yaml synchronization.
"""

import shutil
import tempfile
from pathlib import Path

import multi_repo_automation as mra
import pytest

import python_versions_hook
from python_versions_hook import (
    _detect_node_version,
    _get_node_version_from_file,
    _node_needs_update,
    _node_version_matches,
    _resolve_latest_node,
    _update_node_language_version,
)

# Fake nodejs.org release index (newest first) so no test ever hits the network.
FAKE_INDEX = [
    {"version": "v24.11.0"},
    {"version": "v22.23.3"},
    {"version": "v22.23.2"},
    {"version": "v22.22.0"},
    {"version": "v20.19.0"},
    {"version": "v18.20.4"},
]


@pytest.fixture
def node_index(monkeypatch):
    """Stub the Node.js release index to avoid any network access."""
    monkeypatch.setattr(python_versions_hook, "_get_node_index", lambda: FAKE_INDEX)
    return FAKE_INDEX


@pytest.fixture
def work_dir():
    """Create an isolated temporary directory."""
    directory = Path(tempfile.mkdtemp(prefix="python_version_hook_node_test_"))
    yield directory
    shutil.rmtree(directory)


def _write_config(directory: Path, node_value: str | None = "20.19.0") -> Path:
    """Write a minimal .pre-commit-config.yaml, omitting node when node_value is None."""
    lines = ["default_language_version:", "  python: '3.12'"]
    if node_value is not None:
        lines.append(f"  node: '{node_value}'")
    lines.append("repos: []")
    config_path = directory / ".pre-commit-config.yaml"
    config_path.write_text("\n".join(lines) + "\n")
    return config_path


def _read_node(config_path: Path) -> str | None:
    with mra.EditPreCommitConfig(config_path, run_pre_commit=False) as pre_commit:
        return pre_commit.get("default_language_version", {}).get("node")


# --- .nvmrc reading ---


def test_get_node_version_from_file_major(work_dir):
    (work_dir / ".nvmrc").write_text("22\n")
    assert _get_node_version_from_file(work_dir) == "22"


def test_get_node_version_from_file_v_prefix_full(work_dir):
    (work_dir / ".nvmrc").write_text("v22.23.2")
    assert _get_node_version_from_file(work_dir) == "22.23.2"


def test_get_node_version_from_file_inline_comment(work_dir):
    (work_dir / ".nvmrc").write_text("22.23 # comment\n")
    assert _get_node_version_from_file(work_dir) == "22.23"


def test_get_node_version_from_file_missing(work_dir):
    assert _get_node_version_from_file(work_dir) is None


def test_get_node_version_from_file_empty(work_dir):
    (work_dir / ".nvmrc").write_text("   \n")
    assert _get_node_version_from_file(work_dir) is None


def test_get_node_version_from_file_alias_ignored(work_dir):
    (work_dir / ".nvmrc").write_text("lts/jod")
    assert _get_node_version_from_file(work_dir) is None


# --- detection (recursive) ---


def test_detect_node_version_local(work_dir):
    (work_dir / ".nvmrc").write_text("22")
    assert _detect_node_version(work_dir) == "22"


def test_detect_node_version_inherits_parent(work_dir):
    (work_dir / ".nvmrc").write_text("24")
    child = work_dir / "child"
    child.mkdir()
    assert _detect_node_version(child) == "24"


def test_detect_node_version_local_wins_over_parent(work_dir):
    (work_dir / ".nvmrc").write_text("24")
    child = work_dir / "child"
    child.mkdir()
    (child / ".nvmrc").write_text("20")
    assert _detect_node_version(child) == "20"


# --- version matching ---


def test_node_version_matches():
    assert _node_version_matches("22.23.2", "22")
    assert _node_version_matches("22.23.2", "22.23")
    assert _node_version_matches("22.23.2", "22.23.2")
    assert _node_version_matches("v22.23.2", "v22")
    assert not _node_version_matches("22.23.2", "20")
    assert not _node_version_matches("22.23.2", "22.24")
    assert not _node_version_matches("22.30.0", "22.3")


def test_node_needs_update():
    # A full version matching the spec is kept as-is
    assert not _node_needs_update("22.23.2", "22")
    assert not _node_needs_update("v22.23.2", "22")
    # A full version from another major must be replaced
    assert _node_needs_update("20.19.0", "22")
    # A bare major/minor is not a valid nodeenv version and must be resolved
    assert _node_needs_update("22", "22")
    assert _node_needs_update("22.23", "22")


# --- resolution against the release index ---


def test_resolve_latest_node(node_index):
    assert _resolve_latest_node("22") == "22.23.3"
    assert _resolve_latest_node("22.23") == "22.23.3"
    assert _resolve_latest_node("22.22") == "22.22.0"
    assert _resolve_latest_node("20") == "20.19.0"
    assert _resolve_latest_node("18") == "18.20.4"


def test_resolve_latest_node_no_match(node_index):
    assert _resolve_latest_node("99") is None


def test_resolve_latest_node_index_unavailable(monkeypatch):
    monkeypatch.setattr(python_versions_hook, "_get_node_index", lambda: None)
    assert _resolve_latest_node("22") is None


# --- end-to-end config update ---


def test_update_node_incompatible_major(node_index, work_dir):
    (work_dir / ".nvmrc").write_text("22")
    config_path = _write_config(work_dir, node_value="20.19.0")
    with mra.EditPreCommitConfig(config_path, run_pre_commit=False) as pre_commit:
        _update_node_language_version(work_dir, pre_commit)
    assert _read_node(config_path) == "22.23.3"


def test_update_node_compatible_left_untouched(node_index, work_dir):
    (work_dir / ".nvmrc").write_text("22")
    config_path = _write_config(work_dir, node_value="22.23.2")
    with mra.EditPreCommitConfig(config_path, run_pre_commit=False) as pre_commit:
        _update_node_language_version(work_dir, pre_commit)
    assert _read_node(config_path) == "22.23.2"


def test_update_node_bare_major_resolved(node_index, work_dir):
    (work_dir / ".nvmrc").write_text("22")
    config_path = _write_config(work_dir, node_value="22")
    with mra.EditPreCommitConfig(config_path, run_pre_commit=False) as pre_commit:
        _update_node_language_version(work_dir, pre_commit)
    assert _read_node(config_path) == "22.23.3"


def test_update_node_key_absent_not_added(node_index, work_dir):
    (work_dir / ".nvmrc").write_text("22")
    config_path = _write_config(work_dir, node_value=None)
    with mra.EditPreCommitConfig(config_path, run_pre_commit=False) as pre_commit:
        _update_node_language_version(work_dir, pre_commit)
    assert _read_node(config_path) is None


def test_update_node_index_unavailable_leaves_value(node_index, work_dir, monkeypatch):
    (work_dir / ".nvmrc").write_text("22")
    monkeypatch.setattr(python_versions_hook, "_get_node_index", lambda: None)
    config_path = _write_config(work_dir, node_value="20.19.0")
    with mra.EditPreCommitConfig(config_path, run_pre_commit=False) as pre_commit:
        _update_node_language_version(work_dir, pre_commit)
    assert _read_node(config_path) == "20.19.0"
