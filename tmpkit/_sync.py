"""Sync context managers for temporary files and directories."""

from __future__ import annotations

import contextlib
import errno
import os
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tmpkit._config import _should_keep
from tmpkit._registry import TempRecord, temp_registry
from tmpkit._types import StrPath, _validate_prefix_suffix

CleanupHook = Callable[[Path], None]


class _TempFile:
    """Sync temp file context manager. Returned by temp_file()."""

    __slots__ = (
        "_cleanup_hook",
        "_closed",
        "_content",
        "_deleted",
        "_dest",
        "_dir",
        "_exited",
        "_file",
        "_ignore_cleanup_errors",
        "_keep",
        "_keep_on_error",
        "_kept",
        "_mode",
        "_moved",
        "_path",
        "_prefix",
        "_record",
        "_suffix",
        "_user_keep",
    )

    def __init__(
        self,
        *,
        suffix: str | None = None,
        prefix: str | None = None,
        dir: StrPath | None = None,
        mode: str = "w+b",
        content: str | bytes | None = None,
        dest: StrPath | None = None,
        keep: bool = False,
        keep_on_error: bool = False,
        ignore_cleanup_errors: bool = True,
        cleanup_hook: CleanupHook | None = None,
    ) -> None:
        self._suffix = _validate_prefix_suffix(suffix, "suffix")
        self._prefix = _validate_prefix_suffix(prefix, "prefix")
        self._dir = str(dir) if dir is not None else None
        self._mode = mode
        self._content = content
        self._dest = Path(dest) if dest is not None else None
        self._keep = keep
        self._keep_on_error = keep_on_error
        self._ignore_cleanup_errors = ignore_cleanup_errors
        self._cleanup_hook = cleanup_hook
        self._path: Path | None = None
        self._file: Any = None
        self._closed = False
        self._exited = False
        self._user_keep = False
        self._deleted = False
        self._kept = False
        self._moved = False
        self._record: TempRecord | None = None

    def __enter__(self) -> _TempFile:
        # Reset state for re-entry (context managers can be reused).
        self._closed = False
        self._exited = False
        self._deleted = False
        self._kept = False
        self._moved = False
        self._user_keep = False
        self._record = None
        fd, path_str = tempfile.mkstemp(
            suffix=self._suffix,
            prefix=self._prefix,
            dir=self._dir,
        )
        self._path = Path(path_str)
        try:
            self._file = os.fdopen(fd, mode=self._mode)
        except Exception:
            with contextlib.suppress(OSError):
                os.close(fd)
            with contextlib.suppress(OSError):
                os.unlink(path_str)
            raise
        try:
            if self._content is not None:
                self._validate_content()
                self._file.write(self._content)
                self._file.seek(0)
        except Exception:
            with contextlib.suppress(OSError):
                self._file.close()
            self._closed = True
            with contextlib.suppress(OSError):
                os.unlink(path_str)
            raise
        self._record = temp_registry.register(self._path, "file")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        self._exited = True
        had_error = exc_type is not None
        should_keep = (
            _should_keep(
                keep=self._keep,
                keep_on_error=self._keep_on_error,
                had_error=had_error,
            )
            or self._user_keep
        )

        if not self._closed and self._file is not None:
            try:
                self._file.close()
            except OSError:
                self._closed = True
                effective_keep = should_keep or self._keep_on_error
                self._finalize_keep_or_clean(effective_keep)
                raise
            self._closed = True

        # Call cleanup hook before standard cleanup (even on exception).
        # If the hook fails, capture the error and proceed with cleanup
        # so the temp file never leaks. Re-raise after cleanup if needed.
        hook_error: BaseException | None = None
        if self._cleanup_hook is not None and not should_keep:
            assert self._path is not None
            try:
                self._cleanup_hook(self._path)
            except Exception as e:
                if not self._ignore_cleanup_errors:
                    hook_error = e

        if should_keep:
            self._kept = True
            if self._record is not None:
                temp_registry.mark_kept(self._record)
        elif had_error:
            self._finalize_clean()
        elif self._dest is not None:
            assert self._path is not None
            if self._path == self._dest:
                pass  # no-op: dest same as temp
            else:
                try:
                    os.replace(self._path, self._dest)
                except OSError as exc:
                    if exc.errno == errno.EXDEV:
                        try:
                            shutil.move(self._path, self._dest)
                        except OSError:
                            self._finalize_clean()
                            raise
                    else:
                        self._finalize_clean()
                        raise
                self._moved = True
            if self._record is not None:
                temp_registry.mark_cleaned(self._record)
        else:
            self._finalize_clean()

        if hook_error is not None and exc_type is None:
            raise hook_error

    def _finalize_clean(self) -> None:
        """Unlink the temp file and mark the registry record as cleaned.

        If the unlink fails, the record is left active so ``cleanup_all()``
        can retry later — the registry must reflect on-disk reality.
        """
        assert self._path is not None
        try:
            os.unlink(self._path)
        except OSError:
            if not self._ignore_cleanup_errors:
                raise
            return
        self._deleted = True
        if self._record is not None:
            temp_registry.mark_cleaned(self._record)

    def _finalize_keep_or_clean(self, effective_keep: bool) -> None:
        """Mark kept or attempt cleanup depending on ``effective_keep``."""
        if effective_keep:
            if self._record is not None:
                temp_registry.mark_kept(self._record)
        else:
            self._finalize_clean()

    def read(self, size: int = -1) -> bytes | str:
        if self._closed:
            raise ValueError("I/O operation on closed file.")
        assert self._file is not None
        return self._file.read(size)  # type: ignore[no-any-return]

    def write(self, data: bytes | str) -> int:
        if self._closed:
            raise ValueError("I/O operation on closed file.")
        assert self._file is not None
        return self._file.write(data)  # type: ignore[no-any-return]

    def seek(self, offset: int, whence: int = 0) -> int:
        if self._closed:
            raise ValueError("I/O operation on closed file.")
        assert self._file is not None
        return self._file.seek(offset, whence)  # type: ignore[no-any-return]

    def tell(self) -> int:
        if self._closed:
            raise ValueError("I/O operation on closed file.")
        assert self._file is not None
        return self._file.tell()  # type: ignore[no-any-return]

    def flush(self) -> None:
        if self._closed or self._file is None:
            return
        self._file.flush()

    def close(self) -> None:
        if self._closed:
            return
        if self._file is not None:
            self._file.close()
        self._closed = True

    @property
    def path(self) -> Path:
        assert self._path is not None
        return self._path

    def _validate_content(self) -> None:
        """Validate content type matches mode."""
        assert self._content is not None
        is_text_mode = "b" not in self._mode
        if is_text_mode and isinstance(self._content, bytes):
            raise TypeError("content is bytes but mode is text (no 'b' in mode).")
        if not is_text_mode and isinstance(self._content, str):
            raise TypeError("content is str but mode is binary (contains 'b').")

    def keep(self) -> None:
        if self._file is None:
            raise RuntimeError("Cannot call .keep() before __enter__.")
        if self._exited:
            raise RuntimeError("Cannot call .keep() after __exit__.")
        self._user_keep = True

    def __fspath__(self) -> str:
        assert self._path is not None
        return str(self._path)

    def __repr__(self) -> str:
        if self._path is None:
            return "TempFile(path=None, state=pending)"
        if self._moved:
            state = "moved"
        elif self._deleted:
            state = "deleted"
        elif self._kept:
            state = "kept"
        elif self._closed:
            state = "closed"
        else:
            state = "open"
        return f"TempFile(path={self._path!r}, {state=})"


def temp_file(
    *,
    suffix: str | None = None,
    prefix: str | None = None,
    dir: StrPath | None = None,
    mode: str = "w+b",
    content: str | bytes | None = None,
    dest: StrPath | None = None,
    keep: bool = False,
    keep_on_error: bool = False,
    ignore_cleanup_errors: bool = True,
    cleanup_hook: CleanupHook | None = None,
) -> _TempFile:
    """Create a temporary file context manager.

    The file is created on ``__enter__`` and deleted on ``__exit__``
    (unless keep conditions are met).

    If ``dest`` is set and the context exits without error, the temp file
    is atomically moved to ``dest`` via ``os.replace`` (or ``shutil.move``
    for cross-filesystem moves). On error, the temp is deleted and ``dest``
    is left untouched.

    Precedence: ``.keep()`` > ``keep=True`` > ``DEBUG=1`` > ``dest=`` move.

    Args:
        suffix: File name suffix (e.g. ``".csv"``).
        prefix: File name prefix (e.g. ``"myapp_"``).
        dir: Parent directory. Defaults to system temp dir.
        mode: Open mode passed to ``os.fdopen``. Defaults to ``"w+b"``.
        content: Pre-populate file with this content. ``str`` for text modes, ``bytes`` for binary.
        dest: Destination path. On success, temp is moved here.
        keep: If ``True``, file is NOT deleted on context exit.
        keep_on_error: If ``True``, file is kept only when an exception propagates.
        ignore_cleanup_errors: If ``True``, ``OSError`` during cleanup is silently ignored.
        cleanup_hook: Optional callable invoked with the temp path before standard cleanup.
            Called only when the temp is being deleted (not when kept). Hook errors are
            ignored if ``ignore_cleanup_errors=True``; otherwise they propagate after
            cleanup, with body exceptions taking precedence.

    Returns:
        A ``_TempFile`` context manager.
    """
    return _TempFile(
        suffix=suffix,
        prefix=prefix,
        dir=dir,
        mode=mode,
        content=content,
        dest=dest,
        keep=keep,
        keep_on_error=keep_on_error,
        ignore_cleanup_errors=ignore_cleanup_errors,
        cleanup_hook=cleanup_hook,
    )


class _TempDir:
    """Sync temp dir context manager. Returned by temp_dir()."""

    __slots__ = (
        "_cleanup_hook",
        "_cwd",
        "_cwd_ctx",
        "_deleted",
        "_dir",
        "_exited",
        "_ignore_cleanup_errors",
        "_keep",
        "_keep_on_error",
        "_kept",
        "_path",
        "_prefix",
        "_record",
        "_suffix",
        "_user_keep",
    )

    def __init__(
        self,
        *,
        suffix: str | None = None,
        prefix: str | None = None,
        dir: StrPath | None = None,
        cwd: bool = False,
        keep: bool = False,
        keep_on_error: bool = False,
        ignore_cleanup_errors: bool = True,
        cleanup_hook: CleanupHook | None = None,
    ) -> None:
        self._suffix = _validate_prefix_suffix(suffix, "suffix")
        self._prefix = _validate_prefix_suffix(prefix, "prefix")
        self._dir = str(dir) if dir is not None else None
        self._cwd = cwd
        self._cwd_ctx: Any = None
        self._keep = keep
        self._keep_on_error = keep_on_error
        self._ignore_cleanup_errors = ignore_cleanup_errors
        self._cleanup_hook = cleanup_hook
        self._path: Path | None = None
        self._user_keep = False
        self._exited = False
        self._deleted = False
        self._kept = False
        self._record: TempRecord | None = None

    def __enter__(self) -> Path:
        # Reset state for re-entry (context managers can be reused).
        self._exited = False
        self._deleted = False
        self._kept = False
        self._user_keep = False
        self._record = None
        self._cwd_ctx = None
        path_str = tempfile.mkdtemp(
            suffix=self._suffix,
            prefix=self._prefix,
            dir=self._dir,
        )
        self._path = Path(path_str)
        if self._cwd:
            try:
                self._cwd_ctx = contextlib.chdir(self._path)
                self._cwd_ctx.__enter__()
            except Exception:
                with contextlib.suppress(OSError):
                    shutil.rmtree(self._path)
                self._path = None
                raise
        self._record = temp_registry.register(self._path, "dir")
        return self._path

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        self._exited = True
        cwd_error: OSError | None = None
        if self._cwd_ctx is not None:
            try:
                self._cwd_ctx.__exit__(exc_type, exc_val, exc_tb)
            except OSError as e:
                cwd_error = e
                # Best-effort: chdir to system temp so rmtree can succeed
                # (can't delete cwd on Windows).
                with contextlib.suppress(OSError):
                    os.chdir(tempfile.gettempdir())

        had_error = exc_type is not None
        should_keep = (
            _should_keep(
                keep=self._keep,
                keep_on_error=self._keep_on_error,
                had_error=had_error,
            )
            or self._user_keep
        )

        # Call cleanup hook before standard cleanup (even on exception).
        # If the hook fails, capture the error and proceed with cleanup
        # so the temp dir never leaks. Re-raise after cleanup if needed.
        hook_error: BaseException | None = None
        if self._cleanup_hook is not None and not should_keep:
            assert self._path is not None
            try:
                self._cleanup_hook(self._path)
            except Exception as e:
                if not self._ignore_cleanup_errors:
                    hook_error = e

        if should_keep:
            self._kept = True
            if self._record is not None:
                temp_registry.mark_kept(self._record)
        else:
            self._finalize_clean()

        if cwd_error is not None and exc_type is None:
            raise cwd_error
        if hook_error is not None and exc_type is None:
            raise hook_error

    def _finalize_clean(self) -> None:
        """Remove the temp dir and mark the registry record as cleaned.

        If rmtree fails, the record is left active so ``cleanup_all()``
        can retry later — the registry must reflect on-disk reality.
        """
        assert self._path is not None
        try:
            shutil.rmtree(self._path)
        except OSError:
            if not self._ignore_cleanup_errors:
                raise
            return
        self._deleted = True
        if self._record is not None:
            temp_registry.mark_cleaned(self._record)

    @property
    def path(self) -> Path:
        assert self._path is not None
        return self._path

    def keep(self) -> None:
        if self._path is None:
            raise RuntimeError("Cannot call .keep() before __enter__.")
        if self._exited:
            raise RuntimeError("Cannot call .keep() after __exit__.")
        self._user_keep = True

    def __fspath__(self) -> str:
        assert self._path is not None
        return str(self._path)

    def __truediv__(self, other: str | Path) -> Path:
        assert self._path is not None
        return self._path / other

    def __repr__(self) -> str:
        if self._path is None:
            return "TempDir(path=None, state=pending)"
        if self._deleted:
            state = "deleted"
        elif self._kept:
            state = "kept"
        else:
            state = "active"
        return f"TempDir(path={self._path!r}, {state=})"


def temp_dir(
    *,
    suffix: str | None = None,
    prefix: str | None = None,
    dir: StrPath | None = None,
    cwd: bool = False,
    keep: bool = False,
    keep_on_error: bool = False,
    ignore_cleanup_errors: bool = True,
    cleanup_hook: CleanupHook | None = None,
) -> _TempDir:
    """Create a temporary directory context manager.

    The directory is created on ``__enter__`` and removed on ``__exit__``
    (unless keep conditions are met).

    Args:
        suffix: Directory name suffix.
        prefix: Directory name prefix.
        dir: Parent directory. Defaults to system temp dir.
        cwd: If ``True``, changes working directory to temp dir on ``__enter__``, restores on ``__exit__``.
        keep: If ``True``, directory is NOT removed on context exit.
        keep_on_error: If ``True``, directory is kept only when an exception propagates.
        ignore_cleanup_errors: If ``True``, ``OSError`` during cleanup is silently ignored.
        cleanup_hook: Optional callable invoked with the temp path before standard cleanup.
            Called only when the temp is being deleted (not when kept). Hook errors are
            ignored if ``ignore_cleanup_errors=True``; otherwise they propagate after
            cleanup, with body exceptions taking precedence.

    Returns:
        A ``_TempDir`` context manager.
    """
    return _TempDir(
        suffix=suffix,
        prefix=prefix,
        dir=dir,
        cwd=cwd,
        keep=keep,
        keep_on_error=keep_on_error,
        ignore_cleanup_errors=ignore_cleanup_errors,
        cleanup_hook=cleanup_hook,
    )
