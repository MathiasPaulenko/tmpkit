"""Configuration: DEBUG detection and keep/delete decision logic."""

from __future__ import annotations

import os


def _debug_enabled() -> bool:
    """Check if DEBUG mode is enabled via environment variable.

    TMPKIT_DEBUG takes precedence over DEBUG.
    Returns True only if the resolved value is exactly "1".
    """
    value = os.environ.get("TMPKIT_DEBUG")
    if value is None:
        value = os.environ.get("DEBUG")
    return value == "1"


def _should_keep(*, keep: bool, keep_on_error: bool, had_error: bool) -> bool:
    """Decide whether to keep a temp based on flags and error state.

    Precedence:
      1. ``keep=True`` — always keep.
      2. ``_debug_enabled()`` — DEBUG env var forces keep.
      3. ``keep_on_error`` and an error occurred — keep.
    """
    if keep:
        return True
    if _debug_enabled():
        return True
    return keep_on_error and had_error
