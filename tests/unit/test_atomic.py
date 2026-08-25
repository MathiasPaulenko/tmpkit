"""Tests for atomic_write(): atomic file replacement via temp + os.replace()."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from tmpkit import atomic_write
from tmpkit._async import atomic_write as async_atomic_write


class TestPrefixSuffixPathTraversal:
    """Regression: prefix/suffix must not allow path traversal."""

    def test_prefix_with_separator_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="path separators"):
            atomic_write(tmp_path / "out.txt", prefix="../evil")

    def test_suffix_with_separator_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="path separators"):
            atomic_write(tmp_path / "out.txt", suffix="/../evil")

    def test_absolute_prefix_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="absolute path"):
            atomic_write(tmp_path / "out.txt", prefix="/etc/evil")


class TestBasicWrite:
    """Basic atomic write and rename."""

    def test_write_creates_dest(self, tmp_path: Path) -> None:
        dest = tmp_path / "output.txt"
        with atomic_write(dest, mode="w") as w:
            w.write("hello world")
        assert dest.read_text() == "hello world"

    def test_write_binary(self, tmp_path: Path) -> None:
        dest = tmp_path / "output.bin"
        with atomic_write(dest, mode="wb") as w:
            w.write(b"\x00\x01\x02")
        assert dest.read_bytes() == b"\x00\x01\x02"

    def test_dest_overwritten(self, tmp_path: Path) -> None:
        dest = tmp_path / "existing.txt"
        dest.write_text("old content")
        with atomic_write(dest, mode="w") as w:
            w.write("new content")
        assert dest.read_text() == "new content"

    def test_temp_deleted_after_success(self, tmp_path: Path) -> None:
        dest = tmp_path / "output.txt"
        with atomic_write(dest, mode="w") as w:
            temp_path = w.path
            assert temp_path.exists()
        assert not temp_path.exists()
        assert dest.exists()

    def test_path_is_temp_dest_is_destination(self, tmp_path: Path) -> None:
        dest = tmp_path / "target.txt"
        with atomic_write(dest, mode="w") as w:
            assert w.path != dest
            assert w.dest == dest
            assert w.path.parent == dest.parent


class TestErrorHandling:
    """Exception during write leaves dest untouched, temp deleted."""

    def test_exception_dest_untouched(self, tmp_path: Path) -> None:
        dest = tmp_path / "output.txt"
        dest.write_text("original")
        w = atomic_write(dest, mode="w")
        w.__enter__()
        w.write("partial")
        temp_path = w.path
        w.__exit__(RuntimeError, RuntimeError("boom"), None)
        assert dest.read_text() == "original"
        assert not temp_path.exists()

    def test_exception_temp_deleted(self, tmp_path: Path) -> None:
        dest = tmp_path / "output.txt"
        w = atomic_write(dest, mode="w")
        w.__enter__()
        temp_path = w.path
        w.__exit__(RuntimeError, RuntimeError("boom"), None)
        assert not temp_path.exists()
        assert not dest.exists()

    def test_keep_on_error_keeps_temp(self, tmp_path: Path) -> None:
        dest = tmp_path / "output.txt"
        w = atomic_write(dest, mode="w", keep_on_error=True)
        w.__enter__()
        w.write("partial data")
        temp_path = w.path
        w.__exit__(RuntimeError, RuntimeError("boom"), None)
        assert temp_path.exists()
        assert not dest.exists()
        temp_path.unlink()

    def test_keep_method_keeps_temp(self, tmp_path: Path) -> None:
        dest = tmp_path / "output.txt"
        with atomic_write(dest, mode="w") as w:
            w.write("data")
            w.keep()
            temp_path = w.path
        assert temp_path.exists()
        assert not dest.exists()
        temp_path.unlink()

    def test_keep_before_enter_raises(self, tmp_path: Path) -> None:
        dest = tmp_path / "output.txt"
        w = atomic_write(dest, mode="w")
        with pytest.raises(RuntimeError, match="before __enter__"):
            w.keep()


class TestDestParentMissing:
    """dest.parent doesn't exist -> FileNotFoundError."""

    def test_missing_parent_raises_filenotfounderror(self, tmp_path: Path) -> None:
        dest = tmp_path / "nonexistent" / "output.txt"
        with pytest.raises(FileNotFoundError, match="parent"):
            atomic_write(dest, mode="w").__enter__()

    def test_parent_is_file_raises_notadirectoryerror(self, tmp_path: Path) -> None:
        """Regression: if dest.parent exists but is a file, raise NotADirectoryError
        instead of a confusing OSError from mkstemp."""
        file_path = tmp_path / "afile"
        file_path.write_text("I am a file")
        dest = file_path / "output.txt"
        with pytest.raises(NotADirectoryError, match="not a directory"):
            atomic_write(dest, mode="w").__enter__()


class TestFsync:
    """fsync parameter behavior."""

    def test_fsync_false_skips_fsync(self, tmp_path: Path) -> None:
        dest = tmp_path / "output.txt"
        with atomic_write(dest, mode="w", fsync=False) as w:
            w.write("no fsync")
        assert dest.read_text() == "no fsync"

    def test_fsync_true_default(self, tmp_path: Path) -> None:
        dest = tmp_path / "output.txt"
        with atomic_write(dest, mode="w") as w:
            w.write("with fsync")
        assert dest.read_text() == "with fsync"


class TestTextEncoding:
    """Text mode with encoding and newline."""

    def test_encoding_utf8(self, tmp_path: Path) -> None:
        dest = tmp_path / "unicode.txt"
        with atomic_write(dest, mode="w", encoding="utf-8") as w:
            w.write("héllo wörld")
        assert dest.read_text(encoding="utf-8") == "héllo wörld"

    def test_newline_parameter(self, tmp_path: Path) -> None:
        dest = tmp_path / "newlines.txt"
        with atomic_write(dest, mode="w", newline="") as w:
            w.write("line1\nline2\n")
        assert dest.read_bytes() == b"line1\nline2\n"

    def test_encoding_latin1(self, tmp_path: Path) -> None:
        dest = tmp_path / "latin1.txt"
        with atomic_write(dest, mode="w", encoding="latin-1") as w:
            w.write("café")
        assert dest.read_text(encoding="latin-1") == "café"


class TestPathOps:
    """.path, .dest, __fspath__, __repr__."""

    def test_fspath_returns_temp_path(self, tmp_path: Path) -> None:
        dest = tmp_path / "output.txt"
        with atomic_write(dest, mode="w") as w:
            assert isinstance(w.__fspath__(), str)
            assert w.__fspath__() == str(w.path)

    def test_repr_contains_paths(self, tmp_path: Path) -> None:
        dest = tmp_path / "output.txt"
        with atomic_write(dest, mode="w") as w:
            r = repr(w)
            assert "AtomicWriter" in r
            assert "dest=" in r

    def test_repr_before_enter(self, tmp_path: Path) -> None:
        dest = tmp_path / "output.txt"
        w = atomic_write(dest, mode="w")
        r = repr(w)
        assert "pending" in r
        assert "AtomicWriter" in r


class TestPrefixSuffix:
    """Custom prefix and suffix for temp file."""

    def test_custom_prefix(self, tmp_path: Path) -> None:
        dest = tmp_path / "output.txt"
        with atomic_write(dest, mode="w", prefix="myapp_") as w:
            assert w.path.name.startswith("myapp_")

    def test_custom_suffix(self, tmp_path: Path) -> None:
        dest = tmp_path / "output.txt"
        with atomic_write(dest, mode="w", suffix=".dat") as w:
            assert w.path.suffix == ".dat"


class TestEdgeCases:
    """Edge cases for coverage: close, flush, write-after-close, cleanup errors."""

    def test_write_after_close_raises(self, tmp_path: Path) -> None:
        dest = tmp_path / "output.txt"
        with atomic_write(dest, mode="w") as w:
            w.close()
            with pytest.raises(ValueError, match="closed"):
                w.write("data")

    def test_flush_after_close_noop(self, tmp_path: Path) -> None:
        dest = tmp_path / "output.txt"
        with atomic_write(dest, mode="w") as w:
            w.write("data")
            w.close()
            w.flush()  # should not raise

    def test_close_idempotent(self, tmp_path: Path) -> None:
        dest = tmp_path / "output.txt"
        with atomic_write(dest, mode="w") as w:
            w.write("data")
            w.close()
            w.close()  # should not raise

    def test_close_before_exit_replaces_dest(self, tmp_path: Path) -> None:
        dest = tmp_path / "output.txt"
        with atomic_write(dest, mode="w") as w:
            w.write("pre-closed")
            w.close()
        assert dest.read_text() == "pre-closed"

    def test_error_after_close_deletes_temp(self, tmp_path: Path) -> None:
        dest = tmp_path / "output.txt"
        w = atomic_write(dest, mode="w")
        w.__enter__()
        w.write("data")
        w.close()
        temp_path = w.path
        w.__exit__(RuntimeError, RuntimeError("boom"), None)
        assert not temp_path.exists()
        assert not dest.exists()

    def test_ignore_cleanup_errors_on_error_path(self, tmp_path: Path) -> None:
        dest = tmp_path / "output.txt"
        w = atomic_write(dest, mode="w", ignore_cleanup_errors=True)
        w.__enter__()
        temp_path = w.path
        with patch("tmpkit._atomic.os.unlink", side_effect=OSError("denied")):
            w.__exit__(RuntimeError, RuntimeError("boom"), None)  # should not raise
        assert temp_path.exists()
        temp_path.unlink()

    def test_propagate_cleanup_error_when_not_ignored(self, tmp_path: Path) -> None:
        dest = tmp_path / "output.txt"
        w = atomic_write(dest, mode="w", ignore_cleanup_errors=False)
        w.__enter__()
        with (
            patch("tmpkit._atomic.os.unlink", side_effect=OSError("denied")),
            pytest.raises(OSError, match="denied"),
        ):
            w.__exit__(RuntimeError, RuntimeError("boom"), None)

    def test_fdopen_failure_cleans_temp(self, tmp_path: Path) -> None:
        dest = tmp_path / "output.txt"

        def failing_fdopen(fd: int, **kwargs: object) -> object:
            raise OSError("fdopen failed")

        with (
            patch("tmpkit._atomic.os.fdopen", failing_fdopen),
            pytest.raises(OSError, match="fdopen failed"),
        ):
            atomic_write(dest, mode="w").__enter__()
        assert not dest.exists()

    def test_keep_on_error_with_user_keep(self, tmp_path: Path) -> None:
        dest = tmp_path / "output.txt"
        w = atomic_write(dest, mode="w", keep_on_error=True)
        w.__enter__()
        w.write("data")
        w.keep()
        temp_path = w.path
        w.__exit__(RuntimeError, RuntimeError("boom"), None)
        assert temp_path.exists()
        assert not dest.exists()
        temp_path.unlink()


class TestAsyncAtomicWrite:
    """Async atomic_write() tests."""

    async def test_async_basic_write(self, tmp_path: Path) -> None:
        dest = tmp_path / "async_output.txt"
        async with async_atomic_write(dest, mode="w") as w:
            await w.write("async hello")
        assert dest.read_text() == "async hello"

    async def test_async_binary_write(self, tmp_path: Path) -> None:
        dest = tmp_path / "async_output.bin"
        async with async_atomic_write(dest, mode="wb") as w:
            await w.write(b"\x00\x01\x02")
        assert dest.read_bytes() == b"\x00\x01\x02"

    async def test_async_dest_overwritten(self, tmp_path: Path) -> None:
        dest = tmp_path / "async_existing.txt"
        dest.write_text("old")
        async with async_atomic_write(dest, mode="w") as w:
            await w.write("new")
        assert dest.read_text() == "new"

    async def test_async_exception_dest_untouched(self, tmp_path: Path) -> None:
        dest = tmp_path / "async_output.txt"
        dest.write_text("original")
        w = async_atomic_write(dest, mode="w")
        await w.__aenter__()
        await w.write("partial")
        temp_path = w.path
        await w.__aexit__(RuntimeError, RuntimeError("boom"), None)
        assert dest.read_text() == "original"
        assert not temp_path.exists()

    async def test_async_keep_on_error_keeps_temp(self, tmp_path: Path) -> None:
        dest = tmp_path / "async_output.txt"
        w = async_atomic_write(dest, mode="w", keep_on_error=True)
        await w.__aenter__()
        await w.write("partial data")
        temp_path = w.path
        await w.__aexit__(RuntimeError, RuntimeError("boom"), None)
        assert temp_path.exists()
        assert not dest.exists()
        temp_path.unlink()

    async def test_async_keep_method(self, tmp_path: Path) -> None:
        dest = tmp_path / "async_output.txt"
        async with async_atomic_write(dest, mode="w") as w:
            await w.write("data")
            w.keep()
            temp_path = w.path
        assert temp_path.exists()
        assert not dest.exists()
        temp_path.unlink()

    async def test_async_fsync_false(self, tmp_path: Path) -> None:
        dest = tmp_path / "async_output.txt"
        async with async_atomic_write(dest, mode="w", fsync=False) as w:
            await w.write("no fsync")
        assert dest.read_text() == "no fsync"

    async def test_async_encoding(self, tmp_path: Path) -> None:
        dest = tmp_path / "async_unicode.txt"
        async with async_atomic_write(dest, mode="w", encoding="utf-8") as w:
            await w.write("héllo wörld")
        assert dest.read_text(encoding="utf-8") == "héllo wörld"

    async def test_async_path_and_dest(self, tmp_path: Path) -> None:
        dest = tmp_path / "async_target.txt"
        async with async_atomic_write(dest, mode="w") as w:
            assert w.path != dest
            assert w.dest == dest
            assert w.path.parent == dest.parent

    async def test_async_fspath(self, tmp_path: Path) -> None:
        dest = tmp_path / "async_output.txt"
        async with async_atomic_write(dest, mode="w") as w:
            assert isinstance(w.__fspath__(), str)
            assert w.__fspath__() == str(w.path)

    async def test_async_repr(self, tmp_path: Path) -> None:
        dest = tmp_path / "async_output.txt"
        async with async_atomic_write(dest, mode="w") as w:
            r = repr(w)
            assert "AsyncAtomicWriter" in r
            assert "dest=" in r

    async def test_async_flush(self, tmp_path: Path) -> None:
        dest = tmp_path / "async_output.txt"
        async with async_atomic_write(dest, mode="w") as w:
            await w.write("data")
            await w.flush()
        assert dest.read_text() == "data"

    async def test_async_close(self, tmp_path: Path) -> None:
        dest = tmp_path / "async_output.txt"
        w = async_atomic_write(dest, mode="w")
        await w.__aenter__()
        await w.write("data")
        await w.close()
        await w.__aexit__(None, None, None)
        assert dest.read_text() == "data"

    async def test_async_missing_parent_raises(self, tmp_path: Path) -> None:
        dest = tmp_path / "nonexistent" / "async_output.txt"
        with pytest.raises(FileNotFoundError, match="parent"):
            await async_atomic_write(dest, mode="w").__aenter__()


class TestBinaryModeIgnoresTextKwargs:
    """Regression: newline and encoding must not be passed to fdopen in binary mode."""

    def test_binary_mode_with_newline_does_not_raise(self, tmp_path: Path) -> None:
        dest = tmp_path / "out.bin"
        # Before the fix, newline="" was passed to os.fdopen in binary mode,
        # which raised TypeError: can't have newline in binary mode.
        with atomic_write(dest, mode="wb", newline="") as w:
            w.write(b"\x00\x01\x02")
        assert dest.read_bytes() == b"\x00\x01\x02"

    def test_binary_mode_with_encoding_does_not_raise(self, tmp_path: Path) -> None:
        dest = tmp_path / "out.bin"
        # encoding should be silently ignored in binary mode (like open()).
        with atomic_write(dest, mode="wb", encoding="utf-8") as w:
            w.write(b"data")
        assert dest.read_bytes() == b"data"

    def test_binary_mode_with_both_kwargs(self, tmp_path: Path) -> None:
        dest = tmp_path / "out.bin"
        with atomic_write(dest, mode="wb", encoding="utf-8", newline="") as w:
            w.write(b"binary")
        assert dest.read_bytes() == b"binary"


class TestKeepAfterExitRaises:
    """Regression: keep() after __exit__ must raise RuntimeError."""

    def test_keep_after_exit_raises(self, tmp_path: Path) -> None:
        dest = tmp_path / "out.txt"
        w = atomic_write(dest, mode="w")
        w.__enter__()
        w.write("data")
        w.__exit__(None, None, None)
        with pytest.raises(RuntimeError, match="after __exit__"):
            w.keep()

    def test_keep_after_exit_with_error_raises(self, tmp_path: Path) -> None:
        dest = tmp_path / "out.txt"
        w = atomic_write(dest, mode="w")
        w.__enter__()
        w.write("data")
        w.__exit__(RuntimeError, RuntimeError("boom"), None)
        with pytest.raises(RuntimeError, match="after __exit__"):
            w.keep()


class TestContextManagerReuse:
    """Regression: reusing an atomic_write context manager must reset state."""

    def test_reuse_atomic_write_works(self, tmp_path: Path) -> None:
        """Stale _closed flag must not prevent writes after re-entry."""
        dest = tmp_path / "out.txt"
        w = atomic_write(dest, mode="w")
        with w:
            w.write("first")
        assert dest.read_text() == "first"
        with w:
            w.write("second")
        assert dest.read_text() == "second"

    def test_reuse_atomic_write_keep_works(self, tmp_path: Path) -> None:
        """Stale _exited flag must not prevent keep() after re-entry."""
        dest = tmp_path / "out.txt"
        w = atomic_write(dest, mode="w")
        with w:
            w.write("first")
        with w:
            w.write("second")
            w.keep()
        # keep() prevents the replace, so dest still has "first"
        assert dest.read_text() == "first"
        # temp file should still exist
        assert w.path.exists()
        w.path.unlink()
