"""Smoke test: verify tmpkit imports correctly."""

import tmpkit


def test_import() -> None:
    assert tmpkit.__version__ == "0.1.0"
