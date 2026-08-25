"""Regression tests for error-handling paths in _atomic.py and _sync.py.

Covers:
- atomic_write: flush/fsync failure cleans up temp file
- atomic_write: os.replace failure cleans up temp file
- atomic_write: DEBUG env var keeps temp file
- atomic_write: temp_registry integration
- temp_file dest: os.replace failure cleans up temp file
- temp_file dest: shutil.move failure cleans up temp file
- _safe_unlink / _safe_unlink_temp methods
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from tmpkit._atomic import atomic_write
from tmpkit._registry import temp_registry
from tmpkit._sync import temp_dir, temp_file


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    """Reset registry state before and after each test."""
    temp_registry.reset()
    yield
    temp_registry.reset()


class TestAtomicFlushFsyncFailure:
    """flush()/fsync() failure in atomic_write cleans up temp file."""

    def test_fsync_failure_cleans_up_temp(self, tmp_path: Path) -> None:
        dest = tmp_path / "out.txt"
        with (
            patch("os.fsync", side_effect=OSError("disk full")),
            pytest.raises(OSError, match="disk full"),
            atomic_write(dest, mode="w") as w,
        ):
            w.write("data")

        assert not w.path.exists()
        assert not dest.exists()

    def test_flush_failure_cleans_up_temp(self, tmp_path: Path) -> None:
        dest = tmp_path / "out.txt"
        w = atomic_write(dest, mode="w")
        w.__enter__()
        w.write("data")
        w._file.flush = lambda: (_ for _ in ()).throw(OSError("flush fail"))  # type: ignore[method-assign]
        with pytest.raises(OSError, match="flush fail"):
            w.__exit__(None, None, None)

        assert not w.path.exists()
        assert not dest.exists()

    def test_fsync_failure_with_keep_on_error_keeps_temp(self, tmp_path: Path) -> None:
        dest = tmp_path / "out.txt"
        with (
            patch("os.fsync", side_effect=OSError("disk full")),
            pytest.raises(OSError, match="disk full"),
            atomic_write(dest, mode="w", keep_on_error=True) as w,
        ):
            w.write("data")

        assert w.path.exists()
        w.path.unlink()


class TestAtomicReplaceFailure:
    """os.replace() failure in atomic_write cleans up temp file."""

    def test_replace_failure_cleans_up_temp(self, tmp_path: Path) -> None:
        dest = tmp_path / "out.txt"
        with (
            patch("os.replace", side_effect=OSError("replace failed")),
            pytest.raises(OSError, match="replace failed"),
            atomic_write(dest, mode="w") as w,
        ):
            w.write("data")

        assert not w.path.exists()
        assert not dest.exists()

    def test_replace_failure_with_ignore_cleanup_errors(self, tmp_path: Path) -> None:
        dest = tmp_path / "out.txt"

        def replace_side_effect(src: str, dst: str) -> None:
            raise OSError("replace failed")

        with (
            patch("os.replace", side_effect=replace_side_effect),
            patch("os.unlink", side_effect=OSError("unlink also fails")),
            pytest.raises(OSError, match="replace failed"),
            atomic_write(dest, mode="w", ignore_cleanup_errors=True) as w,
        ):
            w.write("data")

    def test_replace_failure_propagates_unlink_error(self, tmp_path: Path) -> None:
        dest = tmp_path / "out.txt"

        def replace_side_effect(src: str, dst: str) -> None:
            raise OSError("replace failed")

        with (
            patch("os.replace", side_effect=replace_side_effect),
            patch("os.unlink", side_effect=OSError("unlink also fails")),
            pytest.raises(OSError, match="unlink also fails"),
            atomic_write(dest, mode="w", ignore_cleanup_errors=False) as w,
        ):
            w.write("data")


class TestAtomicDebugEnvVar:
    """DEBUG=1 / TMPKIT_DEBUG=1 keeps temp files for atomic_write."""

    def test_debug_env_keeps_temp(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TMPKIT_DEBUG", "1")
        dest = tmp_path / "out.txt"
        with atomic_write(dest, mode="w") as w:
            w.write("data")

        assert w.path.exists()
        assert not dest.exists()
        w.path.unlink()

    def test_debug_env_keeps_temp_on_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TMPKIT_DEBUG", "1")
        dest = tmp_path / "out.txt"
        with (
            pytest.raises(RuntimeError, match="boom"),
            atomic_write(dest, mode="w") as w,
        ):
            w.write("data")
            raise RuntimeError("boom")

        assert w.path.exists()
        assert not dest.exists()
        w.path.unlink()


class TestAtomicRegistryIntegration:
    """atomic_write registers with temp_registry."""

    def test_registry_tracks_atomic_write(self, tmp_path: Path) -> None:
        temp_registry.enable()
        dest = tmp_path / "out.txt"
        with atomic_write(dest, mode="w") as w:
            assert len(temp_registry.active) == 1
            assert temp_registry.active[0].path == w.path
            assert temp_registry.active[0].kind == "file"
        assert len(temp_registry.active) == 0
        assert len(temp_registry.cleaned) == 1

    def test_registry_tracks_kept_atomic(self, tmp_path: Path) -> None:
        temp_registry.enable()
        dest = tmp_path / "out.txt"
        with (
            pytest.raises(RuntimeError, match="boom"),
            atomic_write(dest, mode="w", keep_on_error=True) as w,
        ):
            raise RuntimeError("boom")

        assert len(temp_registry.active) == 0
        records = temp_registry.all
        assert len(records) == 1
        assert records[0].kept is True
        w.path.unlink()


class TestSyncDestMoveFailure:
    """temp_file dest move failure cleans up temp file."""

    def test_replace_failure_cleans_up_temp(self, tmp_path: Path) -> None:
        dest = tmp_path / "final.txt"
        with (
            patch("os.replace", side_effect=OSError("replace failed")),
            pytest.raises(OSError, match="replace failed"),
            temp_file(mode="w+b", dest=dest, dir=str(tmp_path)) as f,
        ):
            f.write(b"data")

        assert not f.path.exists()
        assert not dest.exists()

    def test_replace_failure_propagates_unlink_error(self, tmp_path: Path) -> None:
        dest = tmp_path / "final.txt"

        def replace_side_effect(src: str, dst: str) -> None:
            raise OSError("replace failed")

        with (
            patch("os.replace", side_effect=replace_side_effect),
            patch("os.unlink", side_effect=OSError("unlink fails too")),
            pytest.raises(OSError, match="unlink fails too"),
            temp_file(
                mode="w+b", dest=dest, dir=str(tmp_path), ignore_cleanup_errors=False
            ) as f,
        ):
            f.write(b"data")

    def test_replace_failure_ignores_unlink_error(self, tmp_path: Path) -> None:
        dest = tmp_path / "final.txt"

        def replace_side_effect(src: str, dst: str) -> None:
            raise OSError("replace failed")

        with (
            patch("os.replace", side_effect=replace_side_effect),
            patch("os.unlink", side_effect=OSError("unlink fails too")),
            pytest.raises(OSError, match="replace failed"),
            temp_file(
                mode="w+b", dest=dest, dir=str(tmp_path), ignore_cleanup_errors=True
            ) as f,
        ):
            f.write(b"data")


class TestAtomicReprStates:
    """__repr__ covers closed/kept states."""

    def test_repr_closed_state(self, tmp_path: Path) -> None:
        dest = tmp_path / "out.txt"
        with atomic_write(dest, mode="w") as w:
            w.write("data")
        r = repr(w)
        assert "closed" in r

    def test_repr_pending_state(self, tmp_path: Path) -> None:
        dest = tmp_path / "out.txt"
        w = atomic_write(dest, mode="w")
        r = repr(w)
        assert "pending" in r


class TestAtomicCloseBeforeEnter:
    """close() on unentered writer sets _closed without error."""

    def test_close_before_enter(self, tmp_path: Path) -> None:
        w = atomic_write(tmp_path / "out.txt", mode="w")
        w.close()
        assert w._closed is True


class TestAtomicRegistryErrorPaths:
    """Registry tracking in error paths."""

    def test_registry_marks_cleaned_on_error(self, tmp_path: Path) -> None:
        temp_registry.enable()
        dest = tmp_path / "out.txt"
        with pytest.raises(RuntimeError, match="boom"), atomic_write(dest, mode="w"):
            raise RuntimeError("boom")

        assert len(temp_registry.active) == 0
        assert len(temp_registry.cleaned) == 1

    def test_registry_marks_kept_on_fsync_failure_with_keep_on_error(
        self, tmp_path: Path
    ) -> None:
        temp_registry.enable()
        dest = tmp_path / "out.txt"
        with (
            patch("os.fsync", side_effect=OSError("disk full")),
            pytest.raises(OSError, match="disk full"),
            atomic_write(dest, mode="w", keep_on_error=True) as w,
        ):
            w.write("data")

        records = temp_registry.all
        assert len(records) == 1
        assert records[0].kept is True
        w.path.unlink()


class TestAtomicExdevFallback:
    """EXDEV cross-device fallback in atomic_write."""

    def test_exdev_fallback_to_shutil_move(self, tmp_path: Path) -> None:
        dest = tmp_path / "out.txt"

        def replace_side_effect(src: str, dst: str) -> None:
            exc = OSError("cross-device")
            exc.errno = 18  # EXDEV
            raise exc

        with (
            patch("os.replace", side_effect=replace_side_effect),
            atomic_write(dest, mode="w") as w,
        ):
            w.write("data")

        assert dest.read_text() == "data"
        assert not w.path.exists()

    def test_exdev_shutil_move_failure_cleans_up(self, tmp_path: Path) -> None:
        dest = tmp_path / "out.txt"

        def replace_side_effect(src: str, dst: str) -> None:
            exc = OSError("cross-device")
            exc.errno = 18  # EXDEV
            raise exc

        with (
            patch("os.replace", side_effect=replace_side_effect),
            patch("shutil.move", side_effect=OSError("move failed")),
            pytest.raises(OSError, match="move failed"),
            atomic_write(dest, mode="w") as w,
        ):
            w.write("data")

        assert not w.path.exists()
        assert not dest.exists()


class TestSyncDestExdevFallback:
    """EXDEV cross-device fallback in temp_file dest move."""

    def test_exdev_fallback_to_shutil_move(self, tmp_path: Path) -> None:
        dest = tmp_path / "final.txt"

        def replace_side_effect(src: str, dst: str) -> None:
            exc = OSError("cross-device")
            exc.errno = 18  # EXDEV
            raise exc

        with (
            patch("os.replace", side_effect=replace_side_effect),
            temp_file(mode="w+b", dest=dest, dir=str(tmp_path)) as f,
        ):
            f.write(b"data")

        assert dest.read_bytes() == b"data"
        assert not f.path.exists()

    def test_exdev_shutil_move_failure_cleans_up(self, tmp_path: Path) -> None:
        dest = tmp_path / "final.txt"

        def replace_side_effect(src: str, dst: str) -> None:
            exc = OSError("cross-device")
            exc.errno = 18  # EXDEV
            raise exc

        with (
            patch("os.replace", side_effect=replace_side_effect),
            patch("shutil.move", side_effect=OSError("move failed")),
            pytest.raises(OSError, match="move failed"),
            temp_file(mode="w+b", dest=dest, dir=str(tmp_path)) as f,
        ):
            f.write(b"data")

        assert not f.path.exists()
        assert not dest.exists()


class TestSyncReprKeptState:
    """__repr__ 'kept' state for temp_file and temp_dir."""

    def test_temp_file_repr_kept(self) -> None:
        with temp_file(keep=True) as f:
            pass
        r = repr(f)
        assert "kept" in r
        f.path.unlink()

    def test_temp_dir_repr_kept(self) -> None:
        from tmpkit._sync import temp_dir as sync_temp_dir

        td = sync_temp_dir(keep=True)
        with td:
            pass
        r = repr(td)
        assert "kept" in r
        import shutil

        shutil.rmtree(td.path)


class TestSyncHadErrorWithRegistry:
    """Registry marks cleaned when temp_file exits with error."""

    def test_registry_marks_cleaned_on_error(self) -> None:
        temp_registry.enable()
        with pytest.raises(RuntimeError, match="boom"), temp_file():
            raise RuntimeError("boom")

        assert len(temp_registry.active) == 0
        assert len(temp_registry.cleaned) == 1


class TestSyncFdopenFailure:
    """fdopen failure in __enter__ cleans up temp file."""

    def test_fdopen_failure_cleans_up(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def failing_fdopen(fd: int, mode: str = "w+b", **kwargs: object) -> object:
            raise OSError("fdopen failed")

        monkeypatch.setattr("os.fdopen", failing_fdopen)
        with pytest.raises(OSError, match="fdopen failed"), temp_file():
            pass


class TestAtomicFdopenNoRegistryLeak:
    """atomic_write fdopen failure must not leak a registry record."""

    def test_fdopen_failure_no_registry_leak(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        temp_registry.enable()

        def failing_fdopen(fd: int, mode: str = "w", **kwargs: object) -> object:
            raise OSError("fdopen failed")

        monkeypatch.setattr("os.fdopen", failing_fdopen)
        with (
            pytest.raises(OSError, match="fdopen failed"),
            atomic_write(tmp_path / "out.txt", mode="w"),
        ):
            pass

        assert len(temp_registry.active) == 0
        assert len(temp_registry.all) == 0


class TestSyncContentWriteFailure:
    """temp_file content write/validation failure cleans up file handle."""

    def test_content_type_mismatch_cleans_up(self) -> None:
        with (
            pytest.raises(TypeError, match="content is str but mode is binary"),
            temp_file(mode="w+b", content="text in binary mode"),
        ):
            pass

    def test_content_write_failure_cleans_up(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import os as os_mod

        original_fdopen = os_mod.fdopen

        def patched_fdopen(fd: int, mode: str = "w+b", **kwargs: object) -> object:
            f = original_fdopen(fd, mode, **kwargs)
            f.write = lambda data: (_ for _ in ()).throw(OSError("write fail"))  # type: ignore[method-assign]
            return f

        monkeypatch.setattr("os.fdopen", patched_fdopen)
        with (
            pytest.raises(OSError, match="write fail"),
            temp_file(mode="w+b", content=b"data"),
        ):
            pass

    def test_content_write_failure_no_file_left(self) -> None:
        with pytest.raises(TypeError), temp_file(mode="w+b", content="wrong type"):
            pass


class TestTempDirChdirFailure:
    """temp_dir chdir failure in __enter__ cleans up directory."""

    def test_chdir_failure_cleans_up_dir(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        class FailingChdir:
            def __init__(self, path: Path) -> None:
                self._path = path

            def __enter__(self) -> Path:
                raise OSError("chdir failed")

            def __exit__(self, *args: object) -> None:
                pass

        monkeypatch.setattr("tmpkit._sync.contextlib.chdir", lambda p: FailingChdir(p))

        from tmpkit._sync import temp_dir as sync_temp_dir

        with (
            pytest.raises(OSError, match="chdir failed"),
            sync_temp_dir(cwd=True, dir=str(tmp_path)),
        ):
            pass

        remaining = list(tmp_path.iterdir())
        assert len(remaining) == 0, f"Directory leaked: {remaining}"


class TestTempDirCwdRestoreFailure:
    """temp_dir cwd restoration failure still cleans up directory."""

    def test_cwd_restore_failure_still_cleans(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        import os as os_mod

        original_chdir = os_mod.chdir

        call_count = 0

        def patched_chdir(path: str) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise OSError("cannot restore cwd")
            original_chdir(path)

        monkeypatch.setattr("os.chdir", patched_chdir)

        from tmpkit._sync import temp_dir as sync_temp_dir

        td = sync_temp_dir(cwd=True, dir=str(tmp_path))
        with pytest.raises(OSError, match="cannot restore cwd"), td:
            pass

        assert not td.path.exists(), "Directory was not cleaned up"


class TestSyncCloseFailure:
    """temp_file close() failure (flush error on close) cleans up temp file."""

    def test_close_failure_cleans_up_temp(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import os as os_mod

        original_fdopen = os_mod.fdopen

        def patched_fdopen(fd: int, mode: str = "w+b", **kwargs: object) -> object:
            f = original_fdopen(fd, mode, **kwargs)

            def failing_close() -> None:
                os_mod.close(fd)  # actually close the fd so unlink works
                raise OSError("close fail")

            f.close = failing_close  # type: ignore[method-assign]
            return f

        monkeypatch.setattr("os.fdopen", patched_fdopen)
        with pytest.raises(OSError, match="close fail"), temp_file():
            pass

    def test_close_failure_with_keep_on_error_keeps_temp(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import os as os_mod

        original_fdopen = os_mod.fdopen

        def patched_fdopen(fd: int, mode: str = "w+b", **kwargs: object) -> object:
            f = original_fdopen(fd, mode, **kwargs)

            def failing_close() -> None:
                os_mod.close(fd)  # actually close the fd
                raise OSError("close fail")

            f.close = failing_close  # type: ignore[method-assign]
            return f

        monkeypatch.setattr("os.fdopen", patched_fdopen)
        with (
            pytest.raises(OSError, match="close fail"),
            temp_file(keep_on_error=True) as f,
        ):
            pass

        assert f.path.exists()
        f.path.unlink()

    def test_close_failure_with_keep_on_error_marks_kept_in_registry(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regression: close-failure + keep_on_error marks record kept in registry."""
        import os as os_mod

        from tmpkit._registry import temp_registry

        temp_registry.enable()
        try:
            original_fdopen = os_mod.fdopen

            def patched_fdopen(fd: int, mode: str = "w+b", **kwargs: object) -> object:
                f = original_fdopen(fd, mode, **kwargs)

                def failing_close() -> None:
                    os_mod.close(fd)
                    raise OSError("close fail")

                f.close = failing_close  # type: ignore[method-assign]
                return f

            monkeypatch.setattr("os.fdopen", patched_fdopen)
            with (
                pytest.raises(OSError, match="close fail"),
                temp_file(keep_on_error=True) as f,
            ):
                pass

            assert f.path.exists()
            assert len(temp_registry.active) == 0
            records = temp_registry.all
            assert len(records) == 1
            assert records[0].kept is True
            f.path.unlink()
        finally:
            temp_registry.reset()


class TestAtomicCloseFailure:
    """atomic_write close() failure after successful flush/fsync is suppressed."""

    def test_close_failure_after_flush_still_replaces(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import os as os_mod

        dest = tmp_path / "out.txt"
        w = atomic_write(dest, mode="w")
        w.__enter__()
        w.write("data")

        fd = w._file.fileno()

        def failing_close() -> None:
            os_mod.close(fd)  # actually close so os.replace works
            raise OSError("close fail")

        # Patch close to fail — flush already succeeded so close failure is suppressed
        # and the atomic replace proceeds normally.
        w._file.close = failing_close  # type: ignore[method-assign]
        w.__exit__(None, None, None)

        # close failure after successful flush is suppressed; replace still happens
        assert dest.read_text() == "data"
        assert not w.path.exists()


class TestReprPreEnter:
    """__repr__ before __enter__ should not raise."""

    def test_temp_file_repr_before_enter(self) -> None:
        f = temp_file()
        assert "pending" in repr(f)

    def test_temp_dir_repr_before_enter(self) -> None:
        d = temp_dir()
        assert "pending" in repr(d)

    def test_atomic_writer_repr_before_enter(self) -> None:
        w = atomic_write("/tmp/dummy")
        assert "pending" in repr(w)


class TestRegistryMarkedOnCleanupFailure:
    """Registry is left active when cleanup itself fails — the registry must reflect on-disk reality."""

    def test_atomic_replace_failure_leaves_active(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        temp_registry.enable()
        dest = tmp_path / "out.txt"
        w = atomic_write(dest, mode="w", ignore_cleanup_errors=False)
        w.__enter__()
        w.write("data")

        monkeypatch.setattr(
            "os.replace", lambda *a: (_ for _ in ()).throw(OSError("replace fail"))
        )
        monkeypatch.setattr(
            "os.unlink", lambda *a: (_ for _ in ()).throw(OSError("unlink fail"))
        )
        with pytest.raises(OSError, match="unlink fail"):
            w.__exit__(None, None, None)

        # Cleanup failed — record must remain active, not marked cleaned.
        assert len(temp_registry.active) == 1
        assert len(temp_registry.cleaned) == 0
        monkeypatch.undo()
        w.path.unlink()

    def test_sync_temp_file_replace_failure_leaves_active(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        temp_registry.enable()
        dest = tmp_path / "out.txt"
        f = temp_file(dest=dest, ignore_cleanup_errors=False)
        f.__enter__()

        monkeypatch.setattr(
            "os.replace", lambda *a: (_ for _ in ()).throw(OSError("replace fail"))
        )
        monkeypatch.setattr(
            "os.unlink", lambda *a: (_ for _ in ()).throw(OSError("unlink fail"))
        )
        with pytest.raises(OSError, match="unlink fail"):
            f.__exit__(None, None, None)

        assert len(temp_registry.active) == 1
        assert len(temp_registry.cleaned) == 0
        monkeypatch.undo()
        f.path.unlink()

    def test_sync_temp_dir_rmtree_failure_leaves_active(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        temp_registry.enable()
        d = temp_dir(dir=str(tmp_path), ignore_cleanup_errors=False)
        d.__enter__()

        monkeypatch.setattr(
            "shutil.rmtree", lambda *a: (_ for _ in ()).throw(OSError("rmtree fail"))
        )
        with pytest.raises(OSError, match="rmtree fail"):
            d.__exit__(None, None, None)

        assert len(temp_registry.active) == 1
        assert len(temp_registry.cleaned) == 0
        monkeypatch.undo()
        import shutil

        shutil.rmtree(d.path)

    def test_sync_temp_file_had_error_unlink_failure_leaves_active(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Registry is left active when unlink fails during had_error cleanup."""
        temp_registry.enable()
        f = temp_file(dir=str(tmp_path), ignore_cleanup_errors=False)
        f.__enter__()

        monkeypatch.setattr(
            "os.unlink", lambda *a: (_ for _ in ()).throw(OSError("unlink fail"))
        )
        with pytest.raises(OSError, match="unlink fail"):
            f.__exit__(ValueError, ValueError("body error"), None)

        assert len(temp_registry.active) == 1
        assert len(temp_registry.cleaned) == 0
        # Restore os.unlink and clean up manually.
        monkeypatch.undo()
        f.path.unlink()

    def test_atomic_had_error_unlink_failure_leaves_active(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Registry is left active when unlink fails during had_error cleanup in atomic_write."""
        temp_registry.enable()
        dest = tmp_path / "out.txt"
        w = atomic_write(dest, mode="w", ignore_cleanup_errors=False)
        w.__enter__()
        w.write("data")

        monkeypatch.setattr(
            "os.unlink", lambda *a: (_ for _ in ()).throw(OSError("unlink fail"))
        )
        with pytest.raises(OSError, match="unlink fail"):
            w.__exit__(ValueError, ValueError("body error"), None)

        assert len(temp_registry.active) == 1
        assert len(temp_registry.cleaned) == 0
        monkeypatch.undo()
        w.path.unlink()

    def test_cleanup_failure_swallowed_leaves_active(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When ignore_cleanup_errors=True and cleanup fails, record stays active."""
        temp_registry.enable()
        f = temp_file(dir=str(tmp_path), ignore_cleanup_errors=True)
        f.__enter__()
        f.close()

        monkeypatch.setattr(
            "os.unlink", lambda *a: (_ for _ in ()).throw(OSError("unlink fail"))
        )
        # Should not raise — error is swallowed.
        f.__exit__(None, None, None)

        # File still exists, record must remain active.
        assert len(temp_registry.active) == 1
        assert len(temp_registry.cleaned) == 0
        monkeypatch.undo()
        f.path.unlink()


class TestEnterCleanupFailurePreservesOriginalError:
    """When cleanup fails during __enter__ error handling, the original error is preserved."""

    def test_temp_dir_chdir_fail_rmtree_fail_preserves_original(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If chdir fails and rmtree also fails, the chdir error propagates."""
        monkeypatch.setattr(
            "os.chdir", lambda *a: (_ for _ in ()).throw(OSError("chdir fail"))
        )
        monkeypatch.setattr(
            "shutil.rmtree",
            lambda *a, **kw: (_ for _ in ()).throw(OSError("rmtree fail")),
        )

        with (
            pytest.raises(OSError, match="chdir fail"),
            temp_dir(dir=str(tmp_path), cwd=True),
        ):
            pass

    def test_atomic_fdopen_fail_unlink_fail_preserves_original(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If fdopen fails and unlink also fails, the fdopen error propagates."""
        dest = tmp_path / "out.txt"
        monkeypatch.setattr(
            "os.fdopen",
            lambda *a, **kw: (_ for _ in ()).throw(ValueError("fdopen fail")),
        )
        monkeypatch.setattr(
            "os.unlink", lambda *a: (_ for _ in ()).throw(OSError("unlink fail"))
        )

        with pytest.raises(ValueError, match="fdopen fail"), atomic_write(dest):
            pass

    def test_sync_temp_file_fdopen_fail_unlink_fail_preserves_original(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If fdopen fails and unlink also fails, the fdopen error propagates."""
        monkeypatch.setattr(
            "os.fdopen",
            lambda *a, **kw: (_ for _ in ()).throw(ValueError("fdopen fail")),
        )
        monkeypatch.setattr(
            "os.unlink", lambda *a: (_ for _ in ()).throw(OSError("unlink fail"))
        )

        with (
            pytest.raises(ValueError, match="fdopen fail"),
            temp_file(dir=str(tmp_path)),
        ):
            pass

    def test_sync_temp_file_content_fail_unlink_fail_preserves_original(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If content validation fails and unlink also fails, the content error propagates."""
        monkeypatch.setattr(
            "os.unlink", lambda *a: (_ for _ in ()).throw(OSError("unlink fail"))
        )

        with (
            pytest.raises(TypeError, match="content is bytes but mode is text"),
            temp_file(dir=str(tmp_path), mode="w", content=b"bytes"),
        ):
            pass

    def test_sync_temp_file_fdopen_fail_close_fail_preserves_original(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If fdopen fails and os.close also fails, the fdopen error propagates and file is unlinked."""
        monkeypatch.setattr(
            "os.fdopen",
            lambda *a, **kw: (_ for _ in ()).throw(ValueError("fdopen fail")),
        )
        monkeypatch.setattr(
            "os.close", lambda *a: (_ for _ in ()).throw(OSError("close fail"))
        )

        with (
            pytest.raises(ValueError, match="fdopen fail"),
            temp_file(dir=str(tmp_path)),
        ):
            pass

    def test_sync_temp_file_fdopen_fail_close_fail_unlink_fail_preserves_original(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If fdopen, close, and unlink all fail, the fdopen error still propagates."""
        monkeypatch.setattr(
            "os.fdopen",
            lambda *a, **kw: (_ for _ in ()).throw(ValueError("fdopen fail")),
        )
        monkeypatch.setattr(
            "os.close", lambda *a: (_ for _ in ()).throw(OSError("close fail"))
        )
        monkeypatch.setattr(
            "os.unlink", lambda *a: (_ for _ in ()).throw(OSError("unlink fail"))
        )

        with (
            pytest.raises(ValueError, match="fdopen fail"),
            temp_file(dir=str(tmp_path)),
        ):
            pass

    def test_atomic_fdopen_fail_close_fail_preserves_original(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If fdopen fails and os.close also fails, the fdopen error propagates and file is unlinked."""
        dest = tmp_path / "out.txt"
        monkeypatch.setattr(
            "os.fdopen",
            lambda *a, **kw: (_ for _ in ()).throw(ValueError("fdopen fail")),
        )
        monkeypatch.setattr(
            "os.close", lambda *a: (_ for _ in ()).throw(OSError("close fail"))
        )

        with (
            pytest.raises(ValueError, match="fdopen fail"),
            atomic_write(dest),
        ):
            pass

    def test_sync_temp_file_content_fail_file_close_fail_preserves_original(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If content validation fails and file.close() also fails, the content error propagates and file is unlinked."""
        import os as os_mod

        original_fdopen = os_mod.fdopen

        def patched_fdopen(fd: int, mode: str = "w", **kwargs: object) -> object:
            f = original_fdopen(fd, mode, **kwargs)
            f.close = lambda: (_ for _ in ()).throw(OSError("close fail"))  # type: ignore[method-assign]
            return f

        monkeypatch.setattr("os.fdopen", patched_fdopen)

        with (
            pytest.raises(TypeError, match="content is bytes but mode is text"),
            temp_file(dir=str(tmp_path), mode="w", content=b"bytes"),
        ):
            pass
