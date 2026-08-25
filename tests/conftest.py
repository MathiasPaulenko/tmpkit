"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def assert_no_temps_left():
    """Assert no temp files/dirs are left after a test.

    Returns a callable that checks a list of paths don't exist.
    Usage:
        paths = []
        with temp_file() as f:
            paths.append(f.path)
        assert_no_temps_left(paths)
    """

    def _check(paths: list[Path]) -> None:
        for p in paths:
            assert not p.exists(), f"Temp path still exists: {p}"

    return _check
