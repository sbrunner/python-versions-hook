"""Python versions hooks."""

import argparse
import pkgutil
import re
import subprocess
from pathlib import Path
from typing import Any, Optional, Union

import multi_repo_automation as mra
import packaging.requirements
import packaging.specifiers
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


def _get_python_version() -> tuple[
    packaging.version.Version,
    packaging.version.Version,
]:
    first_version = packaging.version.parse("3.0")
    data = pkgutil.get_data("python_versions_hook", ".python-version")
    assert data is not None
    last_version = packaging.version.parse(data.decode("utf-8").strip())
    return first_version, last_version


def _get_python_specifiers_version(pyproject: mra.EditTOML) -> packaging.specifiers.SpecifierSet | None:
    config = pyproject.get("tool", {}).get("python-versions-hook", {})
    keep_requires_python = config.get("keep-requires-python", False)
    use_requires_python = keep_requires_python and "requires-python" in pyproject.get("project", {})
    if not use_requires_python and "python" in pyproject.get("tool", {}).get("poetry", {}).get(
        "dependencies",
        {},
    ):
        return packaging.specifiers.SpecifierSet(
            pyproject["tool"]["poetry"]["dependencies"]["python"],
        )
    if "requires-python" in pyproject.get("project", {}):
        return packaging.specifiers.SpecifierSet(
            pyproject["project"]["requires-python"],
        )
    return None


def main() -> None:
    """Python version configurations in all project files."""
    args_parser = argparse.ArgumentParser("Update the Python versions in all the project files")
    args_parser.parse_args()

    version_set = None
    for pyproject_filename in _filenames("pyproject.toml"):
        with mra.EditTOML(pyproject_filename) as pyproject:
            version_set = _get_python_specifiers_version(pyproject)
            if version_set is not None:
                break

    if version_set is None:
        return

    first_version, last_version = _get_python_version()
    assert first_version.major == last_version.major

    minimal_version = None
    for minor in range(first_version.minor, last_version.minor + 1):
        version = packaging.version.parse(f"{first_version.major}.{minor}")
        if version_set.contains(version) and minimal_version is None:
            minimal_version = version

    if minimal_version is None:
        return

    # Set the Python version

    # In all pyproject.toml files
    for pyproject_filename in _filenames("pyproject.toml"):
        with mra.EditTOML(pyproject_filename) as pyproject:
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

            version_set = _get_python_specifiers_version(pyproject)
            if version_set is None:
                continue

            all_version = []

            for minor in range(first_version.minor, last_version.minor + 1):
                version = packaging.version.parse(f"{first_version.major}.{minor}")
                if version_set.contains(version):
                    all_version.append(version)

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
                continue

            classifiers = [c for c in classifiers if not c.startswith("Programming Language :: Python")]
            classifiers.append("Programming Language :: Python")
            classifiers.append("Programming Language :: Python :: 3")
            for version in all_version:
                classifiers.append(f"Programming Language :: Python :: {version}")

            classifier_item = tomlkit.array(
                sorted(classifiers, key=_natural_sort_key),  # type: ignore[arg-type]
            ).multiline(multiline=True)
            if has_poetry_classifiers:
                pyproject["tool"]["poetry"]["classifiers"] = classifier_item
            else:
                pyproject["project"]["classifiers"] = classifier_item

            _tweak_dependency_version(pyproject)

    # In .pre-commit-config.yaml
    pre_commit_config_path = Path(".pre-commit-config.yaml")
    if pre_commit_config_path.exists():
        with mra.EditPreCommitConfig() as pre_commit:
            if "python" in pre_commit.get("default_language_version", {}):
                pre_commit["default_language_version"]["python"] = (
                    f"{minimal_version.major}.{minimal_version.minor}"
                )

            if "https://github.com/asottile/pyupgrade" in pre_commit.repos_hooks:
                pre_commit.repos_hooks["https://github.com/asottile/pyupgrade"]["repo"]["hooks"][0][
                    "args"
                ] = [
                    (f"--py{minimal_version.major}{minimal_version.minor}-plus"),
                ]

    # In .python-version
    python_version_path = Path(".python-version")
    if python_version_path.exists():
        python_version_path.write_text(f"{minimal_version.major}.{minimal_version.minor}\n")

    # In all .prospector.yaml files
    for prospector_filename in _filenames("*.prospector.yaml"):
        with mra.EditYAML(prospector_filename) as yaml:
            yaml.setdefault("mypy", {}).setdefault("options", {})["python-version"] = (
                f"{minimal_version.major}.{minimal_version.minor}"
            )
            yaml.setdefault("ruff", {}).setdefault("options", {})["target-version"] = (
                f"py{minimal_version.major}{minimal_version.minor}"
            )

    # In jsonschema-gentypes.yaml
    jsonschema_gentypes_path = Path("jsonschema-gentypes.yaml")
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

    # Parse current dependencies
    pyproject.setdefault("project", {})["dependencies"] = _replace_dependencies(
        pyproject.get("project", {}).get("dependencies", []),
        new_dependencies,
        None,
    )
    for extra_name in all_extras:
        pyproject["project"].setdefault("optional-dependencies", {})[extra_name] = _replace_dependencies(
            pyproject.get("project", {}).get("optional-dependencies", {}).get(extra_name, []),
            new_dependencies,
            extra_name,
        )


def _replace_dependencies(
    current_dependencies: list[str],
    poetry_dependencies: dict[str, dict[str, Any]],
    extra: str | None,
) -> list[str]:
    """Replace the dependencies in the pyproject.toml file."""
    dependencies = {}
    for dependency in current_dependencies:
        requirement = packaging.requirements.Requirement(dependency)
        dependencies[requirement.name] = requirement

    for dependency_name, dependency_config in poetry_dependencies.items():
        if extra is None and dependency_config["optional"]:
            continue
        if extra is not None and extra not in dependency_config["in_extras"]:
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

        dependencies[dependency_name] = requirement

    return [str(requirement) for requirement in dependencies.values()]
