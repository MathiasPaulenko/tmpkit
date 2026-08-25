"""Tests for temp_file() sync: basic parameters, lifecycle, file-like delegation."""

from __future__ import annotations

import errno
from pathlib import Path

import pytest
from tmpkit import temp_file
from tmpkit._sync import _TempFile


class TestPrefixSuffixPathTraversal:
    """Regression: prefix/suffix must not allow path traversal."""

    def test_prefix_with_separator_rejected(self) -> None:
        with pytest.raises(ValueError, match="path separators"):
            temp_file(prefix="../evil")

    def test_suffix_with_separator_rejected(self) -> None:
        with pytest.raises(ValueError, match="path separators"):
            temp_file(suffix="/../evil")

    def test_prefix_with_backslash_rejected(self) -> None:
        with pytest.raises(ValueError, match="path separators"):
            temp_file(prefix="..\\evil")

    def test_absolute_prefix_rejected(self) -> None:
        with pytest.raises(ValueError, match="absolute path"):
            temp_file(prefix="/etc/evil")

    def test_absolute_suffix_rejected(self) -> None:
        with pytest.raises(ValueError, match="absolute path"):
            temp_file(suffix="/evil.txt")

    def test_empty_prefix_allowed(self) -> None:
        with temp_file(prefix="") as f:
            f.write(b"data")
        assert not f.path.exists()

    def test_empty_suffix_allowed(self) -> None:
        with temp_file(suffix="") as f:
            f.write(b"data")
        assert not f.path.exists()


class TestBasicCreate:
    """Basic creation, write, and auto-delete."""

    def test_create_and_write(self) -> None:
        with temp_file() as f:
            f.write(b"hello")
            f.seek(0)
            assert f.read() == b"hello"
            assert f.path.exists()

    def test_auto_delete_after_exit(self) -> None:
        with temp_file() as f:
            path = f.path
            assert path.exists()
        assert not path.exists()

    def test_deleted_even_on_exception(self) -> None:
        with pytest.raises(RuntimeError, match="boom"), temp_file() as f:
            path = f.path
            raise RuntimeError("boom")
        assert not path.exists()

    def test_returns_temp_file_instance(self) -> None:
        with temp_file() as f:
            assert isinstance(f, _TempFile)


class TestSuffixPrefix:
    """Suffix and prefix are applied to the temp file name."""

    def test_suffix_applied(self) -> None:
        with temp_file(suffix=".csv") as f:
            assert f.path.suffix == ".csv"

    def test_prefix_applied(self) -> None:
        with temp_file(prefix="myapp_") as f:
            assert f.path.name.startswith("myapp_")


class TestDir:
    """dir= parameter controls parent directory."""

    def test_dir_works(self, tmp_path: Path) -> None:
        with temp_file(dir=str(tmp_path)) as f:
            assert f.path.parent == tmp_path

    def test_dir_with_path_object(self, tmp_path: Path) -> None:
        with temp_file(dir=tmp_path) as f:
            assert f.path.parent == tmp_path


class TestMode:
    """Mode parameter controls file open mode."""

    def test_text_mode(self) -> None:
        with temp_file(mode="w+") as f:
            f.write("hello")
            f.seek(0)
            assert f.read() == "hello"

    def test_binary_mode(self) -> None:
        with temp_file(mode="wb+") as f:
            f.write(b"hello")
            f.seek(0)
            assert f.read() == b"hello"

    def test_default_mode_is_w_plus_b(self) -> None:
        with temp_file() as f:
            f.write(b"data")
            f.seek(0)
            assert f.read() == b"data"


class TestPath:
    """.path property and __fspath__."""

    def test_path_returns_path_object(self) -> None:
        with temp_file() as f:
            assert isinstance(f.path, Path)

    def test_fspath_returns_str(self) -> None:
        with temp_file() as f:
            assert isinstance(f.__fspath__(), str)
            assert f.__fspath__() == str(f.path)

    def test_fspath_compatible_with_open(self) -> None:
        with temp_file(mode="w+") as f:
            f.write("content")
            f.flush()
            f.seek(0)
            with open(f) as fh:
                assert fh.read() == "content"

    def test_repr_contains_path(self) -> None:
        with temp_file() as f:
            repr_str = repr(f)
            assert "TempFile" in repr_str
            assert "path=" in repr_str
            assert "open" in repr_str

    def test_repr_after_close(self) -> None:
        with temp_file() as f:
            f.close()
            assert "closed" in repr(f)

    def test_repr_after_delete(self) -> None:
        with temp_file() as f:
            pass
        assert "deleted" in repr(f)


class TestClose:
    """close() behavior: does not delete, idempotent, raises on read after close."""

    def test_close_does_not_delete(self) -> None:
        with temp_file() as f:
            f.close()
            assert f.path.exists()
        # __exit__ will delete it
        assert not f.path.exists()

    def test_close_is_idempotent(self) -> None:
        with temp_file() as f:
            f.close()
            f.close()  # should not raise

    def test_read_after_close_raises(self) -> None:
        with temp_file() as f:
            f.close()
            with pytest.raises(ValueError, match="closed"):
                f.read()

    def test_write_after_close_raises(self) -> None:
        with temp_file() as f:
            f.close()
            with pytest.raises(ValueError, match="closed"):
                f.write(b"data")

    def test_seek_after_close_raises(self) -> None:
        with temp_file() as f:
            f.close()
            with pytest.raises(ValueError, match="closed"):
                f.seek(0)

    def test_tell_after_close_raises(self) -> None:
        with temp_file() as f:
            f.close()
            with pytest.raises(ValueError, match="closed"):
                f.tell()

    def test_flush_after_close_noop(self) -> None:
        with temp_file() as f:
            f.close()
            f.flush()  # should not raise


class TestExitDoesNotSuppress:
    """__exit__ never suppresses exceptions."""

    def test_exception_propagates(self) -> None:
        with pytest.raises(ValueError, match="user error"), temp_file():
            raise ValueError("user error")

    def test_exit_returns_none(self) -> None:
        # __exit__ returns None (falsy) so exceptions are not suppressed
        f = temp_file()
        f.__enter__()
        result = f.__exit__(None, None, None)
        assert result is None


class TestContent:
    """content= parameter pre-populates the file."""

    def test_str_content_text_mode(self) -> None:
        with temp_file(mode="w+", content="hello world") as f:
            assert f.read() == "hello world"

    def test_bytes_content_binary_mode(self) -> None:
        with temp_file(mode="w+b", content=b"\x00\x01\x02") as f:
            assert f.read() == b"\x00\x01\x02"

    def test_str_content_seek_zero(self) -> None:
        with temp_file(mode="w+", content="data") as f:
            assert f.tell() == 0
            assert f.read() == "data"

    def test_bytes_content_seek_zero(self) -> None:
        with temp_file(mode="w+b", content=b"abc") as f:
            assert f.tell() == 0
            assert f.read() == b"abc"

    def test_content_none_no_write(self) -> None:
        with temp_file(mode="w+b", content=None) as f:
            assert f.tell() == 0
            assert f.read() == b""

    def test_str_with_binary_mode_raises_type_error(self) -> None:
        with (
            pytest.raises(TypeError, match="content is str"),
            temp_file(mode="w+b", content="hello"),
        ):
            pass

    def test_bytes_with_text_mode_raises_type_error(self) -> None:
        with (
            pytest.raises(TypeError, match="content is bytes"),
            temp_file(mode="w+", content=b"hello"),
        ):
            pass


class TestDest:
    """dest= parameter: move temp to destination on success."""

    def test_dest_success_moves_file(self, tmp_path: Path) -> None:
        dest = tmp_path / "final.txt"
        with temp_file(mode="w+b", dest=dest, dir=str(tmp_path)) as f:
            f.write(b"moved content")
            temp_path = f.path
        assert dest.read_bytes() == b"moved content"
        assert not temp_path.exists()

    def test_dest_exception_temp_deleted_dest_untouched(self, tmp_path: Path) -> None:
        dest = tmp_path / "final.txt"
        dest.write_text("original")
        f = temp_file(mode="w+b", dest=dest, dir=str(tmp_path))
        f.__enter__()
        f.write(b"new content")
        temp_path = f.path
        f.__exit__(RuntimeError, RuntimeError("boom"), None)
        assert not temp_path.exists()
        assert dest.read_text() == "original"

    def test_dest_keep_on_error_true_exception_temp_kept(self, tmp_path: Path) -> None:
        dest = tmp_path / "final.txt"
        f = temp_file(mode="w+b", dest=dest, dir=str(tmp_path), keep_on_error=True)
        f.__enter__()
        f.write(b"partial")
        temp_path = f.path
        f.__exit__(RuntimeError, RuntimeError("boom"), None)
        assert temp_path.exists()
        assert not dest.exists()
        temp_path.unlink()

    def test_dest_already_exists_overwritten(self, tmp_path: Path) -> None:
        dest = tmp_path / "existing.txt"
        dest.write_text("old content")
        with temp_file(mode="w+b", dest=dest, dir=str(tmp_path)) as f:
            f.write(b"new content")
        assert dest.read_bytes() == b"new content"

    def test_dest_same_as_temp_noop(self, tmp_path: Path) -> None:
        f = temp_file(mode="w+b", dir=str(tmp_path))
        f.__enter__()
        f.write(b"data")
        # Force dest to be the same as the temp path to trigger no-op branch
        f._dest = f.path  # type: ignore[attr-defined]
        f.__exit__(None, None, None)
        assert f.path.exists()
        f.path.unlink()

    def test_dest_same_as_temp_noop_with_registry(self, tmp_path: Path) -> None:
        """Regression: dest==temp no-op marks record cleaned in registry."""
        from tmpkit._registry import temp_registry

        temp_registry.enable()
        try:
            f = temp_file(mode="w+b", dir=str(tmp_path))
            f.__enter__()
            f.write(b"data")
            f._dest = f.path  # type: ignore[attr-defined]
            f.__exit__(None, None, None)
            assert f.path.exists()
            # Record should be marked cleaned even though no move happened.
            assert len(temp_registry.cleaned) == 1
            assert len(temp_registry.active) == 0
            f.path.unlink()
        finally:
            temp_registry.reset()

    def test_dest_keep_true_takes_precedence(self, tmp_path: Path) -> None:
        dest = tmp_path / "final.txt"
        with temp_file(mode="w+b", dest=dest, dir=str(tmp_path), keep=True) as f:
            f.write(b"kept content")
            temp_path = f.path
        assert temp_path.exists()
        assert not dest.exists()
        temp_path.unlink()

    def test_dest_user_keep_takes_precedence(self, tmp_path: Path) -> None:
        dest = tmp_path / "final.txt"
        with temp_file(mode="w+b", dest=dest, dir=str(tmp_path)) as f:
            f.write(b"user kept")
            f.keep()
            temp_path = f.path
        assert temp_path.exists()
        assert not dest.exists()
        temp_path.unlink()

    def test_dest_debug_takes_precedence(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DEBUG", "1")
        dest = tmp_path / "final.txt"
        with temp_file(mode="w+b", dest=dest, dir=str(tmp_path)) as f:
            f.write(b"debug kept")
            temp_path = f.path
        assert temp_path.exists()
        assert not dest.exists()
        temp_path.unlink()

    def test_dest_str_path(self, tmp_path: Path) -> None:
        dest = tmp_path / "final.txt"
        with temp_file(mode="w+b", dest=str(dest), dir=str(tmp_path)) as f:
            f.write(b"str dest")
        assert dest.read_bytes() == b"str dest"

    def test_dest_text_mode(self, tmp_path: Path) -> None:
        dest = tmp_path / "final.txt"
        with temp_file(mode="w+", dest=dest, dir=str(tmp_path), content="text content"):
            pass
        assert dest.read_text() == "text content"

    def test_dest_repr_shows_moved(self, tmp_path: Path) -> None:
        dest = tmp_path / "final.txt"
        f = temp_file(mode="w+b", dest=dest, dir=str(tmp_path))
        f.__enter__()
        f.write(b"data")
        f.__exit__(None, None, None)
        assert "moved" in repr(f)

    def test_dest_cross_fs_falls_back_to_shutil_move(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dest = tmp_path / "final.txt"

        def cross_fs_replace(src: str, dst: str) -> None:
            raise OSError(errno.EXDEV, "cross-device link")

        monkeypatch.setattr("tmpkit._sync.os.replace", cross_fs_replace)
        with temp_file(mode="w+b", dest=dest, dir=str(tmp_path)) as f:
            f.write(b"cross fs")
        assert dest.read_bytes() == b"cross fs"


class TestKeepAfterExitRaises:
    """Regression: keep() after __exit__ must raise RuntimeError."""

    def test_keep_after_exit_raises(self) -> None:
        f = temp_file()
        f.__enter__()
        f.__exit__(None, None, None)
        with pytest.raises(RuntimeError, match="after __exit__"):
            f.keep()

    def test_keep_after_exit_with_error_raises(self) -> None:
        f = temp_file()
        f.__enter__()
        f.__exit__(RuntimeError, RuntimeError("boom"), None)
        with pytest.raises(RuntimeError, match="after __exit__"):
            f.keep()


class TestContextManagerReuse:
    """Regression: reusing a context manager must reset state correctly."""

    def test_reuse_temp_file_write_works(self) -> None:
        """Stale _closed flag must not prevent writes after re-entry."""
        f = temp_file()
        with f:
            f.write(b"first")
        with f:
            f.write(b"second")
            f.seek(0)
            assert f.read() == b"second"

    def test_reuse_temp_file_keep_works(self) -> None:
        """Stale _exited flag must not prevent keep() after re-entry."""
        f = temp_file()
        with f:
            f.write(b"x")
        with f:
            f.keep()
        assert f.path.exists()
        f.path.unlink()

    def test_reuse_temp_file_path_changes(self) -> None:
        """Re-entry creates a new temp file at a different path."""
        f = temp_file()
        with f:
            path1 = f.path
        with f:
            path2 = f.path
        assert path1 != path2
        assert not path1.exists()
        assert not path2.exists()
