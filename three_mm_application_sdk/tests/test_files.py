import hashlib
import multiprocessing
import os
from pathlib import Path
import stat
import tempfile

import pytest

from three_mm_application_sdk import (
    SDK_VERSION,
    ApplicationContext,
    ApplicationFileLimits,
    ApplicationFileStorage,
    ApplicationFileStorageError,
    ApplicationStorage,
)
from three_mm_application_sdk import files as files_module

POSIX = os.name == "posix"
posix_only = pytest.mark.skipif(
    not POSIX, reason="Private file adapter requires real POSIX filesystem semantics"
)


@pytest.fixture
def storage(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    return ApplicationFileStorage(data, limits=ApplicationFileLimits(8, 12, 2))


def digest(content):
    return hashlib.sha256(content).hexdigest()


@posix_only
def test_sdk_13_context_keeps_existing_database_and_offers_own_files(tmp_path):
    contexts = []
    for name in ("first", "second"):
        data = tmp_path / name / "data"
        data.mkdir(parents=True)
        (data / "state.sqlite3").write_bytes(b"fixture owned database")
        contexts.append(
            ApplicationContext(
                "org.test." + name, "1.0.0", data, {}, ApplicationStorage(data)
            )
        )
    first, second = contexts
    saved = first.files.put("logo", b"one", expected_sha256=None)
    assert first.files.get("logo") == saved
    assert second.files.get("logo") is None
    assert second.files.list_entries() == []
    assert not (second.data_dir / "sdk-files").exists()
    assert first.storage.database_path.read_bytes() == b"fixture owned database"
    assert SDK_VERSION == "1.3"


@posix_only
def test_create_read_compare_swap_delete_and_restart(storage):
    assert storage.get("a") is None
    assert storage.list_entries() == []
    first = storage.put("a", b"alpha", expected_sha256=None)
    assert first.sha256 == digest(b"alpha")
    with pytest.raises(ApplicationFileStorageError, match="conflict"):
        storage.put("a", b"new", expected_sha256=None)
    second = storage.put("a", b"new", expected_sha256=first.sha256)
    restarted = ApplicationFileStorage(storage.data_dir, limits=storage.limits)
    assert restarted.get("a") == second
    assert restarted.list_entries() == [("a", 3)]
    with pytest.raises(ApplicationFileStorageError, match="conflict"):
        restarted.delete("a", expected_sha256=first.sha256)
    restarted.delete("a", expected_sha256=second.sha256)
    assert restarted.get("a") is None
    with pytest.raises(ApplicationFileStorageError, match="conflict"):
        restarted.delete("a", expected_sha256=second.sha256)


@pytest.mark.parametrize(
    "file_id",
    [
        "../state",
        "/etc/passwd",
        "x/y",
        "x\\y",
        "blob.png",
        "https://host",
        "a\x00b",
        "a" * 65,
        "",
        ".lock",
        1,
    ],
)
def test_logical_ids_cannot_be_paths_or_reserved_files(storage, file_id):
    with pytest.raises(ValueError, match="identity"):
        storage.get(file_id)
    with pytest.raises(ValueError, match="identity"):
        storage.put(file_id, b"x", expected_sha256=None)
    assert list(storage.data_dir.iterdir()) == []


@pytest.mark.parametrize(
    "values",
    [(True, 12, 2), (8, "12", 2), (8, 12, False), (0, 12, 2), (8, 7, 2), (8, 12, 1025)],
)
def test_limits_are_strict_and_consistent(values):
    with pytest.raises(ValueError, match="limits"):
        ApplicationFileLimits(*values)


@posix_only
def test_modes_and_reads_never_initialize_namespace(storage):
    reader = ApplicationFileStorage(
        storage.data_dir, mode="read", limits=storage.limits
    )
    assert reader.get("a") is None
    assert reader.list_entries() == []
    with pytest.raises(ApplicationFileStorageError, match="read-only"):
        reader.put("a", b"x", expected_sha256=None)
    assert list(storage.data_dir.iterdir()) == []
    saved = storage.put("a", b"x", expected_sha256=None)
    assert reader.get("a") == saved
    with pytest.raises(ApplicationFileStorageError, match="read-only"):
        reader.delete("a", expected_sha256=saved.sha256)


def _process_permission_probe(data_dir, uid, gid, scenario, result):
    try:
        if os.geteuid() == 0:
            os.setgroups([])
            os.setgid(gid)
            os.setuid(uid)
        assert os.geteuid() != 0  # Root would hide the deployment failure.
        data = Path(data_dir)
        storage = ApplicationFileStorage(data, limits=ApplicationFileLimits(8, 12, 2))
        if scenario != "search_only":
            for operation in (
                lambda: storage.get("a"),
                lambda: storage.put("a", b"old", expected_sha256=None),
            ):
                try:
                    operation()
                except ApplicationFileStorageError:
                    pass
                else:
                    raise AssertionError("Filesystem permission denial was bypassed")
        else:
            assert os.access(data.parent, os.X_OK)
            assert not os.access(data.parent, os.R_OK)
            try:
                os.listdir(data.parent)
            except PermissionError:
                pass
            else:
                raise AssertionError("Protected parent became listable")
            assert storage.get("a") is None
            assert storage.list_entries() == []
            assert not (data / "sdk-files").exists()
            saved = storage.put("a", b"old", expected_sha256=None)
            restarted = ApplicationFileStorage(data, limits=storage.limits)
            assert restarted.get("a") == saved
            assert restarted.list_entries() == [("a", 3)]
            changed = restarted.put("a", b"new", expected_sha256=saved.sha256)
            assert restarted.get("a") == changed
            restarted.delete("a", expected_sha256=changed.sha256)
            assert restarted.get("a") is None
            assert restarted.list_entries() == []
        result.send(("ok", None))
    except BaseException as error:
        result.send((type(error).__name__, str(error)))
    finally:
        result.close()


@pytest.mark.skipif(
    not POSIX or not hasattr(os, "O_PATH"), reason="Linux directory search semantics"
)
@pytest.mark.parametrize("scenario", ["search_only", "no_search", "unreadable_data"])
def test_real_non_root_permissions_under_protected_state_root(scenario):
    # Only disposable paths change ownership/mode. A fork inherits the already
    # imported SDK, so a root-run suite can drop privileges without needing to
    # expose pytest's private temp parents or the checkout to another user.
    uid, gid = (65534, 65534) if os.geteuid() == 0 else (os.geteuid(), os.getegid())
    with tempfile.TemporaryDirectory(prefix="3mm-file-permissions-") as temporary:
        root = Path(temporary)
        root.chmod(0o711)
        protected = root / "state"
        protected.mkdir()
        data = protected / "data"
        data.mkdir(mode=0o700)
        if os.geteuid() == 0:
            os.chown(data, uid, gid)
        data.chmod(0o300 if scenario == "unreadable_data" else 0o700)
        protected.chmod(0o000 if scenario == "no_search" else 0o111)
        context = multiprocessing.get_context("fork")
        receiver, sender = context.Pipe(duplex=False)
        process = context.Process(
            target=_process_permission_probe,
            args=(str(data), uid, gid, scenario, sender),
        )
        try:
            process.start()
            sender.close()
            assert receiver.poll(15), "Non-root permission probe timed out"
            assert receiver.recv() == ("ok", None)
            process.join(timeout=5)
            assert process.exitcode == 0
            assert stat.S_IMODE(protected.stat().st_mode) == (
                0o000 if scenario == "no_search" else 0o111
            )
            if scenario != "search_only":
                protected.chmod(0o700)
                assert not (data / "sdk-files").exists()
        finally:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
            receiver.close()
            sender.close()
            protected.chmod(0o700)
            data.chmod(0o700)


@posix_only
def test_without_o_path_preserves_supported_readable_directory_walk(
    storage, monkeypatch
):
    monkeypatch.delattr(files_module.os, "O_PATH", raising=False)
    assert storage.get("a") is None
    saved = storage.put("a", b"old", expected_sha256=None)
    assert storage.get("a") == saved
    storage.delete("a", expected_sha256=saved.sha256)
    assert storage.list_entries() == []


@posix_only
def test_quota_failures_leave_existing_file_intact(storage):
    first = storage.put("a", b"12345678", expected_sha256=None)
    storage.put("b", b"1234", expected_sha256=None)
    for file_id, content, expected, message in [
        ("c", b"1", None, "count"),
        ("b", b"12345", digest(b"1234"), "total size"),
        ("a", b"123456789", first.sha256, "file size"),
    ]:
        with pytest.raises(ApplicationFileStorageError, match=message):
            storage.put(file_id, content, expected_sha256=expected)
    assert storage.get("a") == first
    assert storage.list_entries() == [("a", 8), ("b", 4)]


@pytest.mark.parametrize(
    "content,expected",
    [(bytearray(b"a"), None), ("a", None), (b"a", True), (b"a", "bad")],
)
def test_invalid_inputs_are_refused_before_filesystem(storage, content, expected):
    with pytest.raises(ValueError):
        storage.put("a", content, expected_sha256=expected)
    assert list(storage.data_dir.iterdir()) == []


@posix_only
@pytest.mark.parametrize("target", ["ancestor", "data", "namespace", "blob", "lock"])
def test_symlinks_cannot_redirect_operations(tmp_path, target):
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    (foreign / "sentinel").write_bytes(b"untouched")
    ancestor = tmp_path / "instance"
    ancestor.mkdir()
    data = ancestor / "data"
    data.mkdir()
    storage = ApplicationFileStorage(data)
    storage.put("a", b"original", expected_sha256=None)
    namespace = data / "sdk-files"
    if target == "ancestor":
        ancestor.rename(tmp_path / "saved_instance")
        ancestor.symlink_to(foreign, target_is_directory=True)
    elif target == "data":
        data.rename(ancestor / "saved_data")
        data.symlink_to(foreign, target_is_directory=True)
    elif target == "namespace":
        namespace.rename(data / "saved_namespace")
        namespace.symlink_to(foreign, target_is_directory=True)
    else:
        path = namespace / ("blob_a" if target == "blob" else ".lock")
        path.unlink()
        path.symlink_to(foreign / "sentinel")
    with pytest.raises(ApplicationFileStorageError):
        storage.get("a")
    with pytest.raises(ApplicationFileStorageError):
        storage.put("a", b"changed", expected_sha256=digest(b"original"))
    assert (foreign / "sentinel").read_bytes() == b"untouched"
    assert sorted(path.name for path in foreign.iterdir()) == ["sentinel"]


@posix_only
@pytest.mark.parametrize("kind", ["hardlink", "fifo"])
def test_special_files_are_refused_without_following_or_blocking(
    storage, tmp_path, kind
):
    storage.put("a", b"original", expected_sha256=None)
    path = storage.data_dir / "sdk-files" / "blob_a"
    path.unlink()
    foreign = tmp_path / "foreign"
    foreign.write_bytes(b"outside")
    if kind == "hardlink":
        os.link(foreign, path)
    else:
        os.mkfifo(path)
    with pytest.raises(ApplicationFileStorageError, match="regular file"):
        storage.get("a")
    with pytest.raises(ApplicationFileStorageError, match="regular file"):
        storage.list_entries()
    assert foreign.read_bytes() == b"outside"


@posix_only
def test_interrupted_staging_blocks_new_writes_but_preserves_owned_reads(storage):
    saved = storage.put("a", b"old", expected_sha256=None)
    pending = storage.data_dir / "sdk-files" / ".pending_interrupted"
    pending.write_bytes(b"not committed")
    assert storage.get("a") == saved
    with pytest.raises(ApplicationFileStorageError, match="recovery review"):
        storage.put("a", b"new", expected_sha256=saved.sha256)
    assert pending.read_bytes() == b"not committed"
    assert storage.get("a") == saved


@posix_only
def test_failed_atomic_replace_keeps_old_content_and_removes_only_own_staging(
    storage, monkeypatch
):
    saved = storage.put("a", b"old", expected_sha256=None)

    def fail(*args, **kwargs):
        raise OSError("fixture private path must not leak")

    monkeypatch.setattr(files_module.os, "rename", fail)
    # The fault injection replaces the function whose dir_fd support was checked
    # by the successful first write; don't mistake the injected function for an
    # unsupported host and skip the actual atomic-write failure path.
    monkeypatch.setattr(
        ApplicationFileStorage, "_supported", staticmethod(lambda: None)
    )
    with pytest.raises(
        ApplicationFileStorageError, match="could not be accessed"
    ) as caught:
        storage.put("a", b"new", expected_sha256=saved.sha256)
    assert "private path" not in str(caught.value)
    assert storage.get("a") == saved
    assert storage.list_entries() == [("a", 3)]


@posix_only
def test_directory_sync_failure_reports_uncertainty_without_auto_replay(
    storage, monkeypatch
):
    saved = storage.put("a", b"old", expected_sha256=None)
    original = files_module.os.fsync

    def fail_directory(fd):
        import stat

        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError("fixture sync failed")
        original(fd)

    monkeypatch.setattr(files_module.os, "fsync", fail_directory)
    with pytest.raises(ApplicationFileStorageError):
        storage.put("a", b"new", expected_sha256=saved.sha256)
    assert storage.get("a").content == b"new"
    with pytest.raises(ApplicationFileStorageError, match="conflict"):
        storage.put("a", b"new", expected_sha256=saved.sha256)


def _process_cas(data_dir, ready, start, results, content, expected):
    storage = ApplicationFileStorage(Path(data_dir))
    ready.put(True)
    start.wait(10)
    try:
        results.put(
            ("saved", storage.put("a", content, expected_sha256=expected).content)
        )
    except ApplicationFileStorageError as error:
        results.put(("refused", str(error)))


@posix_only
def test_two_real_processes_cannot_overwrite_same_expected_revision(storage):
    saved = storage.put("a", b"old", expected_sha256=None)
    context = multiprocessing.get_context("spawn")
    ready, results = context.Queue(), context.Queue()
    start = context.Event()
    processes = [
        context.Process(
            target=_process_cas,
            args=(str(storage.data_dir), ready, start, results, content, saved.sha256),
        )
        for content in (b"first", b"second")
    ]
    try:
        for process in processes:
            process.start()
        for _ in processes:
            assert ready.get(timeout=10) is True
        start.set()
        outcomes = [results.get(timeout=10) for _ in processes]
        assert sorted(state for state, _ in outcomes) == ["refused", "saved"]
        winner = next(content for state, content in outcomes if state == "saved")
        assert storage.get("a").content == winner
        assert storage.list_entries() == [("a", len(winner))]
    finally:
        for process in processes:
            process.join(timeout=10)
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
        ready.close()
        results.close()


@posix_only
def test_busy_lock_refuses_promptly_instead_of_waiting_indefinitely(storage):
    saved = storage.put("a", b"old", expected_sha256=None)
    with storage._locked(write=True):
        with pytest.raises(ApplicationFileStorageError, match="busy"):
            storage.get("a")
        with pytest.raises(ApplicationFileStorageError, match="busy"):
            storage.put("a", b"new", expected_sha256=saved.sha256)
    assert storage.get("a") == saved


def test_unsupported_runtime_has_no_path_based_fallback(storage, monkeypatch):
    monkeypatch.setattr(files_module, "fcntl", None)
    with pytest.raises(ApplicationFileStorageError, match="supported POSIX"):
        storage.get("a")
    with pytest.raises(ApplicationFileStorageError, match="supported POSIX"):
        storage.put("a", b"x", expected_sha256=None)
    assert list(storage.data_dir.iterdir()) == []
