"""tmpkit — Ergonomic tempfile & tempdir context managers with auto-cleanup, atomic writes, async support, and zero dependencies."""

from tmpkit._async import atomic_write as async_atomic_write
from tmpkit._async import temp_dir as async_temp_dir
from tmpkit._async import temp_file as async_temp_file
from tmpkit._atomic import atomic_write
from tmpkit._decorators import temp_dir as temp_dir_decorator
from tmpkit._decorators import temp_file as temp_file_decorator
from tmpkit._registry import temp_registry
from tmpkit._sync import temp_dir, temp_file

__version__ = "1.0.1"

__all__ = [
    "async_atomic_write",
    "async_temp_dir",
    "async_temp_file",
    "atomic_write",
    "temp_dir",
    "temp_dir_decorator",
    "temp_file",
    "temp_file_decorator",
    "temp_registry",
]
