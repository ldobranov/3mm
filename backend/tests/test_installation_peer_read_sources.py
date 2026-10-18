"""Real signed current peers/configuration; public snapshots never grant rights."""

import copy
from datetime import UTC, datetime
import inspect

import backend.database
import pytest
from sqlalchemy import Column, MetaData, Table, create_engine, event, select, update
from sqlalchemy.orm import Session

from backend.db.installation_identity import CoreInstallationIdentity as Identity
from backend.db.installation_peer import (
    InstallationPeerInbound as Inbound,
    InstallationPeerOutbound as Outbound,
    InstallationPeerOrigin as Origin,
)
from backend.db.module import (
    ApplicationExtensionInstallation as Installation,
    ModulePackage,
)
from backend.services import installation_identity as identity_service
from backend.services import installation_peers as peers
from backend.services.installation_peer_read_sources import read_configured_peer_sources
from backend.services.application_authority_sources import _read_snapshot
from backend.services.module_packages import validate_module_package
from backend.tests.test_application_authority_review import CONFIG
from backend.tests.test_installation_peer_approval_binding import (
    pair_v2,
    activate as activate_v2,
)
from backend.tests.test_installation_peers import pair, activate_pair
from backend.tests.test_module_packages import application_package
from three_mm_protocol.tests.test_application_peer_bindings import peer_request


PRIVATE = "PRIVATE_MUST_NOT_APPEAR"


def store(core, state, direction, peer_id, *, requests=None, overrides=None):
    definition = copy.deepcopy(state.definition)
    manifest = copy.deepcopy(state.manifest)
    definition["service"]["sdk_version"] = "1.3"
    definition["peer_bindings"] = (
        requests
        if requests is not None
        else [peer_request(direction=direction, operations=["read"])]
    )
    properties = manifest["configuration_schema"]["properties"]
    properties.update(
        {
            item["peer_id_config_key"]: {"type": "string"}
            for item in definition["peer_bindings"]
        }
    )
    properties["PRIVATE_NOTE"] = {"type": "string"}
    blob = application_package(definition=definition, manifest_value=manifest)
    core.prepared = validate_module_package(blob)
    path = state.package_path.parent / (direction + "-source.zip")
    path.write_bytes(blob)
    configuration = {
        **CONFIG,
        "PRIVATE_NOTE": PRIVATE,
        "PEER_LINK": peer_id,
        **(overrides or {}),
    }
    with core.engine.begin() as db:
        db.execute(
            update(ModulePackage).values(
                sha256=core.prepared.sha256,
                size_bytes=len(blob),
                manifest=manifest,
                file_path=str(path),
            )
        )
        db.execute(update(Installation).values(configuration=configuration))
    core.peer_id = peer_id
    return core


@pytest.fixture(params=[1, 2])
def current_peers(request):
    state = request.getfixturevalue("pair_v2" if request.param == 2 else "pair")
    if request.param == 2:
        binding_id = activate_v2(state)["binding_id"]
    else:
        binding_id = activate_pair(state)
    store(state.sender, state, "outbound", state.sender.link_id)
    store(state.receiver, state, "inbound", binding_id)
    state.wire_version = request.param
    return state


def read(core, **kwargs):
    with Session(core.engine) as db:
        return read_configured_peer_sources(db, 1, core.prepared, **kwargs)


def no_effects(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail(
            "Public peer source reached private keys, network, signing, audit or execution"
        )

    for name in ("_cipher", "_load_or_create", "prove_installation_identity"):
        monkeypatch.setattr(identity_service, name, forbidden)
    for name in (
        "_load_or_create",
        "prove_installation_identity",
        "peer_http",
        "_audit",
        "_issue",
        "invoke_application",
    ):
        monkeypatch.setattr(peers, name, forbidden)


def test_both_directions_bind_actual_owner_configuration_package_and_signed_metadata(
    current_peers, monkeypatch
):
    state = current_peers
    no_effects(monkeypatch)
    outgoing = read(state.sender)[0]
    incoming = read(state.receiver)[0]
    for source, core, direction in (
        (outgoing, state.sender, "outbound"),
        (incoming, state.receiver, "inbound"),
    ):
        resource = source.binding
        assert (
            source.reviewable is False and source.permission_approval == "not_evaluated"
        )
        assert (
            resource.declaration.direction == direction
            and resource.declaration.operations == ("read",)
        )
        assert (
            resource.peer_id == core.peer_id
            and resource.application_instance_id == "a" * 24
        )
        assert resource.owner.core_installation_id == core.identity.installation_id
        assert resource.owner.application_installation_id == "1"
        assert resource.package_artifact_sha256 == core.prepared.sha256
        assert (
            resource.service_artifact_sha256
            == core.prepared.application_extension.service.artifact_sha256
        )
        assert (
            resource.peer_version == state.wire_version
            and source.observation.state == "active"
        )
        assert PRIVATE not in source.model_dump_json()
        assert not {
            "signature",
            "credential",
            "start_request",
            "completed_digest",
            "sender_challenge",
        } & set(resource.model_dump())
    assert outgoing.binding.sender_identity == incoming.binding.sender_identity
    assert outgoing.binding.receiver_identity == incoming.binding.receiver_identity
    assert outgoing.observation.remote_binding_id == state.receiver.peer_id
    assert outgoing.observation.generation is None
    assert incoming.observation.generation == 1
    assert incoming.observation.remote_binding_id is None
    if state.wire_version == 2:
        assert (
            incoming.binding.enrollment_metadata == outgoing.binding.enrollment_metadata
        )
        assert incoming.binding.consent == outgoing.binding.consent
    else:
        assert (
            incoming.binding.consent is None
            and incoming.binding.consent_revision is None
        )
        assert outgoing.binding.consent_revision == 1
        assert (
            incoming.binding.enrollment_metadata
            is outgoing.binding.enrollment_metadata
            is None
        )


PUBLIC_COLUMNS = {
    Identity.__table__: (
        "singleton_id",
        "installation_id",
        "identity_version",
        "key_generation",
        "key_id",
        "public_key",
        "created_at",
    ),
    Installation.__table__: (
        "id",
        "module_id",
        "module_package_id",
        "instance_id",
        "enabled",
        "status",
        "authority_incarnation",
        "configuration",
        "active_version",
    ),
    ModulePackage.__table__: ("id", "module_id", "version", "sha256"),
    Origin.__table__: ("singleton_id", "origin"),
    Inbound.__table__: (
        "binding_id",
        "module_id",
        "application_instance_id",
        "sender_id",
        "sender_identity",
        "receiver_identity",
        "origin",
        "request_id",
        "start_request",
        "completed_digest",
        "state",
        "generation",
        "approval_expires_at",
    ),
    Outbound.__table__: (
        "link_id",
        "module_id",
        "application_instance_id",
        "sender_identity",
        "receiver_identity",
        "origin",
        "target_module_id",
        "consent",
        "consent_revision",
        "state",
        "start_request",
        "remote_binding_id",
    ),
}


def test_missing_private_columns_and_encryption_key_prove_only_public_selects(
    current_peers, monkeypatch, tmp_path
):
    state = current_peers
    no_effects(monkeypatch)
    monkeypatch.delenv("AI_SETTINGS_MASTER_KEY")
    for direction, core in (("outbound", state.sender), ("inbound", state.receiver)):
        engine = create_engine(
            f"sqlite:///{(tmp_path / (direction + '.db')).as_posix()}"
        )
        metadata = MetaData()
        for original, names in PUBLIC_COLUMNS.items():
            table = Table(
                original.name,
                metadata,
                *(
                    Column(
                        name,
                        original.c[name].type,
                        primary_key=original.c[name].primary_key,
                    )
                    for name in names
                ),
            )
            table.create(engine)
            with core.engine.connect() as source, engine.begin() as target:
                rows = [
                    dict(row._mapping)
                    for row in source.execute(
                        select(*(original.c[name] for name in names))
                    )
                ]
                if rows:
                    target.execute(table.insert(), rows)
        statements, entities = [], []
        event.listen(
            engine,
            "before_cursor_execute",
            lambda c, cu, statement, p, ctx, many: statements.append(statement),
        )
        with Session(engine) as db:
            event.listen(
                db,
                "loaded_as_persistent",
                lambda session, entity: entities.append(entity),
            )
            monkeypatch.setattr(db, "commit", lambda: pytest.fail("Source committed"))
            monkeypatch.setattr(
                db, "rollback", lambda: pytest.fail("Source rolled back")
            )
            result = read_configured_peer_sources(db, 1, core.prepared)
            assert len(result) == 1 and result[0].binding.peer_id == core.peer_id
        assert not entities and all(
            statement.lstrip().upper().startswith("SELECT") for statement in statements
        )
        assert not any(
            token in " ".join(statements)
            for token in (
                "encrypted_private_key",
                ".credential",
                "report_projection",
                "report_result",
                "rotation_request",
                "sender_challenge",
            )
        )
        engine.dispose()


@pytest.mark.parametrize(
    "direction,state",
    [
        ("outbound", "revoked"),
        ("inbound", "revoked"),
        ("inbound", "challenged"),
        ("inbound", "renewable"),
    ],
)
def test_no_history_or_unverified_inbox_even_when_exact_id_is_configured(
    current_peers, direction, state
):
    core = current_peers.receiver if direction == "inbound" else current_peers.sender
    model = Inbound if direction == "inbound" else Outbound
    with core.engine.begin() as db:
        db.execute(update(model).values(state=state))
    with pytest.raises(
        ValueError, match="^Existing peer read sources are unavailable$"
    ):
        read(core)


@pytest.mark.parametrize(
    "change",
    [
        "instance",
        "module",
        "public_key",
        "pin",
        "start_signature",
        "start_target",
        "start_request",
        "consent",
        "remote_id",
    ],
)
def test_foreign_changed_corrupt_or_unbound_outbound_sources_refuse(
    current_peers, change
):
    core = current_peers.sender
    with Session(core.engine) as db, db.begin():
        row = db.get(Outbound, core.peer_id)
        if change == "instance":
            row.application_instance_id = "b" * 24
        elif change == "module":
            row.module_id = "org.example.foreign"
        elif change == "public_key":
            db.execute(
                update(Identity).values(created_at=datetime(2026, 1, 1, tzinfo=UTC))
            )
        elif change == "pin":
            row.receiver_identity = current_peers.sender.identity.model_dump(
                mode="json"
            )
        elif change == "consent":
            row.consent = {"node_ids": ["dev_" + "f" * 32]}
        elif change == "remote_id":
            row.remote_binding_id = None
        else:
            start = copy.deepcopy(row.start_request)
            start[
                {
                    "start_signature": "signature",
                    "start_target": "target_module_id",
                    "start_request": "request_id",
                }[change]
            ] = {
                "start_signature": "A" * 86 + "==",
                "start_target": "org.example.foreign",
                "start_request": "peer_" + "f" * 32,
            }[
                change
            ]
            row.start_request = start
    with pytest.raises(
        ValueError, match="^Existing peer read sources are unavailable$"
    ):
        read(core)


@pytest.mark.parametrize(
    "change",
    [
        "proof_missing",
        "proof_malformed",
        "origin",
        "sender_id",
        "request_id",
        "receiver_version",
        "generation",
        "incarnation",
        "artifact",
        "saved_configuration",
    ],
)
def test_incoming_needs_current_receiver_verified_state_owner_and_saved_configuration(
    current_peers, change
):
    core = current_peers.receiver
    with Session(core.engine) as db, db.begin():
        row = db.get(Inbound, core.peer_id)
        if change.startswith("proof"):
            row.completed_digest = None if change == "proof_missing" else PRIVATE
        elif change == "origin":
            db.execute(update(Origin).values(origin="https://changed.example"))
        elif change == "sender_id":
            row.sender_id = "inst_" + "f" * 32
        elif change == "request_id":
            row.request_id = "peer_" + "f" * 32
        elif change == "generation":
            row.generation = 0
        elif change == "incarnation":
            db.execute(update(Installation).values(authority_incarnation="z" * 32))
        elif change == "artifact":
            db.execute(update(ModulePackage).values(sha256="f" * 64))
        elif change == "saved_configuration":
            app = db.scalar(select(Installation))
            app.configuration = {**app.configuration, "PEER_LINK": PRIVATE}
        else:
            definition = copy.deepcopy(
                core.prepared.application_extension.model_dump(mode="json")
            )
            definition["peer_receiver"]["peer_version"] = (
                2 if current_peers.wire_version == 1 else 1
            )
            # Also supply the v2 receiver schema when switching up from v1.
            operation = next(
                item
                for item in definition["operations"]
                if item["operation_id"] == "peer_enroll"
            )
            operation["input_schema"]["properties"]["enrollment_metadata"] = {
                "type": "object"
            }
            if "enrollment_metadata" not in operation["input_schema"]["required"]:
                operation["input_schema"]["required"].append("enrollment_metadata")
            blob = application_package(
                definition=definition,
                manifest_value=core.prepared.manifest.model_dump(mode="json"),
            )
            core.prepared = validate_module_package(blob)
            db.execute(update(ModulePackage).values(sha256=core.prepared.sha256))
    with pytest.raises(
        ValueError, match="^Existing peer read sources are unavailable$"
    ) as error:
        read(core)
    assert PRIVATE not in str(error.value) and error.value.__cause__ is None


def test_complete_family_rejects_missing_or_aliased_bindings_without_partial_results(
    current_peers,
):
    core = current_peers.sender
    for selected in ("peer_" + "f" * 32, core.peer_id):
        requests = [
            peer_request(operations=["read"]),
            peer_request(
                binding_id="secondary",
                peer_id_config_key="OTHER_PEER",
                operations=["read"],
            ),
        ]
        store(
            core,
            current_peers,
            "outbound",
            core.peer_id,
            requests=requests,
            overrides={"OTHER_PEER": selected},
        )
        with pytest.raises(ValueError):
            read(core)


def test_mutation_request_cannot_be_hidden_by_a_read_request(current_peers):
    core = current_peers.sender
    store(
        core,
        current_peers,
        "outbound",
        core.peer_id,
        requests=[peer_request(operations=["read", "enroll"])],
    )
    with pytest.raises(ValueError):
        read(core)


def test_ordinary_generation_observation_does_not_change_permission_identity(
    current_peers,
):
    core = current_peers.receiver
    before = read(core)[0]
    with core.engine.begin() as db:
        db.execute(update(Inbound).values(generation=2))
    after = read(core)[0]
    assert before.binding == after.binding
    assert before.observation.generation == 1 and after.observation.generation == 2
    # The snapshot is not a credential verification or permission to use gen 2.
    assert not after.reviewable


def test_stopped_read_is_explicit_and_never_enables_the_installation(current_peers):
    core = current_peers.sender
    with core.engine.begin() as db:
        db.execute(update(Installation).values(enabled=False, status="disabled"))
    with pytest.raises(ValueError):
        read(core)
    assert len(read(core, allow_stopped=True)) == 1
    with Session(core.engine) as db:
        assert db.scalar(select(Installation.enabled)) is False
    with pytest.raises(ValueError):
        read(core, allow_stopped=1)


def test_reader_never_flushes_pending_caller_configuration_or_commits(
    current_peers, monkeypatch
):
    core = current_peers.sender
    with Session(core.engine) as db:
        app = db.scalar(select(Installation))
        original = app.configuration
        app.configuration = {**original, "PEER_LINK": "peer_" + "f" * 32}
        monkeypatch.setattr(db, "commit", lambda: pytest.fail("Committed caller work"))
        monkeypatch.setattr(
            db, "rollback", lambda: pytest.fail("Discarded caller work")
        )
        assert (
            read_configured_peer_sources(db, 1, core.prepared)[0].binding.peer_id
            == core.peer_id
        )
        assert app in db.dirty
    assert read(core)[0].binding.peer_id == core.peer_id


def test_snapshot_has_no_external_selector_and_never_includes_operational_credentials(
    current_peers,
):
    assert set(inspect.signature(read_configured_peer_sources).parameters) == {
        "db",
        "installation_id",
        "package",
        "allow_stopped",
    }
    core = current_peers.sender
    before = read(core)[0]
    with core.engine.begin() as db:
        db.execute(
            update(Outbound).values(
                credential={"PRIVATE": PRIVATE},
                report_projection={"PRIVATE": PRIVATE},
                rotation_request={"PRIVATE": PRIVATE},
            )
        )
    after = read(core)[0]
    assert after == before and PRIVATE not in after.model_dump_json()


def test_actual_core_read_snapshot_is_consistent_but_never_authority_after_close(
    current_peers,
):
    core = current_peers.sender
    with core.engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA journal_mode=WAL")
    changed = []

    def interleave(connection, cursor, statement, parameters, context, many):
        if "FROM installation_peer_outbound" in statement and not changed:
            changed.append(True)
            with core.engine.begin() as writer:
                writer.execute(update(Outbound).values(state="revoked"))

    event.listen(core.engine, "before_cursor_execute", interleave)
    try:
        with _read_snapshot(core.engine) as db:
            source = read_configured_peer_sources(db, 1, core.prepared)[0]
            assert source.observation.state == "active" and not source.reviewable
        assert changed
    finally:
        event.remove(core.engine, "before_cursor_execute", interleave)
    with pytest.raises(ValueError):
        read(core)


@pytest.mark.parametrize(
    "corruption",
    [
        "oversized_start",
        "oversized_identity",
        "oversized_config",
        "missing_key",
        "corrupt_consent_revision",
    ],
)
def test_bounded_sql_inputs_and_missing_identity_never_initialize_or_return_partial_data(
    current_peers, corruption, monkeypatch
):
    core = current_peers.sender
    with core.engine.begin() as db:
        if corruption == "oversized_start":
            db.execute(
                update(Outbound).values(
                    start_request={"PRIVATE": "X" * (128 * 1024 + 1)}
                )
            )
        elif corruption == "oversized_identity":
            db.execute(
                update(Outbound).values(receiver_identity={"PRIVATE": "X" * 4097})
            )
        elif corruption == "oversized_config":
            db.execute(
                update(Installation).values(
                    configuration={"PRIVATE": "X" * (32 * 1024 + 1)}
                )
            )
        elif corruption == "corrupt_consent_revision":
            db.execute(update(Outbound).values(consent_revision=0))
        else:
            db.execute(Identity.__table__.delete())
    no_effects(monkeypatch)
    with pytest.raises(
        ValueError, match="^Existing peer read sources are unavailable$"
    ):
        read(core)


@pytest.mark.parametrize("large", [False, True])
def test_complete_32_binding_set_is_sorted_and_total_budget_never_silently_truncates(
    current_peers, large
):
    from three_mm_protocol.installation_peer_v2 import enrollment_metadata

    core = current_peers.sender
    requests = [peer_request(operations=["read"])]
    selections = {}
    with Session(core.engine) as db, db.begin():
        original = db.get(Outbound, core.peer_id)
        for number in range(1, 32):
            link_id = "peer_" + f"{number:032x}"
            consent = {"summary_fields": ["sdk_version"]}
            if large:
                consent.update(
                    node_ids=["dev_" + f"{n:032x}" for n in range(64)],
                    node_fields=["online"],
                )
            metadata = (
                enrollment_metadata("bounded_intent", consent)
                if current_peers.wire_version == 2
                else None
            )
            start = peers._signed_start(
                db,
                link_id,
                original.target_module_id,
                current_peers.receiver.identity,
                original.origin,
                datetime.now(UTC),
                metadata,
            )
            values = {
                column.name: copy.deepcopy(getattr(original, column.name))
                for column in Outbound.__table__.columns
            }
            values.update(
                link_id=link_id,
                state="new",
                credential=None,
                remote_binding_id=None,
                consent=(
                    start.enrollment_metadata.consent.model_dump(mode="json")
                    if metadata
                    else consent
                ),
                start_request=start.model_dump(mode="json"),
            )
            db.add(Outbound(**values))
            requests.append(
                peer_request(
                    binding_id=f"item_{number:02}",
                    peer_id_config_key=f"PEER_{number}",
                    operations=["read"],
                )
            )
            selections[f"PEER_{number}"] = link_id
    store(
        core,
        current_peers,
        "outbound",
        core.peer_id,
        requests=list(reversed(requests)),
        overrides=selections,
    )
    if large:
        with pytest.raises(ValueError):
            read(core)
    else:
        sources = read(core)
        assert len(sources) == 32
        assert [source.binding.declaration.binding_id for source in sources] == sorted(
            request["binding_id"] for request in requests
        )
