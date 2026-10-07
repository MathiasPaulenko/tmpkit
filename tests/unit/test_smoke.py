"""Smoke test: verify tmpkit imports correctly."""

import tmpkit


def test_import() -> None:
    assert tmpkit.__version__ == "1.1.0"
