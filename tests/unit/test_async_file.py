"""Tests for async temp_file(): parameters, keep, content, async I/O."""

from __future__ import annotations

from pathlib import Path

import pytest
from tmpkit._async import temp_file as async_temp_file


class TestAsyncBasic:
    """Basic async creation and auto-delete."""

    async def test_create_and_write(self) -> None:
        async with async_temp_file() as f:
            await f.write(b"hello")
            await f.seek(0)
            data = await f.read()
            assert data == b"hello"

    async def test_auto_delete_after_exit(self) -> None:
        async with async_temp_file() as f:
            path = f.path
        assert not path.exists()

    async def test_deleted_even_on_exception(self) -> None:
        with pytest.raises(RuntimeError, match="boom"):
            async with async_temp_file() as f:
                path = f.path
                raise RuntimeError("boom")
        assert not path.exists()


class TestAsyncParameters:
    """All sync parameters work in async."""

    async def test_suffix_applied(self) -> None:
        async with async_temp_file(suffix=".csv") as f:
            assert f.path.suffix == ".csv"

    async def test_prefix_applied(self) -> None:
        async with async_temp_file(prefix="myapp_") as f:
            assert f.path.name.startswith("myapp_")

    async def test_dir_works(self, tmp_path: Path) -> None:
        async with async_temp_file(dir=str(tmp_path)) as f:
            assert f.path.parent == tmp_path

    async def test_text_mode(self) -> None:
        async with async_temp_file(mode="w+") as f:
            await f.write("text content")
            await f.seek(0)
            assert await f.read() == "text content"

    async def test_binary_mode(self) -> None:
        async with async_temp_file(mode="w+b") as f:
            await f.write(b"binary")
            await f.seek(0)
            assert await f.read() == b"binary"


class TestAsyncContent:
    """content= works in async."""

    async def test_str_content_text_mode(self) -> None:
        async with async_temp_file(mode="w+", content="hello") as f:
            assert await f.read() == "hello"

    async def test_bytes_content_binary_mode(self) -> None:
        async with async_temp_file(mode="w+b", content=b"data") as f:
            assert await f.read() == b"data"

    async def test_str_with_binary_mode_raises(self) -> None:
        with pytest.raises(TypeError, match="content is str"):
            async with async_temp_file(mode="w+b", content="hello"):
                pass

    async def test_bytes_with_text_mode_raises(self) -> None:
        with pytest.raises(TypeError, match="content is bytes"):
            async with async_temp_file(mode="w+", content=b"hello"):
                pass


class TestAsyncKeep:
    """keep, keep_on_error, .keep() work in async."""

    async def test_keep_true_stays(self) -> None:
        async with async_temp_file(keep=True) as f:
            path = f.path
        assert path.exists()

    async def test_keep_on_error_with_exception_stays(self) -> None:
        with pytest.raises(RuntimeError, match="boom"):
            async with async_temp_file(keep_on_error=True) as f:
                path = f.path
                raise RuntimeError("boom")
        assert path.exists()

    async def test_keep_on_error_no_exception_deleted(self) -> None:
        async with async_temp_file(keep_on_error=True) as f:
            path = f.path
        assert not path.exists()

    async def test_keep_method_stays(self) -> None:
        async with async_temp_file() as f:
            f.keep()
            path = f.path
        assert path.exists()

    async def test_keep_before_enter_raises(self) -> None:
        f = async_temp_file()
        with pytest.raises(RuntimeError, match="before __enter__"):
            f.keep()


class TestAsyncPathOps:
    """.path is sync, __fspath__ sync, __repr__ sync."""

    async def test_path_is_sync_property(self) -> None:
        async with async_temp_file() as f:
            assert isinstance(f.path, Path)

    async def test_fspath_returns_str(self) -> None:
        async with async_temp_file() as f:
            assert isinstance(f.__fspath__(), str)

    async def test_repr_contains_path(self) -> None:
        async with async_temp_file() as f:
            r = repr(f)
            assert "AsyncTempFile" in r
            assert "path=" in r


class TestAsyncIO:
    """async I/O methods work via asyncio.to_thread."""

    async def test_seek_tell(self) -> None:
        async with async_temp_file(mode="w+b") as f:
            await f.write(b"abcdef")
            pos = await f.tell()
            assert pos == 6
            await f.seek(3)
            assert await f.tell() == 3
            assert await f.read() == b"def"

    async def test_flush(self) -> None:
        async with async_temp_file(mode="w+b") as f:
            await f.write(b"data")
            await f.flush()

    async def test_close(self) -> None:
        f = async_temp_file()
        await f.__aenter__()
        await f.close()
        with pytest.raises(ValueError, match="closed"):
            await f.read()
        await f.__aexit__(None, None, None)


class TestAsyncDest:
    """dest= parameter in async temp_file()."""

    async def test_dest_success_moves_file(self, tmp_path: Path) -> None:
        dest = tmp_path / "final.txt"
        async with async_temp_file(mode="w+b", dest=dest, dir=str(tmp_path)) as f:
            await f.write(b"moved content")
            temp_path = f.path
        assert dest.read_bytes() == b"moved content"
        assert not temp_path.exists()

    async def test_dest_exception_temp_deleted_dest_untouched(
        self, tmp_path: Path
    ) -> None:
        dest = tmp_path / "final.txt"
        dest.write_text("original")
        f = async_temp_file(mode="w+b", dest=dest, dir=str(tmp_path))
        await f.__aenter__()
        await f.write(b"new content")
        temp_path = f.path
        await f.__aexit__(RuntimeError, RuntimeError("boom"), None)
        assert not temp_path.exists()
        assert dest.read_text() == "original"

    async def test_dest_keep_on_error_true_exception_temp_kept(
        self, tmp_path: Path
    ) -> None:
        dest = tmp_path / "final.txt"
        f = async_temp_file(
            mode="w+b", dest=dest, dir=str(tmp_path), keep_on_error=True
        )
        await f.__aenter__()
        await f.write(b"partial")
        temp_path = f.path
        await f.__aexit__(RuntimeError, RuntimeError("boom"), None)
        assert temp_path.exists()
        assert not dest.exists()
        temp_path.unlink()

    async def test_dest_already_exists_overwritten(self, tmp_path: Path) -> None:
        dest = tmp_path / "existing.txt"
        dest.write_text("old content")
        async with async_temp_file(mode="w+b", dest=dest, dir=str(tmp_path)) as f:
            await f.write(b"new content")
        assert dest.read_bytes() == b"new content"

    async def test_dest_keep_true_takes_precedence(self, tmp_path: Path) -> None:
        dest = tmp_path / "final.txt"
        async with async_temp_file(
            mode="w+b", dest=dest, dir=str(tmp_path), keep=True
        ) as f:
            await f.write(b"kept content")
            temp_path = f.path
        assert temp_path.exists()
        assert not dest.exists()
        temp_path.unlink()

    async def test_dest_user_keep_takes_precedence(self, tmp_path: Path) -> None:
        dest = tmp_path / "final.txt"
        async with async_temp_file(mode="w+b", dest=dest, dir=str(tmp_path)) as f:
            await f.write(b"user kept")
            f.keep()
            temp_path = f.path
        assert temp_path.exists()
        assert not dest.exists()
        temp_path.unlink()

    async def test_dest_str_path(self, tmp_path: Path) -> None:
        dest = tmp_path / "final.txt"
        async with async_temp_file(mode="w+b", dest=str(dest), dir=str(tmp_path)) as f:
            await f.write(b"str dest")
        assert dest.read_bytes() == b"str dest"
