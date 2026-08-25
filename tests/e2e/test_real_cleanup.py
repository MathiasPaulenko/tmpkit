"""E2E tests: real filesystem cleanup verification."""

from __future__ import annotations

import shutil
from pathlib import Path

from tmpkit import temp_dir, temp_file


class TestRealFileCleanup:
    """Real temp file creation and cleanup on the actual filesystem."""

    def test_file_deleted_after_exit(self) -> None:
        with temp_file() as f:
            path = f.path
            assert path.exists()
        assert not path.exists()

    def test_file_keep_true_stays(self) -> None:
        with temp_file(keep=True) as f:
            path = f.path
            assert path.exists()
        assert path.exists()
        path.unlink()

    def test_file_keep_on_error_with_exception_stays(self) -> None:
        f = temp_file(keep_on_error=True)
        f.__enter__()
        path = f.path
        f.__exit__(RuntimeError, RuntimeError("boom"), None)
        assert path.exists()
        path.unlink()

    def test_file_keep_on_error_no_exception_deleted(self) -> None:
        with temp_file(keep_on_error=True) as f:
            path = f.path
        assert not path.exists()

    def test_file_with_content_real_write(self) -> None:
        with temp_file(mode="w+", content="real content") as f:
            assert f.path.read_text() == "real content"
        assert not f.path.exists()

    def test_file_close_then_exit_deletes(self) -> None:
        with temp_file() as f:
            f.write(b"data")
            f.close()
            assert f.path.exists()
        assert not f.path.exists()


class TestRealDirCleanup:
    """Real temp dir creation and cleanup on the actual filesystem."""

    def test_dir_deleted_after_exit(self) -> None:
        with temp_dir() as d:
            assert d.exists()
            (d / "file.txt").write_text("content")
        assert not d.exists()

    def test_dir_keep_true_stays(self) -> None:
        with temp_dir(keep=True) as d:
            pass
        assert d.exists()
        shutil.rmtree(d)

    def test_dir_keep_on_error_with_exception_stays(self) -> None:
        td = temp_dir(keep_on_error=True)
        d = td.__enter__()
        td.__exit__(RuntimeError, RuntimeError("boom"), None)
        assert d.exists()
        shutil.rmtree(d)

    def test_dir_keep_on_error_no_exception_deleted(self) -> None:
        with temp_dir(keep_on_error=True) as d:
            pass
        assert not d.exists()

    def test_dir_cwd_restored_after_exit(self) -> None:
        original = Path.cwd()
        with temp_dir(cwd=True) as d:
            assert Path.cwd() == d
        assert Path.cwd() == original

    def test_dir_tree_fully_removed(self) -> None:
        with temp_dir() as d:
            deep = d / "a" / "b" / "c"
            deep.mkdir(parents=True)
            (deep / "file.txt").write_text("nested")
        assert not d.exists()


class TestRealAsyncCleanup:
    """Real async temp file/dir cleanup."""

    async def test_async_file_deleted_after_exit(self) -> None:
        from tmpkit import async_temp_file

        async with async_temp_file() as f:
            path = f.path
            await f.write(b"async data")
        assert not path.exists()

    async def test_async_dir_deleted_after_exit(self) -> None:
        from tmpkit import async_temp_dir

        async with async_temp_dir() as d:
            assert d.exists()
        assert not d.exists()

    async def test_async_file_keep_true_stays(self) -> None:
        from tmpkit import async_temp_file

        async with async_temp_file(keep=True) as f:
            path = f.path
        assert path.exists()
        path.unlink()

    async def test_async_dir_keep_true_stays(self) -> None:
        from tmpkit import async_temp_dir

        async with async_temp_dir(keep=True) as d:
            pass
        assert d.exists()
        shutil.rmtree(d)
