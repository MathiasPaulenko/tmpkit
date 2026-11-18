"""Atomic file writing via temp file + os.replace()."""

from __future__ import annotations

import contextlib
import errno
import os
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Any

from tmpkit._config import _should_keep
from tmpkit._registry import TempRecord, temp_registry
from tmpkit._types import (
    CleanupHook,
    StrPath,
    _merge_deferred,
    _validate_prefix_suffix,
)


class _AtomicWriter:
    """Atomic file writer. Writes to a temp file, then atomically replaces dest on success."""

    __slots__ = (
        "_cleanup_hook",
        "_closed",
        "_dest",
        "_dest_entered",
        "_dest_resolved",
        "_encoding",
        "_exited",
        "_file",
        "_fsync",
        "_ignore_cleanup_errors",
        "_keep",
        "_keep_on_error",
        "_kept",
        "_mode",
        "_newlines",
        "_path",
        "_prefix",
        "_record",
        "_suffix",
        "_user_keep",
    )

    def __init__(
        self,
        dest: StrPath,
        *,
        mode: str = "w",
        encoding: str | None = None,
        newline: str | None = None,
        prefix: str | None = None,
        suffix: str = ".tmp",
        fsync: bool = True,
        keep: bool = False,
        keep_on_error: bool = False,
        ignore_cleanup_errors: bool = True,
        cleanup_hook: CleanupHook | None = None,
    ) -> None:
        self._dest: Path | None = Path(dest)
        self._mode = mode
        self._encoding = encoding
        self._newlines = newline
        self._prefix = _validate_prefix_suffix(prefix, "prefix")
        validated_suffix = _validate_prefix_suffix(suffix, "suffix")
        self._suffix = validated_suffix if validated_suffix is not None else ".tmp"
        self._fsync = fsync
        self._keep = keep
        self._keep_on_error = keep_on_error
        self._ignore_cleanup_errors = ignore_cleanup_errors
        self._cleanup_hook = cleanup_hook
        self._path: Path | None = None
        self._file: Any = None
        self._closed = False
        self._exited = False
        self._user_keep = False
        self._kept = False
        self._record: TempRecord | None = None
        self._dest_resolved: Path | None = None
        self._dest_entered: Path | None = None

    def __enter__(self) -> _AtomicWriter:
        if self._path is not None and not self._exited:
            raise RuntimeError(
                "Cannot re-enter an active atomic_write context manager."
            )
        # Reset state for re-entry (context managers can be reused).
        self._closed = False
        self._exited = False
        self._user_keep = False
        self._kept = False
        self._record = None
        self._path = None
        self._file = None
        # Resolve dest once, against the enter-time cwd: os.replace() at exit
        # would otherwise resolve a relative dest against whatever cwd the
        # process has then, which may differ (e.g. cwd=True temp dirs).
        assert self._dest is not None
        dest_resolved = Path(os.path.abspath(self._dest))
        self._dest_resolved = dest_resolved
        self._dest_entered = self._dest
        if dest_resolved.is_dir():
            raise IsADirectoryError(f"Destination is a directory: {self._dest}")
        dest_parent = dest_resolved.parent
        try:
            stat_result = os.stat(dest_parent)
        except FileNotFoundError:
            raise FileNotFoundError(
                f"Destination parent does not exist: {dest_parent}"
            ) from None
        if not stat.S_ISDIR(stat_result.st_mode):
            raise NotADirectoryError(
                f"Destination parent is not a directory: {dest_parent}"
            )

        fd, path_str = tempfile.mkstemp(
            suffix=self._suffix,
            prefix=self._prefix,
            dir=str(dest_parent),
        )
        self._path = Path(os.path.abspath(path_str))

        open_kwargs: dict[str, Any] = {}
        if "b" not in self._mode:
            if self._encoding is not None:
                open_kwargs["encoding"] = self._encoding
            if self._newlines is not None:
                open_kwargs["newline"] = self._newlines

        try:
            self._file = os.fdopen(fd, mode=self._mode, **open_kwargs)
        except Exception:
            with contextlib.suppress(OSError):
                os.close(fd)
            with contextlib.suppress(OSError):
                os.unlink(path_str)
            self._path = None
            raise
        self._record = temp_registry.register(self._path, "file")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        if self._path is None:
            return  # never entered (or enter failed) — nothing to finalize
        had_error = exc_type is not None
        should_keep = (
            _should_keep(
                keep=self._keep,
                keep_on_error=self._keep_on_error,
                had_error=had_error,
            )
            or self._user_keep
        )

        # Close file: flush + fsync + close. Errors are captured so a body
        # exception is never masked by a cleanup failure.
        flush_error = self._close_file()

        # Call cleanup hook before the temp is removed (deleted or moved).
        # If the hook fails, capture the error and proceed so the temp
        # never leaks. Re-raise after cleanup if needed.
        # The hook is skipped whenever the temp will be kept — including a
        # flush error triggering keep_on_error.
        hook_error: BaseException | None = None
        will_keep = should_keep or (flush_error is not None and self._keep_on_error)
        if self._cleanup_hook is not None and not will_keep:
            try:
                self._cleanup_hook(self._path)
            except BaseException as e:
                # Defer so the temp still gets cleaned. BaseExceptions
                # (KeyboardInterrupt etc.) are always re-raised later —
                # ignore_cleanup_errors only silences normal exceptions.
                if not self._ignore_cleanup_errors or not isinstance(e, Exception):
                    hook_error = e

        # _exited is set only now so a hook can still call .keep() —
        # after this point keep() correctly raises "after __exit__".
        self._exited = True
        should_keep = should_keep or self._user_keep

        if flush_error is not None and (
            not had_error or not isinstance(flush_error, Exception)
        ):
            effective_keep = should_keep or self._keep_on_error
            with contextlib.suppress(OSError):
                self._finalize_keep_or_clean(effective_keep)
            raise _merge_deferred(flush_error, hook_error)

        if should_keep:
            self._kept = True
            if self._record is not None:
                temp_registry.mark_kept(self._record)
        elif had_error:
            with contextlib.suppress(OSError):
                self._finalize_clean()
        else:
            # Success: atomic replace
            if self._dest is None:
                # _dest was cleared after __enter__ — just drop the temp.
                self._finalize_clean()
            else:
                dest = self._dest_resolved
                if self._dest != self._dest_entered:
                    # _dest was (re)assigned after __enter__ — resolve it now.
                    dest = Path(os.path.abspath(self._dest))
                assert dest is not None
                self._dest_resolved = dest
                if dest.is_dir():
                    # TOCTOU: dest may have become a directory since __enter__.
                    # Also prevents the EXDEV fallback from moving the temp
                    # *inside* the directory.
                    with contextlib.suppress(OSError):
                        self._finalize_clean()
                    raise _merge_deferred(
                        IsADirectoryError(f"Destination is a directory: {self._dest}"),
                        hook_error,
                    )
                replace_error: OSError | None = None
                try:
                    os.replace(self._path, dest)
                except OSError as exc:
                    if exc.errno == errno.EXDEV:
                        try:
                            shutil.move(self._path, dest)
                        except OSError as move_exc:
                            self._finalize_clean()
                            raise _merge_deferred(move_exc, hook_error) from exc
                    else:
                        replace_error = exc
                # Raised outside the except clause: _merge_deferred
                # already chains the deferred hook error as __cause__ —
                # `from exc` would clobber it.
                if replace_error is not None:
                    self._finalize_clean()
                    raise _merge_deferred(replace_error, hook_error)
                self._fsync_dir()
            if self._record is not None:
                temp_registry.mark_cleaned(self._record)

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
        if self._record is not None:
            temp_registry.mark_cleaned(self._record)

    def _finalize_keep_or_clean(self, effective_keep: bool) -> None:
        """Mark kept or attempt cleanup depending on ``effective_keep``."""
        if effective_keep:
            self._kept = True
            if self._record is not None:
                temp_registry.mark_kept(self._record)
        else:
            self._finalize_clean()

    def _fsync_dir(self) -> None:
        """Best-effort fsync of the destination directory.

        ``os.replace`` is atomic but the rename itself is only durable
        once the parent directory's metadata hits disk. This is a
        no-op where directory fsync is unsupported (e.g. Windows).
        """
        if self._dest_resolved is None:
            return
        try:
            dir_fd = os.open(
                str(self._dest_resolved.parent),
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
            )
        except OSError:
            return
        try:
            os.fsync(dir_fd)
        except OSError:
            pass
        finally:
            os.close(dir_fd)

    def write(self, data: bytes | str) -> int:
        if self._closed:
            raise ValueError("I/O operation on closed file.")
        if self._file is None:
            raise RuntimeError("Cannot perform I/O before __enter__.")
        return self._file.write(data)  # type: ignore[no-any-return]

    def flush(self) -> None:
        if self._closed or self._file is None:
            return
        self._file.flush()

    def _close_file(self) -> BaseException | None:
        """Flush, fsync (if enabled) and close the temp file once.

        Returns the first error raised while flushing/fsyncing — the
        caller decides whether to propagate it. A ``ValueError`` from flush
        means the file was already closed underneath, which is not an error.
        ``_closed`` is always set, so ``__exit__`` never retries the close.
        """
        if self._closed or self._file is None:
            return None
        error: BaseException | None = None
        try:
            self._file.flush()
            if self._fsync:
                os.fsync(self._file.fileno())
        except ValueError:
            pass
        except BaseException as e:
            error = e
        try:
            # close() re-flushes internally — errors here cannot lose data
            # once flush+fsync already ran, so they are suppressed and the
            # earlier flush error (if any) is what gets reported. Only
            # interrupts (KeyboardInterrupt etc.) still propagate.
            self._file.close()
        except Exception:
            pass
        except BaseException as e:
            # An interrupt outranks any earlier Exception-class flush
            # error — never swallow a KeyboardInterrupt.
            if error is None or isinstance(error, Exception):
                error = e
        finally:
            self._closed = True
        return error

    def close(self) -> None:
        error = self._close_file()
        self._closed = True
        if error is not None:
            raise error

    @property
    def path(self) -> Path:
        if self._path is None:
            raise RuntimeError("Cannot access .path before __enter__.")
        return self._path

    @property
    def dest(self) -> Path:
        if self._dest is None:
            raise RuntimeError("Cannot access .dest — it was cleared.")
        return self._dest

    def keep(self) -> None:
        if self._file is None:
            raise RuntimeError("Cannot call .keep() before __enter__.")
        if self._exited:
            raise RuntimeError("Cannot call .keep() after __exit__.")
        self._user_keep = True

    def __fspath__(self) -> str:
        if self._path is None:
            raise RuntimeError("Cannot use temp file as path before __enter__.")
        return str(self._path)

    def __repr__(self) -> str:
        path_str = repr(self._path) if self._path else "None"
        if self._kept:
            state = "kept"
        elif self._closed:
            state = "closed"
        elif self._file is not None:
            state = "open"
        else:
            state = "pending"
        return f"AtomicWriter(path={path_str}, dest={self._dest!r}, {state=})"


def atomic_write(
    dest: StrPath,
    *,
    mode: str = "w",
    encoding: str | None = None,
    newline: str | None = None,
    prefix: str | None = None,
    suffix: str = ".tmp",
    fsync: bool = True,
    keep: bool = False,
    keep_on_error: bool = False,
    ignore_cleanup_errors: bool = True,
    cleanup_hook: CleanupHook | None = None,
) -> _AtomicWriter:
    """Create an atomic file writer context manager.

    Writes to a temp file in ``dest.parent``, then atomically replaces
    ``dest`` via ``os.replace()`` on success. On error, the temp file is
    deleted and ``dest`` is left untouched.

    Note: ``DEBUG=1``/``TMPKIT_DEBUG=1`` and keep signals keep the temp file
    and skip the replace — ``dest`` is left untouched even on success.

    Args:
        dest: Final destination path.
        mode: Open mode (e.g. ``"w"`` for text, ``"wb"`` for binary).
        encoding: Text encoding (text modes only).
        newline: Newline parameter (text modes only).
        prefix: Temp file name prefix.
        suffix: Temp file name suffix. Defaults to ``".tmp"``.
        fsync: If ``True``, call ``os.fsync()`` before closing.
        keep: If ``True``, temp file is NOT deleted and ``dest`` is untouched.
        keep_on_error: If ``True``, keep temp file on exception (don't delete).
        ignore_cleanup_errors: If ``True``, ``OSError`` during cleanup is silently ignored.
        cleanup_hook: Optional callable invoked with the temp path before the temp is
            removed (deleted, or moved on success). Not called when the temp is kept.
            Hook errors are ignored if ``ignore_cleanup_errors=True``; otherwise they
            propagate after cleanup, with body exceptions taking precedence.

    Returns:
        An ``_AtomicWriter`` context manager.
    """
    return _AtomicWriter(
        dest,
        mode=mode,
        encoding=encoding,
        newline=newline,
        prefix=prefix,
        suffix=suffix,
        fsync=fsync,
        keep=keep,
        keep_on_error=keep_on_error,
        ignore_cleanup_errors=ignore_cleanup_errors,
        cleanup_hook=cleanup_hook,
    )
