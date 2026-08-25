"""Async context managers for temporary files and directories."""

from __future__ import annotations

import asyncio
from pathlib import Path

from tmpkit._atomic import _AtomicWriter
from tmpkit._sync import CleanupHook, _TempDir, _TempFile
from tmpkit._types import StrPath


class _AsyncTempFile:
    """Async temp file context manager. Returned by temp_file()."""

    __slots__ = ("_sync",)

    def __init__(self, sync: _TempFile) -> None:
        self._sync = sync

    async def __aenter__(self) -> _AsyncTempFile:
        await asyncio.to_thread(self._sync.__enter__)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        await asyncio.to_thread(self._sync.__exit__, exc_type, exc_val, exc_tb)

    async def read(self, size: int = -1) -> bytes | str:
        return await asyncio.to_thread(self._sync.read, size)

    async def write(self, data: bytes | str) -> int:
        return await asyncio.to_thread(self._sync.write, data)

    async def seek(self, offset: int, whence: int = 0) -> int:
        return await asyncio.to_thread(self._sync.seek, offset, whence)

    async def tell(self) -> int:
        return await asyncio.to_thread(self._sync.tell)

    async def flush(self) -> None:
        await asyncio.to_thread(self._sync.flush)

    async def close(self) -> None:
        await asyncio.to_thread(self._sync.close)

    @property
    def path(self) -> Path:
        return self._sync.path

    def keep(self) -> None:
        self._sync.keep()

    def __fspath__(self) -> str:
        return self._sync.__fspath__()

    def __repr__(self) -> str:
        return f"Async{self._sync!r}"


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
) -> _AsyncTempFile:
    """Create an async temporary file context manager.

    The file is created on ``__aenter__`` and deleted on ``__aexit__``
    (unless keep conditions are met).

    If ``dest`` is set and the context exits without error, the temp file
    is moved to ``dest`` (via ``os.replace`` or ``shutil.move`` for cross-FS).

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
        An ``_AsyncTempFile`` context manager.
    """
    return _AsyncTempFile(
        _TempFile(
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
    )


class _AsyncTempDir:
    """Async temp dir context manager. Returned by temp_dir()."""

    __slots__ = ("_sync",)

    def __init__(self, sync: _TempDir) -> None:
        self._sync = sync

    async def __aenter__(self) -> Path:
        return await asyncio.to_thread(self._sync.__enter__)

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        await asyncio.to_thread(self._sync.__exit__, exc_type, exc_val, exc_tb)

    @property
    def path(self) -> Path:
        return self._sync.path

    def keep(self) -> None:
        self._sync.keep()

    def __fspath__(self) -> str:
        return self._sync.__fspath__()

    def __truediv__(self, other: str | Path) -> Path:
        return self._sync.__truediv__(other)

    def __repr__(self) -> str:
        return f"Async{self._sync!r}"


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
) -> _AsyncTempDir:
    """Create an async temporary directory context manager.

    The directory is created on ``__aenter__`` and removed on ``__aexit__``
    (unless keep conditions are met).

    Args:
        suffix: Directory name suffix.
        prefix: Directory name prefix.
        dir: Parent directory. Defaults to system temp dir.
        cwd: If ``True``, changes working directory to temp dir on ``__aenter__``, restores on ``__aexit__``.
        keep: If ``True``, directory is NOT removed on context exit.
        keep_on_error: If ``True``, directory is kept only when an exception propagates.
        ignore_cleanup_errors: If ``True``, ``OSError`` during cleanup is silently ignored.
        cleanup_hook: Optional callable invoked with the temp path before standard cleanup.
            Called only when the temp is being deleted (not when kept). Hook errors are
            ignored if ``ignore_cleanup_errors=True``; otherwise they propagate after
            cleanup, with body exceptions taking precedence.

    Returns:
        An ``_AsyncTempDir`` context manager.
    """
    return _AsyncTempDir(
        _TempDir(
            suffix=suffix,
            prefix=prefix,
            dir=dir,
            cwd=cwd,
            keep=keep,
            keep_on_error=keep_on_error,
            ignore_cleanup_errors=ignore_cleanup_errors,
            cleanup_hook=cleanup_hook,
        )
    )


class _AsyncAtomicWriter:
    """Async atomic file writer. Wraps ``_AtomicWriter`` with async I/O."""

    __slots__ = ("_sync",)

    def __init__(self, sync: _AtomicWriter) -> None:
        self._sync = sync

    async def __aenter__(self) -> _AsyncAtomicWriter:
        await asyncio.to_thread(self._sync.__enter__)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        await asyncio.to_thread(self._sync.__exit__, exc_type, exc_val, exc_tb)

    async def write(self, data: bytes | str) -> int:
        return await asyncio.to_thread(self._sync.write, data)

    async def flush(self) -> None:
        await asyncio.to_thread(self._sync.flush)

    async def close(self) -> None:
        await asyncio.to_thread(self._sync.close)

    @property
    def path(self) -> Path:
        return self._sync.path

    @property
    def dest(self) -> Path:
        return self._sync.dest

    def keep(self) -> None:
        self._sync.keep()

    def __fspath__(self) -> str:
        return self._sync.__fspath__()

    def __repr__(self) -> str:
        return f"Async{self._sync!r}"


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
) -> _AsyncAtomicWriter:
    """Create an async atomic file writer context manager.

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
        An ``_AsyncAtomicWriter`` context manager.
    """
    return _AsyncAtomicWriter(
        _AtomicWriter(
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
    )
