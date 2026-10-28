"""Reuse verified immutable code within one request, never authorization results.

Every reuse checks filesystem identity, including ctime and ownership. Changes
poison the entry rather than replacing the code halfway through an invocation.
The scope expires across both thread-pool phases when the request ends.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
import os
import stat
from threading import RLock


class CodeVerificationError(ValueError):
    pass


class _Scope:
    def __init__(self):
        self.active = True
        self.entries = {}
        self.lock = RLock()


_current = ContextVar('application_code_verification', default=None)


@contextmanager
def code_verification_scope():
    existing = _current.get()
    if existing is not None and existing.active:
        yield
        return
    scope = _Scope()
    token = _current.set(scope)
    try:
        yield
    finally:
        with scope.lock:
            scope.active = False
            scope.entries.clear()
        _current.reset(token)


def file_identity(path):
    value = Path(path).lstat()
    if not stat.S_ISREG(value.st_mode):
        raise CodeVerificationError('Code file is not regular')
    return stat_identity(value)


def stat_identity(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
        value.st_gid, value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def reuse_verified(key, fingerprint, load):
    scope = _current.get()
    if scope is None or not scope.active:
        return load()
    with scope.lock:
        if not scope.active:
            return load()
        try:
            before = fingerprint()
        except (OSError, ValueError):
            if key in scope.entries:
                scope.entries[key] = (None, None)
            raise
        if key in scope.entries:
            previous, value = scope.entries[key]
            if previous != before or value is None:
                scope.entries[key] = (before, None)
                raise CodeVerificationError('Code changed during invocation')
            return value
        value = load()
        if before != fingerprint():
            scope.entries[key] = (before, None)
            raise CodeVerificationError('Code changed during verification')
        # Bound retained descriptors, even for an unexpected recursive consumer.
        if len(scope.entries) < 8:
            scope.entries[key] = (before, value)
        return value


def load_verified_package(path, *, core_version=None):
    from backend.services.module_packages import (
        MAX_PACKAGE_BYTES, ModulePackageError, validate_module_package, actual_core_version,
    )

    path = Path(path).absolute()
    try:
        version = actual_core_version() if core_version is None else core_version
    except ValueError as exc:
        raise ModulePackageError('Core runtime version is unavailable or invalid') from exc
    def load():
        with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
                | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_BINARY', 0)), 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_PACKAGE_BYTES:
                raise ModulePackageError('Code file exceeds package bounds')
            return validate_module_package(stream.read(MAX_PACKAGE_BYTES + 1), core_version=version)
    try:
        return reuse_verified(('package', str(path), version), lambda: file_identity(path), load)
    except CodeVerificationError as exc:
        raise ModulePackageError(str(exc)) from exc
