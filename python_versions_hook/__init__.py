# Copyright (c) 2023-2026, Stéphane Brunner

"""Python versions hooks."""

import argparse
import pkgutil
import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypedDict

import multi_repo_automation as mra
import packaging.requirements
import packaging.specifiers
import packaging.utils
import packaging.version
import requests
import tomlkit


def _filenames(pattern: str) -> list[Path]:
    return [
        Path(file)
        for file in subprocess.run(  # noqa: S603 # nosec
            ["git", "ls-files", pattern],  # noqa: S607
            check=True,
            stdout=subprocess.PIPE,
            encoding="utf-8",
        ).stdout.splitlines()
    ]


_digit = re.compile("([0-9]+)")


def _natural_sort_key(text: str) -> list[int | str]:
    return [int(value) if value.isdigit() else value.lower() for value in _digit.split(text)]


def _get_python_version_from_file(directory: Path) -> packaging.version.Version | None:
    """Read Python version from .python-version file in a directory."""
    python_version_path = directory / ".python-version"
    if python_version_path.exists():
        raw = python_version_path.read_text().strip()
        try:
            return packaging.version.parse(raw)
        except packaging.version.InvalidVersion:
            # pyenv uses "system" to indicate the system Python; not a parseable version
            return None
    return None


def _detect_python_version(
    directory: Path,
) -> packaging.specifiers.SpecifierSet | packaging.version.Version | None:
    """
    Detect Python version for a directory.

    With priority:
    1. pyproject.toml (local)
    2. .python-version (local)
    3. Parent directory (recursive)
    """
    # 1. Check pyproject.toml
    pyproject_path = directory / "pyproject.toml"
    if pyproject_path.exists():
        version_set = _get_python_specifiers_version(pyproject_path)
        if version_set is not None:
            return version_set

    # 2. Check .python-version
    version = _get_python_version_from_file(directory)
    if version is not None:
        return version

    # 3. Recursively check parent directory
    parent = directory.parent
    if parent != directory:  # Avoid infinite loop at root
        return _detect_python_version(parent)

    return None  # No version found


def _get_python_version(
    directory: Path,
) -> tuple[
    packaging.version.Version,
    packaging.version.Version,
]:
    """Get the range of supported Python versions (3.0 to last_version)."""
    first_version = packaging.version.Version("3.0")
    last_version = _get_python_version_from_file(directory)

    # Fallback to embedded .python-version if not found in directory
    if last_version is None:
        data = pkgutil.get_data("python_versions_hook", ".python-version")
        assert data is not None
        last_version = packaging.version.parse(data.decode("utf-8").strip())

    return first_version, last_version


def _convert_poetry_version_to_specifier(version: str) -> str:
    """Convert Poetry version syntax (^3.8) to PEP 440 specifiers (>=3.8,<4.0)."""
    if version.startswith("^"):
        version = version[1:]
        major = packaging.version.parse(version).major
        return f">={version},<{major + 1}.0"
    return version


def _normalize_specifier_set(specifier_set: packaging.specifiers.SpecifierSet) -> str:
    """Normalize the order of specifiers for consistent comparison."""
    specifiers = sorted(str(s) for s in specifier_set)
    return ",".join(specifiers)


def _get_python_specifiers_version(pyproject_path: Path) -> packaging.specifiers.SpecifierSet | None:
    with mra.EditTOML(pyproject_path) as pyproject:
        config = pyproject.get("tool", {}).get("python-versions-hook", {})
        keep_requires_python = config.get("keep-requires-python", False)
        use_requires_python = keep_requires_python and "requires-python" in pyproject.get("project", {})

        if not use_requires_python and "python" in pyproject.get("tool", {}).get("poetry", {}).get(
            "dependencies",
            {},
        ):
            version = pyproject["tool"]["poetry"]["dependencies"]["python"]
            version = _convert_poetry_version_to_specifier(version)
            specifier_set = packaging.specifiers.SpecifierSet(version)
            # Normalize the order of specifiers
            normalized_version = ",".join(sorted(str(s) for s in specifier_set))
            return packaging.specifiers.SpecifierSet(normalized_version)

        if "requires-python" in pyproject.get("project", {}):
            return packaging.specifiers.SpecifierSet(
                pyproject["project"]["requires-python"],
            )
        return None


def _get_all_directories() -> list[Path]:
    """Get all directories in the repository, excluding __pycache__ and .git."""
    result = subprocess.run(
        ["find", ".", "-type", "d", "-not", "-path", "./.git/*", "-not", "-path", "./__pycache__/*"],  # noqa: S607
        check=True,
        stdout=subprocess.PIPE,
        encoding="utf-8",
    )
    return [Path(directory) for directory in result.stdout.splitlines() if directory != "."]


class _NodeRelease(TypedDict):
    """Node.js release entry as found in nodejs.org/dist/index.json."""

    version: str


_NODE_INDEX_CACHE: dict[str, list[_NodeRelease] | None] = {}
_NODE_SPEC_REGEX = re.compile(r"^\d+(\.\d+){0,2}$")
_NODE_FULL_VERSION_REGEX = re.compile(r"^\d+\.\d+\.\d+$")


def _get_node_index() -> list[_NodeRelease] | None:
    """Fetch and cache the Node.js release index (newest version first)."""
    if "index" in _NODE_INDEX_CACHE:
        return _NODE_INDEX_CACHE["index"]
    index: list[_NodeRelease] | None = None
    try:
        response = requests.get("https://nodejs.org/dist/index.json", timeout=30)
        response.raise_for_status()
        index = response.json()
    except requests.RequestException as e:
        # Do not break the hook on a network failure; the Node.js version is just not synced
        print(f"Error fetching Node.js version index: {e}")
    _NODE_INDEX_CACHE["index"] = index
    return index


def _get_node_version_from_file(directory: Path) -> str | None:
    """Read the Node.js version spec from an .nvmrc file in a directory."""
    nvmrc_path = directory / ".nvmrc"
    if not nvmrc_path.exists():
        return None
    raw = nvmrc_path.read_text().strip()
    if not raw:
        return None
    # Only consider the first line, drop any inline comment and the leading `v`
    spec = raw.splitlines()[0].split("#", 1)[0].strip().removeprefix("v")
    # Aliases like `lts/*` or `node` cannot be resolved to a fixed major, skip them
    if _NODE_SPEC_REGEX.match(spec):
        return spec
    return None


def _detect_node_version(directory: Path) -> str | None:
    """
    Detect the Node.js version spec for a directory.

    With priority:
    1. .nvmrc (local)
    2. Parent directory (recursive)
    """
    spec = _get_node_version_from_file(directory)
    if spec is not None:
        return spec
    parent = directory.parent
    if parent != directory:  # Avoid infinite loop at root
        return _detect_node_version(parent)
    return None


def _node_version_matches(version: str, spec: str) -> bool:
    """Return True if a full Node.js version satisfies the given version spec."""
    version_parts = version.lstrip("v").split(".")
    spec_parts = spec.lstrip("v").split(".")
    return version_parts[: len(spec_parts)] == spec_parts


def _node_needs_update(existing: str, spec: str) -> bool:
    """Return True if the configured Node.js version must be replaced to match the spec."""
    normalized = existing.lstrip("v").strip()
    # A bare major/minor is not a valid nodeenv version, it must be resolved to a full one
    if not _NODE_FULL_VERSION_REGEX.match(normalized):
        return True
    return not _node_version_matches(normalized, spec)


def _resolve_latest_node(spec: str) -> str | None:
    """Resolve a Node.js version spec to the most recent matching full version."""
    index = _get_node_index()
    if index is None:
        return None
    for entry in index:  # The index is sorted from the newest to the oldest version
        version = entry["version"].lstrip("v")
        if _node_version_matches(version, spec):
            return version
    return None


def _update_node_language_version(directory: Path, pre_commit: mra.EditPreCommitConfig) -> None:
    """
    Sync `default_language_version.node` with the `.nvmrc` spec.

    Only when the `node` key is already defined: if the configured version is incompatible
    with `.nvmrc` (or is not a full version), it is replaced by the most recent matching one.
    """
    node_spec = _detect_node_version(directory)
    if node_spec is None or "node" not in pre_commit.get("default_language_version", {}):
        return
    existing_node = str(pre_commit["default_language_version"]["node"])
    if _node_needs_update(existing_node, node_spec):
        latest_node = _resolve_latest_node(node_spec)
        if latest_node is not None:
            pre_commit["default_language_version"]["node"] = latest_node


def main() -> None:
    """Python version configurations in all project files."""
    args_parser = argparse.ArgumentParser("Update the Python versions in all the project files")
    args_parser.parse_args()

    # Process each directory independently
    for directory in _get_all_directories():
        version = _detect_python_version(directory)
        if version is None:
            continue

        first_version, last_version = _get_python_version(directory)
        assert first_version.major == last_version.major

        minimal_version = None
        if isinstance(version, packaging.specifiers.SpecifierSet):
            for minor in range(first_version.minor, last_version.minor + 1):
                current_version = packaging.version.parse(f"{first_version.major}.{minor}")
                if version.contains(current_version) and minimal_version is None:
                    minimal_version = current_version
        else:
            # version is a packaging.version.Version
            minimal_version = version

        if minimal_version is None:
            continue

        # Update files in the current directory only
        _update_files_in_directory(directory, minimal_version, first_version, last_version)


def _update_files_in_directory(
    directory: Path,
    minimal_version: packaging.version.Version,
    first_version: packaging.version.Version,
    last_version: packaging.version.Version,
) -> None:
    """Update Python version configurations in all project files for a specific directory."""
    # In pyproject.toml
    pyproject_path = directory / "pyproject.toml"
    if pyproject_path.exists():
        with mra.EditTOML(pyproject_path) as pyproject:
            if "python_version" in pyproject.get("tool", {}).get("mypy", {}):
                pyproject["tool"]["mypy"]["python_version"] = str(minimal_version)

            if "target-version" in pyproject.get("tool", {}).get("black", {}):
                pyproject["tool"]["black"]["target-version"] = [
                    f"py{minimal_version.major}{minimal_version.minor}",
                ]

            if "target-version" in pyproject.get("tool", {}).get("ruff", {}):
                pyproject["tool"]["ruff"]["target-version"] = (
                    f"py{minimal_version.major}{minimal_version.minor}"
                )

            version_set = _get_python_specifiers_version(pyproject_path)
            if version_set is None:
                return

            all_version = []
            for minor in range(first_version.minor, last_version.minor + 1):
                current_version = packaging.version.parse(f"{first_version.major}.{minor}")
                if version_set.contains(current_version):
                    all_version.append(current_version)

            config = pyproject.get("tool", {}).get("python-versions-hook", {})
            keep_requires_python = config.get("keep-requires-python", False)
            if not keep_requires_python and "project" in pyproject:
                pyproject["project"]["requires-python"] = f">={minimal_version}"

            has_classifiers = False
            has_poetry_classifiers = False
            classifiers = []
            if "classifiers" in pyproject.get("project", {}):
                has_classifiers = True
                classifiers = pyproject["project"]["classifiers"]
            elif "classifiers" in pyproject.get("tool", {}).get(
                "poetry",
                {},
            ) and "python" in pyproject.get("tool", {}).get("poetry", {}).get(
                "dependencies",
                {},
            ):
                has_classifiers = True
                has_poetry_classifiers = True
                classifiers = pyproject["tool"]["poetry"]["classifiers"]

            if not has_classifiers:
                return

            classifiers = [c for c in classifiers if not c.startswith("Programming Language :: Python")]
            classifiers.append("Programming Language :: Python")
            classifiers.append("Programming Language :: Python :: 3")
            for current_version in all_version:
                classifiers.append(f"Programming Language :: Python :: {current_version}")

            classifier_item = tomlkit.array(
                sorted(classifiers, key=_natural_sort_key),  # type: ignore[arg-type]
            ).multiline(multiline=True)
            if has_poetry_classifiers:
                pyproject["tool"]["poetry"]["classifiers"] = classifier_item
            else:
                pyproject["project"]["classifiers"] = classifier_item

            _tweak_dependency_version(pyproject)

    # In .pre-commit-config.yaml (local)
    pre_commit_config_path = directory / ".pre-commit-config.yaml"
    if pre_commit_config_path.exists():
        with mra.EditPreCommitConfig(pre_commit_config_path) as pre_commit:
            if "python" in pre_commit.get("default_language_version", {}):
                pre_commit["default_language_version"]["python"] = (
                    f"{minimal_version.major}.{minimal_version.minor}"
                )

            _update_node_language_version(directory, pre_commit)

            if "https://github.com/asottile/pyupgrade" in pre_commit.repos_hooks:
                pre_commit.repos_hooks["https://github.com/asottile/pyupgrade"]["repo"]["hooks"][0][
                    "args"
                ] = [
                    (f"--py{minimal_version.major}{minimal_version.minor}-plus"),
                ]

    # In .python-version (local)
    python_version_path = directory / ".python-version"
    if python_version_path.exists():
        python_version_path.write_text(f"{minimal_version.major}.{minimal_version.minor}\n")

    # In all .prospector.yaml files (local)
    for prospector_path in directory.glob("*.prospector.yaml"):
        with mra.EditYAML(prospector_path) as yaml:
            yaml.setdefault("mypy", {}).setdefault("options", {})["python-version"] = (
                f"{minimal_version.major}.{minimal_version.minor}"
            )
            yaml.setdefault("ruff", {}).setdefault("options", {})["target-version"] = (
                f"py{minimal_version.major}{minimal_version.minor}"
            )

    # In jsonschema-gentypes.yaml (local)
    jsonschema_gentypes_path = directory / "jsonschema-gentypes.yaml"
    if jsonschema_gentypes_path.exists():
        with mra.EditYAML(jsonschema_gentypes_path) as yaml:
            yaml["python_version"] = f"{minimal_version.major}.{minimal_version.minor}"


# beaker (>=1.13.0,<2.0.0)
_POETRY_ADD_PACKAGE_REGEX = re.compile(r"([a-z][a-z0-9_-]*) \(>=([0-9][0-9\.a-z-]+),<([0-9][0-9\.a-z-]+)\)$")


def _tweak_dependency_version(pyproject: mra.EditTOML) -> None:
    """Tweak the dependency version in pyproject.toml."""

    all_poetry_deps = set(pyproject.get("tool", {}).get("poetry", {}).get("dependencies", {}).keys())
    for group_deps in (
        pyproject.get("tool", {})
        .get("poetry", {})
        .get(
            "group",
            {},
        )
        .values()
    ):
        if isinstance(group_deps, dict):
            all_poetry_deps.update(group_deps.get("dependencies", {}).keys())

    current_project_dependencies = pyproject.get("project", {}).get("dependencies", [])
    for full_dependencies in current_project_dependencies:
        if isinstance(full_dependencies, str):
            match = _POETRY_ADD_PACKAGE_REGEX.match(full_dependencies)
            if match and match.group(1) not in all_poetry_deps:
                # Get the latest version that match the constraint
                try:
                    min_version = packaging.version.parse(match.group(2))
                    max_version = packaging.version.parse(match.group(3))
                    pypi_response = requests.get(f"https://pypi.org/pypi/{match.group(1)}/json", timeout=30)
                    pypi_response.raise_for_status()
                    package_info = pypi_response.json()
                    releases = package_info.get("releases", {})
                    valid_versions = [
                        v
                        for v in releases
                        if packaging.version.parse(v) >= min_version
                        and packaging.version.parse(v) < max_version
                    ]
                    valid_versions.sort(key=packaging.version.parse)
                    if valid_versions:
                        latest_version = valid_versions[-1]
                        pyproject.setdefault("tool", {}).setdefault("poetry", {}).setdefault(
                            "dependencies",
                            {},
                        )[match.group(1)] = latest_version
                except requests.RequestException as e:
                    print(f"Error fetching package info for {match.group(1)}: {e}")
                except packaging.version.InvalidVersion as e:
                    print(f"Invalid version for {match.group(1)}: {e}")
                except Exception as e:  # pylint: disable=broad-except # noqa: BLE001
                    print(f"Unexpected error for {match.group(1)}: {e}")

    plugin_config = pyproject.get("tool", {}).get("tweak-poetry-dependencies-versions")
    if plugin_config is None:
        plugin_config = pyproject.get("tool", {}).get(
            "poetry-plugin-tweak-dependencies-version",
        )
    if plugin_config is None:
        return

    extras = pyproject.get("tool", {}).get("poetry", {}).get("extras", {})
    new_dependencies = {}
    for dependency_name, dependency_config in (
        pyproject.get("tool", {}).get("poetry", {}).get("dependencies", {}).items()
    ):
        if isinstance(dependency_config, str):
            dependency_config = {"version": dependency_config}  # noqa: PLW2901

        modifier = plugin_config.get(dependency_name)
        if modifier is None:
            modifier = plugin_config.get("default", "full")

        new_version = {
            "version": dependency_config.get("version"),
            "in_extras": [],
            "use_extras": dependency_config.get("extras", []),
            "optional": dependency_config.get("optional", False),
            "modifier": modifier,
        }
        if dependency_config.get("optional", False):
            for extra_name, packages in extras.items():
                if dependency_name in packages:
                    new_version["in_extras"].append(extra_name)

        new_dependencies[dependency_name] = new_version

    all_extras = []
    for dependency_config in new_dependencies.values():
        all_extras.extend(dependency_config["in_extras"])

    # The `keep-project-dependencies` option can be a boolean (True: do not prune anything)
    # or a list of package names to keep in the project sections even if they are prunable.
    config = pyproject.get("tool", {}).get("python-versions-hook", {})
    keep_project_dependencies = config.get("keep-project-dependencies", False)
    prune_enabled = keep_project_dependencies is not True
    keep_canonical_names = (
        {packaging.utils.canonicalize_name(str(name)) for name in keep_project_dependencies}
        if isinstance(keep_project_dependencies, list)
        else set()
    )

    def should_prune(dependency_name: str) -> bool:
        """Return True if the dependency entries can be pruned from the project sections."""
        return prune_enabled and (
            packaging.utils.canonicalize_name(dependency_name) not in keep_canonical_names
        )

    # Parse current dependencies
    pyproject.setdefault("project", {})["dependencies"] = _replace_dependencies(
        pyproject.get("project", {}).get("dependencies", []),
        new_dependencies,
        None,
        should_prune,
    )
    for extra_name in all_extras:
        pyproject["project"].setdefault("optional-dependencies", {})[extra_name] = _replace_dependencies(
            pyproject.get("project", {}).get("optional-dependencies", {}).get(extra_name, []),
            new_dependencies,
            extra_name,
            should_prune,
        )

    # Prune the optional-dependencies entries of the extras removed from tool.poetry.extras,
    # the unknown dependencies are kept and the extra is removed only if it becomes empty.
    optional_dependencies = pyproject.get("project", {}).get("optional-dependencies", {})
    for extra_name in list(optional_dependencies):
        if extra_name in all_extras:
            continue
        pruned_dependencies = _replace_dependencies(
            optional_dependencies[extra_name],
            new_dependencies,
            extra_name,
            should_prune,
        )
        if pruned_dependencies:
            optional_dependencies[extra_name] = pruned_dependencies
        else:
            del optional_dependencies[extra_name]


def _replace_dependencies(
    current_dependencies: list[str],
    poetry_dependencies: dict[str, dict[str, Any]],
    extra: str | None,
    should_prune: Callable[[str], bool],
) -> list[str]:
    """Replace the dependencies in the pyproject.toml file."""
    # The keys are canonicalized to match the packages independently of the name spelling
    dependencies: dict[str, packaging.requirements.Requirement] = {}
    for dependency in current_dependencies:
        requirement = packaging.requirements.Requirement(dependency)
        dependencies[packaging.utils.canonicalize_name(requirement.name)] = requirement

    for dependency_name, dependency_config in poetry_dependencies.items():
        canonical_name = packaging.utils.canonicalize_name(dependency_name)
        if extra is None and dependency_config["optional"]:
            # Prune the optional dependencies, they are published in the extras
            if should_prune(dependency_name):
                dependencies.pop(canonical_name, None)
            continue
        if extra is not None and extra not in dependency_config["in_extras"]:
            # Prune the dependencies that are not (or no longer) in this extra
            if should_prune(dependency_name):
                dependencies.pop(canonical_name, None)
            continue
        if dependency_name == "python":
            # Skip python dependency
            continue
        requirement = packaging.requirements.Requirement(dependency_name)
        requirement.extras = dependency_config["use_extras"]
        if dependency_config["modifier"] in ["major", "minor", "patch"]:
            try:
                version_split = [int(part) for part in dependency_config["version"].split(".")]
            except ValueError:
                # If the version is not a valid version, skip it
                print(
                    "Warning: Invalid version for dependency %s: %s",
                    dependency_name,
                    dependency_config["version"],
                )
                continue

            version_min = None
            version_max = None
            if dependency_config["modifier"] == "major":
                version_min = [version_split[0]]
                version_max = [version_split[0] + 1]
            elif dependency_config["modifier"] == "minor":
                version_min = version_split[0:2]
                if len(version_min) == 2:
                    version_max = [version_min[0], version_min[1] + 1]
                else:
                    version_min = version_split
                    version_max = version_split
            elif dependency_config["modifier"] == "patch":
                version_min = version_split[0:3]
                if len(version_min) == 3:
                    version_max = [
                        version_min[0],
                        version_min[1],
                        version_min[2] + 1,
                    ]
                else:
                    version_max = version_min
            if version_min is not None and version_max is not None:
                if version_min == version_max:
                    requirement.specifier = packaging.specifiers.SpecifierSet(
                        f"== {'.'.join(map(str, version_min))}",
                    )
                else:
                    requirement.specifier = packaging.specifiers.SpecifierSet(
                        f">={'.'.join(map(str, version_min))},<{'.'.join(map(str, version_max))}",
                    )
        elif dependency_config["modifier"] == "full":
            version = dependency_config["version"]
            requirement.specifier = packaging.specifiers.SpecifierSet(
                f"== {version}",
            )
        elif dependency_config["modifier"] != "present":
            version = dependency_config["modifier"]
            requirement.specifier = packaging.specifiers.SpecifierSet(
                version,
            )

        dependencies[canonical_name] = requirement

    return [str(requirement) for requirement in dependencies.values()]
