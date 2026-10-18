"""Existing local status consent is a public snapshot, not a new grant."""

import base64
import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
import backend.database  # Register the same complete ORM model set as Core.
from sqlalchemy import (
    Column,
    MetaData,
    Table,
    create_engine,
    event,
    insert,
    select,
    update,
)
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from backend.db.base import Base
from backend.db.device import Device, DeviceHeartbeat, DeviceInventorySnapshot
from backend.db.installation_identity import CoreInstallationIdentity
from backend.db.installation_peer import InstallationPeerOutbound
from backend.services import installation_identity as identity_service
from backend.services import installation_projection as projection
from backend.services.installation_status_binding import read_existing_status_binding


NOW = datetime(2026, 10, 16, 12, 0, 0, tzinfo=UTC)
LINK = "peer_" + "a" * 32
NODE = "dev_" + "a" * 32
OTHER_NODE = "dev_" + "b" * 32
MODULE = "org.example.status-client"
INSTANCE = "c" * 24


def public_identity(character, identifier):
    raw = character.encode() * 32
    return {
        "identity_version": 1,
        "installation_id": "inst_" + identifier * 32,
        "algorithm": "ed25519",
        "key_id": hashlib.sha256(raw).hexdigest(),
        "public_key": base64.b64encode(raw).decode(),
        "key_generation": 1,
        "created_at": NOW.isoformat().replace("+00:00", "Z"),
    }


SENDER = public_identity("p", "1")
RECEIVER = public_identity("q", "2")


class CallerBase(DeclarativeBase):
    pass


class StoredCaller(CallerBase):
    __tablename__ = "status_test_caller"
    id: Mapped[int] = mapped_column(primary_key=True)
    enabled: Mapped[bool]
    status: Mapped[str]
    module_id: Mapped[str]
    instance_id: Mapped[str]


@pytest.fixture
def status_database(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'status.db').as_posix()}",
        connect_args={"timeout": 0.1},
    )
    public = MetaData()
    # Deliberately omit ALL private peer columns and the Core private key.
    # An ORM entity read or a credentials/proof access fails at the SQL boundary.
    selections = {
        CoreInstallationIdentity.__table__: (
            "singleton_id",
            "installation_id",
            "identity_version",
            "key_generation",
            "key_id",
            "public_key",
            "created_at",
        ),
        InstallationPeerOutbound.__table__: (
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
        ),
    }
    for source, names in selections.items():
        Table(
            source.name,
            public,
            *(
                Column(
                    name, source.c[name].type, primary_key=source.c[name].primary_key
                )
                for name in names
            ),
        )
    public.create_all(engine)
    CallerBase.metadata.create_all(engine)
    Base.metadata.create_all(
        engine,
        tables=[
            Device.__table__,
            DeviceHeartbeat.__table__,
            DeviceInventorySnapshot.__table__,
        ],
    )
    with engine.begin() as connection:
        connection.execute(
            insert(CoreInstallationIdentity.__table__).values(
                singleton_id=1,
                created_at=NOW,
                **{
                    key: value
                    for key, value in SENDER.items()
                    if key not in {"algorithm", "created_at"}
                },
            )
        )
        connection.execute(
            insert(InstallationPeerOutbound.__table__).values(
                link_id=LINK,
                module_id=MODULE,
                application_instance_id=INSTANCE,
                sender_identity=SENDER,
                receiver_identity=RECEIVER,
                origin="https://receiver.example",
                target_module_id="org.example.receiver",
                consent={"summary_fields": ["sdk_version", "core_version"]},
                consent_revision=3,
                state="active",
            )
        )
    statements = []

    @event.listens_for(engine, "before_cursor_execute")
    def capture(_connection, _cursor, statement, parameters, _context, _many):
        statements.append((statement, parameters))

    try:
        yield SimpleNamespace(
            engine=engine,
            statements=statements,
            app=SimpleNamespace(
                enabled=True, status="active", module_id=MODULE, instance_id=INSTANCE
            ),
        )
    finally:
        engine.dispose()


def forbid_key_work(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Status read attempted private key work or identity initialization")

    monkeypatch.delenv("AI_SETTINGS_MASTER_KEY", raising=False)
    for name in ("_cipher", "_load_or_create", "_decode_identity"):
        monkeypatch.setattr(identity_service, name, forbidden)
    monkeypatch.setattr(identity_service.Ed25519PrivateKey, "generate", forbidden)


def change_link(fixture, **changes):
    with fixture.engine.begin() as connection:
        connection.execute(
            update(InstallationPeerOutbound.__table__)
            .where(
                InstallationPeerOutbound.link_id == LINK,
            )
            .values(**changes)
        )


def test_binding_reader_has_only_public_selects_no_key_or_transaction_side_effects(
    status_database,
    monkeypatch,
):
    fixture = status_database
    forbid_key_work(monkeypatch)
    with Session(fixture.engine) as db:
        with monkeypatch.context() as patch:

            def forbidden(*_args, **_kwargs):
                pytest.fail("Status snapshot attempted writes or transaction control")

            for name in ("get", "add", "flush", "commit", "rollback"):
                patch.setattr(db, name, forbidden)
            fixture.statements.clear()
            binding = read_existing_status_binding(db, fixture.app, LINK)
            assert binding.sender_identity.model_dump(mode="json") == SENDER
            assert binding.receiver_identity.model_dump(mode="json") == RECEIVER
            assert binding.consent_revision == 3
            assert binding.consent.summary_fields == ("sdk_version", "core_version")
            assert len(fixture.statements) == 2
            for statement, _parameters in fixture.statements:
                assert (
                    statement.lstrip().upper().startswith("SELECT ")
                    and "*" not in statement
                )
                assert all(
                    word not in statement
                    for word in (
                        "encrypted_private_key",
                        "credential",
                        "start_request",
                        "complete_request",
                        "report_projection",
                        "report_result",
                        "rotation_request",
                    )
                )


def test_binding_reader_does_not_flush_the_callers_pending_work(status_database):
    fixture = status_database
    with Session(fixture.engine) as db:
        pending = Device(
            device_id=NODE,
            display_name="pending",
            role="node",
            protocol_version="1.0",
            approved_at=NOW,
        )
        db.add(pending)
        fixture.statements.clear()
        read_existing_status_binding(db, fixture.app, LINK)
        assert pending in db.new and len(fixture.statements) == 2
        db.expunge(pending)


def test_expired_caller_attributes_do_not_flush_unrelated_pending_work(
    status_database,
    monkeypatch,
):
    fixture = status_database
    with Session(fixture.engine) as db:
        app = StoredCaller(id=1, **vars(fixture.app))
        db.add(app)
        db.commit()
        # All application attributes are now expired. The validation itself
        # must not let SQLAlchemy flush an unrelated pending device first.
        pending = Device(
            device_id=NODE, role="node", protocol_version="1.0", approved_at=NOW
        )
        db.add(pending)
        with monkeypatch.context() as patch:

            def forbidden(*_args, **_kwargs):
                pytest.fail("Expired caller validation autoflushed unrelated work")

            patch.setattr(db, "flush", forbidden)
            result = read_existing_status_binding(db, app, LINK)
            assert result.application_instance_id == INSTANCE and pending in db.new
        db.expunge(pending)


@pytest.mark.parametrize(
    "changes",
    [
        {"state": "revoked"},
        {"state": "corrupt"},
        {"module_id": "org.example.foreign"},
        {"application_instance_id": "d" * 24},
        {"origin": "http://receiver.example"},
        {"origin": "https://receiver.example/path"},
        {"origin": "https://receiver.example:443"},
        {"target_module_id": "invalid"},
        {"consent_revision": 0},
        {"consent_revision": 2**53},
        {"consent_revision": 1.5},
        {"consent": {"consent_version": True}},
        {"consent": {"consent_version": "1"}},
        {"consent": {"consent_version": 1.0}},
        {"consent": {"unknown": []}},
        {"consent": {"summary_fields": "core_version"}},
        {"consent": {"summary_fields": ["core_version", "core_version"]}},
        {"consent": {"node_ids": [NODE]}},
        {"consent": {"node_ids": [NODE] * 65, "node_fields": ["online"]}},
        {"consent": {"node_ids": [NODE], "node_fields": ["credential"]}},
        {"sender_identity": {**SENDER, "installation_id": "inst_" + "3" * 32}},
        {"sender_identity": {**SENDER, "created_at": "2026-10-16T12:00:01+00:00"}},
        {"receiver_identity": {**RECEIVER, "key_id": "0" * 64}},
        {"receiver_identity": {**RECEIVER, "key_generation": 1.0}},
        {"receiver_identity": {**RECEIVER, "private_key": "never allowed"}},
    ],
)
def test_binding_reader_refuses_foreign_withdrawn_or_corrupt_state(
    status_database, changes
):
    fixture = status_database
    change_link(fixture, **changes)
    with Session(fixture.engine) as db, pytest.raises(ValueError):
        read_existing_status_binding(db, fixture.app, LINK)


@pytest.mark.parametrize(
    "attribute,value",
    [
        ("enabled", False),
        ("status", "disabled"),
        ("module_id", "org.example.foreign"),
        ("instance_id", "d" * 24),
        ("instance_id", "invalid"),
    ],
)
def test_binding_reader_cannot_reuse_another_application_incarnation(
    status_database, attribute, value
):
    fixture = status_database
    setattr(fixture.app, attribute, value)
    with Session(fixture.engine) as db, pytest.raises(ValueError):
        read_existing_status_binding(db, fixture.app, LINK)


@pytest.mark.parametrize(
    "link_id", [None, 1, "all", "peer_" + "b" * 32, LINK + "/status"]
)
def test_binding_reader_requires_one_exact_existing_link(status_database, link_id):
    with Session(status_database.engine) as db, pytest.raises(ValueError):
        read_existing_status_binding(db, status_database.app, link_id)


def test_missing_public_identity_is_not_created_or_repaired(
    status_database, monkeypatch
):
    fixture = status_database
    with fixture.engine.begin() as connection:
        connection.execute(CoreInstallationIdentity.__table__.delete())
    forbid_key_work(monkeypatch)
    with (
        Session(fixture.engine) as db,
        pytest.raises(identity_service.InstallationIdentityError),
    ):
        read_existing_status_binding(db, fixture.app, LINK)
    with fixture.engine.connect() as connection:
        assert (
            connection.execute(select(CoreInstallationIdentity.singleton_id)).all()
            == []
        )


def test_both_projection_paths_need_no_private_columns_key_or_inner_commit(
    status_database, monkeypatch
):
    fixture = status_database
    forbid_key_work(monkeypatch)
    with Session(fixture.engine) as db:
        expected = read_existing_status_binding(db, fixture.app, LINK)

        def forbidden(*_args, **_kwargs):
            pytest.fail("Projection changed its caller's transaction")

        with monkeypatch.context() as patch:
            patch.setattr(db, "commit", forbidden)
            patch.setattr(db, "rollback", forbidden)
            result = projection.bound_installation_projection(
                db, fixture.app, expected, now=NOW
            )
            legacy = projection.installation_projection(db, fixture.app, LINK, now=NOW)
            assert legacy == result
            assert result.installation_id == SENDER["installation_id"]
            assert result.consent_revision == 3 and result.nodes == ()
            assert tuple(result.summary) == ("sdk_version", "core_version")
        db.commit()


def test_bound_projection_refuses_pending_writes_without_autoflush(status_database):
    fixture = status_database
    with Session(fixture.engine) as db:
        expected = read_existing_status_binding(db, fixture.app, LINK)
        pending = Device(
            device_id=NODE, role="node", protocol_version="1.0", approved_at=NOW
        )
        db.add(pending)
        fixture.statements.clear()
        with pytest.raises(ValueError, match="clean session"):
            projection.bound_installation_projection(db, fixture.app, expected)
        assert pending in db.new and not fixture.statements
        db.expunge(pending)


@pytest.mark.parametrize(
    "changes",
    [
        {"state": "revoked"},
        {"consent_revision": 4},
        {"consent": {"summary_fields": ["core_version"]}},
        {"origin": "https://another.example"},
        {"target_module_id": "org.example.another"},
        {"receiver_identity": public_identity("r", "3")},
        {"application_instance_id": "d" * 24},
        {"module_id": "org.example.foreign"},
    ],
)
def test_changed_binding_refuses_before_projecting_any_device_data(
    status_database, monkeypatch, changes
):
    fixture = status_database
    with Session(fixture.engine) as db:
        expected = read_existing_status_binding(db, fixture.app, LINK)
    change_link(fixture, **changes)

    def forbidden(*_args, **_kwargs):
        pytest.fail("Projection ran after its binding changed")

    monkeypatch.setattr(projection, "_project_consented_status", forbidden)
    with Session(fixture.engine) as db, pytest.raises(ValueError):
        projection.bound_installation_projection(db, fixture.app, expected, now=NOW)


def test_public_core_identity_change_refuses_an_old_snapshot(status_database):
    fixture = status_database
    with Session(fixture.engine) as db:
        expected = read_existing_status_binding(db, fixture.app, LINK)
    with fixture.engine.begin() as connection:
        connection.execute(
            update(CoreInstallationIdentity.__table__).values(
                installation_id="inst_" + "4" * 32,
            )
        )
    with (
        Session(fixture.engine) as db,
        pytest.raises(ValueError, match="identity changed"),
    ):
        projection.bound_installation_projection(db, fixture.app, expected)


def test_binding_is_not_a_caller_selected_receiver_or_consent(status_database):
    fixture = status_database
    with Session(fixture.engine) as db:
        expected = read_existing_status_binding(db, fixture.app, LINK)
        forged = replace(expected, origin="https://caller.example")
        with pytest.raises(ValueError, match="binding changed"):
            projection.bound_installation_projection(db, fixture.app, forged)


def test_selected_nodes_and_fields_are_filtered_before_inventory_queries(
    status_database,
):
    fixture = status_database
    change_link(fixture, consent={"node_ids": [NODE], "node_fields": ["display_name"]})
    with fixture.engine.begin() as connection:
        for identifier, name in ((NODE, "Selected"), (OTHER_NODE, "Hidden device")):
            result = connection.execute(
                insert(Device.__table__).values(
                    device_id=identifier,
                    display_name=name,
                    role="node",
                    protocol_version="1.0",
                    approved_at=NOW,
                )
            )
            device_id = result.inserted_primary_key[0]
            connection.execute(
                insert(DeviceInventorySnapshot.__table__).values(
                    device_id=device_id,
                    inventory={"credential": "fixture-secret", "architecture": "arm64"},
                    received_at=NOW,
                )
            )
            connection.execute(
                insert(DeviceHeartbeat.__table__).values(
                    device_id=device_id,
                    protocol_version="1.0",
                    payload={"token": "fixture-secret"},
                    received_at=NOW,
                )
            )
    with Session(fixture.engine) as db:
        expected = read_existing_status_binding(db, fixture.app, LINK)
        fixture.statements.clear()
        result = projection.bound_installation_projection(
            db, fixture.app, expected, now=NOW
        )
        assert len(result.nodes) == 1 and result.nodes[0].device_id == NODE
        assert tuple(result.nodes[0].fields) == ("display_name",)
        assert result.nodes[0].fields["display_name"].value == "Selected"
        assert (
            "Hidden device" not in result.model_dump_json()
            and "fixture-secret" not in result.model_dump_json()
        )
        device_queries = [
            (sql, params) for sql, params in fixture.statements if "FROM devices" in sql
        ]
        assert len(device_queries) == 1 and device_queries[0][1] == (NODE,)
        assert all(
            "device_inventory_snapshots" not in sql and "device_heartbeats" not in sql
            for sql, _ in fixture.statements
        )


@pytest.mark.parametrize("withdrawal", ["revoke", "consent"])
def test_local_withdrawal_serializes_with_the_entire_projection(
    status_database, withdrawal
):
    fixture = status_database
    with Session(fixture.engine) as reader:
        expected = read_existing_status_binding(reader, fixture.app, LINK)
        reader.rollback()
        result = projection.bound_installation_projection(
            reader, fixture.app, expected, now=NOW
        )
        assert result.consent_revision == 3
        # Independent real SQLite connection cannot withdraw while the read
        # transaction holds the same outbound row lock as the peer writers.
        changes = (
            {"state": "revoked"}
            if withdrawal == "revoke"
            else {"consent_revision": 4, "consent": {}}
        )
        with pytest.raises(OperationalError, match="locked"):
            change_link(fixture, **changes)
        reader.commit()
        change_link(fixture, **changes)
        with pytest.raises(ValueError):
            projection.bound_installation_projection(
                reader, fixture.app, expected, now=NOW
            )
        reader.rollback()
