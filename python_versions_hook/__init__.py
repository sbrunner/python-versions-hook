"""Python versions hooks."""

import argparse
import os
import re
import subprocess
from typing import Union

import multi_repo_automation as mra
import packaging.version
import tomlkit


def _filenames(pattern) -> list[str]:
    return subprocess.run(  # noqa: S603
        ["git", "ls-files", pattern], check=True, stdout=subprocess.PIPE, encoding="utf-8"  # noqa: S607
    ).stdout.splitlines()


_digit = re.compile("([0-9]+)")


def _natural_sort_key(text: str) -> list[Union[int, str]]:
    return [int(value) if value.isdigit() else value.lower() for value in _digit.split(text)]


_python_version_re = re.compile(r"^>=(\d+\.\d+),<(\d+\.\d+)$")


def main() -> None:
    """Update the copyright header of the files."""
    args_parser = argparse.ArgumentParser("Update the Python versions in all the files")
    args_parser.parse_args()

    minimal_version = packaging.version.parse("3.99")
    for pyproject_filename in _filenames("pyproject.toml"):
        with mra.EditTOML(pyproject_filename) as pyproject:
            if "requires-python" in pyproject.get("project", {}):
                match = _python_version_re.match(pyproject["project"]["requires-python"])
                if match:
                    version = packaging.version.parse(match.group(1))
                    if version < minimal_version:
                        minimal_version = version
            elif "python" in pyproject.get("tool", {}).get("poetry", {}).get("dependencies", {}):
                match = _python_version_re.match(pyproject["tool"]["poetry"]["dependencies"]["python"])
                if match:
                    version = packaging.version.parse(match.group(1))
                    if version < minimal_version:
                        minimal_version = version

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

            match = _python_version_re.match(python_version)
            if not match:
                continue
            min_python_version = packaging.version.parse(match.group(1))
            max_python_version = packaging.version.parse(match.group(2))
            if max_python_version.major == 4:
                max_python_version = packaging.version.parse("3.13")

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
            for minor in range(min_python_version.minor, max_python_version.minor + 1):
                classifiers.append(f"Programming Language :: Python :: {min_python_version.major}.{minor}")

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
            yaml.setdefault("pypy", {}).setdefault("options", {})[
                "python-version"
            ] = f"{minimal_version.major}.{minimal_version.minor}"
            yaml.setdefault("ruff", {}).setdefault("options", {})[
                "target-version"
            ] = f"py{minimal_version.major}{minimal_version.minor}"
