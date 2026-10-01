"""Root boundary checks without root privileges, hardware or subprocesses."""
from datetime import UTC, datetime, timedelta
import hashlib
import io
import os
import json
from pathlib import Path
from types import SimpleNamespace
import tarfile

import pytest

from three_mm_protocol.node_updates import (
    NodeUpdateApplyRequest,
    NodeUpdatePrepareRequest,
)
from three_mm_runtime import node_update_helper as module


def request(number=1, **changes):
    created = datetime.now(UTC)
    values = dict(
        operation_id="nodeupd_" + f"{number:032x}",
        device_id="dev_" + "a" * 32,
        release_id="v1.2.0",
        archive_sha256="b" * 64,
        confirmed_install=True,
        created_at=created,
        expires_at=created + timedelta(seconds=120),
    )
    values.update(changes)
    return NodeUpdateApplyRequest(**values)


def envelope(value):
    return {
        "action": "apply",
        "request": value.model_dump(mode="json"),
    }


class Scheduler:
    def __init__(self, store, state="active", fail=False):
        self.store = store
        self.current_state = state
        self.fail = fail
        self.calls = []

    def schedule(self, operation_id):
        assert (
            self.store.read(operation_id)["operation"].status
            == "accepted"
        )
        self.calls.append(operation_id)

        if self.fail:
            raise OSError("ambiguous systemd handover")

    def state(self, operation_id):
        return self.current_state


@pytest.fixture
def boundary(tmp_path):
    store = module.NodeUpdateStore(
        tmp_path / "state",
        enforce_permissions=False,
    )
    scheduler = Scheduler(store)
    validated = []

    helper = module.NodeUpdateHelper(
        store,
        service_uid=1000,
        scheduler=scheduler,
        validator=lambda value: validated.append(
            value.operation_id
        ),
    )

    return store, scheduler, helper, validated


def test_durable_acceptance_replay_conflict_and_active_serialization(
    boundary,
):
    store, scheduler, helper, validated = boundary

    value = request(
        created_at=datetime.now(UTC) - timedelta(minutes=10),
        expires_at=datetime.now(UTC) - timedelta(minutes=9),
    )

    # Admission TTL belongs to the validator; replay must never
    # reauthorize it.
    response = helper.handle_request(
        envelope(value),
        peer_uid=1000,
    )

    assert response["operation"]["status"] == "accepted"

    restarted = module.NodeUpdateHelper(
        module.NodeUpdateStore(
            store.root,
            enforce_permissions=False,
        ),
        service_uid=1000,
        scheduler=scheduler,
        validator=lambda _: pytest.fail(
            "replay revalidated"
        ),
    )

    assert (
        restarted.handle_request(
            envelope(value),
            peer_uid=0,
        )
        == response
    )

    assert scheduler.calls == validated == [
        value.operation_id
    ]

    conflict = value.model_copy(
        update={"release_id": "v1.3.0"}
    )

    assert (
        helper.handle_request(
            envelope(conflict),
            peer_uid=1000,
        )["error"]
        == "identity_conflict"
    )

    assert (
        helper.handle_request(
            envelope(request(2)),
            peer_uid=1000,
        )["error"]
        == "update_busy"
    )


@pytest.mark.parametrize(
    "payload,uid,error",
    [
        (
            {"action": "status"},
            2000,
            "forbidden_peer",
        ),
        (
            {
                "action": "status",
                "path": "/tmp/anything",
            },
            1000,
            "invalid_request",
        ),
        (
            {
                "action": "shell",
                "command": "true",
            },
            0,
            "invalid_request",
        ),
    ],
)
def test_untrusted_peer_and_arbitrary_actions_are_refused(
    boundary,
    payload,
    uid,
    error,
):
    store, scheduler, helper, _ = boundary

    assert helper.handle_request(
        payload,
        peer_uid=uid,
    ) == {
        "ok": False,
        "error": error,
    }

    assert store.records() == []
    assert scheduler.calls == []


def test_unresolved_worker_or_handover_never_reexecutes(
    boundary,
):
    store, scheduler, helper, _ = boundary

    value = request()

    helper.handle_request(
        envelope(value),
        peer_uid=1000,
    )

    scheduler.current_state = "unknown"

    result = helper.handle_request(
        {"action": "status"},
        peer_uid=1000,
    )

    assert result["operation"]["status"] == "unknown"
    assert (
        result["operation"]["error_code"]
        == "worker_unresolved"
    )

    assert (
        helper.handle_request(
            envelope(value),
            peer_uid=1000,
        )
        == result
    )

    assert (
        helper.handle_request(
            envelope(request(2)),
            peer_uid=1000,
        )["error"]
        == "update_busy"
    )

    assert scheduler.calls == [
        value.operation_id
    ]


def test_failed_start_is_durable_unknown_and_history_is_bounded(
    boundary,
    monkeypatch,
):
    store, scheduler, helper, _ = boundary

    scheduler.fail = True
    value = request()

    result = helper.handle_request(
        envelope(value),
        peer_uid=1000,
    )

    assert result["operation"]["status"] == "unknown"
    assert (
        result["operation"]["error_code"]
        == "schedule_unknown"
    )

    assert (
        helper.handle_request(
            envelope(value),
            peer_uid=1000,
        )
        == result
    )

    assert len(scheduler.calls) == 1

    record = store.read(value.operation_id)

    store.transition(
        record,
        "failed",
        error_code="preflight_failed",
    )

    monkeypatch.setattr(
        module,
        "MAX_OPERATIONS",
        1,
    )

    assert (
        helper.handle_request(
            envelope(request(2)),
            peer_uid=1000,
        )["error"]
        == "history_full"
    )

    assert len(store.records()) == 1


def test_persisted_operation_must_agree_with_request(
    boundary,
):
    store, _, helper, _ = boundary

    value = request()

    helper.handle_request(
        envelope(value),
        peer_uid=1000,
    )

    path = (
        store.root
        / "operations"
        / (value.operation_id + ".json")
    )

    raw = json.loads(path.read_bytes())

    raw["operation"]["device_id"] = (
        "dev_" + "c" * 32
    )

    path.write_text(json.dumps(raw))

    assert (
        helper.handle_request(
            {"action": "status"},
            peer_uid=1000,
        )["error"]
        == "invalid_state"
    )

    for invalid in (
        None,
        [],
        "invalid",
    ):
        path.write_text(
            json.dumps(invalid)
        )

        assert (
            helper.handle_request(
                {"action": "status"},
                peer_uid=1000,
            )["error"]
            == "invalid_state"
        )


def prepare_archive(
    tmp_path,
    store,
    *,
    metadata_changes=None,
    unsafe=None,
):
    current = tmp_path / "current"
    current.mkdir(exist_ok=True)

    (
        current
        / ".3mm-install-profile"
    ).write_text("node\n")

    agent = tmp_path / "agent"
    agent.mkdir(exist_ok=True)

    (
        agent
        / "identity.json"
    ).write_text(
        json.dumps(
            {
                "device_id":
                    "dev_" + "a" * 32,
            }
        )
    )

    metadata = dict(
        profile="node",
        architecture="armv6l",
        python="3.13",
        release_id="v1.2.0",
        version="1.2.0",
        branch="main",
        commit="a" * 40,
        includes_working_tree=False,
    )

    metadata.update(
        metadata_changes or {}
    )

    contents = {
        name: b"fixture"
        for name in module.REQUIRED_FILES
    }

    contents.update(
        {
            ".3mm-release.json":
                json.dumps(metadata).encode(),
            ".3mm-install-profile":
                b"node\n",
            "VERSION":
                b"1.2.0\n",
        }
    )

    output = io.BytesIO()

    with tarfile.open(
        fileobj=output,
        mode="w:gz",
    ) as archive:
        for name, data in sorted(
            contents.items()
        ):
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            entry.mode = 0o644

            if (
                unsafe == "directory"
                and name == "agent/main.py"
            ):
                entry.type = tarfile.DIRTYPE
                entry.size = 0

            if (
                unsafe == "setuid"
                and name == "agent/main.py"
            ):
                entry.mode = 0o4755

            archive.addfile(
                entry,
                io.BytesIO(data)
                if entry.isfile()
                else None,
            )

        if unsafe in {
            "traversal",
            "link",
        }:
            entry = tarfile.TarInfo(
                "../outside"
                if unsafe == "traversal"
                else "link"
            )

            if unsafe == "link":
                entry.type = tarfile.SYMTYPE
                entry.linkname = "/etc/passwd"

            archive.addfile(entry)

    value = request(
        archive_sha256=hashlib.sha256(
            output.getvalue()
        ).hexdigest()
    )

    directory = (
        store.root
        / "staging"
        / value.operation_id
    )

    directory.mkdir(
        exist_ok=True
    )

    path = (
        directory
        / "release.tar.gz"
    )

    path.write_bytes(
        output.getvalue()
    )

    return (
        value,
        current,
        agent,
        path,
        metadata,
    )


def inspect(
    value,
    store,
    current,
    agent,
    **changes,
):
    return module.inspect_prepared_archive(
        value,
        store=store,
        current_root=current,
        agent_data=agent,
        machine="armv6l",
        python_version=(3, 13),
        system="Linux",
        **changes,
    )


def test_official_archive_and_all_release_metadata_constraints(
    tmp_path,
    boundary,
):
    store = boundary[0]

    value, current, agent, path, metadata = (
        prepare_archive(
            tmp_path,
            store,
        )
    )

    assert inspect(
        value,
        store,
        current,
        agent,
    ) == (
        path,
        metadata,
    )

    for changes in (
        {"includes_working_tree": True},
        {"branch": "feature"},
        {"profile": "full"},
        {"architecture": "aarch64"},
        {"python": "3.12"},
        {"version": "1.1.0"},
    ):
        value, current, agent, _, _ = (
            prepare_archive(
                tmp_path,
                store,
                metadata_changes=changes,
            )
        )

        with pytest.raises(
            module.NodeUpdateError,
            match="official Node",
        ):
            inspect(
                value,
                store,
                current,
                agent,
            )


@pytest.mark.parametrize(
    "unsafe",
    [
        "traversal",
        "link",
        "directory",
        "setuid",
    ],
)
def test_unsafe_archive_entries_fail_before_extraction(
    tmp_path,
    boundary,
    unsafe,
):
    store = boundary[0]

    value, current, agent, _, _ = (
        prepare_archive(
            tmp_path,
            store,
            unsafe=unsafe,
        )
    )

    with pytest.raises(
        module.NodeUpdateError
    ):
        inspect(
            value,
            store,
            current,
            agent,
        )

    assert not (
        tmp_path / "outside"
    ).exists()


def test_sha_ttl_identity_host_and_root_permissions_are_independent(
    tmp_path,
    boundary,
    monkeypatch,
):
    store = boundary[0]

    value, current, agent, _, _ = (
        prepare_archive(
            tmp_path,
            store,
        )
    )

    with pytest.raises(
        module.NodeUpdateError
    ) as error:
        inspect(
            value.model_copy(
                update={
                    "archive_sha256":
                        "0" * 64,
                }
            ),
            store,
            current,
            agent,
        )

    assert (
        error.value.code
        == "checksum_mismatch"
    )

    with pytest.raises(
        module.NodeUpdateError
    ) as error:
        inspect(
            value,
            store,
            current,
            agent,
            now=value.expires_at,
        )

    assert (
        error.value.code
        == "expired"
    )

    (
        agent
        / "identity.json"
    ).write_text("[]")

    with pytest.raises(
        module.NodeUpdateError
    ) as error:
        inspect(
            value,
            store,
            current,
            agent,
        )

    assert (
        error.value.code
        == "identity_mismatch"
    )

    with pytest.raises(
        module.NodeUpdateError
    ) as error:
        module.inspect_prepared_archive(
            value,
            store=store,
            system="Windows",
        )

    assert (
        error.value.code
        == "unsupported_target"
    )

    info = SimpleNamespace(
        st_mode=0o40755,
        st_uid=1000,
        st_nlink=1,
    )

    monkeypatch.setattr(
        Path,
        "lstat",
        lambda _: info,
    )

    with pytest.raises(
        module.NodeUpdateError
    ) as error:
        module.trusted_path(
            current,
            directory=True,
        )

    assert (
        error.value.code
        == "unsafe_path"
    )


def test_scheduler_is_pinned_fixed_and_detached_but_waits_for_startup(
    tmp_path,
):
    release = (
        tmp_path
        / "old-release"
    )

    (
        release
        / "deployment"
    ).mkdir(
        parents=True
    )

    (
        release
        / "deployment"
        / "apply_node_update.py"
    ).write_text("fixture")

    (
        release
        / ".venv"
        / "bin"
    ).mkdir(
        parents=True
    )

    (
        release
        / ".venv"
        / "bin"
        / "python"
    ).write_text("fixture")

    calls = []

    scheduler = (
        module.SubprocessNodeUpdateScheduler(
            release,
            runner=lambda argv, **kwargs: (
                calls.append(
                    (
                        argv,
                        kwargs,
                    )
                )
                or SimpleNamespace(
                    returncode=0
                )
            ),
            enforce_permissions=False,
        )
    )

    value = request()

    scheduler.schedule(
        value.operation_id
    )

    argv, options = calls[0]

    assert "--no-block" not in argv
    assert "--wait" not in argv

    assert (
        "--property=KillMode=control-group"
        in argv
    )

    assert (
        "--property=RuntimeMaxSec=45min"
        in argv
    )

    assert (
        "--property=UMask=0022"
        in argv
    )

    assert argv[-4:] == [
        str(
            release
            / ".venv"
            / "bin"
            / "python"
        ),
        str(
            release
            / "deployment"
            / "apply_node_update.py"
        ),
        "--operation-id",
        value.operation_id,
    ]

    assert options["timeout"] == 15
    assert options["check"] is False


def make_download(
    tmp_path,
    store,
    *,
    number=100,
    data=b"node-release-fixture",
    service_uid=None,
):
    uid = (
        os.stat(tmp_path).st_uid
        if service_uid is None
        else service_uid
    )

    operation_id = (
        "nodeupd_"
        + f"{number:032x}"
    )

    device_id = (
        "dev_"
        + "a" * 32
    )

    agent = (
        tmp_path
        / f"agent-{number}"
    )

    inbox = (
        agent
        / "node-update-inbox"
    )

    operation_dir = (
        inbox
        / operation_id
    )

    operation_dir.mkdir(
        parents=True
    )

    for directory in (
        agent,
        inbox,
        operation_dir,
    ):
        os.chmod(
            directory,
            0o700,
        )

    archive = (
        operation_dir
        / "release.tar.gz"
    )

    archive.write_bytes(data)

    os.chmod(
        archive,
        0o600,
    )

    request = NodeUpdatePrepareRequest(
        operation_id=operation_id,
        device_id=device_id,
        release_id="v1.2.0",
        archive_sha256=hashlib.sha256(
            data
        ).hexdigest(),
        archive_size_bytes=len(data),
    )

    return (
        request,
        agent,
        archive,
        uid,
    )


def test_prepare_moves_verified_agent_download_into_root_staging(
    tmp_path,
    boundary,
):
    store = boundary[0]

    request, agent, source, uid = (
        make_download(
            tmp_path,
            store,
        )
    )

    result = (
        module.prepare_downloaded_archive(
            request,
            store=store,
            service_uid=uid,
            agent_data=agent,
        )
    )

    assert (
        result.operation_id
        == request.operation_id
    )

    assert (
        result.device_id
        == request.device_id
    )

    assert (
        result.release_id
        == request.release_id
    )

    assert (
        result.archive_sha256
        == request.archive_sha256
    )

    assert (
        result.archive_size_bytes
        == request.archive_size_bytes
    )

    target = (
        store.root
        / "staging"
        / request.operation_id
        / "release.tar.gz"
    )

    metadata = (
        store.root
        / "staging"
        / request.operation_id
        / "prepared.json"
    )

    assert (
        target.read_bytes()
        == source.read_bytes()
    )

    assert metadata.is_file()


def test_prepare_replay_is_idempotent_and_identity_conflict_is_rejected(
    tmp_path,
    boundary,
):
    store = boundary[0]

    request, agent, _, uid = (
        make_download(
            tmp_path,
            store,
            number=101,
        )
    )

    first = (
        module.prepare_downloaded_archive(
            request,
            store=store,
            service_uid=uid,
            agent_data=agent,
        )
    )

    second = (
        module.prepare_downloaded_archive(
            request,
            store=store,
            service_uid=uid,
            agent_data=agent,
        )
    )

    assert second == first

    conflict = request.model_copy(
        update={
            "release_id": "v1.3.0",
        }
    )

    with pytest.raises(
        module.NodeUpdateError
    ) as error:
        module.prepare_downloaded_archive(
            conflict,
            store=store,
            service_uid=uid,
            agent_data=agent,
        )

    assert (
        error.value.code
        == "identity_conflict"
    )


@pytest.mark.parametrize(
    "change,error_code",
    [
        (
            "sha",
            "checksum_mismatch",
        ),
        (
            "size",
            "unsafe_download",
        ),
    ],
)
def test_prepare_rejects_wrong_digest_or_size(
    tmp_path,
    boundary,
    change,
    error_code,
):
    store = boundary[0]

    request, agent, _, uid = (
        make_download(
            tmp_path,
            store,
            number=(
                102
                if change == "sha"
                else 103
            ),
        )
    )

    if change == "sha":
        request = request.model_copy(
            update={
                "archive_sha256":
                    "0" * 64,
            }
        )
    else:
        request = request.model_copy(
            update={
                "archive_size_bytes":
                    request.archive_size_bytes
                    + 1,
            }
        )

    with pytest.raises(
        module.NodeUpdateError
    ) as error:
        module.prepare_downloaded_archive(
            request,
            store=store,
            service_uid=uid,
            agent_data=agent,
        )

    assert (
        error.value.code
        == error_code
    )


@pytest.mark.skipif(
    os.name != "posix",
    reason=(
        "Unix ownership boundary is "
        "verified on POSIX/Linux"
    ),
)
def test_prepare_rejects_download_owned_by_another_user(
    tmp_path,
    boundary,
):
    store = boundary[0]

    request, agent, _, uid = (
        make_download(
            tmp_path,
            store,
            number=104,
        )
    )

    with pytest.raises(
        module.NodeUpdateError
    ) as error:
        module.prepare_downloaded_archive(
            request,
            store=store,
            service_uid=uid + 1,
            agent_data=agent,
        )

    assert (
        error.value.code
        == "unsafe_download"
    )


@pytest.mark.skipif(
    os.name != "posix",
    reason=(
        "O_NOFOLLOW security boundary "
        "is verified on POSIX/Linux"
    ),
)
def test_prepare_refuses_symlink_archive(
    tmp_path,
    boundary,
):
    store = boundary[0]

    request, agent, archive, uid = (
        make_download(
            tmp_path,
            store,
            number=105,
        )
    )

    real = archive.with_name(
        "real-release.tar.gz"
    )

    archive.rename(real)
    archive.symlink_to(real)

    with pytest.raises(
        module.NodeUpdateError
    ) as error:
        module.prepare_downloaded_archive(
            request,
            store=store,
            service_uid=uid,
            agent_data=agent,
        )

    assert error.value.code in {
        "missing_download",
        "unsafe_download",
    }