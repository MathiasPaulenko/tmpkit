"""Tests for TempRegistry and cleanup_hook parameter."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from tmpkit._registry import TempRecord, TempRegistry, temp_registry
from tmpkit._sync import temp_dir, temp_file


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    """Reset registry state before and after each test."""
    temp_registry.reset()
    yield
    temp_registry.reset()


class TestTempRecord:
    """TempRecord dataclass."""

    def test_temp_record_defaults(self) -> None:
        record = TempRecord(
            path=Path("/tmp/foo"),
            kind="file",
            created_at=1000.0,
        )
        assert record.path == Path("/tmp/foo")
        assert record.kind == "file"
        assert record.created_at == 1000.0
        assert record.cleaned is False
        assert record.kept is False

    def test_temp_record_cleaned(self) -> None:
        record = TempRecord(
            path=Path("/tmp/foo"),
            kind="file",
            created_at=1000.0,
            cleaned=True,
        )
        assert record.cleaned is True

    def test_temp_record_kept(self) -> None:
        record = TempRecord(
            path=Path("/tmp/bar"),
            kind="dir",
            created_at=2000.0,
            kept=True,
        )
        assert record.kept is True


class TestTempRegistryBasic:
    """Basic registry operations."""

    def test_disabled_by_default(self) -> None:
        reg = TempRegistry()
        assert reg.enabled is False

    def test_enable_disable(self) -> None:
        reg = TempRegistry()
        reg.enable()
        assert reg.enabled is True
        reg.disable()
        assert reg.enabled is False

    def test_register_returns_none_when_disabled(self) -> None:
        reg = TempRegistry()
        record = reg.register(Path("/tmp/foo"), "file")
        assert record is None

    def test_register_returns_record_when_enabled(self) -> None:
        reg = TempRegistry()
        reg.enable()
        record = reg.register(Path("/tmp/foo"), "file")
        assert record is not None
        assert record.path == Path("/tmp/foo")
        assert record.kind == "file"
        assert record.cleaned is False
        assert record.kept is False

    def test_all_property(self) -> None:
        reg = TempRegistry()
        reg.enable()
        reg.register(Path("/tmp/a"), "file")
        reg.register(Path("/tmp/b"), "dir")
        assert len(reg.all) == 2

    def test_active_property(self) -> None:
        reg = TempRegistry()
        reg.enable()
        r1 = reg.register(Path("/tmp/a"), "file")
        reg.register(Path("/tmp/b"), "dir")
        assert len(reg.active) == 2
        reg.mark_cleaned(r1)
        assert len(reg.active) == 1
        assert reg.active[0].path == Path("/tmp/b")

    def test_cleaned_property(self) -> None:
        reg = TempRegistry()
        reg.enable()
        r1 = reg.register(Path("/tmp/a"), "file")
        reg.register(Path("/tmp/b"), "dir")
        reg.mark_cleaned(r1)
        assert len(reg.cleaned) == 1
        assert reg.cleaned[0].path == Path("/tmp/a")
        assert len(reg.all) == 2

    def test_mark_kept(self) -> None:
        reg = TempRegistry()
        reg.enable()
        r1 = reg.register(Path("/tmp/a"), "file")
        reg.mark_kept(r1)
        assert r1.kept is True
        assert len(reg.active) == 0


class TestTempRegistryCleanupAll:
    """cleanup_all() deletes active temps."""

    def test_cleanup_all_deletes_files(self) -> None:
        reg = TempRegistry()
        reg.enable()
        with temp_file() as f:
            reg.register(f.path, "file")
        # File already cleaned by context manager, but let's test with a real file
        reg.reset()
        reg.enable()
        with temp_file(keep=True) as f:
            reg.register(f.path, "file")
        # Now the file exists and is active in registry
        assert len(reg.active) == 1
        count = reg.cleanup_all()
        assert count == 1
        assert len(reg.active) == 0
        assert len(reg.cleaned) == 1

    def test_cleanup_all_deletes_dirs(self) -> None:
        reg = TempRegistry()
        reg.enable()
        with temp_dir(keep=True) as d:
            reg.register(d, "dir")
        assert len(reg.active) == 1
        count = reg.cleanup_all()
        assert count == 1
        assert len(reg.active) == 0

    def test_cleanup_all_mixed(self) -> None:
        reg = TempRegistry()
        reg.enable()
        with temp_file(keep=True) as f, temp_dir(keep=True) as d:
            reg.register(f.path, "file")
            reg.register(d, "dir")
        assert len(reg.active) == 2
        count = reg.cleanup_all()
        assert count == 2
        assert len(reg.active) == 0

    def test_cleanup_all_empty(self) -> None:
        reg = TempRegistry()
        reg.enable()
        assert reg.cleanup_all() == 0

    def test_cleanup_all_count_excludes_already_gone(self) -> None:
        """cleanup_all() count only reflects temps actually deleted, not already-gone ones."""
        reg = TempRegistry()
        reg.enable()
        with temp_file(keep=True) as f:
            reg.register(f.path, "file")
        # File exists and is active.
        assert len(reg.active) == 1
        # Delete the file manually so it's already gone on disk.
        f.path.unlink()
        # cleanup_all should mark it cleaned but NOT count it as deleted.
        count = reg.cleanup_all()
        assert count == 0
        assert len(reg.active) == 0
        assert len(reg.cleaned) == 1


class TestTempRegistryKeepAll:
    """keep_all() marks all active temps as kept."""

    def test_keep_all_marks_active(self) -> None:
        reg = TempRegistry()
        reg.enable()
        with temp_file(keep=True) as f, temp_dir(keep=True) as d:
            reg.register(f.path, "file")
            reg.register(d, "dir")
        assert len(reg.active) == 2
        count = reg.keep_all()
        assert count == 2
        assert len(reg.active) == 0
        # Clean up manually
        f.path.unlink()
        import shutil

        shutil.rmtree(d)

    def test_keep_all_empty(self) -> None:
        reg = TempRegistry()
        reg.enable()
        assert reg.keep_all() == 0


class TestTempRegistryClearHistory:
    """clear_history() removes cleaned records."""

    def test_clear_history_removes_cleaned(self) -> None:
        reg = TempRegistry()
        reg.enable()
        r1 = reg.register(Path("/tmp/a"), "file")
        reg.register(Path("/tmp/b"), "dir")
        reg.mark_cleaned(r1)
        assert len(reg.all) == 2
        reg.clear_history()
        assert len(reg.all) == 1
        assert reg.all[0].path == Path("/tmp/b")

    def test_clear_history_empty(self) -> None:
        reg = TempRegistry()
        reg.enable()
        reg.clear_history()
        assert len(reg.all) == 0


class TestTempRegistryEnvVar:
    """TMPKIT_REGISTRY=1 env var enables registry."""

    def test_env_var_enables(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TMPKIT_REGISTRY", "1")
        reg = TempRegistry()
        assert reg.enabled is True

    def test_env_var_disabled_by_default(self) -> None:
        reg = TempRegistry()
        assert reg.enabled is False

    def test_env_var_not_one(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TMPKIT_REGISTRY", "0")
        reg = TempRegistry()
        assert reg.enabled is False


class TestTempRegistryThreadSafety:
    """Thread-safe with threading.Lock."""

    def test_concurrent_registration(self) -> None:
        reg = TempRegistry()
        reg.enable()
        results: list[TempRecord | None] = []

        def register_one(idx: int) -> None:
            record = reg.register(Path(f"/tmp/concurrent_{idx}"), "file")
            if record is not None:
                results.append(record)

        threads = [threading.Thread(target=register_one, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 50
        assert len(reg.all) == 50

    def test_concurrent_cleanup_all(self) -> None:
        reg = TempRegistry()
        reg.enable()
        # Register some real temp files
        paths: list[Path] = []
        for _ in range(10):
            with temp_file(keep=True) as f:
                reg.register(f.path, "file")
                paths.append(f.path)

        assert len(reg.active) == 10

        def cleanup() -> None:
            reg.cleanup_all()

        threads = [threading.Thread(target=cleanup) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All should be cleaned
        assert len(reg.active) == 0

    def test_cleanup_all_skips_records_marked_kept_concurrently(self) -> None:
        """Regression: if a record is marked kept after the active snapshot
        but before cleanup, cleanup_all must NOT delete it or mark it cleaned."""
        reg = TempRegistry()
        reg.enable()
        with temp_file(keep=True) as f:
            record = reg.register(f.path, "file")
        assert record is not None
        assert len(reg.active) == 1

        # Simulate a concurrent keep: mark the record as kept AFTER the
        # snapshot would have been taken. We do this by calling cleanup_all
        # but first marking the record kept.
        reg.mark_kept(record)
        count = reg.cleanup_all()
        assert count == 0
        # Record should still be kept, not cleaned.
        assert record.kept is True
        assert record.cleaned is False
        assert len(reg.active) == 0
        f.path.unlink()

    def test_cleanup_all_recheck_skips_concurrently_kept_record(self) -> None:
        """Regression: the re-check inside the loop must skip records marked
        kept between the snapshot and the actual cleanup."""
        reg = TempRegistry()
        reg.enable()
        # Create two real temp files and register them.
        with temp_file(keep=True) as f1, temp_file(keep=True) as f2:
            r1 = reg.register(f1.path, "file")
            r2 = reg.register(f2.path, "file")
        assert r1 is not None and r2 is not None
        assert len(reg.active) == 2

        import os as os_mod

        original_unlink = os_mod.unlink
        call_count = 0

        def patched_unlink(path) -> None:
            nonlocal call_count
            call_count += 1
            # After deleting the first record, mark the second as kept
            # to simulate a concurrent keep operation.
            if call_count == 1:
                reg.mark_kept(r2)
            original_unlink(path)

        import unittest.mock

        with unittest.mock.patch("os.unlink", side_effect=patched_unlink):
            count = reg.cleanup_all()

        # Only the first record was actually deleted.
        assert count == 1
        # r2 was marked kept by the "concurrent" operation.
        assert r2.kept is True
        assert r2.cleaned is False
        # r1 was cleaned.
        assert r1.cleaned is True
        # Clean up f2 manually.
        f2.path.unlink()


class TestCleanupHookTempFile:
    """cleanup_hook parameter on temp_file()."""

    def test_hook_called_before_cleanup(self) -> None:
        hook_calls: list[Path] = []

        def hook(path: Path) -> None:
            hook_calls.append(path)

        with temp_file(cleanup_hook=hook) as f:
            f.write(b"data")
            f.seek(0)
            assert f.path.exists()

        assert len(hook_calls) == 1
        assert hook_calls[0] == f.path
        assert not f.path.exists()

    def test_hook_called_on_exception(self) -> None:
        hook_calls: list[Path] = []

        def hook(path: Path) -> None:
            hook_calls.append(path)

        with (
            pytest.raises(RuntimeError, match="boom"),
            temp_file(cleanup_hook=hook) as f,
        ):
            f.write(b"data")
            raise RuntimeError("boom")

        assert len(hook_calls) == 1

    def test_hook_error_ignored(self) -> None:
        def bad_hook(path: Path) -> None:
            raise OSError("hook failed")

        # Should not raise
        with temp_file(cleanup_hook=bad_hook) as f:
            f.write(b"data")

    def test_hook_error_propagated_when_not_ignoring(self) -> None:
        """Regression: temp_file cleanup_hook error with ignore_cleanup_errors=False
        propagates AFTER cleanup — the temp file must NOT leak."""

        def bad_hook(path: Path) -> None:
            raise OSError("hook failed")

        f = temp_file(cleanup_hook=bad_hook, ignore_cleanup_errors=False)
        with pytest.raises(OSError, match="hook failed"), f:
            f.write(b"data")
        # Cleanup must still run even when the hook fails — file should be gone.
        assert not f.path.exists()

    def test_hook_error_suppressed_when_body_exception(self) -> None:
        """Regression: when both body and hook raise, body exception takes precedence."""

        def bad_hook(path: Path) -> None:
            raise OSError("hook failed")

        f = temp_file(cleanup_hook=bad_hook, ignore_cleanup_errors=False)
        with pytest.raises(ValueError, match="body boom"), f:
            f.write(b"data")
            raise ValueError("body boom")
        # Cleanup must still run.
        assert not f.path.exists()

    def test_hook_not_called_when_keep(self) -> None:
        hook_calls: list[Path] = []

        def hook(path: Path) -> None:
            hook_calls.append(path)

        with temp_file(keep=True, cleanup_hook=hook) as f:
            f.write(b"data")

        assert len(hook_calls) == 0
        f.path.unlink()

    def test_hook_not_called_when_user_keep(self) -> None:
        hook_calls: list[Path] = []

        def hook(path: Path) -> None:
            hook_calls.append(path)

        with temp_file(cleanup_hook=hook) as f:
            f.write(b"data")
            f.keep()

        assert len(hook_calls) == 0
        f.path.unlink()


class TestCleanupHookTempDir:
    """cleanup_hook parameter on temp_dir()."""

    def test_hook_called_before_cleanup(self) -> None:
        hook_calls: list[Path] = []

        def hook(path: Path) -> None:
            hook_calls.append(path)

        with temp_dir(cleanup_hook=hook) as d:
            assert d.exists()

        assert len(hook_calls) == 1
        assert hook_calls[0] == d
        assert not d.exists()

    def test_hook_called_on_exception(self) -> None:
        hook_calls: list[Path] = []

        def hook(path: Path) -> None:
            hook_calls.append(path)

        with pytest.raises(RuntimeError, match="dir boom"), temp_dir(cleanup_hook=hook):
            raise RuntimeError("dir boom")

        assert len(hook_calls) == 1

    def test_hook_error_ignored(self) -> None:
        def bad_hook(path: Path) -> None:
            raise OSError("dir hook failed")

        with temp_dir(cleanup_hook=bad_hook) as d:
            assert d.exists()

    def test_hook_not_called_when_keep(self) -> None:
        hook_calls: list[Path] = []

        def hook(path: Path) -> None:
            hook_calls.append(path)

        with temp_dir(keep=True, cleanup_hook=hook) as d:
            assert d.exists()

        assert len(hook_calls) == 0
        import shutil

        shutil.rmtree(d)

    def test_hook_error_propagated_when_not_ignoring(self) -> None:
        """Regression: temp_dir cleanup_hook error with ignore_cleanup_errors=False
        propagates AFTER cleanup — the temp dir must NOT leak."""

        def bad_hook(path: Path) -> None:
            raise OSError("dir hook failed")

        td = temp_dir(cleanup_hook=bad_hook, ignore_cleanup_errors=False)
        with pytest.raises(OSError, match="dir hook failed"), td as d:
            assert d.exists()
        # Cleanup must still run even when the hook fails — dir should be gone.
        assert not td.path.exists()

    def test_hook_error_suppressed_when_body_exception(self) -> None:
        """Regression: when both body and hook raise, body exception takes precedence."""

        def bad_hook(path: Path) -> None:
            raise OSError("dir hook failed")

        td = temp_dir(cleanup_hook=bad_hook, ignore_cleanup_errors=False)
        with pytest.raises(ValueError, match="body boom"), td as d:
            assert d.exists()
            raise ValueError("body boom")
        # Cleanup must still run.
        assert not td.path.exists()


class TestRegistryIntegration:
    """Registry integration with temp_file/temp_dir."""

    def test_registry_tracks_temp_file(self) -> None:
        temp_registry.enable()
        with temp_file() as f:
            assert len(temp_registry.active) == 1
            assert temp_registry.active[0].path == f.path
            assert temp_registry.active[0].kind == "file"
        assert len(temp_registry.active) == 0
        assert len(temp_registry.cleaned) == 1

    def test_registry_tracks_temp_dir(self) -> None:
        temp_registry.enable()
        with temp_dir() as d:
            assert len(temp_registry.active) == 1
            assert temp_registry.active[0].path == d
            assert temp_registry.active[0].kind == "dir"
        assert len(temp_registry.active) == 0
        assert len(temp_registry.cleaned) == 1

    def test_registry_tracks_kept(self) -> None:
        temp_registry.enable()
        with temp_file(keep=True) as f:
            pass
        assert len(temp_registry.active) == 0
        assert len(temp_registry.cleaned) == 0
        records = temp_registry.all
        assert len(records) == 1
        assert records[0].kept is True
        f.path.unlink()

    def test_registry_disabled_no_tracking(self) -> None:
        # Registry disabled by default
        with temp_file():
            assert len(temp_registry.all) == 0
        assert len(temp_registry.all) == 0

    def test_registry_cleanup_all_with_real_temps(self) -> None:
        temp_registry.enable()
        # Create temps that are kept (so they survive context exit)
        # Kept temps are marked as kept in registry, not active.
        # We need to manually register them as active for cleanup_all to work.
        with temp_file(keep=True), temp_dir(keep=True):
            pass
        # Kept temps are not "active" (active = not cleaned and not kept)
        # They are in registry.all with kept=True
        assert len(temp_registry.all) == 2
        assert all(r.kept for r in temp_registry.all)
        # cleanup_all only cleans active (not kept), so we need to
        # manually un-keep them to test cleanup_all
        for r in temp_registry.all:
            r.kept = False
        assert len(temp_registry.active) == 2
        count = temp_registry.cleanup_all()
        assert count == 2
        assert len(temp_registry.active) == 0
