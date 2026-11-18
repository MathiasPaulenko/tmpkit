"""Decorators: @temp_dir() and @temp_file() for functions and test classes."""

from __future__ import annotations

import functools
import inspect
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path
from typing import Any, TypeVar

from tmpkit._async import temp_dir as async_temp_dir
from tmpkit._async import temp_file as async_temp_file
from tmpkit._sync import temp_dir as sync_temp_dir
from tmpkit._sync import temp_file as sync_temp_file
from tmpkit._types import StrPath

F = TypeVar("F", bound=Callable[..., Any])

# Set on every wrapper we produce so re-decoration never double-wraps:
# classes skip already-wrapped methods (inherited methods legitimately
# carry it), while re-decorating a *function* is always a bug — the temp
# argument would be injected twice.
_WRAPPED_ATTR = "__tmpkit_wrapped__"


def _mark_wrapped(func: F) -> F:
    setattr(func, _WRAPPED_ATTR, True)
    return func


def temp_dir(
    *,
    suffix: str | None = None,
    prefix: str | None = None,
    dir: StrPath | None = None,
    cwd: bool = True,
    keep: bool = False,
    keep_on_error: bool = False,
    ignore_cleanup_errors: bool = True,
    cleanup_hook: Callable[[Path], None] | None = None,
) -> Callable[[F], F]:
    """Decorator that provides a fresh temp directory for each call.

    By default ``cwd=True`` — the function runs inside the temp dir and
    the original cwd is restored on exit. Warning: ``os.chdir`` is
    process-global — do not use ``cwd=True`` from multiple threads or
    concurrent async tasks.

    Works on:
    - Sync functions: wrapped normally. The temp dir path is injected
      as the first positional argument.
    - Async functions: detected via ``inspect.iscoroutinefunction``.
    - Generators / async generators: the temp dir stays alive while the
      generator is being consumed (cleaned on exhaustion or ``close()``).
    - Test classes: each ``test_*`` method — including inherited ones —
      gets a fresh temp dir as ``self.tmpdir``.

    Only plain module-level functions are supported — decorating a method
    injects the temp path in place of ``self``. For classes, decorate the
    class itself instead.

    Args:
        suffix: Directory name suffix.
        prefix: Directory name prefix.
        dir: Parent directory. Defaults to system temp dir.
        cwd: If ``True``, changes working directory to temp dir. Defaults to ``True``.
        keep: If ``True``, directory is NOT removed.
        keep_on_error: If ``True``, directory is kept only on exception.
        ignore_cleanup_errors: If ``True``, ``OSError`` during cleanup is silently ignored.
        cleanup_hook: Optional callable invoked with the temp path before cleanup.
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
                cleanup_hook=cleanup_hook,
            )
            return func_or_cls

        if getattr(func_or_cls, _WRAPPED_ATTR, False):
            raise TypeError(
                "function is already wrapped by a tmpkit decorator — "
                "double decoration would inject the temp argument twice"
            )

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
                    cleanup_hook=cleanup_hook,
                ) as tmp:
                    return await func_or_cls(tmp, *args, **kwargs)

            return _mark_wrapped(async_wrapper)  # type: ignore[return-value]

        if inspect.isasyncgenfunction(func_or_cls):

            @functools.wraps(func_or_cls)
            async def async_gen_wrapper(
                *args: Any, **kwargs: Any
            ) -> AsyncIterator[Any]:
                async with async_temp_dir(
                    suffix=suffix,
                    prefix=prefix,
                    dir=dir,
                    cwd=cwd,
                    keep=keep,
                    keep_on_error=keep_on_error,
                    ignore_cleanup_errors=ignore_cleanup_errors,
                    cleanup_hook=cleanup_hook,
                ) as tmp:
                    # aclose() the inner generator in finally: plain
                    # async-for does not delegate outer.aclose()/athrow()
                    # — without this the inner generator's cleanup only
                    # runs via the nondeterministic asyncgen finalizer.
                    inner = func_or_cls(tmp, *args, **kwargs)
                    try:
                        async for item in inner:
                            yield item
                    finally:
                        await inner.aclose()

            return _mark_wrapped(async_gen_wrapper)  # type: ignore[return-value]

        if inspect.isgeneratorfunction(func_or_cls):

            @functools.wraps(func_or_cls)
            def gen_wrapper(*args: Any, **kwargs: Any) -> Iterator[Any]:
                # The temp must outlive iteration: yield inside the context
                # so cleanup happens when the generator is exhausted, closed
                # or garbage-collected — not when it is first called.
                with sync_temp_dir(
                    suffix=suffix,
                    prefix=prefix,
                    dir=dir,
                    cwd=cwd,
                    keep=keep,
                    keep_on_error=keep_on_error,
                    ignore_cleanup_errors=ignore_cleanup_errors,
                    cleanup_hook=cleanup_hook,
                ) as tmp:
                    result = yield from func_or_cls(tmp, *args, **kwargs)
                    return result  # type: ignore[no-any-return]

            return _mark_wrapped(gen_wrapper)  # type: ignore[return-value]

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
                cleanup_hook=cleanup_hook,
            ) as tmp:
                return func_or_cls(tmp, *args, **kwargs)

        return _mark_wrapped(sync_wrapper)  # type: ignore[return-value]

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
    cleanup_hook: Callable[[Path], None] | None = None,
) -> Callable[[F], F]:
    """Decorator that injects a temp file as the first positional argument.

    Works on sync and async **plain functions**, including generators and
    async generators (the temp file stays alive while the generator is
    consumed). The temp file object is
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
        cleanup_hook: Optional callable invoked with the temp path before cleanup.
    """

    def decorator(func: F) -> F:
        if inspect.isclass(func):
            raise TypeError(
                "@temp_file() does not support classes — use @temp_dir() "
                "for test classes or decorate a plain function."
            )

        if getattr(func, _WRAPPED_ATTR, False):
            raise TypeError(
                "function is already wrapped by a tmpkit decorator — "
                "double decoration would inject the temp argument twice"
            )

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
                    cleanup_hook=cleanup_hook,
                ) as f:
                    return await func(f, *args, **kwargs)

            return _mark_wrapped(async_wrapper)  # type: ignore[return-value]

        if inspect.isasyncgenfunction(func):

            @functools.wraps(func)
            async def async_gen_wrapper(
                *args: Any, **kwargs: Any
            ) -> AsyncIterator[Any]:
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
                    cleanup_hook=cleanup_hook,
                ) as f:
                    # Same as temp_dir: inner.aclose() in finally so the
                    # decorated generator's cleanup runs deterministically.
                    inner = func(f, *args, **kwargs)
                    try:
                        async for item in inner:
                            yield item
                    finally:
                        await inner.aclose()

            return _mark_wrapped(async_gen_wrapper)  # type: ignore[return-value]

        if inspect.isgeneratorfunction(func):

            @functools.wraps(func)
            def gen_wrapper(*args: Any, **kwargs: Any) -> Iterator[Any]:
                # Same as temp_dir: the temp must stay alive while the
                # generator is being consumed.
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
                    cleanup_hook=cleanup_hook,
                ) as f:
                    result = yield from func(f, *args, **kwargs)
                    return result  # type: ignore[no-any-return]

            return _mark_wrapped(gen_wrapper)  # type: ignore[return-value]

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
                cleanup_hook=cleanup_hook,
            ) as f:
                return func(f, *args, **kwargs)

        return _mark_wrapped(sync_wrapper)  # type: ignore[return-value]

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
    cleanup_hook: Callable[[Path], None] | None,
) -> None:
    """Decorate a test class so each test method gets a fresh temp dir.

    The temp dir path is available as ``self.tmpdir`` during the test.
    Each plain method starting with ``test_`` is wrapped to enter/exit a
    temp dir context around the original call — including methods
    inherited from base classes. ``staticmethod`` and ``classmethod``
    members are skipped — they have no ``self``.
    """
    # Resolve the effective attribute for every test_* name across the MRO
    # (base classes first so derived overrides win), then wrap the raw
    # functions. Checking vars() keeps staticmethod/classmethod descriptors
    # from being unwrapped by getattr() and misdetected as plain functions.
    members: dict[str, Any] = {}
    for klass in reversed(cls.__mro__):
        for name, member in vars(klass).items():
            if name.startswith("test_"):
                members[name] = member

    for name, method in members.items():
        if not inspect.isfunction(method):
            continue
        if getattr(method, _WRAPPED_ATTR, False):
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
                cleanup_hook=cleanup_hook,
            )
        elif inspect.isasyncgenfunction(method):
            wrapped = _wrap_asyncgen_test_method(
                method,
                suffix=suffix,
                prefix=prefix,
                dir=dir,
                cwd=cwd,
                keep=keep,
                keep_on_error=keep_on_error,
                ignore_cleanup_errors=ignore_cleanup_errors,
                cleanup_hook=cleanup_hook,
            )
        elif inspect.isgeneratorfunction(method):
            wrapped = _wrap_gen_test_method(
                method,
                suffix=suffix,
                prefix=prefix,
                dir=dir,
                cwd=cwd,
                keep=keep,
                keep_on_error=keep_on_error,
                ignore_cleanup_errors=ignore_cleanup_errors,
                cleanup_hook=cleanup_hook,
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
                cleanup_hook=cleanup_hook,
            )
        setattr(wrapped, _WRAPPED_ATTR, True)
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
    cleanup_hook: Callable[[Path], None] | None,
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
            cleanup_hook=cleanup_hook,
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
    cleanup_hook: Callable[[Path], None] | None,
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
            cleanup_hook=cleanup_hook,
        ) as tmp:
            self.tmpdir = tmp
            return await method(self, *args, **kwargs)

    return wrapper


def _wrap_gen_test_method(
    method: Callable[..., Any],
    *,
    suffix: str | None,
    prefix: str | None,
    dir: StrPath | None,
    cwd: bool,
    keep: bool,
    keep_on_error: bool,
    ignore_cleanup_errors: bool,
    cleanup_hook: Callable[[Path], None] | None,
) -> Callable[..., Any]:
    @functools.wraps(method)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Iterator[Any]:
        # Same lifecycle as the module-level generator wrapper: the temp
        # stays alive for the whole iteration, not just the call.
        with sync_temp_dir(
            suffix=suffix,
            prefix=prefix,
            dir=dir,
            cwd=cwd,
            keep=keep,
            keep_on_error=keep_on_error,
            ignore_cleanup_errors=ignore_cleanup_errors,
            cleanup_hook=cleanup_hook,
        ) as tmp:
            self.tmpdir = tmp
            result = yield from method(self, *args, **kwargs)
            return result  # type: ignore[no-any-return]

    return wrapper


def _wrap_asyncgen_test_method(
    method: Callable[..., Any],
    *,
    suffix: str | None,
    prefix: str | None,
    dir: StrPath | None,
    cwd: bool,
    keep: bool,
    keep_on_error: bool,
    ignore_cleanup_errors: bool,
    cleanup_hook: Callable[[Path], None] | None,
) -> Callable[..., Any]:
    @functools.wraps(method)
    async def wrapper(self: Any, *args: Any, **kwargs: Any) -> AsyncIterator[Any]:
        async with async_temp_dir(
            suffix=suffix,
            prefix=prefix,
            dir=dir,
            cwd=cwd,
            keep=keep,
            keep_on_error=keep_on_error,
            ignore_cleanup_errors=ignore_cleanup_errors,
            cleanup_hook=cleanup_hook,
        ) as tmp:
            self.tmpdir = tmp
            inner = method(self, *args, **kwargs)
            try:
                async for item in inner:
                    yield item
            finally:
                await inner.aclose()

    return wrapper
