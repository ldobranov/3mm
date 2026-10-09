"""Private configuration evidence only; no approval/isolated-runtime claim."""

import base64
import copy
from datetime import UTC, datetime
import hashlib
import hmac
import json
import multiprocessing
import os
from pathlib import Path
import secrets
import stat
import tempfile
import traceback

import backend.database  # noqa: F401 -- register the same full ORM metadata as Core
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import create_engine, event, update

from backend.db.authority import CoreAuthorityGuard
from backend.db.installation_identity import CoreInstallationIdentity
from backend.services import application_authority_keys as keys
from backend.services.application_authority_context import _canonical_bytes


CORE_ID = "inst_" + "1" * 32
GENERATION = "2" * 32
PRINCIPAL = {
    "core_installation_id": CORE_ID, "application_installation_id": "7",
    "incarnation": "3" * 32, "module_id": "org.example.reference",
}
posix_only = pytest.mark.skipif(os.name != "posix", reason="Requires real POSIX ACL/dirfd/flock")


def record():
    return keys._KeyRecord(keys.ReviewKeyIdentity("review_" + "4" * 32,
        keys.ReviewKeyBinding(CORE_ID, GENERATION)), bytes(range(32)))


@pytest.fixture
def installed(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'core.db').as_posix()}")
    CoreAuthorityGuard.__table__.create(engine)
    CoreInstallationIdentity.__table__.create(engine)
    public = Ed25519PrivateKey.generate().public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    with engine.begin() as db:
        db.execute(CoreAuthorityGuard.__table__.insert().values(
            singleton_id=1, generation=GENERATION, revision=1))
        db.execute(CoreInstallationIdentity.__table__.insert().values(
            singleton_id=1, installation_id=CORE_ID, identity_version=1, key_generation=1,
            key_id=hashlib.sha256(public).hexdigest(), public_key=base64.b64encode(public).decode("ascii"),
            encrypted_private_key="NEVER_READ_PRIVATE_IDENTITY", created_at=datetime.now(UTC)))
    store = keys.CoreReviewKeyStore(engine, tmp_path / "authority-review")
    yield engine, store, tmp_path / "authority-review"
    engine.dispose()


def fingerprint(configuration=None, *, principal=None, key=None):
    return keys._configuration_identity(record() if key is None else key,
        PRINCIPAL if principal is None else principal,
        {"PASSWORD": "private-low-entropy", "nested": {"value": 1, "items": [True, None]}}
        if configuration is None else configuration)


def test_hmac_is_purpose_key_owner_generation_and_full_configuration_bound():
    config = {"password": "1234", "cosmetic": "also-included"}
    original = copy.deepcopy(config)
    result = fingerprint(config)
    # Synthetic deterministic vector only; never a production key/configuration.
    assert result.keyed_sha256 == "20eb3e2e98685454619cf697d0b8e3e6dc68e11f803a735a982df425d3e6df54"
    encoded = _canonical_bytes({"principal": PRINCIPAL, "configuration": config,
        "key_id": record().identity.key_id, "recovery_generation": GENERATION})
    assert result.keyed_sha256 == hmac.new(bytes(range(32)), keys.CONFIGURATION_DOMAIN + encoded,
        hashlib.sha256).hexdigest()
    assert result.keyed_sha256 != hashlib.sha256(encoded).hexdigest()
    assert result.keyed_sha256 != hmac.new(bytes(range(32)), encoded, hashlib.sha256).hexdigest()
    assert config == original
    assert set(result.model_dump()) == {"key_id", "keyed_sha256"}
    assert "1234" not in result.model_dump_json()
    assert "private-low-entropy" not in repr(record())
    assert base64.b64encode(record().secret).decode("ascii") not in repr(record())
    assert fingerprint(dict(reversed(list(config.items())))) == result
    assert fingerprint({**config, "cosmetic": "changed"}) != result
    for name in ("application_installation_id", "incarnation", "module_id"):
        principal = {**PRINCIPAL, name: {"module_id": "org.example.other"}.get(name, "new_owner")}
        assert fingerprint(config, principal=principal) != result
    for alternative in (
        keys._KeyRecord(record().identity, b"x" * 32),
        keys._KeyRecord(keys.ReviewKeyIdentity("review_" + "5" * 32, record().identity.binding), record().secret),
        keys._KeyRecord(keys.ReviewKeyIdentity(record().identity.key_id,
            keys.ReviewKeyBinding(CORE_ID, "6" * 32)), record().secret),
    ):
        assert fingerprint(config, key=alternative) != result


def test_configuration_encoding_preserves_sequences_numeric_types_unicode_and_absence():
    variants = ({"v": [1, 2]}, {"v": [2, 1]}, {"v": 1}, {"v": 1.0}, {"v": True},
        {"v": 0.0}, {"v": -0.0}, {"v": None}, {}, {"v": "é"}, {"v": "e\u0301"})
    assert len({fingerprint(config).keyed_sha256 for config in variants}) == len(variants)


@pytest.mark.parametrize("invalid", [
    [], "PASSWORD_PRIVATE", {1: "PASSWORD_PRIVATE"}, {"v": float("nan")},
    {"v": float("inf")}, {"v": 2**53}, {"v": "x" * 4097}, {"v": b"PASSWORD_PRIVATE"},
    {"v": "\ud800"}, {"v": ["x" * 4096] * 33},
])
def test_invalid_configuration_is_bounded_and_errors_are_redacted(invalid):
    with pytest.raises(keys.AuthorityReviewKeyError) as error:
        fingerprint(invalid)
    assert "PASSWORD_PRIVATE" not in "".join(traceback.format_exception(error.value))


def test_foreign_principal_constructed_model_and_cycles_cannot_bypass_validation():
    from backend.services.application_authority_context import AuthorityPrincipal

    for principal in ({**PRINCIPAL, "core_installation_id": "inst_" + "9" * 32},
            {**PRINCIPAL, "extra": "PASSWORD_PRIVATE"},
            AuthorityPrincipal.model_construct(**{**PRINCIPAL, "incarnation": True})):
        with pytest.raises(keys.AuthorityReviewKeyError):
            fingerprint(principal=principal)
    recursive = {}
    recursive["PASSWORD_PRIVATE"] = recursive
    with pytest.raises(keys.AuthorityReviewKeyError):
        fingerprint(recursive)


@pytest.mark.parametrize("change", [
    {"version": True}, {"version": 2}, {"purpose": "transport-key"}, {"extra": "PRIVATE"},
    {"secret": "PRIVATE"}, {"secret": base64.b64encode(b"short").decode("ascii")},
    {"key_id": "bad"}, {"core_installation_id": "foreign"}, {"recovery_generation": "old"},
])
def test_closed_record_format_refuses_wrong_key_material(change):
    value = json.loads(keys._encode(record()))
    value.update(change)
    with pytest.raises(keys.AuthorityReviewKeyError) as error:
        keys._decode(json.dumps(value).encode())
    assert "PRIVATE" not in "".join(traceback.format_exception(error.value))


@pytest.mark.parametrize("data", [b"", b"[]", b"not-json", b"x" * 1025,
    b'{"version":1,"version":1}', b"[" * 1000 + b"]" * 1000])
def test_record_bytes_are_bounded_and_duplicate_json_keys_fail(data):
    with pytest.raises(keys.AuthorityReviewKeyError):
        keys._decode(data)


@posix_only
def test_explicit_provision_retry_restart_and_read_have_no_implicit_repair(installed):
    engine, store, directory = installed
    for operation in (store.identity, lambda: store.fingerprint(PRINCIPAL, {})):
        with pytest.raises(keys.AuthorityReviewKeyError):
            operation()
    assert not directory.exists()
    first = store.provision()
    content = (directory / keys.KEY_NAME).read_bytes()
    assert store.provision() == first
    assert store.identity() == first
    assert (directory / keys.KEY_NAME).read_bytes() == content
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert stat.S_IMODE((directory / keys.KEY_NAME).stat().st_mode) == 0o600
    assert stat.S_IMODE((directory / keys.LOCK_NAME).stat().st_mode) == 0o600
    fresh = keys.CoreReviewKeyStore(engine, directory)
    assert fresh.identity() == first
    assert fresh.fingerprint(PRINCIPAL, {"secret": "1234"}) == store.fingerprint(PRINCIPAL, {"secret": "1234"})
    statements = []
    event.listen(engine, "before_cursor_execute", lambda conn, cursor, statement, *rest: statements.append(statement))
    store.fingerprint(PRINCIPAL, {})
    assert statements and not any("encrypted_private_key" in sql for sql in statements)
    assert not any(sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for sql in statements)
    with engine.begin() as db:
        db.execute(update(CoreAuthorityGuard).values(revision=2))
    assert store.identity() == first  # Ordinary writer revision is not key recovery.


@posix_only
def test_missing_core_identity_or_guard_cannot_create_files(installed):
    engine, store, directory = installed
    for table in (CoreInstallationIdentity, CoreAuthorityGuard):
        with engine.begin() as db:
            db.execute(table.__table__.delete())
        with pytest.raises(keys.AuthorityReviewKeyError):
            store.provision()
        assert not directory.exists()


@posix_only
def test_rotation_cas_and_recovery_never_restore_old_key_identity(installed):
    engine, store, directory = installed
    old = store.provision()
    old_digest = store.fingerprint(PRINCIPAL, {"PASSWORD": "1234"})
    old_bytes = (directory / keys.KEY_NAME).read_bytes()
    with pytest.raises(keys.AuthorityReviewKeyError):
        store.recover(expected_key_id=old.key_id)  # Current key uses normal rotation.
    current = store.rotate(expected_key_id=old.key_id)
    assert current != old
    assert store.fingerprint(PRINCIPAL, {"PASSWORD": "1234"}) != old_digest
    with pytest.raises(keys.AuthorityReviewKeyError):
        store.rotate(expected_key_id=old.key_id)
    with engine.begin() as db:
        db.execute(update(CoreAuthorityGuard).values(generation=secrets.token_hex(16), revision=2))
    # Simulate backed-up key material copied back. A fresh recovery generation
    # denies it without rewriting the key, issuing grants or replaying any work.
    (directory / keys.KEY_NAME).write_bytes(old_bytes)
    for operation in (store.identity, store.provision, lambda: store.fingerprint(PRINCIPAL, {}),
            lambda: store.rotate(expected_key_id=old.key_id)):
        with pytest.raises(keys.AuthorityReviewKeyError):
            operation()
        assert (directory / keys.KEY_NAME).read_bytes() == old_bytes
    recovered = store.recover(expected_key_id=old.key_id)
    assert recovered.key_id not in {old.key_id, current.key_id}
    assert recovered.binding.recovery_generation != GENERATION
    assert store.fingerprint(PRINCIPAL, {"PASSWORD": "1234"}) != old_digest


@posix_only
def test_foreign_core_and_missing_material_require_explicit_new_local_key(installed):
    engine, store, directory = installed
    first = store.provision()
    with engine.begin() as db:
        db.execute(update(CoreInstallationIdentity).values(installation_id="inst_" + "8" * 32))
    with pytest.raises(keys.AuthorityReviewKeyError):
        store.identity()
    recovered = store.recover(expected_key_id=first.key_id)
    assert recovered.binding.core_installation_id != first.binding.core_installation_id
    assert recovered.key_id != first.key_id
    (directory / keys.KEY_NAME).unlink()
    with pytest.raises(keys.AuthorityReviewKeyError):
        store.identity()
    assert store.provision().key_id != recovered.key_id


@posix_only
@pytest.mark.parametrize("kind", ["corrupt", "oversize", "mode", "hardlink", "symlink", "fifo", "directory"])
def test_unsafe_key_is_not_overwritten_or_chmod_repaired(installed, kind):
    _, store, directory = installed
    store.provision()
    path = directory / keys.KEY_NAME
    if kind == "corrupt":
        path.write_bytes(b"PASSWORD_PRIVATE")
    elif kind == "oversize":
        path.write_bytes(b"x" * 1025)
    elif kind == "mode":
        path.chmod(0o640)
    elif kind == "hardlink":
        os.link(path, directory / "extra-link")
    else:
        path.unlink()
        if kind == "symlink":
            path.symlink_to(directory / "absent")
        elif kind == "fifo":
            os.mkfifo(path, 0o600)
        else:
            path.mkdir()
    before = path.lstat()
    for operation in (store.identity, store.provision):
        with pytest.raises(keys.AuthorityReviewKeyError):
            operation()
        after = path.lstat()
        assert (after.st_ino, after.st_mode, after.st_size) == (before.st_ino, before.st_mode, before.st_size)


@posix_only
@pytest.mark.parametrize("kind", ["leaf-mode", "leaf-symlink", "ancestor-symlink", "ancestor-writable", "lock-mode", "lock-hardlink", "lock-missing"])
def test_private_directory_ancestors_and_lock_are_validated(installed, kind, tmp_path):
    engine, store, directory = installed
    store.provision()
    if kind == "leaf-mode":
        directory.chmod(0o750)
    elif kind == "leaf-symlink":
        original = directory.with_name("original")
        directory.rename(original)
        directory.symlink_to(original, target_is_directory=True)
    elif kind == "ancestor-symlink":
        alias = tmp_path / "alias"
        alias.symlink_to(tmp_path, target_is_directory=True)
        store = keys.CoreReviewKeyStore(engine, alias / directory.name)
    elif kind == "ancestor-writable":
        tmp_path.chmod(0o777)
    elif kind == "lock-mode":
        (directory / keys.LOCK_NAME).chmod(0o644)
    elif kind == "lock-hardlink":
        os.link(directory / keys.LOCK_NAME, directory / "lock-copy")
    else:
        (directory / keys.LOCK_NAME).unlink()
    with pytest.raises(keys.AuthorityReviewKeyError):
        store.identity()


@posix_only
def test_failed_atomic_replace_preserves_old_key_and_cleans_own_temp(installed, monkeypatch):
    _, store, directory = installed
    original = store.provision()
    content = (directory / keys.KEY_NAME).read_bytes()
    def fail(*args, **kwargs):
        raise OSError("PRIVATE failure")
    monkeypatch.setattr(keys.os, "replace", fail)
    with pytest.raises(keys.AuthorityReviewKeyError) as error:
        store.rotate(expected_key_id=original.key_id)
    assert "PRIVATE" not in "".join(traceback.format_exception(error.value))
    assert (directory / keys.KEY_NAME).read_bytes() == content
    assert store.identity() == original
    assert set(path.name for path in directory.iterdir()) == {keys.KEY_NAME, keys.LOCK_NAME}


@posix_only
def test_recovery_drift_after_file_commit_fails_closed_without_reverting(installed, monkeypatch):
    engine, store, directory = installed
    old = store.provision()
    write = keys._write_record
    def drift(descriptor, value):
        write(descriptor, value)
        with engine.begin() as db:
            db.execute(update(CoreAuthorityGuard).values(generation="9" * 32))
    monkeypatch.setattr(keys, "_write_record", drift)
    with pytest.raises(keys.AuthorityReviewKeyError):
        store.rotate(expected_key_id=old.key_id)
    assert keys._decode((directory / keys.KEY_NAME).read_bytes()).identity.key_id != old.key_id
    with pytest.raises(keys.AuthorityReviewKeyError):
        store.identity()


def _rotate_child(database, directory, expected, start, output):
    engine = create_engine(f"sqlite:///{database}")
    try:
        start.wait(5)
        result = keys.CoreReviewKeyStore(engine, Path(directory)).rotate(expected_key_id=expected)
        output.put(("ok", result.key_id))
    except keys.AuthorityReviewKeyError:
        output.put(("denied", None))
    finally:
        engine.dispose()


@posix_only
def test_real_two_process_rotation_has_one_cas_winner(installed):
    engine, store, directory = installed
    old = store.provision()
    context = multiprocessing.get_context("fork")
    start, output = context.Event(), context.Queue()
    children = [context.Process(target=_rotate_child,
        args=(engine.url.database, str(directory), old.key_id, start, output)) for _ in range(2)]
    try:
        for child in children:
            child.start()
        start.set()
        results = [output.get(timeout=10) for _ in children]
        for child in children:
            child.join(10)
            assert child.exitcode == 0
        assert sorted(result[0] for result in results) == ["denied", "ok"]
        assert store.identity().key_id == next(result[1] for result in results if result[0] == "ok")
    finally:
        for child in children:
            if child.is_alive():
                child.terminate()
                child.join(5)
        output.close()


@posix_only
def test_busy_process_lock_is_bounded_unavailable(installed):
    _, store, directory = installed
    old = store.provision()
    with keys._private_directory(directory) as descriptor, keys._key_lock(descriptor):
        with pytest.raises(keys.AuthorityReviewKeyError):
            store.rotate(expected_key_id=old.key_id)
    assert store.identity() == old


@pytest.mark.skipif(os.name != "posix" or getattr(os, "geteuid", lambda: -1)() != 0,
    reason="Real foreign UID check needs disposable root-run POSIX test")
def test_real_foreign_uid_can_read_parent_but_cannot_read_core_key():
    # A fresh disposable /tmp parent, not production paths or pytest's private
    # ancestors. Public sentinel proves the child can actually reach that parent.
    with tempfile.TemporaryDirectory(prefix="3mm-review-acl-") as parent:
        root = Path(parent)
        root.chmod(0o755)
        (root / "public").write_text("reachable")
        (root / "public").chmod(0o644)
        private = root / "authority-review"
        private.mkdir(mode=0o700)
        with keys._private_directory(private) as descriptor:
            keys._write_record(descriptor, record())
        child = os.fork()
        if child == 0:
            try:
                os.setgroups([])
                os.setgid(65534)
                os.setuid(65534)
                assert (root / "public").read_text() == "reachable"
                try:
                    (private / keys.KEY_NAME).read_bytes()
                except PermissionError:
                    os._exit(0)
                os._exit(2)
            except BaseException:
                os._exit(3)
        _, status = os.waitpid(child, 0)
        assert os.waitstatus_to_exitcode(status) == 0


@pytest.mark.skipif(os.name == "posix", reason="Non-POSIX refusal only")
def test_non_posix_storage_fails_closed_without_faking_acl_security(installed):
    _, store, directory = installed
    with pytest.raises(keys.AuthorityReviewKeyError):
        store.provision()
    assert not directory.exists()
