# tmpkit

Ergonomic tempfile & tempdir context managers with auto-cleanup, atomic writes, async support, and zero dependencies.

[![CI](https://github.com/MathiasPaulenko/tmpkit/actions/workflows/ci.yml/badge.svg)](https://github.com/MathiasPaulenko/tmpkit/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/tmpkit)](https://pypi.org/project/tmpkit/)
[![Python](https://img.shields.io/pypi/pyversions/tmpkit)](https://pypi.org/project/tmpkit/)
[![License](https://img.shields.io/pypi/l/tmpkit)](https://github.com/MathiasPaulenko/tmpkit/blob/main/LICENSE)
[![Coverage](https://img.shields.io/codecov/c/github/MathiasPaulenko/tmpkit)](https://codecov.io/gh/MathiasPaulenko/tmpkit)

---

## Table of Contents

- [Why tmpkit?](#why-tmpkit)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Features](#features)
- [API Reference](#api-reference)
  - [`temp_file()`](#temp_file)
  - [`temp_dir()`](#temp_dir)
  - [`atomic_write()`](#atomic_write)
  - [`@temp_dir()` Decorator](#temp_dir-decorator)
  - [`@temp_file()` Decorator](#temp_file-decorator)
  - [`temp_registry`](#temp_registry)
  - [Async API](#async-api)
  - [Environment Variables](#environment-variables)
- [Keep Control: Precedence](#keep-control-precedence)
- [Cleanup Hooks](#cleanup-hooks)
- [Comparison](#comparison)
- [Contributing](#contributing)
- [Changelog](#changelog)
- [Acknowledgements](#acknowledgements)
- [License](#license)

---

## Why tmpkit?

Python's `tempfile` gives you the pieces but forces you to write cleanup boilerplate every time. tmpkit wraps it in ergonomic context managers that **guarantee cleanup** — with features nobody else offers.

```python
# stdlib — verbose, easy to forget cleanup
import os, tempfile, shutil
tmpdir = tempfile.mkdtemp()
try:
    with open(os.path.join(tmpdir, "data.csv"), "w") as f:
        f.write(data)
finally:
    shutil.rmtree(tmpdir, ignore_errors=True)

# tmpkit — one line, always cleans up
from tmpkit import temp_file
with temp_file(suffix=".csv") as f:
    f.write(data)
```

---

## Installation

```bash
pip install tmpkit
```

**Requirements:** Python >= 3.11. Zero runtime dependencies.

For development:

```bash
pip install -e ".[dev]"
```

This installs `pytest`, `pytest-asyncio`, `pytest-cov`, `ruff`, `mypy`, and `build`.

---

## Quick Start

```python
from tmpkit import temp_file, temp_dir, atomic_write, async_temp_file

# Temp file
with temp_file(suffix=".csv", prefix="myapp_") as f:
    f.write(data)
    # deleted on exit

# Temp dir with auto-chdir
with temp_dir(cwd=True) as d:
    (d / "output.txt").write_text("hello")
    # cwd restored, dir removed on exit

# Keep on error — the killer debugging feature
with temp_file(keep_on_error=True) as f:
    f.write(data)
    risky_operation(f)  # if this raises, file stays
# if no exception, file is deleted

# Atomic write
with atomic_write("config.json") as f:
    f.write(data)
# on success: atomically renamed to config.json
# on error: config.json untouched, temp cleaned up

# Promote temp to permanent location
with temp_file(dest="output.csv") as f:
    f.write(data)
# on success: moved to output.csv

# Async
async def main() -> None:
    async with async_temp_file(suffix=".json") as f:
        await f.write(data)
```

---

## Features

- **`keep_on_error=True`** — keep temp only on exception, delete on success. The #1 most requested tempfile feature. Nobody else has it.
- **`atomic_write()`** — temp file + atomic rename. The most reimplemented pattern, now built-in.
- **`dest=` parameter** — promote temp to a permanent location on success.
- **`DEBUG=1` env var** — keep all temps for debugging, no code changes.
- **`keep=True` per-call** — keep a specific temp without global DEBUG.
- **`.keep()` method** — decide at runtime whether to keep.
- **`cwd=True`** — auto-chdir into temp dir, restore on exit.
- **`content=`** — pre-populate file with content.
- **`cleanup_hook=`** — custom hook called before standard cleanup.
- **`temp_registry`** — track all temps globally, cleanup on demand.
- **`@temp_dir()` / `@temp_file()` decorators** — inject temps into functions and test classes.
- **Close without delete** — file survives `close()`, deleted on context exit (Windows subprocess friendly).
- **`.path` attribute** — `Path` object, no more `Path(f.name)` boilerplate.
- **Async support** — `async with temp_file() as f:` with async I/O methods.
- **Windows-safe by default** — no `O_TEMPORARY` lock, `ignore_cleanup_errors=True`.
- **Zero dependencies** — stdlib only.

---

## API Reference

### `temp_file()`

```python
from tmpkit import temp_file

with temp_file(
    suffix: str | None = None,        # e.g. ".csv"
    prefix: str | None = None,        # e.g. "myapp_"
    dir: str | Path | None = None,    # parent directory
    mode: str = "w+b",                # open mode
    content: str | bytes | None = None,  # pre-populate
    dest: str | Path | None = None,   # move here on success
    keep: bool = False,               # always keep
    keep_on_error: bool = False,      # keep only on exception
    ignore_cleanup_errors: bool = True,
    cleanup_hook: Callable[[Path], None] | None = None,
) as f:
    f.write(data)      # file-like I/O
    f.read()
    f.seek(0)
    f.path             # Path object
    f.keep()           # runtime decision to keep
```

**Returns:** A file-like object with `.path` (Path), `.keep()`, and all standard file methods (`read`, `write`, `seek`, `tell`, `flush`, `close`).

**`dest=` behavior:**

- On success: temp is moved to `dest` via `os.replace()` (same filesystem) or `shutil.move()` (cross-filesystem).
- On error: temp is deleted, `dest` is untouched.
- If `dest` already exists, it is overwritten.

### `temp_dir()`

```python
from tmpkit import temp_dir

with temp_dir(
    suffix: str | None = None,
    prefix: str | None = None,
    dir: str | Path | None = None,
    cwd: bool = False,                # auto-chdir into temp dir
    keep: bool = False,
    keep_on_error: bool = False,
    ignore_cleanup_errors: bool = True,
    cleanup_hook: Callable[[Path], None] | None = None,
) as d:
    (d / "file.txt").write_text("hello")
    d                  # Path object

# To call .keep(), use the context manager object directly:
td = temp_dir()
with td as d:
    (d / "file.txt").write_text("hello")
td.keep()           # runtime decision to keep
```

**Returns:** A `Path` object (the temp directory path) with `/` operator support. To call `.keep()`, use the context manager object directly (see example above).

**`cwd=True`:** Changes the working directory to the temp dir on `__enter__`, restores the original on `__exit__`.

### `atomic_write()`

```python
from tmpkit import atomic_write

with atomic_write(
    dest: str | Path,                 # final destination
    mode: str = "w",                  # "w" (text) or "wb" (binary)
    encoding: str | None = None,
    newline: str | None = None,
    prefix: str | None = None,
    suffix: str = ".tmp",
    fsync: bool = True,               # fsync before rename
    keep_on_error: bool = False,
    ignore_cleanup_errors: bool = True,
) as f:
    f.write(data)
# on success: atomically renamed to dest
# on error: dest untouched, temp deleted
```

Writes to a temp file in `dest`'s parent directory, then atomically replaces `dest` via `os.replace()` on success. On error, the temp is cleaned up and `dest` is left untouched.

### `@temp_dir()` Decorator

```python
from tmpkit import temp_dir_decorator

# On a function — temp dir injected as first arg
@temp_dir_decorator()
def process(tmp: Path, data: str) -> None:
    (tmp / "output.txt").write_text(data)

# cwd=True by default for the decorator
@temp_dir_decorator(prefix="test_")
def my_func(tmp: Path) -> str:
    return str(tmp)

# On a test class — each test_ method gets a fresh temp dir
@temp_dir_decorator()
class TestMyApp:
    def test_writes_file(self) -> None:
        assert self.tmpdir.exists()
        (self.tmpdir / "data.txt").write_text("test")

    async def test_async(self) -> None:
        assert self.tmpdir.exists()
```

**Decorator defaults:** `cwd=True` (unlike the context manager where `cwd=False` by default).

**Class decoration:** Each method starting with `test_` is wrapped. The temp dir is available as `self.tmpdir`. Works with both sync and async test methods.

### `@temp_file()` Decorator

```python
from tmpkit import temp_file_decorator

@temp_file_decorator(mode="w+")
def process(f, data: str) -> str:
    f.write(data)
    f.seek(0)
    return f.read()

result = process("hello world")

# Async functions supported
@temp_file_decorator(suffix=".json")
async def process_async(f, data: str) -> None:
    await f.write(data)
```

The temp file object is injected as the **first positional argument**.

### `temp_registry`

```python
from tmpkit import temp_registry

# Enable tracking
temp_registry.enable()

# Or via env var: TMPKIT_REGISTRY=1

with temp_file() as f:
    assert len(temp_registry.active) == 1
    assert temp_registry.active[0].path == f.path
# After exit:
assert len(temp_registry.active) == 0
assert len(temp_registry.cleaned) == 1

# Inspect all records
for record in temp_registry.all:
    print(f"{record.kind} at {record.path} (cleaned={record.cleaned}, kept={record.kept})")

# Emergency cleanup
count = temp_registry.cleanup_all()  # deletes all active temps

# Mark all as kept
temp_registry.keep_all()

# Clear cleaned records from history
temp_registry.clear_history()

# Disable
temp_registry.disable()
```

**`TempRecord` fields:**

| Field | Type | Description |
| --- | --- | --- |
| `path` | `Path` | Filesystem path |
| `kind` | `"file"` or `"dir"` | Resource type |
| `created_at` | `float` | Epoch timestamp |
| `cleaned` | `bool` | Whether it was cleaned up |
| `kept` | `bool` | Whether it was kept |

**Thread-safe:** All operations are protected by `threading.Lock`.

### Async API

All sync APIs have async counterparts with identical parameters:

```python
from tmpkit import async_temp_file, async_temp_dir, async_atomic_write

# Async temp file
async with async_temp_file(suffix=".csv") as f:
    await f.write(data)
    await f.seek(0)
    content = await f.read()

# Async temp dir
async with async_temp_dir(cwd=True) as d:
    ...

# Async atomic write
async with async_atomic_write("config.json") as f:
    await f.write(data)
```

Async file objects support `await f.read()`, `await f.write()`, `await f.seek()`, `await f.tell()`, `await f.flush()`, `await f.close()`.

### Environment Variables

| Variable | Value | Effect |
| --- | --- | --- |
| `TMPKIT_DEBUG` | `1` | Keep all temps (overrides `keep=False`) |
| `DEBUG` | `1` | Same as `TMPKIT_DEBUG=1` (fallback) |
| `TMPKIT_REGISTRY` | `1` | Enable `temp_registry` at import time |

`TMPKIT_DEBUG` takes precedence over `DEBUG`.

---

## Keep Control: Precedence

When multiple keep signals are present, precedence is:

1. **`.keep()` method** — highest priority, always keeps.
2. **`keep=True` parameter** — always keeps.
3. **`DEBUG=1` / `TMPKIT_DEBUG=1` env var** — keeps all temps globally.
4. **`keep_on_error=True` + exception** — keeps only on error.
5. **`dest=` move** — if none of the above trigger, temp is moved to dest on success.
6. **Standard cleanup** — temp is deleted.

```python
# .keep() wins over everything
with temp_file(keep=False) as f:
    f.write(data)
    f.keep()  # file is kept despite keep=False

# DEBUG=1 overrides keep=False
# $ TMPKIT_DEBUG=1 python my_script.py
with temp_file() as f:  # file is kept
    f.write(data)

# keep_on_error keeps only on exception
with temp_file(keep_on_error=True) as f:
    f.write(data)
    raise RuntimeError("oops")  # file is kept
```

---

## Cleanup Hooks

The `cleanup_hook` parameter lets you run custom logic before standard cleanup:

```python
def my_hook(path: Path) -> None:
    print(f"Cleaning up {path}")
    # e.g. log, collect metrics, copy to backup, etc.

with temp_file(cleanup_hook=my_hook) as f:
    f.write(data)
# hook is called, then standard cleanup runs

# Hook is called even on exceptions
with temp_file(cleanup_hook=my_hook) as f:
    raise RuntimeError("oops")
# hook is still called, then temp is deleted

# Hook errors are swallowed if ignore_cleanup_errors=True (default)
def bad_hook(path: Path) -> None:
    raise OSError("hook failed")

with temp_file(cleanup_hook=bad_hook) as f:  # no error raised
    f.write(data)

# Hook is NOT called when temp is kept
with temp_file(keep=True, cleanup_hook=my_hook) as f:
    f.write(data)
# hook is NOT called
```

---

## Comparison

| Feature | tmpkit | stdlib `tempfile` | `temporary` | `tdir` | `temppathlib` | `ephemdir` |
| --- | --- | --- | --- | --- | --- | --- |
| `keep_on_error` | Yes | No | No | No | No | No |
| `atomic_write()` | Yes | No | No | No | No | No |
| `dest=` promote | Yes | No | No | No | No | No |
| `cleanup_hook` | Yes | No | No | No | No | No |
| `temp_registry` | Yes | No | No | No | No | No |
| Decorators | Yes | No | No | No | No | No |
| `DEBUG=1` env var | Yes | No | No | No | No | No |
| `keep=True` per-call | Yes | No | No | No | No | No |
| `.keep()` method | Yes | No | No | No | No | No |
| Close without delete | Yes | No | No | No | No | No |
| `.path` attribute | Yes | No | No | No | Yes | No |
| `cwd=True` | Yes | No | Yes | Yes | No | No |
| `content=` | Yes | No | Yes | No | No | No |
| Async support | Yes | No | No | No | No | No |
| Windows-safe by default | Yes | No | No | No | No | No |
| `ignore_cleanup_errors` | Yes (default) | Yes (opt-in) | No | No | No | No |
| Returns `Path` | Yes | No | Yes | No | Yes | No |
| Zero deps | Yes | Yes | No | Yes | Yes | Yes |
| Python >=3.11 | Yes | Yes | No | Yes | No | Yes |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, code style, testing, and pull request guidelines.

Please read our [Code of Conduct](CODE_OF_CONDUCT.md) before contributing.

To report a security vulnerability, see [SECURITY.md](SECURITY.md).

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for a full list of changes.

---

## Acknowledgements

- Python's [`tempfile`](https://docs.python.org/3/library/tempfile.html) module — the foundation tmpkit builds upon.
- [`contextlib`](https://docs.python.org/3/library/contextlib.html) — inspiration for the context manager patterns.
- Every developer who has written `try/finally/shutil.rmtree` boilerplate — you deserved better.

---

## License

[MIT](LICENSE) — Copyright (c) 2025 Mathias Paulenko
