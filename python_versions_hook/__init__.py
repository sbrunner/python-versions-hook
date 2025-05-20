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


def _natural_sort_key(text: str) -> list[Union[int, str]]:
    return [
        int(value) if value.isdigit() else value.lower() for value in _digit.split(text)
    ]


def _get_python_version() -> tuple[
    packaging.version.Version,
    packaging.version.Version,
]:
    first_version = packaging.version.parse("3.0")
    data = pkgutil.get_data("python_versions_hook", ".python-version")
    assert data is not None
    last_version = packaging.version.parse(data.decode("utf-8").strip())
    return first_version, last_version


def main() -> None:
    """Update the copyright header of the files."""
    args_parser = argparse.ArgumentParser("Update the Python versions in all the files")
    args_parser.parse_args()

    version_set = None
    for pyproject_filename in _filenames("pyproject.toml"):
        with mra.EditTOML(pyproject_filename) as pyproject:
            if "requires-python" in pyproject.get("project", {}):
                version_set = packaging.specifiers.SpecifierSet(
                    pyproject["project"]["requires-python"],
                )
            elif "python" in pyproject.get("tool", {}).get("poetry", {}).get(
                "dependencies",
                {},
            ):
                version_set = packaging.specifiers.SpecifierSet(
                    pyproject["tool"]["poetry"]["dependencies"]["python"],
                )

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

            python_version = ""
            if "requires-python" in pyproject.get("project", {}):
                python_version = pyproject["project"]["requires-python"]
            elif "python" in pyproject.get("tool", {}).get("poetry", {}).get(
                "dependencies",
                {},
            ):
                python_version = pyproject["tool"]["poetry"]["dependencies"]["python"]

            if not python_version:
                continue

            version_set = packaging.specifiers.SpecifierSet(python_version)
            all_version = []

            for minor in range(first_version.minor, last_version.minor + 1):
                version = packaging.version.parse(f"{first_version.major}.{minor}")
                if version_set.contains(version):
                    all_version.append(version)

            if "project" in pyproject:
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

            classifiers = [
                c
                for c in classifiers
                if not c.startswith("Programming Language :: Python")
            ]
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

    pre_commit_config_path = Path(".pre-commit-config.yaml")
    if pre_commit_config_path.exists():
        with mra.EditPreCommitConfig() as pre_commit:
            if "https://github.com/asottile/pyupgrade" in pre_commit.repos_hooks:
                print(pre_commit.repos_hooks["https://github.com/asottile/pyupgrade"])
                pre_commit.repos_hooks["https://github.com/asottile/pyupgrade"]["repo"][
                    "hooks"
                ][0]["args"] = [
                    (f"--py{minimal_version.major}{minimal_version.minor}-plus"),
                ]

    jsonschema_gentypes_path = Path("jsonschema-gentypes.yaml")
    if jsonschema_gentypes_path.exists():
        with mra.EditYAML(jsonschema_gentypes_path) as yaml:
            yaml["python_version"] = f"{minimal_version.major}.{minimal_version.minor}"

    # on all .prospector.yaml files
    for prospector_filename in _filenames("*.prospector.yaml"):
        with mra.EditYAML(prospector_filename) as yaml:
            yaml.setdefault("mypy", {}).setdefault("options", {})["python-version"] = (
                f"{minimal_version.major}.{minimal_version.minor}"
            )
            yaml.setdefault("ruff", {}).setdefault("options", {})["target-version"] = (
                f"py{minimal_version.major}{minimal_version.minor}"
            )


def _tweak_dependency_version(pyproject: mra.EditTOML) -> None:
    """Tweak the dependency version in pyproject.toml."""

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
        pyproject["project"].setdefault("optional-dependencies", {})[extra_name] = (
            _replace_dependencies(
                pyproject.get("project", {})
                .get("optional-dependencies", {})
                .get(extra_name, []),
                new_dependencies,
                extra_name,
            )
        )


def _replace_dependencies(
    current_dependencies: list[str],
    poetry_dependencies: dict[str, dict[str, Any]],
    extra: Optional[str],
) -> list[str]:
    """Replace the dependencies in the pyproject.toml file."""
    dependencies = {}
    for dependency in current_dependencies:
        requirement = packaging.requirements.Requirement(dependency)
        dependencies[requirement.name] = requirement

    for dependency_name, dependency_config in poetry_dependencies.items():
        if extra is None and dependency_config["in_extras"]:
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
                version_split = [
                    int(part) for part in dependency_config["version"].split(".")
                ]
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
                f"== {version}",
            )

        dependencies[dependency_name] = requirement

    return [str(requirement) for requirement in dependencies.values()]
