"""Tests for temp_dir() sync: basic parameters, lifecycle, path operations."""

from __future__ import annotations

from pathlib import Path

import pytest
from tmpkit import temp_dir
from tmpkit._sync import _TempDir


class TestPrefixSuffixPathTraversal:
    """Regression: prefix/suffix must not allow path traversal."""

    def test_prefix_with_separator_rejected(self) -> None:
        with pytest.raises(ValueError, match="path separators"):
            temp_dir(prefix="../evil")

    def test_suffix_with_separator_rejected(self) -> None:
        with pytest.raises(ValueError, match="path separators"):
            temp_dir(suffix="/../evil")

    def test_absolute_prefix_rejected(self) -> None:
        with pytest.raises(ValueError, match="absolute path"):
            temp_dir(prefix="/etc/evil")


class TestBasicCreate:
    """Basic creation and auto-delete."""

    def test_create_and_auto_delete(self) -> None:
        with temp_dir() as d:
            assert d.exists()
            assert d.is_dir()
        assert not d.exists()

    def test_returns_temp_dir_instance(self) -> None:
        td = temp_dir()
        with td as d:
            assert isinstance(td, _TempDir)
            assert isinstance(d, Path)

    def test_enter_returns_path_not_self(self) -> None:
        td = temp_dir()
        with td as d:
            assert d is not td
            assert isinstance(d, Path)

    def test_removed_even_on_exception(self) -> None:
        with pytest.raises(RuntimeError, match="boom"), temp_dir() as d:
            (d / "file.txt").write_text("content")
            raise RuntimeError("boom")
        assert not d.exists()


class TestSuffixPrefix:
    """Suffix and prefix are applied to the temp dir name."""

    def test_suffix_applied(self) -> None:
        with temp_dir(suffix="_data") as d:
            assert d.name.endswith("_data")

    def test_prefix_applied(self) -> None:
        with temp_dir(prefix="myapp_") as d:
            assert d.name.startswith("myapp_")


class TestDir:
    """dir= parameter controls parent directory."""

    def test_dir_works(self, tmp_path: Path) -> None:
        with temp_dir(dir=str(tmp_path)) as d:
            assert d.parent == tmp_path

    def test_dir_with_path_object(self, tmp_path: Path) -> None:
        with temp_dir(dir=tmp_path) as d:
            assert d.parent == tmp_path


class TestPathOperations:
    """.path, __fspath__, __truediv__, __repr__."""

    def test_path_property(self) -> None:
        td = temp_dir()
        with td as d:
            assert td.path == d

    def test_path_returns_path_object(self) -> None:
        td = temp_dir()
        with td as d:
            assert isinstance(td.path, Path)
            assert td.path == d

    def test_fspath_returns_str(self) -> None:
        td = temp_dir()
        with td as d:
            assert isinstance(td.__fspath__(), str)
            assert td.__fspath__() == str(d)

    def test_truediv_creates_child_path(self) -> None:
        td = temp_dir()
        with td as d:
            child = td / "file.txt"
            assert isinstance(child, Path)
            assert child == d / "file.txt"

    def test_repr_contains_path(self) -> None:
        td = temp_dir()
        with td:
            repr_str = repr(td)
            assert "TempDir" in repr_str
            assert "path=" in repr_str
            assert "active" in repr_str

    def test_repr_after_delete(self) -> None:
        td = temp_dir()
        with td:
            pass
        assert "deleted" in repr(td)


class TestTreeRemoval:
    """Directory tree is fully removed on exit."""

    def test_tree_with_files_removed(self) -> None:
        with temp_dir() as d:
            (d / "file1.txt").write_text("hello")
            (d / "subdir").mkdir()
            (d / "subdir" / "file2.txt").write_text("world")
            assert (d / "file1.txt").exists()
            assert (d / "subdir" / "file2.txt").exists()
        assert not d.exists()

    def test_tree_with_nested_dirs_removed(self) -> None:
        with temp_dir() as d:
            deep = d / "a" / "b" / "c"
            deep.mkdir(parents=True)
            (deep / "file.txt").write_text("data")
            assert deep.exists()
        assert not d.exists()


class TestCwd:
    """cwd=True changes working directory and restores on exit."""

    def test_cwd_changes_to_temp_dir(self) -> None:
        original = Path.cwd()
        with temp_dir(cwd=True) as d:
            assert Path.cwd().resolve() == d.resolve()
        assert Path.cwd() == original

    def test_cwd_restored_on_exception(self) -> None:
        original = Path.cwd()
        with pytest.raises(RuntimeError, match="boom"), temp_dir(cwd=True):
            raise RuntimeError("boom")
        assert Path.cwd() == original

    def test_cwd_false_does_not_change(self) -> None:
        original = Path.cwd()
        with temp_dir(cwd=False):
            assert Path.cwd() == original
        assert Path.cwd() == original

    def test_nested_cwd_restores_correctly(self) -> None:
        original = Path.cwd()
        outer = temp_dir(cwd=True)
        inner = temp_dir(cwd=True)
        with outer as od:
            assert Path.cwd().resolve() == od.resolve()
            with inner as id_:
                assert Path.cwd().resolve() == id_.resolve()
            assert Path.cwd().resolve() == od.resolve()
        assert Path.cwd() == original

    def test_cwd_with_keep(self) -> None:
        original = Path.cwd()
        td = temp_dir(cwd=True, keep=True)
        with td as d:
            pass
        assert Path.cwd() == original
        assert d.exists()
        import shutil

        shutil.rmtree(d)


class TestKeepAfterExitRaises:
    """Regression: keep() after __exit__ must raise RuntimeError."""

    def test_keep_after_exit_raises(self) -> None:
        td = temp_dir()
        td.__enter__()
        td.__exit__(None, None, None)
        with pytest.raises(RuntimeError, match="after __exit__"):
            td.keep()

    def test_keep_after_exit_with_error_raises(self) -> None:
        td = temp_dir()
        td.__enter__()
        td.__exit__(RuntimeError, RuntimeError("boom"), None)
        with pytest.raises(RuntimeError, match="after __exit__"):
            td.keep()


class TestContextManagerReuse:
    """Regression: reusing a context manager must reset state correctly."""

    def test_reuse_temp_dir_works(self) -> None:
        """Stale _deleted flag must not affect re-entry."""
        td = temp_dir()
        with td as d1:
            (d1 / "a.txt").write_text("a")
        assert not d1.exists()
        with td as d2:
            assert d2.exists()
            assert d2 != d1
        assert not d2.exists()

    def test_reuse_temp_dir_keep_works(self) -> None:
        """Stale _exited flag must not prevent keep() after re-entry."""
        td = temp_dir()
        with td:
            pass
        with td as d:
            td.keep()
        assert d.exists()
        import shutil

        shutil.rmtree(d)
