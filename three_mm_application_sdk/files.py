"""Bounded private-file helper for reviewed native applications, not a sandbox.

The host supplies the existing installation's data directory. Callers use logical
IDs, never paths. This does not mint a grant or protect against code bypassing the
SDK; production identity/mount isolation remains the runtime's responsibility.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import stat
from typing import Iterator, Literal
import uuid

try:
    import fcntl
except ImportError:  # No unsafe filesystem fallback on a non-POSIX host.
    fcntl = None


FILE_ID = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")


class ApplicationFileStorageError(RuntimeError):
    """Bounded refusal, conflict or uncertain local write; contains no host path."""


@dataclass(frozen=True, slots=True)
class ApplicationFileLimits:
    """SDK safety bounds, not package-authored approval or an OS disk quota."""

    max_file_bytes: int = 1024 * 1024
    max_total_bytes: int = 16 * 1024 * 1024
    max_files: int = 256

    def __post_init__(self) -> None:
        for value, ceiling in (
            (self.max_file_bytes, 16 * 1024 * 1024),
            (self.max_total_bytes, 64 * 1024 * 1024),
            (self.max_files, 1024),
        ):
            if type(value) is not int or not 1 <= value <= ceiling:
                raise ValueError("Private file limits are invalid")
        if self.max_file_bytes > self.max_total_bytes:
            raise ValueError("Private file limits are inconsistent")


@dataclass(frozen=True, slots=True)
class ApplicationFile:
    file_id: str
    content: bytes
    sha256: str


@dataclass(frozen=True, slots=True)
class ApplicationFileStorage:
    """Additive SDK 1.3 API over data/sdk-files; old DB/outbox are untouched.

    Mutation requires an explicit expected digest (None means absent). Atomic
    replacement and process-wide advisory locks serialize cooperating SDK users.
    On an uncertain write, read/compare before deciding to retry; no auto replay.
    """

    data_dir: Path
    mode: Literal["read", "read_write"] = "read_write"
    limits: ApplicationFileLimits = ApplicationFileLimits()

    def __post_init__(self) -> None:
        if not isinstance(self.data_dir, Path):
            raise ValueError("Private file storage requires a host-supplied directory")
        if not isinstance(self.mode, str) or self.mode not in {"read", "read_write"}:
            raise ValueError("Private file storage mode is invalid")
        if type(self.limits) is not ApplicationFileLimits:
            raise ValueError("Private file limits are invalid")

    @staticmethod
    def _identity(file_id: str) -> str:
        if not isinstance(file_id, str) or not FILE_ID.fullmatch(file_id):
            raise ValueError("Private file identity is invalid")
        return "blob_" + file_id

    @staticmethod
    def _expected(value: str | None) -> None:
        if value is not None and (
            not isinstance(value, str) or not DIGEST.fullmatch(value)
        ):
            raise ValueError("Private file expected digest is invalid")

    @staticmethod
    def _regular(fd: int) -> os.stat_result:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ApplicationFileStorageError(
                "Private file is not a singly owned regular file"
            )
        return info

    @staticmethod
    def _supported() -> None:
        if (
            fcntl is None
            or not hasattr(os, "O_NOFOLLOW")
            or not hasattr(os, "O_DIRECTORY")
            or os.open not in os.supports_dir_fd
            or os.rename not in os.supports_dir_fd
            or os.scandir not in os.supports_fd
        ):
            raise ApplicationFileStorageError(
                "Private files require the supported POSIX runtime"
            )

    def _open_data(self) -> int:
        # Walk without resolving symlinks, including ancestors. Each open is
        # relative to a pinned directory descriptor, not a checked-then-used path.
        path = self.data_dir.absolute()
        if ".." in path.parts:
            raise ApplicationFileStorageError("Private data directory is invalid")
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        fd = os.open(path.anchor, flags)
        try:
            for component in path.parts[1:]:
                child = os.open(component, flags, dir_fd=fd)
                os.close(fd)
                fd = child
            return fd
        except BaseException:
            os.close(fd)
            raise

    @contextmanager
    def _locked(self, *, write: bool) -> Iterator[int | None]:
        if write and self.mode != "read_write":
            raise ApplicationFileStorageError("Private file storage is read-only")
        self._supported()
        data_fd = namespace_fd = lock_fd = None
        try:
            data_fd = self._open_data()
            if write:
                try:
                    os.mkdir("sdk-files", mode=0o700, dir_fd=data_fd)
                    os.fsync(data_fd)
                except FileExistsError:
                    pass
            try:
                namespace_fd = os.open(
                    "sdk-files",
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                    dir_fd=data_fd,
                )
            except FileNotFoundError:
                if write:
                    raise
                yield None
                return
            flags = os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
            flags |= (os.O_RDWR | os.O_CREAT) if write else os.O_RDONLY
            lock_fd = os.open(".lock", flags, 0o600, dir_fd=namespace_fd)
            self._regular(lock_fd)
            try:
                fcntl.flock(
                    lock_fd, (fcntl.LOCK_EX if write else fcntl.LOCK_SH) | fcntl.LOCK_NB
                )
            except BlockingIOError as exc:
                raise ApplicationFileStorageError(
                    "Private file storage is busy"
                ) from exc
            # Detect a detached/replaced namespace or lock before using it.
            for parent, name, fd in (
                (data_fd, "sdk-files", namespace_fd),
                (namespace_fd, ".lock", lock_fd),
            ):
                named = os.stat(name, dir_fd=parent, follow_symlinks=False)
                opened = os.fstat(fd)
                if (named.st_dev, named.st_ino) != (opened.st_dev, opened.st_ino):
                    raise ApplicationFileStorageError("Private file namespace changed")
            yield namespace_fd
        except OSError as exc:
            raise ApplicationFileStorageError(
                "Private file storage could not be accessed"
            ) from exc
        finally:
            for fd in (lock_fd, namespace_fd, data_fd):
                if fd is not None:
                    os.close(fd)

    def _read(self, directory: int, file_id: str) -> ApplicationFile | None:
        try:
            fd = os.open(
                self._identity(file_id),
                os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                dir_fd=directory,
            )
        except FileNotFoundError:
            return None
        with os.fdopen(fd, "rb") as stream:
            info = self._regular(stream.fileno())
            if info.st_size > self.limits.max_file_bytes:
                raise ApplicationFileStorageError("Private file size limit exceeded")
            content = stream.read(self.limits.max_file_bytes + 1)
            if (
                len(content) > self.limits.max_file_bytes
                or len(content) != info.st_size
            ):
                raise ApplicationFileStorageError(
                    "Private file size changed or exceeded its limit"
                )
        return ApplicationFile(file_id, content, hashlib.sha256(content).hexdigest())

    def _entries(self, directory: int) -> list[tuple[str, int]]:
        entries = []
        with os.scandir(directory) as scan:
            for entry in scan:
                if entry.name == ".lock":
                    continue
                if not entry.name.startswith("blob_") or not FILE_ID.fullmatch(
                    entry.name[5:]
                ):
                    raise ApplicationFileStorageError(
                        "Private file namespace requires recovery review"
                    )
                info = entry.stat(follow_symlinks=False)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise ApplicationFileStorageError(
                        "Private file is not a singly owned regular file"
                    )
                if info.st_size > self.limits.max_file_bytes:
                    raise ApplicationFileStorageError(
                        "Private file size limit exceeded"
                    )
                entries.append((entry.name[5:], info.st_size))
                if len(entries) > self.limits.max_files:
                    raise ApplicationFileStorageError(
                        "Private file count limit exceeded"
                    )
        if sum(size for _, size in entries) > self.limits.max_total_bytes:
            raise ApplicationFileStorageError("Private file total size limit exceeded")
        return sorted(entries)

    def get(self, file_id: str) -> ApplicationFile | None:
        self._identity(file_id)
        with self._locked(write=False) as directory:
            return None if directory is None else self._read(directory, file_id)

    def list_entries(self) -> list[tuple[str, int]]:
        """Sorted logical IDs/sizes only; no paths, global scan or pagination drift."""
        with self._locked(write=False) as directory:
            return [] if directory is None else self._entries(directory)

    def put(
        self, file_id: str, content: bytes, *, expected_sha256: str | None
    ) -> ApplicationFile:
        self._identity(file_id)
        self._expected(expected_sha256)
        if type(content) is not bytes:
            raise ValueError("Private file content must be bytes")
        if len(content) > self.limits.max_file_bytes:
            raise ApplicationFileStorageError("Private file size limit exceeded")
        with self._locked(write=True) as directory:
            assert directory is not None
            entries = self._entries(directory)
            current = self._read(directory, file_id)
            if (current.sha256 if current else None) != expected_sha256:
                raise ApplicationFileStorageError("Private file revision conflict")
            sizes = dict(entries)
            total = sum(sizes.values()) - sizes.get(file_id, 0) + len(content)
            if len(entries) + (current is None) > self.limits.max_files:
                raise ApplicationFileStorageError("Private file count limit exceeded")
            if total > self.limits.max_total_bytes:
                raise ApplicationFileStorageError(
                    "Private file total size limit exceeded"
                )
            temporary = ".pending_" + uuid.uuid4().hex
            try:
                fd = os.open(
                    temporary,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                    0o600,
                    dir_fd=directory,
                )
                with os.fdopen(fd, "wb") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.rename(
                    temporary,
                    self._identity(file_id),
                    src_dir_fd=directory,
                    dst_dir_fd=directory,
                )
                os.fsync(directory)
            finally:
                try:
                    os.unlink(temporary, dir_fd=directory)
                except FileNotFoundError:
                    pass
            return ApplicationFile(
                file_id, content, hashlib.sha256(content).hexdigest()
            )

    def delete(self, file_id: str, *, expected_sha256: str) -> None:
        self._identity(file_id)
        self._expected(expected_sha256)
        if expected_sha256 is None:
            raise ValueError("Private file deletion requires an expected digest")
        with self._locked(write=True) as directory:
            assert directory is not None
            self._entries(directory)
            current = self._read(directory, file_id)
            if current is None or current.sha256 != expected_sha256:
                raise ApplicationFileStorageError("Private file revision conflict")
            os.unlink(self._identity(file_id), dir_fd=directory)
            os.fsync(directory)
