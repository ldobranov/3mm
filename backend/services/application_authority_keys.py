"""Private M20 configuration identities and authenticated coordinator records.

Explicit local administration only; no startup hook, key route or SDK export. The
POSIX store is Core-owned and separate from transport/signing/encryption keys.
Read/fingerprint never creates or repairs state. A recovered DB generation makes
an old key unavailable even if its private file was copied back with the DB.
"""

import base64
from contextlib import contextmanager
from dataclasses import dataclass, field
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import stat

from sqlalchemy.exc import SQLAlchemyError

from backend.services.application_authority_context import (
    AuthorityPrincipal, ConfigurationIdentity, _canonical_bytes, _parse,
)
from backend.services.application_authority_sources import _core_identity, _read_snapshot
from backend.services.authority_metadata import read_authority_guard


KEY_NAME = "configuration-key.json"
LOCK_NAME = "configuration-key.lock"
KEY_PURPOSE = "3mm:m20:configuration-key:v1"
CONFIGURATION_DOMAIN = b"3mm:m20:private-configuration:v1\x00"
MAX_KEY_BYTES = 1024


class AuthorityReviewKeyError(ValueError):
    def __init__(self):
        super().__init__("Authority review key is unavailable or stale")


@dataclass(frozen=True)
class ReviewKeyBinding:
    core_installation_id: str
    recovery_generation: str


@dataclass(frozen=True)
class ReviewKeyIdentity:
    key_id: str
    binding: ReviewKeyBinding


@dataclass(frozen=True)
class _KeyRecord:
    identity: ReviewKeyIdentity
    secret: bytes = field(repr=False)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AuthorityReviewKeyError()
        result[key] = value
    return result


def _decode(data):
    try:
        if not data or len(data) > MAX_KEY_BYTES:
            raise AuthorityReviewKeyError()
        value = json.loads(data, object_pairs_hook=_unique_object)
        if type(value) is not dict or set(value) != {
            "version", "purpose", "key_id", "core_installation_id",
            "recovery_generation", "secret",
        }:
            raise AuthorityReviewKeyError()
        if type(value["version"]) is not int or value["version"] != 1 or value["purpose"] != KEY_PURPOSE:
            raise AuthorityReviewKeyError()
        for key, pattern in (
            ("key_id", r"review_[0-9a-f]{32}"),
            ("core_installation_id", r"inst_[0-9a-f]{32}"),
            ("recovery_generation", r"[0-9a-f]{32}"),
        ):
            if type(value[key]) is not str or re.fullmatch(pattern, value[key]) is None:
                raise AuthorityReviewKeyError()
        if type(value["secret"]) is not str:
            raise AuthorityReviewKeyError()
        secret = base64.b64decode(value["secret"], validate=True)
        if len(secret) != 32 or base64.b64encode(secret).decode("ascii") != value["secret"]:
            raise AuthorityReviewKeyError()
        return _KeyRecord(ReviewKeyIdentity(value["key_id"], ReviewKeyBinding(
            value["core_installation_id"], value["recovery_generation"],
        )), secret)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise AuthorityReviewKeyError() from None


def _encode(record):
    return json.dumps({
        "version": 1, "purpose": KEY_PURPOSE, "key_id": record.identity.key_id,
        "core_installation_id": record.identity.binding.core_installation_id,
        "recovery_generation": record.identity.binding.recovery_generation,
        "secret": base64.b64encode(record.secret).decode("ascii"),
    }, sort_keys=True, separators=(",", ":")).encode("ascii")


def _new_record(binding):
    return _KeyRecord(ReviewKeyIdentity("review_" + secrets.token_hex(16), binding), secrets.token_bytes(32))


def _configuration_identity(record, principal, configuration):
    """Bounded purpose-separated HMAC over FULL trusted resolved configuration.

    This does not validate a package schema or prove that inputs are authoritative.
    Only a future Core resolver may supply them; never expose a client HMAC oracle.
    """
    try:
        principal = _parse(AuthorityPrincipal, principal)
        if (principal.core_installation_id != record.identity.binding.core_installation_id
                or type(configuration) is not dict):
            raise AuthorityReviewKeyError()
        encoded = _canonical_bytes({
            "principal": principal.model_dump(mode="json"),
            "configuration": configuration,
            "key_id": record.identity.key_id,
            "recovery_generation": record.identity.binding.recovery_generation,
        })
        return ConfigurationIdentity(key_id=record.identity.key_id, keyed_sha256=hmac.new(
            record.secret, CONFIGURATION_DOMAIN + encoded, hashlib.sha256,
        ).hexdigest())
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise AuthorityReviewKeyError() from None


def _file_info(descriptor):
    info = os.fstat(descriptor)
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600):
        raise AuthorityReviewKeyError()
    return info


@contextmanager
def _private_directory(path, *, create=False):
    """Anchor each component with dirfd + NOFOLLOW; never chmod existing paths.

    Ancestors must be root/Core-owned and not group/world-writable, except a
    root-owned sticky directory (e.g. /tmp for disposable tests). The final
    dedicated directory must be owned by the effective Core UID with mode 0700.
    Only explicit first provisioning may create that final component.
    """
    if (os.name != "posix" or not hasattr(os, "O_NOFOLLOW")
            or not path.is_absolute() or len(path.parts) < 3
            or any(part in {".", ".."} for part in path.parts)):
        raise AuthorityReviewKeyError()
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for index, part in enumerate(path.parts[1:]):
            final = index == len(path.parts) - 2
            if final and create:
                try:
                    os.mkdir(part, 0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                            dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
            info = os.fstat(descriptor)
            if final:
                safe = info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o700
            else:
                safe = info.st_uid in {0, os.geteuid()} and (
                    not info.st_mode & 0o022 or (info.st_uid == 0 and info.st_mode & stat.S_ISVTX)
                )
            if not safe:
                raise AuthorityReviewKeyError()
        yield descriptor
    finally:
        os.close(descriptor)


@contextmanager
def _key_lock(directory, *, create=False):
    import fcntl

    descriptor = os.open(LOCK_NAME, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
                         | (os.O_CREAT if create else 0), 0o600, dir_fd=directory)
    try:
        info = _file_info(descriptor)
        if info.st_size != 0:
            raise AuthorityReviewKeyError()
        # Bounded admission: busy is unavailable, not an unbounded server wait.
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(descriptor)  # Also releases flock, including on failed admission.


def _read_record(directory):
    descriptor = os.open(KEY_NAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                         dir_fd=directory)
    with os.fdopen(descriptor, "rb") as stream:
        info = _file_info(stream.fileno())
        if info.st_size > MAX_KEY_BYTES:
            raise AuthorityReviewKeyError()
        return _decode(stream.read(MAX_KEY_BYTES + 1))


def _write_record(directory, record):
    temporary = ".configuration-key-" + secrets.token_hex(16)
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                         0o600, dir_fd=directory)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(_encode(record))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, KEY_NAME, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    finally:
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass


class CoreReviewKeyStore:
    """Internal Linux/POSIX adapter; no implicit provisioning.

    Directory is trusted Core configuration, NOT a request/package path. Normal
    deployment location: /var/lib/3mm/core/authority-review (not public uploads).
    Must run as the Core UID; root and application UIDs are not interchangeable.
    The local admin CLI coordinates/audits explicit creation/rotation/recovery;
    approval/apply/effect admission revalidate the current key under a lease.
    A key seal alone is not a grant or an OS/browser isolation proof.
    """

    def __init__(self, engine, directory: Path):
        self._engine = engine
        self._directory = Path(directory)

    def _binding(self):
        with _read_snapshot(self._engine) as db:
            guard = read_authority_guard(db)
            return ReviewKeyBinding(_core_identity(db), guard.generation)

    @contextmanager
    def _access(self, *, provision=False):
        try:
            with _private_directory(self._directory, create=provision) as directory:
                with _key_lock(directory, create=provision):
                    yield directory
        except (OSError, ValueError, TypeError, SQLAlchemyError, RuntimeError):
            raise AuthorityReviewKeyError() from None

    def provision(self) -> ReviewKeyIdentity:
        """Explicit first creation; exact retry returns the SAME existing key.

        Corrupt, foreign or recovery-stale files are never silently overwritten.
        Missing Core identity/guard blocks before any filesystem creation.
        """
        try:
            binding = self._binding()
            with self._access(provision=True) as directory:
                if self._binding() != binding:
                    raise AuthorityReviewKeyError()
                try:
                    record = _read_record(directory)
                except FileNotFoundError:
                    record = _new_record(binding)
                    _write_record(directory, record)
                if record.identity.binding != binding or self._binding() != binding:
                    raise AuthorityReviewKeyError()
                return record.identity
        except (OSError, ValueError, TypeError, SQLAlchemyError, RuntimeError):
            raise AuthorityReviewKeyError() from None

    def _change(self, expected_key_id, *, recovery):
        with self._access() as directory:
            binding = self._binding()
            old = _read_record(directory)
            if (type(expected_key_id) is not str or old.identity.key_id != expected_key_id
                    or (old.identity.binding != binding) != recovery):
                raise AuthorityReviewKeyError()
            record = _new_record(binding)
            _write_record(directory, record)
            if self._binding() != binding:
                # File/DB cannot share a transaction. Never undo the fresh key or
                # claim success; a concurrent recovery leaves it unusable.
                raise AuthorityReviewKeyError()
            return record.identity

    def rotate(self, *, expected_key_id: str) -> ReviewKeyIdentity:
        """Explicit CAS replacement of a currently bound key, never a stale retry."""
        return self._change(expected_key_id, recovery=False)

    def recover(self, *, expected_key_id: str) -> ReviewKeyIdentity:
        """Explicit replacement of a valid but foreign/recovery-stale record.

        Always fresh random ID/bytes; never import its old secret as current.
        Missing material needs explicit provision; malformed material stays denied
        for operator-led quarantine, not automatic deletion/repair here.
        """
        return self._change(expected_key_id, recovery=True)

    def identity(self) -> ReviewKeyIdentity:
        with self._access() as directory:
            binding = self._binding()
            record = _read_record(directory)
            if record.identity.binding != binding or self._binding() != binding:
                raise AuthorityReviewKeyError()
            return record.identity

    def fingerprint(self, principal, configuration) -> ConfigurationIdentity:
        """Private evidence only. Schema/source validation belongs to the resolver.

        No configuration or key bytes in the result, no durable grant/fingerprint
        cache, no promise of freshness after this call or across restore/apply.
        """
        with self._access() as directory:
            binding = self._binding()
            record = _read_record(directory)
            if record.identity.binding != binding:
                raise AuthorityReviewKeyError()
            result = _configuration_identity(record, principal, configuration)
            if self._binding() != binding:
                raise AuthorityReviewKeyError()
            return result

    def _fingerprint_in_snapshot(self, db, principal, configuration) -> ConfigurationIdentity:
        """Resolver-only composition in its existing dedicated read snapshot.

        Never open independent DB snapshots around a configuration/resource read.
        Key material is locked/checked by the same real POSIX adapter. The result
        remains historical read evidence: approval/apply must recheck this key ID
        and the DB guard, and no provisioning or rotation is performed here.
        """
        with self._access() as directory:
            if db.get_bind().engine is not self._engine or not db.in_transaction():
                raise AuthorityReviewKeyError()
            binding = ReviewKeyBinding(_core_identity(db), read_authority_guard(db).generation)
            record = _read_record(directory)
            if record.identity.binding != binding:
                raise AuthorityReviewKeyError()
            return _configuration_identity(record, principal, configuration)

    @contextmanager
    def locked(self):
        """Core coordinator: hold key before DB guard through durable admission.

        No key creation/rotation. The yielded adapter is invalid after exit and
        never exposes raw key material. No lock may span a helper/network call.
        """
        with self._access() as directory:
            adapter = _LockedKey(self._engine, _read_record(directory))
            try:
                yield adapter
            finally:
                adapter.active = False


class _LockedKey:
    def __init__(self, engine, record):
        self.engine, self._record, self.active = engine, record, True

    def _check(self, db):
        if (not self.active or db.get_bind().engine is not self.engine or not db.in_transaction()
                or self._record.identity.binding != ReviewKeyBinding(
                    _core_identity(db), read_authority_guard(db).generation)):
            raise AuthorityReviewKeyError()

    def _fingerprint_in_snapshot(self, db, principal, configuration):
        self._check(db)
        return _configuration_identity(self._record, principal, configuration)

    def seal(self, db, kind, payload):
        self._check(db)
        if kind not in {"native", "plan", "grant", "action"}:
            raise AuthorityReviewKeyError()
        key_id = self._record.identity.key_id
        digest = hmac.new(self._record.secret, b"3mm:m20:sealed-authority:v1\x00" +
            _canonical_bytes({"kind": kind, "key_id": key_id, "payload": payload}), hashlib.sha256).hexdigest()
        return key_id, digest

    def verify(self, db, kind, payload, key_id, digest):
        expected_id, expected = self.seal(db, kind, payload)
        if (type(digest) is not str or expected_id != key_id or not hmac.compare_digest(digest, expected)):
            raise AuthorityReviewKeyError()
