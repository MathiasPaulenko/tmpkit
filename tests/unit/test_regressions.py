"""Regression tests for bugs found during the stabilization audit.

Covers: context-manager re-entry leaks, ``:`` in names on Windows (ADS),
atomic-write durability when the user closes the handle early, destination
resolved against the enter-time cwd, ``_dest`` reassigned after ``__enter__``,
registry cleanup of dirs/symlinks, and generator/class decorator lifecycles.
"""

from __future__ import annotations

import os
import shutil
import unittest.mock
from pathlib import Path

import pytest
from tmpkit._atomic import atomic_write
from tmpkit._decorators import temp_dir as temp_dir_decorator
from tmpkit._decorators import temp_file as temp_file_decorator
from tmpkit._registry import TempRegistry
from tmpkit._sync import temp_dir, temp_file


class TestReentry:
    """Re-entering an *active* context raised no error and leaked the
    previous temp — it must now raise RuntimeError."""

    def test_temp_file_reenter_active_raises(self, tmp_path: Path) -> None:
        f = temp_file(mode="w+b", dir=str(tmp_path))
        f.__enter__()
        first = f.path
        with pytest.raises(RuntimeError, match="re-enter"):
            f.__enter__()
        # The first temp is still tracked and cleaned on exit.
        assert first.exists()
        f.__exit__(None, None, None)
        assert not first.exists()

    def test_temp_file_reuse_after_exit(self, tmp_path: Path) -> None:
        f = temp_file(mode="w+b", dir=str(tmp_path))
        with f as a:
            p1 = a.path
        assert not p1.exists()
        with f as b:
            p2 = b.path
            assert p2.exists()
            assert p1 != p2
        assert not p2.exists()

    def test_temp_dir_reenter_active_raises(self, tmp_path: Path) -> None:
        d = temp_dir(dir=str(tmp_path), cwd=True)
        p1 = d.__enter__()
        with pytest.raises(RuntimeError, match="re-enter"):
            d.__enter__()
        assert p1.exists()
        d.__exit__(None, None, None)
        assert not p1.exists()

    def test_atomic_reenter_active_raises(self, tmp_path: Path) -> None:
        w = atomic_write(tmp_path / "out.txt", mode="w")
        w.__enter__()
        tmp = w.path
        with pytest.raises(RuntimeError, match="re-enter"):
            w.__enter__()
        assert tmp.exists()
        w.write("data")
        w.__exit__(None, None, None)
        assert (tmp_path / "out.txt").read_text() == "data"
        assert not tmp.exists()


class TestWindowsColonValidation:
    """``:`` in prefix/suffix creates an NTFS alternate data stream whose
    base file escapes cleanup — rejected on Windows."""

    def test_colon_in_prefix_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(os, "name", "nt")
        with pytest.raises(ValueError, match="invalid on Windows"):
            temp_file(prefix="x:y")

    def test_colon_in_suffix_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(os, "name", "nt")
        with pytest.raises(ValueError, match="invalid on Windows"):
            temp_dir(suffix=":z")

    @pytest.mark.parametrize("char", '<>"|?*')
    def test_other_invalid_chars_rejected(
        self, char: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(os, "name", "nt")
        with pytest.raises(ValueError, match="invalid on Windows"):
            temp_file(prefix=f"a{char}b")

    def test_nul_byte_rejected(self) -> None:
        with pytest.raises(ValueError, match="NUL"):
            temp_file(prefix="a\0b")
        with pytest.raises(ValueError, match="NUL"):
            temp_dir(suffix="\0x")

    @pytest.mark.skipif(os.name == "nt", reason="Windows rejects ':'")
    def test_colon_allowed_on_posix(self, tmp_path: Path) -> None:
        with temp_file(prefix="x:y", dir=str(tmp_path)) as f:
            assert ":" in f.path.name


class TestAtomicCloseDurability:
    """User-close inside the block used to skip flush/fsync entirely."""

    def test_user_close_still_fsyncs_and_replaces(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fsync_calls: list[int] = []
        real_fsync = os.fsync

        def spy(fd: int) -> None:
            fsync_calls.append(fd)
            real_fsync(fd)

        monkeypatch.setattr(os, "fsync", spy)
        dest = tmp_path / "out.bin"
        with atomic_write(dest, mode="wb") as w:
            w.write(b"payload")
            w.close()
        assert dest.read_bytes() == b"payload"
        assert fsync_calls


class TestDestIsDirectory:
    """A directory at ``dest`` must raise IsADirectoryError and clean the
    temp — never move the temp *inside* the directory via EXDEV fallback."""

    def test_temp_file_dest_dir_raises_and_cleans(self, tmp_path: Path) -> None:
        target = tmp_path / "target"
        target.mkdir()
        f_ref = None
        with (
            pytest.raises(IsADirectoryError),
            temp_file(mode="w+b", dest=target, dir=str(tmp_path)) as f,
        ):
            f_ref = f
            f.write(b"x")
        assert f_ref is not None
        assert not f_ref.path.exists()
        assert target.is_dir()

    def test_atomic_dest_becomes_dir_after_enter(self, tmp_path: Path) -> None:
        # TOCTOU: dest was not a dir at __enter__ but became one.
        dest = tmp_path / "x"
        w = atomic_write(dest, mode="w")
        w.__enter__()
        tmp = w.path
        dest.mkdir()
        with pytest.raises(IsADirectoryError):
            w.__exit__(None, None, None)
        assert not tmp.exists()
        assert dest.is_dir()


class TestRelativeDest:
    """A relative ``dest`` must resolve against the cwd at ``__enter__``,
    not the cwd at ``__exit__``."""

    def test_temp_file_relative_dest_resolved_at_enter(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        a = tmp_path / "a"
        b = tmp_path / "b"
        a.mkdir()
        b.mkdir()
        monkeypatch.chdir(a)
        with temp_file(mode="w+b", dest="out.bin") as f:
            f.write(b"data")
            os.chdir(b)
        assert (a / "out.bin").read_bytes() == b"data"
        assert not (b / "out.bin").exists()

    def test_atomic_relative_dest_resolved_at_enter(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        a = tmp_path / "a"
        b = tmp_path / "b"
        a.mkdir()
        b.mkdir()
        monkeypatch.chdir(a)
        with atomic_write("out.txt", mode="w") as w:
            w.write("hi")
            os.chdir(b)
        assert (a / "out.txt").read_text() == "hi"
        assert not (b / "out.txt").exists()

    def test_atomic_dest_reassigned_after_enter(self, tmp_path: Path) -> None:
        w = atomic_write(tmp_path / "orig.txt", mode="w")
        w.__enter__()
        w.write("x")
        w._dest = tmp_path / "new.txt"  # type: ignore[attr-defined]
        w.__exit__(None, None, None)
        assert (tmp_path / "new.txt").read_text() == "x"
        assert not (tmp_path / "orig.txt").exists()


class TestAtomicErrorPaths:
    """Hook failures, externally-closed files, and fsync_dir edge cases."""

    def test_cleanup_hook_error_ignored(self, tmp_path: Path) -> None:
        dest = tmp_path / "o.txt"

        def bad(_p: Path) -> None:
            raise RuntimeError("hook")

        with atomic_write(
            dest, mode="w", cleanup_hook=bad, ignore_cleanup_errors=True
        ) as w:
            w.write("x")
        assert dest.read_text() == "x"

    def test_cleanup_hook_error_propagates(self, tmp_path: Path) -> None:
        dest = tmp_path / "o.txt"

        def bad(_p: Path) -> None:
            raise RuntimeError("hook")

        with (
            pytest.raises(RuntimeError, match="hook"),
            atomic_write(
                dest, mode="w", cleanup_hook=bad, ignore_cleanup_errors=False
            ) as w,
        ):
            w.write("x")
        # The replace still happened — hook errors are deferred, not fatal.
        assert dest.read_text() == "x"

    def test_file_closed_externally_still_replaces(self, tmp_path: Path) -> None:
        # Raw-closing the file object must not break __exit__: flush() and
        # fileno() raise ValueError on a closed file — suppressed internally.
        dest = tmp_path / "o.txt"
        w = atomic_write(dest, mode="w")
        w.__enter__()
        w.write("data")
        w._file.close()  # type: ignore[union-attr]
        w.__exit__(None, None, None)
        assert dest.read_text() == "data"

    def test_close_raises_flush_error(self, tmp_path: Path) -> None:
        dest = tmp_path / "o.txt"
        w = atomic_write(dest, mode="w")
        w.__enter__()
        w.write("x")

        def boom() -> None:
            raise OSError("flush fail")

        w._file.flush = boom  # type: ignore[union-attr, method-assign]
        with pytest.raises(OSError, match="flush fail"):
            w.close()
        w.__exit__(None, None, None)
        assert not w.path.exists()

    def test_fsync_dir_before_enter_noop(self, tmp_path: Path) -> None:
        w = atomic_write(tmp_path / "o.txt", mode="w")
        w._fsync_dir()  # no dest resolved yet — must be a no-op

    def test_hook_keyboard_interrupt_cleans_and_propagates(
        self, tmp_path: Path
    ) -> None:
        # BaseException in a hook must not leak the temp, and must
        # propagate even with ignore_cleanup_errors=True.
        dest = tmp_path / "o.txt"

        def ki(_p: Path) -> None:
            raise KeyboardInterrupt

        with (
            pytest.raises(KeyboardInterrupt),
            atomic_write(
                dest, mode="w", cleanup_hook=ki, ignore_cleanup_errors=True
            ) as w,
        ):
            w.write("x")
        assert dest.read_text() == "x"  # replace still ran

    def test_hook_keyboard_interrupt_deletes_temp(self, tmp_path: Path) -> None:
        captured: list[Path] = []

        def ki(_p: Path) -> None:
            raise KeyboardInterrupt

        with (
            pytest.raises(KeyboardInterrupt),
            temp_file(dir=str(tmp_path), cleanup_hook=ki) as f,
        ):
            captured.append(f.path)
        assert not captured[0].exists()

    def test_hook_baseexc_dropped_when_body_errors(self, tmp_path: Path) -> None:
        captured: list[Path] = []

        def ki(_p: Path) -> None:
            raise KeyboardInterrupt

        with (
            pytest.raises(RuntimeError, match="body"),
            temp_file(dir=str(tmp_path), cleanup_hook=ki) as f,
        ):
            captured.append(f.path)
            raise RuntimeError("body")
        assert not captured[0].exists()

    def test_fsync_dir_failures_suppressed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        w = atomic_write(tmp_path / "o.txt", mode="w")
        w.__enter__()
        w.write("x")
        monkeypatch.setattr(
            os, "open", unittest.mock.Mock(side_effect=OSError("no open"))
        )
        w._fsync_dir()  # os.open failure → suppressed
        monkeypatch.undo()
        monkeypatch.setattr(
            os, "fsync", unittest.mock.Mock(side_effect=OSError("no fsync"))
        )
        w._fsync_dir()  # os.fsync failure → suppressed
        monkeypatch.undo()
        w.__exit__(None, None, None)
        assert (tmp_path / "o.txt").read_text() == "x"

    def test_fsync_dir_inner_block(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # On Windows os.open() on a directory always fails, so the fsync
        # block inside _fsync_dir is only reachable with a mocked open.
        dest = tmp_path / "o.txt"
        w = atomic_write(dest, mode="w")
        w.__enter__()
        w.write("x")
        dummy = tmp_path / "dummy.txt"
        dummy.write_text("d")
        real_open = os.open
        monkeypatch.setattr(
            os,
            "open",
            lambda *a, **k: real_open(str(dummy), os.O_RDONLY),
        )
        w._fsync_dir()  # success: open + fsync + close
        monkeypatch.setattr(
            os, "fsync", unittest.mock.Mock(side_effect=OSError("fsync fail"))
        )
        w._fsync_dir()  # fsync error swallowed, fd still closed
        monkeypatch.undo()
        w.__exit__(None, None, None)
        assert dest.read_text() == "x"


class TestRegistryCleanup:
    """cleanup_all must handle dir records, files replacing dirs, and
    symlinks (which are unlinked, never rmtree'd)."""

    def test_cleanup_all_removes_dir_record(self, tmp_path: Path) -> None:
        reg = TempRegistry()
        reg.enable()
        d = tmp_path / "d"
        d.mkdir()
        (d / "f.txt").write_text("x")
        rec = reg.register(d, "dir")
        assert reg.cleanup_all() == 1
        assert not d.exists()
        assert rec is not None and rec.cleaned

    def test_cleanup_all_dir_record_replaced_by_file(self, tmp_path: Path) -> None:
        reg = TempRegistry()
        reg.enable()
        p = tmp_path / "p"
        p.write_text("x")
        reg.register(p, "dir")  # kind says dir but the path is a file
        assert reg.cleanup_all() == 1
        assert not p.exists()

    def test_cleanup_all_symlink_record_unlinked(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A dir-kind record pointing at a symlink must be unlinked, never
        # passed to rmtree (which would fail or follow the link).
        reg = TempRegistry()
        reg.enable()
        target = tmp_path / "real.txt"
        target.write_text("x")
        reg.register(target, "dir")
        monkeypatch.setattr(Path, "is_symlink", lambda self: True)
        monkeypatch.setattr(
            shutil,
            "rmtree",
            unittest.mock.Mock(side_effect=AssertionError("rmtree called")),
        )
        assert reg.cleanup_all() == 1
        assert not target.exists()

    def test_keep_all_marks_every_active_record(self, tmp_path: Path) -> None:
        reg = TempRegistry()
        reg.enable()
        reg.register(tmp_path / "a", "file")
        reg.register(tmp_path / "b", "file")
        assert reg.keep_all() == 2
        assert reg.active == []

    def test_keep_all_skips_cleaned_records(self, tmp_path: Path) -> None:
        reg = TempRegistry()
        reg.enable()
        r1 = reg.register(tmp_path / "a", "file")
        r2 = reg.register(tmp_path / "b", "file")
        assert r1 is not None
        r1.cleaned = True
        assert reg.keep_all() == 1
        assert r2 is not None and r2.kept
        assert not r1.kept


class TestGeneratorDecorators:
    """Decorated generators must keep the temp alive for the whole
    iteration — before the fix the temp died when the call returned."""

    def test_temp_dir_sync_generator(self) -> None:
        @temp_dir_decorator(cwd=False)
        def gen(p: Path):
            yield p
            yield p

        it = gen()
        p = next(it)
        assert p.exists()
        assert next(it) == p
        with pytest.raises(StopIteration):
            next(it)
        assert not p.exists()

    def test_temp_dir_generator_close_cleans(self) -> None:
        @temp_dir_decorator(cwd=False)
        def gen(p: Path):
            yield p
            yield p

        it = gen()
        p = next(it)
        assert p.exists()
        it.close()
        assert not p.exists()

    async def test_temp_dir_async_generator(self) -> None:
        @temp_dir_decorator(cwd=False)
        async def gen(p: Path):
            yield p

        paths = []
        async for x in gen():
            assert x.exists()
            paths.append(x)
        assert not paths[0].exists()

    def test_temp_file_sync_generator(self) -> None:
        @temp_file_decorator(mode="w+b")
        def gen(f):
            f.write(b"hi")
            yield f.path

        captured = None
        for p in gen():
            assert p.exists()
            captured = p
        assert captured is not None
        assert not captured.exists()

    async def test_temp_file_async_generator(self) -> None:
        @temp_file_decorator(mode="w+b")
        async def gen(f):
            await f.write(b"hi")
            yield f.path

        paths = []
        async for p in gen():
            assert p.exists()
            paths.append(p)
        assert not paths[0].exists()


class TestClassDecoration:
    """Inherited test methods must be wrapped too, and re-decoration or
    decorating a subclass of a decorated class must never double-wrap."""

    def test_inherited_test_methods_wrapped(self) -> None:
        class Base:
            def test_inherited(self) -> None:
                assert self.tmpdir.exists()

        cls = temp_dir_decorator(cwd=False)(
            type("Derived", (Base,), {"__module__": __name__})
        )
        cls().test_inherited()  # type: ignore[attr-defined]

    def test_redecoration_no_double_wrap(self) -> None:
        calls: list[Path] = []

        class C:
            def test_x(self) -> None:
                calls.append(self.tmpdir)

        cls = temp_dir_decorator(cwd=False)(C)
        cls = temp_dir_decorator(cwd=False)(cls)
        cls().test_x()  # type: ignore[attr-defined]
        assert len(calls) == 1

    def test_subclass_of_decorated_no_double_wrap(self) -> None:
        calls: list[Path] = []

        class C:
            def test_x(self) -> None:
                calls.append(self.tmpdir)

        base = temp_dir_decorator(cwd=False)(C)
        sub = temp_dir_decorator(cwd=False)(
            type("Sub", (base,), {"__module__": __name__})
        )
        sub().test_x()  # type: ignore[attr-defined]
        assert len(calls) == 1


class TestExitBeforeEnter:
    """__exit__ on a never-entered context is a no-op, not a crash."""

    def test_temp_file_exit_before_enter(self) -> None:
        temp_file().__exit__(None, None, None)

    def test_temp_dir_exit_before_enter(self) -> None:
        temp_dir().__exit__(None, None, None)

    def test_atomic_exit_before_enter(self, tmp_path: Path) -> None:
        atomic_write(tmp_path / "x").__exit__(None, None, None)


class TestAtomicDestClearedPostEnter:
    """Clearing ``_dest`` after __enter__ drops the temp instead of
    writing to a stale resolved destination."""

    def test_dest_set_to_none_drops_temp(self, tmp_path: Path) -> None:
        dest = tmp_path / "out.txt"
        w = atomic_write(dest, mode="w")
        w.__enter__()
        tmp = w.path
        w._dest = None
        w.__exit__(None, None, None)
        assert not tmp.exists()
        assert not dest.exists()


class TestDoubleWrapGuards:
    """Re-decorating an already-wrapped function is always a bug — the
    temp argument would be injected twice."""

    def test_temp_dir_double_decoration_raises(self) -> None:
        @temp_dir_decorator()
        def f(tmp: Path) -> Path:
            return tmp

        with pytest.raises(TypeError, match="already wrapped"):
            temp_dir_decorator()(f)

    def test_temp_file_double_decoration_raises(self) -> None:
        @temp_file_decorator()
        def f(fh) -> object:
            return fh

        with pytest.raises(TypeError, match="already wrapped"):
            temp_file_decorator()(f)

    def test_cross_decorator_double_wrap_raises(self) -> None:
        @temp_file_decorator()
        def f(fh) -> object:
            return fh

        with pytest.raises(TypeError, match="already wrapped"):
            temp_dir_decorator()(f)


class TestGeneratorClassMethods:
    """Generator/asyncgen test_* methods in a decorated class get the
    same hold-during-iteration lifecycle as module-level generators."""

    def test_generator_method_holds_temp_through_iteration(self) -> None:
        @temp_dir_decorator(cwd=False)
        class T:
            def test_gen(self):
                yield self.tmpdir

        gen = T().test_gen()
        tmpdir = next(gen)
        assert tmpdir.is_dir()
        gen.close()
        assert not tmpdir.exists()

    async def test_asyncgen_method_holds_temp_through_iteration(self) -> None:
        @temp_dir_decorator(cwd=False)
        class T:
            async def test_gen(self):
                yield self.tmpdir

        agen = T().test_gen()
        tmpdir = await agen.__anext__()
        assert tmpdir.is_dir()
        await agen.aclose()
        assert not tmpdir.exists()


class TestAsyncgenDeterministicClose:
    """Closing the outer wrapper must deterministically aclose() the
    inner generator — plain async-for does not delegate it."""

    async def test_inner_aclose_runs_on_outer_close(self) -> None:
        finalized = False

        @temp_dir_decorator()
        async def gen(tmp: Path):
            nonlocal finalized
            try:
                yield 1
            finally:
                finalized = True

        outer = gen()
        assert await outer.__anext__() == 1
        await outer.aclose()
        assert finalized


class TestRegistryCleanupEdgeCases:
    """cleanup_all claim/fallback branches."""

    def test_failed_delete_releases_claim_for_retry(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        reg = TempRegistry()
        reg.enable()
        f = tmp_path / "f"
        f.write_text("x")
        record = reg.register(f, "file")
        assert record is not None

        monkeypatch.setattr(os, "unlink", unittest.mock.Mock(side_effect=OSError))
        assert reg.cleanup_all() == 0
        # Claim released — record is active again, not stuck "cleaned".
        assert record.cleaned is False
        assert reg.active == [record]

        monkeypatch.undo()
        assert reg.cleanup_all() == 1
        assert record.cleaned is True
        assert not f.exists()

    def test_rmtree_notadir_falls_back_to_unlink(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        reg = TempRegistry()
        reg.enable()
        d = tmp_path / "d"
        d.mkdir()
        record = reg.register(d, "dir")
        assert record is not None

        real_rmtree = shutil.rmtree

        def fake_rmtree(path: Path) -> None:
            # Dir replaced by a file between the is_dir() check and the
            # removal — NotADirectoryError must fall back to unlink.
            real_rmtree(path)
            Path(path).write_text("x")
            raise NotADirectoryError(str(path))

        monkeypatch.setattr(shutil, "rmtree", fake_rmtree)
        assert reg.cleanup_all() == 1
        assert record.cleaned is True
        assert not d.exists()

    def test_missing_path_counts_as_cleaned_not_deleted(self, tmp_path: Path) -> None:
        reg = TempRegistry()
        reg.enable()
        f = tmp_path / "gone"
        f.write_text("x")
        record = reg.register(f, "file")
        assert record is not None
        f.unlink()
        assert reg.cleanup_all() == 0
        assert record.cleaned is True


class TestDeferredErrorChaining:
    """_merge_deferred: a deferred hook error chains as __cause__ on the
    primary; a non-Exception deferred error always wins."""

    def test_hook_error_chained_on_close_error(self, tmp_path: Path) -> None:
        hook_err = ValueError("hook boom")

        def hook(p: Path) -> None:
            raise hook_err

        f = temp_file(cleanup_hook=hook, ignore_cleanup_errors=False)
        f.__enter__()
        # Force a close error that is not an OSError subclass issue —
        # patch close to raise so close_error captures it.
        real_close = f._file.close
        f._file.close = unittest.mock.Mock(  # type: ignore[method-assign]
            side_effect=OSError("close boom")
        )
        with pytest.raises(OSError, match="close boom") as ei:
            f.__exit__(None, None, None)
        f._file.close = real_close  # type: ignore[method-assign]
        assert ei.value.__cause__ is hook_err

    def test_non_exception_deferred_wins_over_primary(self, tmp_path: Path) -> None:
        def hook(p: Path) -> None:
            raise KeyboardInterrupt

        f = temp_file(cleanup_hook=hook, ignore_cleanup_errors=True)
        f.__enter__()
        real_close = f._file.close
        f._file.close = unittest.mock.Mock(  # type: ignore[method-assign]
            side_effect=OSError("close boom")
        )
        with pytest.raises(KeyboardInterrupt):
            f.__exit__(None, None, None)
        f._file.close = real_close  # type: ignore[method-assign]


class TestGeneratorMethodExhaustion:
    """Full exhaustion of decorated gen/asyncgen methods."""

    def test_gen_method_return_value_propagates(self) -> None:
        @temp_dir_decorator(cwd=False)
        class T:
            def test_gen(self):
                yield self.tmpdir
                return "done"

        gen = T().test_gen()
        tmpdir = next(gen)
        assert tmpdir.is_dir()
        with pytest.raises(StopIteration) as ei:
            next(gen)
        assert ei.value.value == "done"
        assert not tmpdir.exists()

    async def test_asyncgen_method_exhaustion_cleans(self) -> None:
        @temp_dir_decorator(cwd=False)
        class T:
            async def test_gen(self):
                yield self.tmpdir
                yield 2

        agen = T().test_gen()
        tmpdir = await agen.__anext__()
        assert tmpdir.is_dir()
        assert await agen.__anext__() == 2
        with pytest.raises(StopAsyncIteration):
            await agen.__anext__()
        assert not tmpdir.exists()


def test_atomic_dest_property_after_cleared(tmp_path: Path) -> None:
    """.dest raises once the private _dest was cleared post-enter."""
    w = atomic_write(tmp_path / "x", mode="w")
    w.__enter__()
    w._dest = None
    with pytest.raises(RuntimeError, match="dest"):
        _ = w.dest
    w.__exit__(None, None, None)


class TestInterruptDuringClose:
    """A non-Exception error from close/flush must propagate AFTER
    cleanup — never leak the temp, never be swallowed by a body error."""

    def test_close_keyboard_interrupt_still_cleans(self) -> None:
        f = temp_file()
        f.__enter__()
        tmp = f.path
        real_close = f._file.close

        def close_then_raise() -> None:
            real_close()
            raise KeyboardInterrupt

        f._file.close = close_then_raise  # type: ignore[method-assign]
        with pytest.raises(KeyboardInterrupt):
            f.__exit__(None, None, None)
        assert not tmp.exists()

    def test_close_interrupt_wins_over_body_error(self) -> None:
        f = temp_file()
        f.__enter__()
        tmp = f.path
        real_close = f._file.close

        def close_then_raise() -> None:
            real_close()
            raise KeyboardInterrupt

        f._file.close = close_then_raise  # type: ignore[method-assign]
        with pytest.raises(KeyboardInterrupt):
            f.__exit__(ValueError, ValueError("body"), None)
        assert not tmp.exists()

    def test_atomic_flush_interrupt_still_cleans(self, tmp_path: Path) -> None:
        w = atomic_write(tmp_path / "out.txt", mode="w", fsync=False)
        w.__enter__()
        tmp = w.path
        real_close = w._file.close

        def close_then_raise() -> None:
            real_close()
            raise KeyboardInterrupt

        w._file.close = close_then_raise  # type: ignore[method-assign]
        with pytest.raises(KeyboardInterrupt):
            w.__exit__(None, None, None)
        assert not tmp.exists()

    def test_atomic_flush_interrupt_wins_over_body_error(
        self, tmp_path: Path
    ) -> None:
        w = atomic_write(tmp_path / "out.txt", mode="w", fsync=False)
        w.__enter__()
        tmp = w.path
        real_close = w._file.close

        def close_then_raise() -> None:
            real_close()
            raise KeyboardInterrupt

        w._file.close = close_then_raise  # type: ignore[method-assign]
        with pytest.raises(KeyboardInterrupt):
            w.__exit__(ValueError, ValueError("body"), None)
        assert not tmp.exists()


def test_atomic_close_interrupt_outranks_flush_error(tmp_path: Path) -> None:
    """An interrupt from close() wins over an earlier flush OSError."""
    w = atomic_write(tmp_path / "out.txt", mode="w", fsync=False)
    w.__enter__()
    tmp = w.path
    real_close = w._file.close
    w._file.flush = unittest.mock.Mock(  # type: ignore[method-assign]
        side_effect=OSError("flush boom")
    )

    def close_then_raise() -> None:
        try:
            real_close()  # still triggers the mocked flush — ignore it
        except OSError:
            pass
        raise KeyboardInterrupt

    w._file.close = close_then_raise  # type: ignore[method-assign]
    with pytest.raises(KeyboardInterrupt):
        w.__exit__(None, None, None)
    assert not tmp.exists()


def test_atomic_flush_interrupt_kept_over_close_interrupt(
    tmp_path: Path,
) -> None:
    """Interrupt from flush stays primary when close also interrupts."""
    w = atomic_write(tmp_path / "out.txt", mode="w", fsync=False)
    w.__enter__()
    tmp = w.path
    real_close = w._file.close
    w._file.flush = unittest.mock.Mock(  # type: ignore[method-assign]
        side_effect=KeyboardInterrupt
    )

    def close_then_raise() -> None:
        real_close()
        raise KeyboardInterrupt

    w._file.close = close_then_raise  # type: ignore[method-assign]
    with pytest.raises(KeyboardInterrupt):
        w.__exit__(None, None, None)
    assert not tmp.exists()
