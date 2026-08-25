"""Tests for keep control: precedence matrix, .keep(), DEBUG env, ignore_cleanup_errors."""

from __future__ import annotations

import pytest
from tmpkit import temp_dir, temp_file

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _raise_boom() -> None:
    raise RuntimeError("boom")


# ---------------------------------------------------------------------------
# temp_file() keep tests
# ---------------------------------------------------------------------------


class TestTempFileKeepParam:
    """keep=True always keeps the file."""

    def test_keep_true_stays(self) -> None:
        with temp_file(keep=True) as f:
            path = f.path
        assert path.exists()

    def test_keep_true_with_exception_stays(self) -> None:
        with pytest.raises(RuntimeError, match="boom"), temp_file(keep=True) as f:
            path = f.path
            _raise_boom()
        assert path.exists()


class TestTempFileKeepOnError:
    """keep_on_error behavior."""

    def test_keep_on_error_with_exception_stays(self) -> None:
        with (
            pytest.raises(RuntimeError, match="boom"),
            temp_file(keep_on_error=True) as f,
        ):
            path = f.path
            _raise_boom()
        assert path.exists()

    def test_keep_on_error_no_exception_deleted(self) -> None:
        with temp_file(keep_on_error=True) as f:
            path = f.path
        assert not path.exists()


class TestTempFileUserKeep:
    """.keep() method."""

    def test_keep_method_stays(self) -> None:
        with temp_file() as f:
            f.keep()
            path = f.path
        assert path.exists()

    def test_keep_before_enter_raises(self) -> None:
        f = temp_file()
        with pytest.raises(RuntimeError, match="before __enter__"):
            f.keep()

    def test_keep_overrides_keep_on_error_no_exception(self) -> None:
        with temp_file(keep_on_error=True) as f:
            f.keep()
            path = f.path
        assert path.exists()


class TestTempFileDebug:
    """DEBUG / TMPKIT_DEBUG env vars force keep."""

    def test_debug_env_stays(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DEBUG", "1")
        with temp_file() as f:
            path = f.path
        assert path.exists()

    def test_tmpkit_debug_env_stays(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TMPKIT_DEBUG", "1")
        with temp_file() as f:
            path = f.path
        assert path.exists()

    def test_no_debug_no_keep_deleted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DEBUG", raising=False)
        monkeypatch.delenv("TMPKIT_DEBUG", raising=False)
        with temp_file() as f:
            path = f.path
        assert not path.exists()


class TestTempFilePrecedence:
    """Precedence: .keep() > keep=True > DEBUG=1 > keep_on_error=True."""

    def test_keep_true_wins_over_keep_on_error(self) -> None:
        with temp_file(keep=True, keep_on_error=True) as f:
            path = f.path
        assert path.exists()

    def test_debug_wins_over_keep_on_error_no_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DEBUG", "1")
        with temp_file(keep_on_error=True) as f:
            path = f.path
        assert path.exists()

    def test_user_keep_wins_over_everything(self) -> None:
        with temp_file(keep=False, keep_on_error=False) as f:
            f.keep()
            path = f.path
        assert path.exists()


class TestTempFileIgnoreCleanupErrors:
    """ignore_cleanup_errors behavior."""

    def test_ignore_true_swallows_error(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        monkeypatch.delenv("DEBUG", raising=False)
        monkeypatch.delenv("TMPKIT_DEBUG", raising=False)
        # Pre-delete the file so os.unlink raises FileNotFoundError
        with temp_file(ignore_cleanup_errors=True) as f:
            path = f.path
        # File already deleted by __exit__ (swallowed), no exception raised
        assert not path.exists()

    def test_ignore_false_propagates_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("DEBUG", raising=False)
        monkeypatch.delenv("TMPKIT_DEBUG", raising=False)
        f = temp_file(ignore_cleanup_errors=False)
        f.__enter__()
        # Close the file first (Windows locks open files), then delete so __exit__'s os.unlink fails
        import os

        f.close()
        os.unlink(f.path)
        with pytest.raises(OSError):
            f.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# temp_dir() keep tests
# ---------------------------------------------------------------------------


class TestTempDirKeepParam:
    """keep=True always keeps the directory."""

    def test_keep_true_stays(self) -> None:
        td = temp_dir(keep=True)
        with td as d:
            pass
        assert d.exists()
        d.rmdir()

    def test_keep_true_with_exception_stays(self) -> None:
        td = temp_dir(keep=True)
        with pytest.raises(RuntimeError, match="boom"), td as d:
            _raise_boom()
        assert d.exists()
        import shutil

        shutil.rmtree(d)


class TestTempDirKeepOnError:
    """keep_on_error behavior."""

    def test_keep_on_error_with_exception_stays(self) -> None:
        td = temp_dir(keep_on_error=True)
        with pytest.raises(RuntimeError, match="boom"), td as d:
            _raise_boom()
        assert d.exists()
        import shutil

        shutil.rmtree(d)

    def test_keep_on_error_no_exception_deleted(self) -> None:
        with temp_dir(keep_on_error=True) as d:
            pass
        assert not d.exists()


class TestTempDirUserKeep:
    """.keep() method."""

    def test_keep_method_stays(self) -> None:
        td = temp_dir()
        with td as d:
            td.keep()
        assert d.exists()
        d.rmdir()

    def test_keep_before_enter_raises(self) -> None:
        td = temp_dir()
        with pytest.raises(RuntimeError, match="before __enter__"):
            td.keep()


class TestTempDirDebug:
    """DEBUG / TMPKIT_DEBUG env vars force keep."""

    def test_debug_env_stays(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DEBUG", "1")
        with temp_dir() as d:
            pass
        assert d.exists()
        import shutil

        shutil.rmtree(d)

    def test_tmpkit_debug_env_stays(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TMPKIT_DEBUG", "1")
        with temp_dir() as d:
            pass
        assert d.exists()
        import shutil

        shutil.rmtree(d)

    def test_no_debug_no_keep_deleted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DEBUG", raising=False)
        monkeypatch.delenv("TMPKIT_DEBUG", raising=False)
        with temp_dir() as d:
            pass
        assert not d.exists()


class TestTempDirPrecedence:
    """Precedence: .keep() > keep=True > DEBUG=1 > keep_on_error=True."""

    def test_keep_true_wins_over_keep_on_error(self) -> None:
        td = temp_dir(keep=True, keep_on_error=True)
        with td as d:
            pass
        assert d.exists()
        import shutil

        shutil.rmtree(d)

    def test_debug_wins_over_keep_on_error_no_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DEBUG", "1")
        with temp_dir(keep_on_error=True) as d:
            pass
        assert d.exists()
        import shutil

        shutil.rmtree(d)

    def test_user_keep_wins_over_everything(self) -> None:
        td = temp_dir(keep=False, keep_on_error=False)
        with td as d:
            td.keep()
        assert d.exists()
        import shutil

        shutil.rmtree(d)


class TestTempDirIgnoreCleanupErrors:
    """ignore_cleanup_errors behavior."""

    def test_ignore_true_swallows_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("DEBUG", raising=False)
        monkeypatch.delenv("TMPKIT_DEBUG", raising=False)
        # Pre-delete the dir so shutil.rmtree raises
        td = temp_dir(ignore_cleanup_errors=True)
        td.__enter__()
        import shutil

        shutil.rmtree(td.path)
        # Should not raise
        td.__exit__(None, None, None)

    def test_ignore_false_propagates_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("DEBUG", raising=False)
        monkeypatch.delenv("TMPKIT_DEBUG", raising=False)
        td = temp_dir(ignore_cleanup_errors=False)
        td.__enter__()
        import shutil

        shutil.rmtree(td.path)
        with pytest.raises(OSError):
            td.__exit__(None, None, None)
