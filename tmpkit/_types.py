"""Type system: shared type aliases, protocols, and input validation."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol, TypeAlias, runtime_checkable

StrPath: TypeAlias = str | Path


def _validate_prefix_suffix(value: str | None, name: str) -> str | None:
    """Validate that prefix/suffix doesn't contain path separators.

    Python's ``tempfile.mkstemp``/``mkdtemp`` concatenate prefix and suffix
    into the filename within ``dir``. If they contain path separators or are
    absolute paths, the resulting temp file can escape the intended directory.
    """
    if value is None:
        return None
    if not value:
        return value
    if os.path.isabs(value) or os.sep in value or "/" in value or "\\" in value:
        raise ValueError(
            f"{name} must not contain path separators or be an absolute path: {value!r}"
        )
    return value


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
