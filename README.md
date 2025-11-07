# Python versions hook

Python versions hook is a [pre-commit](https://pre-commit.com/) hook to maintain the Python versions in sync.

Support:

- [Poetry](https://python-poetry.org/) as version provider and update classifiers in `pyproject.toml`.
- [Mypy](https://mypy.readthedocs.io/en/stable/) in `pyporoject.toml` and in `.prospector.yaml`.
- [Pyupgrade](https://pypi.org/project/pyupgrade/) as pre-commit hook.
- [Ruff](https://docs.astral.sh/ruff/) in `pyporoject.toml` and in `.prospector.yaml`.
- [Prospector](https://prospector.landscape.io/) in `.prospector.yaml` for Mypy and Ruff.
- [PEP-621](https://peps.python.org/pep-0621/) in `pyproject.toml`.
- [jsonschema-gentypes](https://developer.mend.io/github/sbrunner/jsonschema-gentypes) in `jsonschema-gentypes.yaml`.

## Adding to your `.pre-commit-config.yaml`

```yaml
repos:
  - repo: https://github.com/sbrunner/python-versions-hook
    rev: <version> # Use the ref you want to point at
    hooks:
      - id: python-versions
```

## How it works

This hook automatically keeps your Python version settings consistent across various configuration files in your project. When you run the hook, it:

1. Detects the Python versions your project supports from your Poetry dependencies or PEP-621 `requires-python` field
2. Updates the following based on the supported versions:
   - Python classifiers in `pyproject.toml`
   - Mypy's `python_version` setting in both `pyproject.toml` and `.prospector.yaml`
   - Ruff's `target-version` setting in both `pyproject.toml` and `.prospector.yaml`
   - Black's `target-version` setting in `pyproject.toml`
   - Pyupgrade's `--py{version}-plus` argument in `.pre-commit-config.yaml`
   - Python version in `jsonschema-gentypes.yaml`

## Usage

Once installed as a pre-commit hook, it will run automatically when you commit changes to your repository.

You can also run it manually with:

```bash
pre-commit run python-versions --all-files
```

## Options

The options are stored in the `pyproject.toml` file under the `[tool.python-versions-hook]` section.

- `keep-requires-python`: Controls whether the hook modifies the `requires-python` field in the `pyproject.toml` file.
  - When `false` (default): The hook will automatically update the `requires-python` field.
  - When `true`: The hook will not modify the `requires-python` field (preserves its existing value).

## Tweak dependency

This project can also be used as a replacement of the [Poetry plugin tweak dependencies version](https://github.com/sbrunner/poetry-plugin-tweak-dependencies-version) project.

The configuration is like that:

```toml

[tool.poetry-plugin-tweak-dependencies-version]
default = "(present|major|minor|patch|full)" # Default to `full`
"<package>" = "(present|major|minor|patch|full|<alternate version>)"
```

And he will fill the PEP 631 `project.dependencies` and `project.optional-dependencies` section from the
Poetry section with values that respect the configuration:

- `present` => Just add the package as dependency.
- `major` => Just fix the major version.
- `minor` => Just fix the major and minor version.
- `patch` => Just fix the major, minor and patch version.
- `full` => Get the full version from the Poetry section.
- `<alternate version>` => use is as a version.
