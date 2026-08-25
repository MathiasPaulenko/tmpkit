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
from tmpkit._types import StrPath, _validate_prefix_suffix


class _AtomicWriter:
    """Atomic file writer. Writes to a temp file, then atomically replaces dest on success."""

    __slots__ = (
        "_closed",
        "_dest",
        "_encoding",
        "_exited",
        "_file",
        "_fsync",
        "_ignore_cleanup_errors",
        "_keep_on_error",
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
        keep_on_error: bool = False,
        ignore_cleanup_errors: bool = True,
    ) -> None:
        self._dest = Path(dest)
        self._mode = mode
        self._encoding = encoding
        self._newlines = newline
        self._prefix = _validate_prefix_suffix(prefix, "prefix")
        validated_suffix = _validate_prefix_suffix(suffix, "suffix")
        self._suffix = validated_suffix if validated_suffix is not None else ".tmp"
        self._fsync = fsync
        self._keep_on_error = keep_on_error
        self._ignore_cleanup_errors = ignore_cleanup_errors
        self._path: Path | None = None
        self._file: Any = None
        self._closed = False
        self._exited = False
        self._user_keep = False
        self._record: TempRecord | None = None

    def __enter__(self) -> _AtomicWriter:
        # Reset state for re-entry (context managers can be reused).
        self._closed = False
        self._exited = False
        self._user_keep = False
        self._record = None
        dest_parent = self._dest.parent
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
        self._path = Path(path_str)

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
                keep=False,
                keep_on_error=self._keep_on_error,
                had_error=had_error,
            )
            or self._user_keep
        )

        # Close file: flush + fsync + close
        if not self._closed and self._file is not None:
            try:
                self._file.flush()
                if self._fsync:
                    assert self._path is not None
                    os.fsync(self._file.fileno())
            except OSError:
                with contextlib.suppress(OSError):
                    self._file.close()
                self._closed = True
                effective_keep = should_keep or self._keep_on_error
                self._finalize_keep_or_clean(effective_keep)
                raise
            with contextlib.suppress(OSError):
                self._file.close()
            self._closed = True

        if should_keep:
            if self._record is not None:
                temp_registry.mark_kept(self._record)
            return

        if had_error:
            self._finalize_clean()
            return

        # Success: atomic replace
        assert self._path is not None
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
        if self._record is not None:
            temp_registry.mark_cleaned(self._record)

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
            if self._record is not None:
                temp_registry.mark_kept(self._record)
        else:
            self._finalize_clean()

    def write(self, data: bytes | str) -> int:
        if self._closed:
            raise ValueError("I/O operation on closed file.")
        assert self._file is not None
        return self._file.write(data)  # type: ignore[no-any-return]

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

    @property
    def dest(self) -> Path:
        return self._dest

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
        path_str = repr(self._path) if self._path else "None"
        if self._closed:
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
    keep_on_error: bool = False,
    ignore_cleanup_errors: bool = True,
) -> _AtomicWriter:
    """Create an atomic file writer context manager.

    Writes to a temp file in ``dest.parent``, then atomically replaces
    ``dest`` via ``os.replace()`` on success. On error, the temp file is
    deleted and ``dest`` is left untouched.

    Args:
        dest: Final destination path.
        mode: Open mode (e.g. ``"w"`` for text, ``"wb"`` for binary).
        encoding: Text encoding (text modes only).
        newline: Newline parameter (text modes only).
        prefix: Temp file name prefix.
        suffix: Temp file name suffix. Defaults to ``".tmp"``.
        fsync: If ``True``, call ``os.fsync()`` before closing.
        keep_on_error: If ``True``, keep temp file on exception (don't delete).
        ignore_cleanup_errors: If ``True``, ``OSError`` during cleanup is silently ignored.

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
        keep_on_error=keep_on_error,
        ignore_cleanup_errors=ignore_cleanup_errors,
    )
