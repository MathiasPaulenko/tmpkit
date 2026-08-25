"""Tests for Windows safety: close-without-delete, ignore_cleanup_errors, mkstemp usage."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from tmpkit import temp_dir, temp_file


class TestCloseDoesNotDelete:
    """close() does NOT delete the file — explicit tests."""

    def test_close_keeps_file_on_disk(self) -> None:
        with temp_file() as f:
            f.write(b"data")
            f.close()
            assert f.path.exists()

    def test_close_then_reopen_by_path(self) -> None:
        with temp_file() as f:
            f.write(b"content")
            f.close()
            with open(f.path, "rb") as fh:
                assert fh.read() == b"content"

    def test_close_idempotent(self) -> None:
        with temp_file() as f:
            f.close()
            f.close()  # should not raise

    def test_read_after_close_raises(self) -> None:
        with temp_file() as f:
            f.close()
            with pytest.raises(ValueError, match="closed"):
                f.read()

    def test_file_deleted_on_context_exit_not_on_close(self) -> None:
        f = temp_file()
        f.__enter__()
        path = f.path
        f.close()
        assert path.exists()
        f.__exit__(None, None, None)
        assert not path.exists()


class TestIgnoreCleanupErrorsDefault:
    """ignore_cleanup_errors=True is the default."""

    def test_default_ignore_cleanup_errors_true_file(self) -> None:
        f = temp_file()
        assert f._ignore_cleanup_errors is True

    def test_default_ignore_cleanup_errors_true_dir(self) -> None:
        td = temp_dir()
        assert td._ignore_cleanup_errors is True

    def test_permission_error_on_unlink_swallowed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("DEBUG", raising=False)
        monkeypatch.delenv("TMPKIT_DEBUG", raising=False)
        f = temp_file(ignore_cleanup_errors=True)
        f.__enter__()
        f.close()
        # Patch os.unlink to raise PermissionError
        with patch("os.unlink", side_effect=PermissionError("denied")):
            f.__exit__(None, None, None)  # should not raise

    def test_permission_error_on_rmtree_swallowed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("DEBUG", raising=False)
        monkeypatch.delenv("TMPKIT_DEBUG", raising=False)
        td = temp_dir(ignore_cleanup_errors=True)
        td.__enter__()
        with patch("shutil.rmtree", side_effect=PermissionError("denied")):
            td.__exit__(None, None, None)  # should not raise

    def test_cleanup_error_propagates_when_not_ignored(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("DEBUG", raising=False)
        monkeypatch.delenv("TMPKIT_DEBUG", raising=False)
        f = temp_file(ignore_cleanup_errors=False)
        f.__enter__()
        f.close()
        with (
            patch("os.unlink", side_effect=PermissionError("denied")),
            pytest.raises(PermissionError, match="denied"),
        ):
            f.__exit__(None, None, None)

    def test_cleanup_error_propagates_for_dir_when_not_ignored(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("DEBUG", raising=False)
        monkeypatch.delenv("TMPKIT_DEBUG", raising=False)
        td = temp_dir(ignore_cleanup_errors=False)
        td.__enter__()
        with (
            patch("shutil.rmtree", side_effect=PermissionError("denied")),
            pytest.raises(PermissionError, match="denied"),
        ):
            td.__exit__(None, None, None)


class TestMkstempUsage:
    """Verify mkstemp is used (not NamedTemporaryFile with delete=True)."""

    def test_temp_file_uses_mkstemp(self, monkeypatch: pytest.MonkeyPatch) -> None:
        called = {"mkstemp": False}
        original_mkstemp = __import__("tempfile").mkstemp

        def tracking_mkstemp(*args: object, **kwargs: object) -> tuple[int, str]:
            called["mkstemp"] = True
            return original_mkstemp()

        monkeypatch.setattr("tempfile.mkstemp", tracking_mkstemp)
        with temp_file():
            pass
        assert called["mkstemp"] is True

    def test_temp_dir_uses_mkdtemp(self, monkeypatch: pytest.MonkeyPatch) -> None:
        called = {"mkdtemp": False}
        original_mkdtemp = __import__("tempfile").mkdtemp

        def tracking_mkdtemp(*args: object, **kwargs: object) -> str:
            called["mkdtemp"] = True
            return original_mkdtemp()

        monkeypatch.setattr("tempfile.mkdtemp", tracking_mkdtemp)
        with temp_dir():
            pass
        assert called["mkdtemp"] is True

    def test_file_does_not_use_named_temporary_file(self) -> None:
        """The file handle comes from os.fdopen, not NamedTemporaryFile."""
        f = temp_file()
        f.__enter__()
        # NamedTemporaryFile sets .name and .delete; our file comes from fdopen
        assert hasattr(f, "_file")
        assert f._file is not None
        # Our file should not have a 'delete' attribute (NamedTemporaryFile does)
        assert not hasattr(f._file, "delete")
        f.__exit__(None, None, None)


class TestWindowsNameMock:
    """Mock os.name=='nt' to exercise Windows code paths on non-Windows.

    These tests mock ``os.name`` to ``"nt"`` to verify that tmpkit's code
    paths don't break when ``os.name`` is ``"nt"``. However, ``tempfile``
    uses ``os.name`` internally to select the temp directory and path
    conventions, so mocking it on non-Windows causes ``mkstemp``/``mkdtemp``
    to produce paths that don't exist on the real filesystem. Therefore
    these tests only run on Windows.
    """

    @pytest.mark.skipif(os.name != "nt", reason="requires real Windows filesystem")
    def test_file_works_with_nt_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(os, "name", "nt")
        with temp_file() as f:
            f.write(b"test")
            f.seek(0)
            assert f.read() == b"test"

    @pytest.mark.skipif(os.name != "nt", reason="requires real Windows filesystem")
    def test_dir_works_with_nt_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(os, "name", "nt")
        with temp_dir() as d:
            assert d.exists()
        assert not d.exists()

    @pytest.mark.skipif(os.name != "nt", reason="requires real Windows filesystem")
    def test_close_does_not_delete_with_nt_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(os, "name", "nt")
        f = temp_file()
        f.__enter__()
        f.close()
        assert f.path.exists()
        f.__exit__(None, None, None)
        assert not f.path.exists()


class TestSubprocessCanOpenAfterClose:
    """After close(), a subprocess can open the file by path."""

    def test_subprocess_reads_closed_file(self) -> None:
        import subprocess
        import sys

        with temp_file(mode="w+b") as f:
            f.write(b"subprocess content")
            f.close()
            # subprocess can open the file by path
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    f"import sys; print(open(r'{f.path}', 'rb').read())",
                ],
                capture_output=True,
                timeout=10,
            )
            assert b"subprocess content" in result.stdout
