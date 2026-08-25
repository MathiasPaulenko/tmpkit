"""Tests for @temp_dir() and @temp_file() decorators."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from tmpkit._decorators import temp_dir as temp_dir_decorator
from tmpkit._decorators import temp_file as temp_file_decorator


class TestTempDirDecoratorSync:
    """@temp_dir() on sync functions."""

    def test_sync_function_gets_temp_dir(self) -> None:
        @temp_dir_decorator()
        def my_func(tmp: Path) -> Path:
            assert tmp.exists()
            assert tmp.is_dir()
            return tmp

        result = my_func()
        assert isinstance(result, Path)
        assert not result.exists()  # cleaned up after exit

    def test_sync_function_cwd_default_true(self) -> None:
        original_cwd = os.getcwd()

        @temp_dir_decorator()
        def my_func(tmp: Path) -> str:
            return os.getcwd()

        result = my_func()
        assert result != original_cwd
        assert os.getcwd() == original_cwd  # restored after exit

    def test_sync_function_cwd_false(self) -> None:
        original_cwd = os.getcwd()

        @temp_dir_decorator(cwd=False)
        def my_func(tmp: Path) -> str:
            return os.getcwd()

        result = my_func()
        assert result == original_cwd

    def test_sync_function_preserves_metadata(self) -> None:
        @temp_dir_decorator()
        def my_func(tmp: Path) -> Path:
            """My docstring."""
            return tmp

        assert my_func.__name__ == "my_func"
        assert my_func.__doc__ == "My docstring."

    def test_sync_function_with_args(self) -> None:
        @temp_dir_decorator()
        def my_func(tmp: Path, a: int, b: int) -> int:
            assert tmp.exists()
            return a + b

        assert my_func(1, 2) == 3

    def test_sync_function_exception_cleans_up(self) -> None:
        @temp_dir_decorator()
        def my_func(tmp: Path) -> Path:
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            my_func()

    def test_sync_function_keep_true(self) -> None:
        @temp_dir_decorator(keep=True)
        def my_func(tmp: Path) -> Path:
            return tmp

        result = my_func()
        assert result.exists()
        result.rmdir()  # cleanup

    def test_sync_function_prefix_suffix(self) -> None:
        @temp_dir_decorator(prefix="test_", suffix="_end")
        def my_func(tmp: Path) -> str:
            return tmp.name

        name = my_func()
        assert name.startswith("test_")
        assert name.endswith("_end")


class TestTempDirDecoratorAsync:
    """@temp_dir() on async functions."""

    async def test_async_function_gets_temp_dir(self) -> None:
        @temp_dir_decorator()
        async def my_func(tmp: Path) -> Path:
            assert tmp.exists()
            return tmp

        result = await my_func()
        assert isinstance(result, Path)
        assert not result.exists()

    async def test_async_function_cwd_default_true(self) -> None:
        original_cwd = os.getcwd()

        @temp_dir_decorator()
        async def my_func(tmp: Path) -> str:
            return os.getcwd()

        result = await my_func()
        assert result != original_cwd
        assert os.getcwd() == original_cwd

    async def test_async_function_preserves_metadata(self) -> None:
        @temp_dir_decorator()
        async def my_func(tmp: Path) -> Path:
            """Async docstring."""
            return tmp

        assert my_func.__name__ == "my_func"
        assert my_func.__doc__ == "Async docstring."

    async def test_async_function_with_args(self) -> None:
        @temp_dir_decorator()
        async def my_func(tmp: Path, a: int, b: str) -> str:
            assert tmp.exists()
            return f"{a}{b}"

        assert await my_func(1, "x") == "1x"

    async def test_async_function_exception_cleans_up(self) -> None:
        @temp_dir_decorator()
        async def my_func(tmp: Path) -> Path:
            raise RuntimeError("async boom")

        with pytest.raises(RuntimeError, match="async boom"):
            await my_func()


class TestTempDirDecoratorClass:
    """@temp_dir() on test classes — each method gets fresh temp."""

    def test_class_each_method_gets_fresh_temp(self) -> None:
        @temp_dir_decorator()
        class MyClass:
            def test_one(self) -> Path:
                assert hasattr(self, "tmpdir")
                assert self.tmpdir.exists()
                return self.tmpdir

            def test_two(self) -> Path:
                assert hasattr(self, "tmpdir")
                assert self.tmpdir.exists()
                return self.tmpdir

        obj = MyClass()
        result1 = obj.test_one()
        assert not result1.exists()  # cleaned up after method

        result2 = obj.test_two()
        assert not result2.exists()
        assert result1 != result2  # different temp dirs

    def test_class_cwd_true_default(self) -> None:
        original_cwd = os.getcwd()

        @temp_dir_decorator()
        class MyClass:
            def test_method(self) -> str:
                return os.getcwd()

        obj = MyClass()
        result = obj.test_method()
        assert result != original_cwd
        assert os.getcwd() == original_cwd

    def test_class_preserves_existing_setup_teardown(self) -> None:
        setup_calls: list[str] = []
        teardown_calls: list[str] = []

        @temp_dir_decorator()
        class MyClass:
            def setup_method(self) -> None:
                setup_calls.append("setup")

            def teardown_method(self) -> None:
                teardown_calls.append("teardown")

            def test_method(self) -> None:
                assert hasattr(self, "tmpdir")

        obj = MyClass()
        obj.setup_method()
        obj.test_method()
        obj.teardown_method()
        assert setup_calls == ["setup"]
        assert teardown_calls == ["teardown"]

    def test_class_keep_true(self) -> None:
        @temp_dir_decorator(keep=True)
        class MyClass:
            def test_method(self) -> Path:
                return self.tmpdir

        obj = MyClass()
        result = obj.test_method()
        assert result.exists()
        result.rmdir()


class TestTempDirDecoratorAsyncClass:
    """@temp_dir() on classes with async test methods."""

    async def test_async_class_method_gets_temp_dir(self) -> None:
        @temp_dir_decorator()
        class MyClass:
            async def test_method(self) -> Path:
                assert hasattr(self, "tmpdir")
                assert self.tmpdir.exists()
                return self.tmpdir

        obj = MyClass()
        result = await obj.test_method()
        assert isinstance(result, Path)
        assert not result.exists()  # cleaned up after method


class TestTempFileDecoratorSync:
    """@temp_file() injects temp file as first positional arg."""

    def test_sync_function_gets_temp_file(self) -> None:
        @temp_file_decorator()
        def my_func(f: object) -> bool:
            f.write(b"hello")  # type: ignore[attr-defined]
            f.seek(0)  # type: ignore[attr-defined]
            return True

        assert my_func() is True

    def test_sync_function_preserves_metadata(self) -> None:
        @temp_file_decorator()
        def my_func(f: object) -> None:
            """File docstring."""
            return None

        assert my_func.__name__ == "my_func"
        assert my_func.__doc__ == "File docstring."

    def test_sync_function_with_args(self) -> None:
        @temp_file_decorator(mode="w+")
        def my_func(f: object, a: int, b: str) -> str:
            f.write(f"{a}{b}")  # type: ignore[attr-defined]
            f.seek(0)  # type: ignore[attr-defined]
            return f.read()  # type: ignore[no-any-return]

        assert my_func(42, "x") == "42x"

    def test_sync_function_content_preset(self) -> None:
        @temp_file_decorator(mode="w+", content="preset data")
        def my_func(f: object) -> str:
            f.seek(0)  # type: ignore[attr-defined]
            return f.read()  # type: ignore[no-any-return]

        assert my_func() == "preset data"

    def test_sync_function_exception_cleans_up(self) -> None:
        @temp_file_decorator()
        def my_func(f: object) -> None:
            raise RuntimeError("file boom")

        with pytest.raises(RuntimeError, match="file boom"):
            my_func()

    def test_sync_function_keep_true(self) -> None:
        @temp_file_decorator(keep=True)
        def my_func(f: object) -> Path:
            f.write(b"kept")  # type: ignore[attr-defined]
            return f.path  # type: ignore[attr-defined]

        result = my_func()
        assert result.exists()
        result.unlink()

    def test_sync_function_dest_moves(self, tmp_path: Path) -> None:
        dest = tmp_path / "final.txt"

        @temp_file_decorator(mode="w+b", dest=dest, dir=str(tmp_path))
        def my_func(f: object) -> None:
            f.write(b"decorated dest")  # type: ignore[attr-defined]

        my_func()
        assert dest.read_bytes() == b"decorated dest"


class TestTempFileDecoratorAsync:
    """@temp_file() on async functions."""

    async def test_async_function_gets_temp_file(self) -> None:
        @temp_file_decorator()
        async def my_func(f: object) -> bool:
            await f.write(b"async hello")  # type: ignore[attr-defined]
            await f.seek(0)  # type: ignore[attr-defined]
            data = await f.read()  # type: ignore[attr-defined]
            return data == b"async hello"

        assert await my_func() is True

    async def test_async_function_preserves_metadata(self) -> None:
        @temp_file_decorator()
        async def my_func(f: object) -> None:
            """Async file docstring."""
            return None

        assert my_func.__name__ == "my_func"
        assert my_func.__doc__ == "Async file docstring."

    async def test_async_function_with_args(self) -> None:
        @temp_file_decorator(mode="w+")
        async def my_func(f: object, a: int, b: str) -> str:
            await f.write(f"{a}{b}")  # type: ignore[attr-defined]
            await f.seek(0)  # type: ignore[attr-defined]
            return await f.read()  # type: ignore[no-any-return]

        assert await my_func(42, "x") == "42x"

    async def test_async_function_exception_cleans_up(self) -> None:
        @temp_file_decorator()
        async def my_func(f: object) -> None:
            raise RuntimeError("async file boom")

        with pytest.raises(RuntimeError, match="async file boom"):
            await my_func()
