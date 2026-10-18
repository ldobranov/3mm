"""Public listing source boundary; never grants scoped peer execution."""

import base64
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    event,
    func,
    select,
    update,
)
from sqlalchemy.orm import DeclarativeBase, Session

from backend.services import installation_peers as peers
from backend.services.installation_peer_listing import public_peer_records
from three_mm_protocol.installation_peer import (
    PeerEnrollmentStartV1,
    ProjectionConsentV1,
)
from three_mm_protocol.installation_peer_v2 import enrollment_metadata, peer_model
from three_mm_protocol.tests.test_installation_identity import (
    identity_and_key,
    proof_request,
)


MODULE = "org.example.peer-reference"
NOW = datetime(2026, 10, 16, 12, tzinfo=UTC)


class ListingBase(DeclarativeBase):
    pass


class PendingNote(ListingBase):
    __tablename__ = "listing_pending_note"
    id = Column(Integer, primary_key=True)


class CallerApplication(ListingBase):
    __tablename__ = "listing_caller"
    id = Column(Integer, primary_key=True)
    module_id = Column(String, nullable=False)


def wire(version):
    sender, _ = identity_and_key()
    receiver, _ = identity_and_key()
    receiver = receiver.model_copy(update={"installation_id": "inst_" + "b" * 32})
    metadata = enrollment_metadata(
        "opaque_reference", ProjectionConsentV1(summary_fields=("core_version",)), 3
    )
    value = peer_model(PeerEnrollmentStartV1, version)(
        request_id="peer_" + "a" * 32,
        target_module_id=MODULE,
        sender=sender,
        receiver=receiver,
        receiver_challenge=proof_request(),
        signature=base64.b64encode(bytes(64)).decode(),
        **({"enrollment_metadata": metadata} if version == 2 else {}),
    )
    return value.model_dump(mode="json")


@pytest.fixture
def listing(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'listing.db').as_posix()}")
    schema = MetaData()
    # No Core identity/key, private inbound credential/challenge, report cache or
    # other unused peer columns exist: entity reads would fail, not merely leak.
    inbound = Table(
        "installation_peer_inbound",
        schema,
        Column("binding_id", String, primary_key=True),
        Column("module_id", String),
        Column("sender_identity", JSON),
        Column("state", String),
        Column("generation", Integer),
        Column("approval_expires_at", DateTime),
        Column("start_request", JSON),
        Column("completed_digest", String),
        Column("created_at", DateTime),
    )
    outbound = Table(
        "installation_peer_outbound",
        schema,
        Column("link_id", String, primary_key=True),
        Column("module_id", String),
        Column("state", String),
        Column("consent_revision", Integer),
        Column("consent", JSON),
        Column("origin", String),
        Column("receiver_identity", JSON),
        Column("target_module_id", String),
        Column("remote_binding_id", String),
        Column("start_request", JSON),
        Column("credential", JSON),
        Column("created_at", DateTime),
    )
    schema.create_all(engine)
    ListingBase.metadata.create_all(engine)
    state = SimpleNamespace(
        engine=engine,
        inbound=inbound,
        outbound=outbound,
        app=SimpleNamespace(module_id=MODULE),
    )
    yield state
    engine.dispose()


def seed(state, version=1, *, inbound_state="active", completed=True, credential=None):
    start = wire(version)
    incoming = dict(
        binding_id="peer_" + "b" * 32,
        module_id=MODULE,
        sender_identity=start["sender"],
        state=inbound_state,
        generation=2,
        approval_expires_at=NOW,
        start_request=start,
        completed_digest="c" * 64 if completed else None,
        created_at=NOW,
    )
    outgoing = dict(
        link_id="peer_" + "a" * 32,
        module_id=MODULE,
        state="revoked",
        consent_revision=3,
        consent={
            "consent_version": 1,
            "summary_fields": ["core_version"],
            "node_ids": [],
            "node_fields": [],
        },
        origin="https://receiver.example",
        receiver_identity=start["receiver"],
        target_module_id=MODULE,
        remote_binding_id=incoming["binding_id"],
        start_request=start,
        credential=credential,
        created_at=NOW,
    )
    with state.engine.begin() as db:
        db.execute(state.inbound.insert().values(**incoming))
        db.execute(state.outbound.insert().values(**outgoing))
    return incoming, outgoing


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize(
    "credential",
    [
        None,
        {},
        {"claims": {}},
        {"claims": {"expires_at": None}},
        {
            "claims": {"expires_at": "2026-10-17T12:00:00Z"},
            "signature": "PRIVATE_CREDENTIAL_SENTINEL",
        },
    ],
)
def test_public_queries_preserve_exact_legacy_v1_v2_response_without_entities(
    listing, monkeypatch, version, credential
):
    incoming, outgoing = seed(listing, version, credential=credential)
    expected = {
        "inbound": [peers._inbound_status(SimpleNamespace(**incoming))],
        "outbound": [peers.outbound_status(SimpleNamespace(**outgoing))],
    }

    def forbidden(*_args, **_kwargs):
        pytest.fail("Listing touched signing, initialization, network or audit")

    for name in (
        "_load_or_create",
        "prove_installation_identity",
        "peer_http",
        "_audit",
    ):
        monkeypatch.setattr(peers, name, forbidden)
    queries, columns = [], []

    def observe(_connection, cursor, sql, _parameters, _context, _many):
        queries.append(sql)
        columns.extend(item[0] for item in (cursor.description or ()))

    event.listen(listing.engine, "after_cursor_execute", observe)
    try:
        with Session(listing.engine) as db:
            actual = peers.list_peers(db, listing.app)
            assert not db.identity_map  # No peer ORM entities or hidden columns.
    finally:
        event.remove(listing.engine, "after_cursor_execute", observe)
    assert actual == expected
    assert len(queries) == 2 and all(
        query.lstrip().upper().startswith("SELECT") for query in queries
    )
    assert not {
        "credential",
        "report_projection",
        "report_result",
        "rotation_request",
        "sender_challenge",
    } & set(columns)
    assert "credential_expires_at" in columns
    assert "PRIVATE_CREDENTIAL_SENTINEL" not in str(actual)


@pytest.mark.parametrize(
    "state,completed,visible",
    [
        ("challenged", False, False),
        ("pending", False, False),
        ("pending", True, True),
        ("active", True, True),
        ("revoked", True, False),
        ("renewable", True, False),
    ],
)
def test_verified_v2_metadata_keeps_its_original_proof_state_boundary(
    listing, state, completed, visible
):
    seed(listing, 2, inbound_state=state, completed=completed)
    with Session(listing.engine) as db:
        result = peers.list_peers(db, listing.app)
    assert bool(result["inbound"][0]["verified_metadata"]) is visible
    assert result["inbound"][0]["state"] == state


def test_listing_preserves_bounded_module_history_order_and_foreign_filter(listing):
    incoming, outgoing = seed(listing)
    with listing.engine.begin() as db:
        for n in range(1, 105):
            when = NOW + timedelta(seconds=n)
            db.execute(
                listing.inbound.insert().values(
                    **{**incoming, "binding_id": f"peer_{n:032x}", "created_at": when}
                )
            )
            db.execute(
                listing.outbound.insert().values(
                    **{**outgoing, "link_id": f"peer_{n:032x}", "created_at": when}
                )
            )
        db.execute(
            listing.inbound.insert().values(
                **{
                    **incoming,
                    "binding_id": "peer_" + "f" * 32,
                    "module_id": "org.example.foreign",
                    "created_at": NOW + timedelta(days=1),
                }
            )
        )
        db.execute(
            listing.outbound.insert().values(
                **{
                    **outgoing,
                    "link_id": "peer_" + "f" * 32,
                    "module_id": "org.example.foreign",
                    "created_at": NOW + timedelta(days=1),
                }
            )
        )
    with Session(listing.engine) as db:
        result = peers.list_peers(db, listing.app)
    assert len(result["inbound"]) == len(result["outbound"]) == 100
    assert result["outbound"][0]["link_id"] == f"peer_{104:032x}"
    assert result["inbound"][-1]["binding_id"] == f"peer_{5:032x}"
    assert all(row["state"] == "revoked" for row in result["outbound"])
    assert "peer_" + "f" * 32 not in str(result)


def test_expired_caller_attribute_does_not_flush_pending_work_or_commit(listing):
    seed(listing)
    with Session(listing.engine) as db:
        db.add(CallerApplication(id=1, module_id=MODULE))
        db.commit()
        application = db.get(CallerApplication, 1)
        db.expire(application, ["module_id"])
        pending = PendingNote(id=1)
        db.add(pending)
        before = db.get_transaction()
        incoming, outgoing = public_peer_records(db, application)
        assert len(incoming) == len(outgoing) == 1
        assert pending in db.new and db.get_transaction() is before
        assert (
            db.connection().scalar(select(func.count()).select_from(PendingNote)) == 0
        )
        assert db.in_transaction()
        db.rollback()
    with listing.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(PendingNote)) == 0


def test_invalid_v2_metadata_remains_a_refusal_not_an_empty_approved_list(listing):
    _, outgoing = seed(listing, 2)
    outgoing["start_request"]["enrollment_metadata"]["metadata_hash"] = "f" * 64
    with listing.engine.begin() as db:
        db.execute(
            update(listing.outbound).values(start_request=outgoing["start_request"])
        )
    with Session(listing.engine) as db, pytest.raises(ValueError):
        peers.list_peers(db, listing.app)


@pytest.mark.parametrize(
    "expiry",
    [
        True,
        123,
        {},
        [],
        {"private": "PRIVATE_SENTINEL"},
        "PRIVATE_SENTINEL",
        "2026-10-17T12:00:00",
        "x" * 1000,
    ],
)
def test_malformed_expiry_never_becomes_an_arbitrary_public_payload(listing, expiry):
    seed(listing, credential={"claims": {"expires_at": expiry}})
    with Session(listing.engine) as db, pytest.raises(ValueError) as error:
        peers.list_peers(db, listing.app)
    assert "PRIVATE_SENTINEL" not in str(error.value)
