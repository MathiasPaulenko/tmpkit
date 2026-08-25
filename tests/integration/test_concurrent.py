"""Integration tests: concurrent temp creation and cleanup."""

from __future__ import annotations

import threading
from pathlib import Path

from tmpkit import temp_dir, temp_file


class TestConcurrentTempFile:
    """100 threads creating temp files, verify all cleaned up."""

    def test_100_threads_all_cleaned_up(self) -> None:
        paths: list[Path] = []
        lock = threading.Lock()
        errors: list[Exception] = []

        def worker() -> None:
            try:
                with temp_file() as f:
                    f.write(b"concurrent")
                    with lock:
                        paths.append(f.path)
            except Exception as e:
                with lock:
                    errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert len(paths) == 100
        for p in paths:
            assert not p.exists(), f"Temp file still exists: {p}"


class TestConcurrentTempDir:
    """100 threads creating temp dirs, verify all cleaned up."""

    def test_100_threads_all_cleaned_up(self) -> None:
        paths: list[Path] = []
        lock = threading.Lock()
        errors: list[Exception] = []

        def worker() -> None:
            try:
                with temp_dir() as d:
                    (d / "file.txt").write_text("concurrent")
                    with lock:
                        paths.append(d)
            except Exception as e:
                with lock:
                    errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert len(paths) == 100
        for p in paths:
            assert not p.exists(), f"Temp dir still exists: {p}"


class TestConcurrentMixed:
    """50 threads with files + 50 threads with dirs."""

    def test_mixed_all_cleaned_up(self) -> None:
        file_paths: list[Path] = []
        dir_paths: list[Path] = []
        lock = threading.Lock()
        errors: list[Exception] = []

        def file_worker() -> None:
            try:
                with temp_file() as f:
                    f.write(b"mixed")
                    with lock:
                        file_paths.append(f.path)
            except Exception as e:
                with lock:
                    errors.append(e)

        def dir_worker() -> None:
            try:
                with temp_dir() as d, lock:
                    dir_paths.append(d)
            except Exception as e:
                with lock:
                    errors.append(e)

        threads = [threading.Thread(target=file_worker) for _ in range(50)]
        threads += [threading.Thread(target=dir_worker) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert len(file_paths) == 50
        assert len(dir_paths) == 50
        for p in file_paths:
            assert not p.exists()
        for p in dir_paths:
            assert not p.exists()
