"""Tests for async temp_dir(): parameters, keep, cwd, path ops."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from tmpkit._async import temp_dir as async_temp_dir


class TestAsyncBasic:
    """Basic async creation and auto-delete."""

    async def test_create_and_auto_delete(self) -> None:
        async with async_temp_dir() as d:
            assert d.exists()
            assert d.is_dir()
        assert not d.exists()

    async def test_enter_returns_path(self) -> None:
        async with async_temp_dir() as d:
            assert isinstance(d, Path)

    async def test_removed_even_on_exception(self) -> None:
        with pytest.raises(RuntimeError, match="boom"):
            async with async_temp_dir() as d:
                (d / "file.txt").write_text("content")
                raise RuntimeError("boom")
        assert not d.exists()


class TestAsyncParameters:
    """All sync parameters work in async."""

    async def test_suffix_applied(self) -> None:
        async with async_temp_dir(suffix="_data") as d:
            assert d.name.endswith("_data")

    async def test_prefix_applied(self) -> None:
        async with async_temp_dir(prefix="myapp_") as d:
            assert d.name.startswith("myapp_")

    async def test_dir_works(self, tmp_path: Path) -> None:
        async with async_temp_dir(dir=str(tmp_path)) as d:
            assert d.parent == tmp_path


class TestAsyncKeep:
    """keep, keep_on_error, .keep() work in async."""

    async def test_keep_true_stays(self) -> None:
        async with async_temp_dir(keep=True) as d:
            pass
        assert d.exists()
        shutil.rmtree(d)

    async def test_keep_on_error_with_exception_stays(self) -> None:
        with pytest.raises(RuntimeError, match="boom"):
            async with async_temp_dir(keep_on_error=True) as d:
                raise RuntimeError("boom")
        assert d.exists()
        shutil.rmtree(d)

    async def test_keep_on_error_no_exception_deleted(self) -> None:
        async with async_temp_dir(keep_on_error=True) as d:
            pass
        assert not d.exists()

    async def test_keep_method_stays(self) -> None:
        td = async_temp_dir()
        async with td as d:
            td.keep()
        assert d.exists()
        shutil.rmtree(d)

    async def test_keep_before_enter_raises(self) -> None:
        td = async_temp_dir()
        with pytest.raises(RuntimeError, match="before __enter__"):
            td.keep()


class TestAsyncCwd:
    """cwd=True works in async."""

    async def test_cwd_changes_and_restores(self) -> None:
        original = Path.cwd()
        async with async_temp_dir(cwd=True) as d:
            assert Path.cwd() == d
        assert Path.cwd() == original

    async def test_cwd_restored_on_exception(self) -> None:
        original = Path.cwd()
        with pytest.raises(RuntimeError, match="boom"):
            async with async_temp_dir(cwd=True):
                raise RuntimeError("boom")
        assert Path.cwd() == original


class TestAsyncPathOps:
    """.path, __fspath__, __truediv__, __repr__ are sync."""

    async def test_path_is_sync_property(self) -> None:
        td = async_temp_dir()
        async with td as d:
            assert isinstance(td.path, Path)
            assert td.path == d

    async def test_fspath_returns_str(self) -> None:
        async with async_temp_dir():
            td = async_temp_dir()
            async with td as inner:
                assert isinstance(td.__fspath__(), str)
                assert td.__fspath__() == str(inner)

    async def test_truediv(self) -> None:
        td = async_temp_dir()
        async with td as d:
            child = td / "file.txt"
            assert isinstance(child, Path)
            assert child == d / "file.txt"

    async def test_repr_contains_path(self) -> None:
        td = async_temp_dir()
        async with td:
            r = repr(td)
            assert "AsyncTempDir" in r
            assert "path=" in r


class TestAsyncTreeRemoval:
    """Directory tree fully removed on exit."""

    async def test_tree_with_files_removed(self) -> None:
        async with async_temp_dir() as d:
            (d / "file.txt").write_text("hello")
            (d / "sub").mkdir()
            (d / "sub" / "deep.txt").write_text("world")
        assert not d.exists()
