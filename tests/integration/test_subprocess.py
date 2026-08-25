"""Integration tests: subprocess interaction with temp files."""

from __future__ import annotations

import subprocess
import sys

from tmpkit import temp_file


class TestSubprocessFile:
    """Create temp file, close, spawn subprocess to read it, verify content."""

    def test_subprocess_reads_file_after_close(self) -> None:
        with temp_file(mode="w+b") as f:
            f.write(b"hello from subprocess test")
            f.close()
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    f"import sys; sys.stdout.buffer.write(open(r'{f.path}', 'rb').read())",
                ],
                capture_output=True,
                timeout=10,
            )
            assert result.returncode == 0
            assert result.stdout == b"hello from subprocess test"

    def test_file_deleted_after_context_exit(self) -> None:
        with temp_file(mode="w+b") as f:
            f.write(b"temporary")
            path = f.path
        assert not path.exists()
        # Subprocess confirms file is gone
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                f"import os; print(os.path.exists(r'{path}'))",
            ],
            capture_output=True,
            timeout=10,
        )
        assert b"False" in result.stdout

    def test_subprocess_writes_to_file_path(self) -> None:
        with temp_file(mode="w+b") as f:
            f.close()
            # Subprocess writes to the file path
            subprocess.run(
                [
                    sys.executable,
                    "-c",
                    f"open(r'{f.path}', 'wb').write(b'written by subprocess')",
                ],
                capture_output=True,
                timeout=10,
                check=True,
            )
            # Read it back
            with open(f.path, "rb") as fh:
                assert fh.read() == b"written by subprocess"

    def test_subprocess_with_text_file(self) -> None:
        with temp_file(mode="w+", content="line1\nline2\n") as f:
            f.close()
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    f"print(open(r'{f.path}').read(), end='')",
                ],
                capture_output=True,
                timeout=10,
            )
            assert result.returncode == 0
            assert b"line1" in result.stdout
            assert b"line2" in result.stdout
