"""Type system: shared type aliases, protocols, and input validation."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, TypeAlias, runtime_checkable

StrPath: TypeAlias = str | Path
CleanupHook: TypeAlias = Callable[[Path], None]


def _validate_prefix_suffix(value: str | None, name: str) -> str | None:
    """Validate that prefix/suffix doesn't contain path separators.

    Python's ``tempfile.mkstemp``/``mkdtemp`` concatenate prefix and suffix
    into the filename within ``dir``. If they contain path separators or are
    absolute paths, the resulting temp file can escape the intended directory.
    On Windows, characters like ``:`` are also rejected: ``name:stream``
    creates an NTFS alternate data stream on a base file that cleanup would
    leave behind, and ``<>|"?*`` are invalid in filenames outright.
    """
    if value is None:
        return None
    if not value:
        return value
    if "\0" in value:
        raise ValueError(f"{name} must not contain NUL bytes: {value!r}")
    if os.path.isabs(value) or os.sep in value or "/" in value or "\\" in value:
        raise ValueError(
            f"{name} must not contain path separators or be an absolute path: {value!r}"
        )
    if os.name == "nt" and any(c in value for c in '<>:"|?*'):
        raise ValueError(f"{name} contains characters invalid on Windows: {value!r}")
    return value


def _merge_deferred(
    primary: BaseException, deferred: BaseException | None
) -> BaseException:
    """Choose which exception propagates out of ``__exit__``.

    A deferred secondary error (e.g. a cleanup_hook failure captured while
    a close/replace error is being raised) is chained as ``__cause__`` so it
    is never silently lost. A non-Exception deferred error
    (KeyboardInterrupt, SystemExit, ...) always takes precedence — process
    interrupts must never be swallowed.
    """
    if deferred is None:
        return primary
    if not isinstance(deferred, Exception):
        return deferred
    primary.__cause__ = deferred
    return primary


@runtime_checkable
class TempFileLike(Protocol):
    """Protocol for temp file objects returned by temp_file()."""

    path: Path

    def read(self, size: int = -1, /) -> bytes | str: ...
    def write(self, data: bytes | str, /) -> int: ...
    def close(self) -> None: ...
    def seek(self, offset: int, whence: int = 0) -> int: ...
    def tell(self) -> int: ...
    def flush(self) -> None: ...
    def keep(self) -> None: ...
