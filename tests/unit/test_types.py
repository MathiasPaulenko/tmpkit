"""Smoke tests for _types.py: import, StrPath alias, TempFileLike protocol."""

from __future__ import annotations

from pathlib import Path

from tmpkit._types import StrPath, TempFileLike


def test_import() -> None:
    """Module imports without error."""
    assert StrPath is not None
    assert TempFileLike is not None


def test_strpath_accepts_str() -> None:
    """StrPath accepts str values."""
    p: StrPath = "/tmp/test"
    assert isinstance(p, str)


def test_strpath_accepts_path() -> None:
    """StrPath accepts Path values."""
    p: StrPath = Path("/tmp/test")
    assert isinstance(p, Path)


class _FakeTempFile:
    """Minimal implementation of TempFileLike for protocol testing."""

    def __init__(self) -> None:
        self.path: Path = Path("/tmp/fake")

    def read(self, size: int = -1, /) -> bytes | str:
        return b""

    def write(self, data: bytes | str, /) -> int:
        return len(data)

    def close(self) -> None:
        pass

    def seek(self, offset: int, whence: int = 0) -> int:
        return 0

    def tell(self) -> int:
        return 0

    def flush(self) -> None:
        pass

    def keep(self) -> None:
        pass


def test_tempfilelike_protocol() -> None:
    """_FakeTempFile satisfies TempFileLike protocol at runtime."""
    f = _FakeTempFile()
    assert isinstance(f, TempFileLike)


def test_non_matching_object_fails_protocol() -> None:
    """A plain object does not satisfy TempFileLike."""

    class _NoMatch:
        pass

    assert not isinstance(_NoMatch(), TempFileLike)
