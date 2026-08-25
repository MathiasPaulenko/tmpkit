"""Decorators: @temp_dir() and @temp_file() for functions and test classes."""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from typing import Any, TypeVar

from tmpkit._async import temp_dir as async_temp_dir
from tmpkit._async import temp_file as async_temp_file
from tmpkit._sync import temp_dir as sync_temp_dir
from tmpkit._sync import temp_file as sync_temp_file
from tmpkit._types import StrPath

F = TypeVar("F", bound=Callable[..., Any])


def temp_dir(
    *,
    suffix: str | None = None,
    prefix: str | None = None,
    dir: StrPath | None = None,
    cwd: bool = True,
    keep: bool = False,
    keep_on_error: bool = False,
    ignore_cleanup_errors: bool = True,
) -> Callable[[F], F]:
    """Decorator that provides a fresh temp directory for each call.

    By default ``cwd=True`` — the function runs inside the temp dir and
    the original cwd is restored on exit.

    Works on:
    - Sync functions: wrapped normally.
    - Async functions: detected via ``inspect.iscoroutinefunction``.
    - Test classes: each method gets a fresh temp dir as ``self.tmpdir``.

    Args:
        suffix: Directory name suffix.
        prefix: Directory name prefix.
        dir: Parent directory. Defaults to system temp dir.
        cwd: If ``True``, changes working directory to temp dir. Defaults to ``True``.
        keep: If ``True``, directory is NOT removed.
        keep_on_error: If ``True``, directory is kept only on exception.
        ignore_cleanup_errors: If ``True``, ``OSError`` during cleanup is silently ignored.
    """

    def decorator(func_or_cls: F) -> F:
        if inspect.isclass(func_or_cls):
            _decorate_class(
                func_or_cls,
                suffix=suffix,
                prefix=prefix,
                dir=dir,
                cwd=cwd,
                keep=keep,
                keep_on_error=keep_on_error,
                ignore_cleanup_errors=ignore_cleanup_errors,
            )
            return func_or_cls

        if inspect.iscoroutinefunction(func_or_cls):

            @functools.wraps(func_or_cls)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                async with async_temp_dir(
                    suffix=suffix,
                    prefix=prefix,
                    dir=dir,
                    cwd=cwd,
                    keep=keep,
                    keep_on_error=keep_on_error,
                    ignore_cleanup_errors=ignore_cleanup_errors,
                ) as tmp:
                    return await func_or_cls(tmp, *args, **kwargs)

            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(func_or_cls)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            with sync_temp_dir(
                suffix=suffix,
                prefix=prefix,
                dir=dir,
                cwd=cwd,
                keep=keep,
                keep_on_error=keep_on_error,
                ignore_cleanup_errors=ignore_cleanup_errors,
            ) as tmp:
                return func_or_cls(tmp, *args, **kwargs)

        return sync_wrapper  # type: ignore[return-value]

    return decorator


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
) -> Callable[[F], F]:
    """Decorator that injects a temp file as the first positional argument.

    Works on sync and async **plain functions**. The temp file object is
    injected as the very first positional argument, before any user-supplied
    arguments. This decorator does **not** support methods or classes — use
    it on module-level functions whose signature begins with the temp file
    parameter.

    Args:
        suffix: File name suffix.
        prefix: File name prefix.
        dir: Parent directory. Defaults to system temp dir.
        mode: Open mode. Defaults to ``"w+b"``.
        content: Pre-populate file with this content.
        dest: Destination path. On success, temp is moved here.
        keep: If ``True``, file is NOT deleted.
        keep_on_error: If ``True``, file is kept only on exception.
        ignore_cleanup_errors: If ``True``, ``OSError`` during cleanup is silently ignored.
    """

    def decorator(func: F) -> F:
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                async with async_temp_file(
                    suffix=suffix,
                    prefix=prefix,
                    dir=dir,
                    mode=mode,
                    content=content,
                    dest=dest,
                    keep=keep,
                    keep_on_error=keep_on_error,
                    ignore_cleanup_errors=ignore_cleanup_errors,
                ) as f:
                    return await func(f, *args, **kwargs)

            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            with sync_temp_file(
                suffix=suffix,
                prefix=prefix,
                dir=dir,
                mode=mode,
                content=content,
                dest=dest,
                keep=keep,
                keep_on_error=keep_on_error,
                ignore_cleanup_errors=ignore_cleanup_errors,
            ) as f:
                return func(f, *args, **kwargs)

        return sync_wrapper  # type: ignore[return-value]

    return decorator


def _decorate_class(
    cls: type,
    *,
    suffix: str | None,
    prefix: str | None,
    dir: StrPath | None,
    cwd: bool,
    keep: bool,
    keep_on_error: bool,
    ignore_cleanup_errors: bool,
) -> None:
    """Decorate a test class so each test method gets a fresh temp dir.

    The temp dir path is available as ``self.tmpdir`` during the test.
    Each method starting with ``test_`` is wrapped to enter/exit a temp dir
    context around the original call.
    """
    for name, method in list(vars(cls).items()):
        if not name.startswith("test_"):
            continue
        if not callable(method):
            continue

        if inspect.iscoroutinefunction(method):
            wrapped = _wrap_async_test_method(
                method,
                suffix=suffix,
                prefix=prefix,
                dir=dir,
                cwd=cwd,
                keep=keep,
                keep_on_error=keep_on_error,
                ignore_cleanup_errors=ignore_cleanup_errors,
            )
        else:
            wrapped = _wrap_sync_test_method(
                method,
                suffix=suffix,
                prefix=prefix,
                dir=dir,
                cwd=cwd,
                keep=keep,
                keep_on_error=keep_on_error,
                ignore_cleanup_errors=ignore_cleanup_errors,
            )
        setattr(cls, name, wrapped)


def _wrap_sync_test_method(
    method: Callable[..., Any],
    *,
    suffix: str | None,
    prefix: str | None,
    dir: StrPath | None,
    cwd: bool,
    keep: bool,
    keep_on_error: bool,
    ignore_cleanup_errors: bool,
) -> Callable[..., Any]:
    @functools.wraps(method)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        with sync_temp_dir(
            suffix=suffix,
            prefix=prefix,
            dir=dir,
            cwd=cwd,
            keep=keep,
            keep_on_error=keep_on_error,
            ignore_cleanup_errors=ignore_cleanup_errors,
        ) as tmp:
            self.tmpdir = tmp
            return method(self, *args, **kwargs)

    return wrapper


def _wrap_async_test_method(
    method: Callable[..., Any],
    *,
    suffix: str | None,
    prefix: str | None,
    dir: StrPath | None,
    cwd: bool,
    keep: bool,
    keep_on_error: bool,
    ignore_cleanup_errors: bool,
) -> Callable[..., Any]:
    @functools.wraps(method)
    async def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        async with async_temp_dir(
            suffix=suffix,
            prefix=prefix,
            dir=dir,
            cwd=cwd,
            keep=keep,
            keep_on_error=keep_on_error,
            ignore_cleanup_errors=ignore_cleanup_errors,
        ) as tmp:
            self.tmpdir = tmp
            return await method(self, *args, **kwargs)

    return wrapper
