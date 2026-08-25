"""Temp registry: track all temp files/dirs for cleanup and inspection."""

from __future__ import annotations

import os
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(slots=True)
class TempRecord:
    """Record of a single temp file or directory.

    Attributes:
        path: Filesystem path of the temp.
        kind: ``"file"`` or ``"dir"``.
        created_at: Creation timestamp (epoch seconds from ``time.time``).
        cleaned: ``True`` once the temp has been deleted/moved.
        kept: ``True`` if the temp was kept (not cleaned up).
    """

    path: Path
    kind: Literal["file", "dir"]
    created_at: float
    cleaned: bool = False
    kept: bool = False


class TempRegistry:
    """Thread-safe registry of temporary files and directories.

    Disabled by default for zero overhead. Enable via ``enable()`` or
    setting ``TMPKIT_REGISTRY=1`` environment variable at import time.
    """

    __slots__ = ("_enabled", "_lock", "_records")

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: list[TempRecord] = []
        self._enabled = os.environ.get("TMPKIT_REGISTRY") == "1"

    @property
    def enabled(self) -> bool:
        """Whether the registry is currently active."""
        with self._lock:
            return self._enabled

    def enable(self) -> None:
        """Enable the registry."""
        with self._lock:
            self._enabled = True

    def disable(self) -> None:
        """Disable the registry. Existing records are preserved."""
        with self._lock:
            self._enabled = False

    def register(self, path: Path, kind: Literal["file", "dir"]) -> TempRecord | None:
        """Register a new temp. Returns the record, or ``None`` if disabled."""
        with self._lock:
            if not self._enabled:
                return None
            record = TempRecord(
                path=path,
                kind=kind,
                created_at=_now(),
            )
            self._records.append(record)
            return record

    def mark_cleaned(self, record: TempRecord) -> None:
        """Mark a record as cleaned up."""
        with self._lock:
            record.cleaned = True

    def mark_kept(self, record: TempRecord) -> None:
        """Mark a record as kept (not cleaned up)."""
        with self._lock:
            record.kept = True

    @property
    def all(self) -> list[TempRecord]:
        """All records (active + cleaned)."""
        with self._lock:
            return list(self._records)

    @property
    def active(self) -> list[TempRecord]:
        """Records for temps that have not been cleaned or kept."""
        with self._lock:
            return [r for r in self._records if not r.cleaned and not r.kept]

    @property
    def cleaned(self) -> list[TempRecord]:
        """Records for temps that have been cleaned up."""
        with self._lock:
            return [r for r in self._records if r.cleaned]

    def cleanup_all(self) -> int:
        """Delete all active temps. Returns the number of temps deleted."""
        count = 0
        with self._lock:
            active = [r for r in self._records if not r.cleaned and not r.kept]

        for record in active:
            # Re-check under the lock that the record is still active;
            # another thread may have marked it kept/cleaned since the snapshot.
            with self._lock:
                if record.cleaned or record.kept:
                    continue
            try:
                if not record.path.exists():
                    # Already gone on disk — mark cleaned without counting.
                    with self._lock:
                        record.cleaned = True
                    continue
                if record.kind == "dir":
                    shutil.rmtree(record.path)
                else:
                    record.path.unlink()
                with self._lock:
                    record.cleaned = True
                count += 1
            except OSError:
                pass
        return count

    def keep_all(self) -> int:
        """Mark all active temps as kept. Returns the number marked."""
        with self._lock:
            count = 0
            for record in self._records:
                if not record.cleaned and not record.kept:
                    record.kept = True
                    count += 1
            return count

    def clear_history(self) -> None:
        """Remove all cleaned records from history."""
        with self._lock:
            self._records = [r for r in self._records if not r.cleaned]

    def reset(self) -> None:
        """Clear all records and disable. Useful for testing."""
        with self._lock:
            self._records.clear()
            self._enabled = False


def _now() -> float:
    return time.time()


temp_registry = TempRegistry()
