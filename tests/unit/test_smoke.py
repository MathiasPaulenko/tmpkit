"""Smoke test: verify tmpkit imports correctly."""

import tomllib
from pathlib import Path

import tmpkit


def test_import() -> None:
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    version = tomllib.loads(pyproject.read_text())["project"]["version"]
    assert tmpkit.__version__ == version
