# Changelog

All notable changes to tmpkit will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Nothing yet.

### Changed

- Nothing yet.

### Deprecated

- Nothing yet.

### Removed

- Nothing yet.

### Fixed

- Nothing yet.

### Security

- Nothing yet.

## [1.0.1] - 2025-01-24

### Fixed

- Bump `codecov/codecov-action` from v4 to v7 to resolve Node.js 20
  deprecation warnings in CI.
- Fix `test_windows.py` failures on Linux/macOS — `TestWindowsNameMock`
  tests now skip on non-Windows platforms.
- Fix macOS CI failures from `/var` symlink resolution — cwd tests now
  compare resolved paths.

## [1.0.0] - 2025-01-24

### Added

- Project design documents in `ref/` (context, competitor analysis, features, design, API contract, object spec, migration guide).
- `temp_file()` sync context manager with auto-cleanup.
- `temp_dir()` sync context manager with auto-cleanup.
- `temp_file()` async context manager.
- `temp_dir()` async context manager.
- `DEBUG=1` / `TMPKIT_DEBUG=1` environment variable to keep all temps.
- `keep=True` parameter for per-call keep override.
- `keep_on_error=True` parameter — keep temp only on exception (killer feature).
- `.keep()` method — runtime decision to keep temp.
- `cwd=True` parameter in `temp_dir()` — auto-chdir with restore.
- `content=` parameter in `temp_file()` — pre-populate file content.
- `dir=` parameter — specify parent directory.
- `mode=` parameter in `temp_file()` — text/binary mode control.
- Close-without-delete — file survives `close()`, deleted on context exit (Windows subprocess friendly).
- `.path` attribute — `Path` object on temp file objects.
- `__fspath__` protocol — temp objects work with `os.path`, `shutil`, `subprocess`.
- `ignore_cleanup_errors=True` by default — best-effort cleanup on Windows.
- `prefix=` and `suffix=` support.
- Returns `Path` objects (not raw strings).
- Named temps by default — Windows-safe (no `O_TEMPORARY` flag).
- `atomic_write()` context manager — temp file + atomic rename on success.
- `dest=` parameter in `temp_file()` — promote temp to permanent destination.
- `@temp_dir()` and `@temp_file()` decorator support.
- Cleanup hooks.
- Temp registry — process-local tracking of all temps.

### Changed

- Nothing yet.

### Deprecated

- Nothing yet.

### Removed

- Nothing yet.

### Fixed

- Registry records are no longer marked `cleaned` when cleanup fails — the
  registry now reflects on-disk reality so `cleanup_all()` can retry.
- `cleanup_all()` no longer counts already-gone temps as deleted, and
  re-checks record state under the lock to prevent a race condition where
  a concurrently-kept record could be deleted.
- `atomic_write()` no longer passes `newline`/`encoding` to `os.fdopen` in
  binary mode (previously raised `TypeError`).
- `.keep()` now raises `RuntimeError` if called after `__exit__` instead
  of silently succeeding.
- `atomic_write()` now raises `NotADirectoryError` when the destination
  parent exists but is a file, instead of a confusing `OSError` from
  `mkstemp`.
- `TempFileLike` protocol `read()` signature now matches the
  implementation (`read(size: int = -1)`).
- `@temp_file()` decorator docstring no longer claims method support.
- `cleanup_hook` failure no longer prevents standard cleanup — the temp
  file/directory is always cleaned up, and the hook error is re-raised
  after cleanup (body exceptions take precedence).
- Context manager reuse (`__enter__` called twice) now correctly resets
  internal state instead of raising stale `ValueError` or `RuntimeError`.

### Security

- `prefix` and `suffix` parameters are now validated to reject path
  separators and absolute paths, preventing path traversal via
  `tempfile.mkstemp`/`mkdtemp`.
