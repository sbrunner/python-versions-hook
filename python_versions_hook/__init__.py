"""Python versions hooks."""

import argparse
import os
import pkgutil
import re
import subprocess
from typing import Union

import multi_repo_automation as mra
import packaging.specifiers
import packaging.version
import tomlkit


def _filenames(pattern) -> list[str]:
    return subprocess.run(  # noqa: S603
        ["git", "ls-files", pattern], check=True, stdout=subprocess.PIPE, encoding="utf-8"  # noqa: S607
    ).stdout.splitlines()


_digit = re.compile("([0-9]+)")


def _natural_sort_key(text: str) -> list[Union[int, str]]:
    return [int(value) if value.isdigit() else value.lower() for value in _digit.split(text)]


def _get_python_version() -> tuple[packaging.version.Version, packaging.version.Version]:
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
                version_set = packaging.specifiers.SpecifierSet(pyproject["project"]["requires-python"])
            elif "python" in pyproject.get("tool", {}).get("poetry", {}).get("dependencies", {}):
                version_set = packaging.specifiers.SpecifierSet(
                    pyproject["tool"]["poetry"]["dependencies"]["python"]
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
                    f"py{minimal_version.major}{minimal_version.minor}"
                ]

            if "target-version" in pyproject.get("tool", {}).get("ruff", {}):
                pyproject["tool"]["ruff"][
                    "target-version"
                ] = f"py{minimal_version.major}{minimal_version.minor}"

            python_version = ""
            if "requires-python" in pyproject.get("project", {}):
                python_version = pyproject["project"]["requires-python"]
            elif "python" in pyproject.get("tool", {}).get("poetry", {}).get("dependencies", {}):
                python_version = pyproject["tool"]["poetry"]["dependencies"]["python"]

            if not python_version:
                continue

            version_set = packaging.specifiers.SpecifierSet(python_version)
            all_version = []

            for minor in range(first_version.minor, last_version.minor + 1):
                version = packaging.version.parse(f"{first_version.major}.{minor}")
                if version_set.contains(version):
                    all_version.append(version)

            has_classifiers = False
            has_poetry_classifiers = False
            classifiers = []
            if "classifiers" in pyproject.get("project", {}):
                has_classifiers = True
                classifiers = pyproject["project"]["classifiers"]
            elif "classifiers" in pyproject.get("tool", {}).get("poetry", {}) and "python" in pyproject.get(
                "tool", {}
            ).get("poetry", {}).get("dependencies", {}):
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

            classifier_item = tomlkit.array(sorted(classifiers, key=_natural_sort_key)).multiline(True)
            if has_poetry_classifiers:
                pyproject["tool"]["poetry"]["classifiers"] = classifier_item
            else:
                pyproject["project"]["classifiers"] = classifier_item

    if os.path.exists(".pre-commit-config.yaml"):
        with mra.EditPreCommitConfig() as pre_commit:
            if "https://github.com/asottile/pyupgrade" in pre_commit.repos_hooks:
                print(pre_commit.repos_hooks["https://github.com/asottile/pyupgrade"])
                pre_commit.repos_hooks["https://github.com/asottile/pyupgrade"]["repo"]["hooks"][0][
                    "args"
                ] = [(f"--py{minimal_version.major}{minimal_version.minor}-plus")]

    if os.path.exists("jsonschema-gentypes.yaml"):
        with mra.EditYAML("jsonschema-gentypes.yaml") as yaml:
            yaml["python_version"] = f"{minimal_version.major}.{minimal_version.minor}"

    # on all .prospector.yaml files
    for prospector_filename in _filenames("*.prospector.yaml"):
        with mra.EditYAML(prospector_filename) as yaml:
            yaml.setdefault("mypy", {}).setdefault("options", {})[
                "python-version"
            ] = f"{minimal_version.major}.{minimal_version.minor}"
            yaml.setdefault("ruff", {}).setdefault("options", {})[
                "target-version"
            ] = f"py{minimal_version.major}{minimal_version.minor}"
