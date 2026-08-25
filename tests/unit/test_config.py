"""Tests for _config.py: env var parsing and keep decision logic."""

from __future__ import annotations

import pytest
from tmpkit._config import _debug_enabled, _should_keep


class TestDebugEnabled:
    """Tests for _debug_enabled()."""

    def test_tmpkit_debug_1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TMPKIT_DEBUG", "1")
        monkeypatch.delenv("DEBUG", raising=False)
        assert _debug_enabled() is True

    def test_debug_1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TMPKIT_DEBUG", raising=False)
        monkeypatch.setenv("DEBUG", "1")
        assert _debug_enabled() is True

    def test_tmpkit_debug_wins_over_debug(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TMPKIT_DEBUG", "0")
        monkeypatch.setenv("DEBUG", "1")
        assert _debug_enabled() is False

    def test_neither_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TMPKIT_DEBUG", raising=False)
        monkeypatch.delenv("DEBUG", raising=False)
        assert _debug_enabled() is False

    def test_tmpkit_debug_not_1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TMPKIT_DEBUG", "true")
        monkeypatch.delenv("DEBUG", raising=False)
        assert _debug_enabled() is False

    def test_debug_empty_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TMPKIT_DEBUG", raising=False)
        monkeypatch.setenv("DEBUG", "")
        assert _debug_enabled() is False


class TestShouldKeep:
    """Tests for _should_keep()."""

    def test_keep_true_no_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TMPKIT_DEBUG", raising=False)
        monkeypatch.delenv("DEBUG", raising=False)
        assert _should_keep(keep=True, keep_on_error=False, had_error=False) is True

    def test_keep_true_with_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TMPKIT_DEBUG", raising=False)
        monkeypatch.delenv("DEBUG", raising=False)
        assert _should_keep(keep=True, keep_on_error=False, had_error=True) is True

    def test_keep_on_error_with_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TMPKIT_DEBUG", raising=False)
        monkeypatch.delenv("DEBUG", raising=False)
        assert _should_keep(keep=False, keep_on_error=True, had_error=True) is True

    def test_keep_on_error_no_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TMPKIT_DEBUG", raising=False)
        monkeypatch.delenv("DEBUG", raising=False)
        assert _should_keep(keep=False, keep_on_error=True, had_error=False) is False

    def test_debug_wins_over_keep_on_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("TMPKIT_DEBUG", raising=False)
        monkeypatch.setenv("DEBUG", "1")
        assert _should_keep(keep=False, keep_on_error=True, had_error=False) is True

    def test_no_keep_no_error_no_debug(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TMPKIT_DEBUG", raising=False)
        monkeypatch.delenv("DEBUG", raising=False)
        assert _should_keep(keep=False, keep_on_error=False, had_error=False) is False

    def test_keep_true_overrides_debug(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TMPKIT_DEBUG", "1")
        assert _should_keep(keep=True, keep_on_error=False, had_error=False) is True

    def test_all_false_with_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TMPKIT_DEBUG", raising=False)
        monkeypatch.delenv("DEBUG", raising=False)
        assert _should_keep(keep=False, keep_on_error=False, had_error=True) is False
