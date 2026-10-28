"""Quiescent CAP11 preimages, bounded streaming copy and staged rollback.

The enclosing lifecycle owns the 0700 rollback directory. Candidate bytes are
detached as evidence before the validated preimage is installed. No data reset.
"""
import hashlib
import json
import os
from pathlib import Path
import re
from contextlib import nullcontext

from three_mm_application_sdk.files import ApplicationFileStorage, ApplicationFileStorageError
from three_mm_application_sdk.media_store import _Namespace, INDEX_LIMIT
from three_mm_application_sdk.media_wire import CHUNK_BYTES

NAME = re.compile(r'^(?:\.lock|index\.json|(?:part|blob|idx)_[0-9a-f]{32})$')
MAX_BYTES = 9 * 1024**3


def _copy(source_fd, destination, expected=None):
    fd = None if destination is None else os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    size, digest = 0, hashlib.sha256()
    with os.fdopen(source_fd, 'rb') as source, (nullcontext(None) if fd is None else os.fdopen(fd, 'wb')) as target:
        info = ApplicationFileStorage._regular(source.fileno())
        if info.st_size > 1024**3 + CHUNK_BYTES:
            raise ApplicationFileStorageError('Media snapshot exceeds its bound')
        while chunk := source.read(CHUNK_BYTES):
            size += len(chunk)
            if size > info.st_size:
                raise ApplicationFileStorageError('Media snapshot changed')
            digest.update(chunk)
            if target is not None:
                target.write(chunk)
        if target is not None:
            target.flush()
            os.fsync(target.fileno())
    value = {'size_bytes': size, 'sha256': digest.hexdigest()}
    if size != info.st_size or expected is not None and value != expected:
        raise ApplicationFileStorageError('Media snapshot changed')
    return value


def _sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def capture_media(data_root, rollback_root):
    manifest = {'version': 1, 'present': False, 'entries': {}}
    with _Namespace(data_root)._locked(write=False) as directory:
        if directory is not None:
            destination = rollback_root / 'sdk-media'
            destination.mkdir(mode=0o700)
            total = 0
            for entry in sorted(os.scandir(directory), key=lambda item: item.name):
                if not NAME.fullmatch(entry.name) or len(manifest['entries']) >= 8192:
                    raise ApplicationFileStorageError('Media snapshot requires review')
                fd = os.open(entry.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=directory)
                item = _copy(fd, destination / entry.name)
                total += item['size_bytes']
                if total > MAX_BYTES:
                    raise ApplicationFileStorageError('Media snapshot exceeds its bound')
                manifest['entries'][entry.name] = item
            manifest['present'] = True
            _sync(destination)
    fd = os.open(rollback_root / 'media.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode())
        stream.flush()
        os.fsync(stream.fileno())
    _sync(rollback_root)


def stage_media(rollback_root, service_uid, service_gid, *, verify_only=False):
    fd = os.open(rollback_root / 'media.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = ApplicationFileStorage._regular(stream.fileno())
        if info.st_size > INDEX_LIMIT:
            raise ApplicationFileStorageError('Media snapshot manifest exceeds its bound')
        manifest = json.loads(stream.read(INDEX_LIMIT + 1))
    if (type(manifest) is not dict or set(manifest) != {'version', 'present', 'entries'} or type(manifest['version']) is not int or manifest['version'] != 1
            or type(manifest['present']) is not bool or type(manifest['entries']) is not dict or len(manifest['entries']) > 8192
            or not manifest['present'] and manifest['entries']):
        raise ApplicationFileStorageError('Media snapshot manifest is invalid')
    source = _Namespace(rollback_root)
    with source._locked(write=False) as directory:
        if manifest['present'] != (directory is not None):
            raise ApplicationFileStorageError('Media snapshot is incomplete')
        if directory is None:
            return False
        if set(os.listdir(directory)) != set(manifest['entries']):
            raise ApplicationFileStorageError('Media snapshot entries changed')
        stage = rollback_root / 'restored-sdk-media'
        if not verify_only:
            stage.mkdir(mode=0o700)
        total = 0
        for name, value in manifest['entries'].items():
            if (not NAME.fullmatch(name) or type(value) is not dict or set(value) != {'size_bytes', 'sha256'}
                    or type(value['size_bytes']) is not int or not 0 <= value['size_bytes'] <= 1024**3 + CHUNK_BYTES
                    or type(value['sha256']) is not str or not re.fullmatch(r'[0-9a-f]{64}', value['sha256'])):
                raise ApplicationFileStorageError('Media snapshot entry is invalid')
            total += value['size_bytes']
            if total > MAX_BYTES:
                raise ApplicationFileStorageError('Media snapshot exceeds its bound')
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=directory)
            _copy(fd, None if verify_only else stage / name, value)
            if not verify_only and service_uid is not None and service_gid is not None:
                os.chown(stage / name, service_uid, service_gid, follow_symlinks=False)
        if not verify_only and service_uid is not None and service_gid is not None:
            os.chown(stage, service_uid, service_gid, follow_symlinks=False)
        if not verify_only:
            _sync(stage)
    return True


def switch_media(data_root, rollback_root, present):
    data = ApplicationFileStorage(data_root)._open_data()
    backup = ApplicationFileStorage(rollback_root)._open_data()
    try:
        try:
            os.stat('candidate-sdk-media', dir_fd=backup, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise ApplicationFileStorageError('Media restore requires review')
        try:
            os.rename('sdk-media', 'candidate-sdk-media', src_dir_fd=data, dst_dir_fd=backup)
        except FileNotFoundError:
            pass
        os.fsync(data)
        os.fsync(backup)
        if present:
            os.rename('restored-sdk-media', 'sdk-media', src_dir_fd=backup, dst_dir_fd=data)
            os.fsync(data)
            os.fsync(backup)
    finally:
        os.close(data)
        os.close(backup)
