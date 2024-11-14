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
