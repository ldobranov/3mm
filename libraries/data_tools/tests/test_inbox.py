"""Real disposable, application-owned SQLite; human and worker resolve their own scope."""
import json
import sqlite3

import pytest
from application_data_tools.inbox import Audience, Inbox, InboxError, InboxLimits, initialize
from packages.application_sdk import ApplicationMigration, ApplicationStorage


TOPIC = "report.ready"
def ref(n): return format(n, "032x")
def account(name):
    def resolve(db):
        row = db.execute("SELECT subject,revision FROM example_acl WHERE subject=? AND allowed=1",(name,)).fetchone()
        return Audience(*row) if row else None
    return resolve


def migrate(db):
    db.execute("CREATE TABLE example_acl(subject TEXT PRIMARY KEY, revision INTEGER, allowed INTEGER)")
    initialize(db)


@pytest.fixture
def storage(tmp_path):
    store = ApplicationStorage(tmp_path/"own-data")
    store.migrate([ApplicationMigration("0001",migrate)],"0001")
    with store.transaction() as db:
        db.executemany("INSERT INTO example_acl VALUES(?,1,1)",[("alice",),("bob",)])
    return store


def enable(box,db,name):
    box.set_preference(db,account(name),TOPIC,True,expected=box.preference(db,account(name),TOPIC)["revision"])
    return box.capture_consent(db,account(name),TOPIC)


def publish(box,db,name,consent,n,*,now=100,start=100,end=300):
    return box.publish(db,account(name),topic=TOPIC,consent=consent,event_ref=ref(n),resource_ref=ref(n+500),
                       now=now,available=start,expires=end)


def test_scheduled_visible_only_to_current_recipient_and_no_duplicate_or_read_side_effect(storage):
    box = Inbox([TOPIC])
    with storage.transaction() as db:
        assert publish(box,db,"alice",None,1) == "not_subscribed"
        a,b = enable(box,db,"alice"), enable(box,db,"bob")
        assert publish(box,db,"alice",b,1) == "not_subscribed"
        assert publish(box,db,"alice",a,1,start=110) == "scheduled"
        assert publish(box,db,"bob",b,1) == "available"
        assert box.page(db,account("alice"),now=109) == {"items":[],"next":None}
    with storage.transaction() as db:
        writes = db.total_changes
        alice = box.page(db,account("alice"),now=110)["items"]
        bob = box.page(db,account("bob"),now=110)["items"]
        assert db.total_changes == writes
        assert len(alice) == len(bob) == 1 and alice[0]["id"] != bob[0]["id"]
        assert alice[0] == {"id":alice[0]["id"],"topic":TOPIC,"resource_ref":ref(501),"available":110,"state":"unread"}
        assert box.mark(db,account("bob"),notice_id=alice[0]["id"],state="dismissed",now=111) == "not_visible"
        for action, state in (("read","read"),("acknowledged","acknowledged"),("read","acknowledged"),("dismissed","dismissed")):
            assert box.mark(db,account("alice"),notice_id=alice[0]["id"],state=action,now=111) == state
        assert publish(box,db,"alice",a,1,now=112,start=110) == "already_recorded"
        assert box.page(db,account("alice"),now=112)["items"] == []
        assert len(box.page(db,account("bob"),now=112)["items"]) == 1
        with pytest.raises(InboxError,match="reference_conflict"):
            publish(box,db,"alice",a,1,now=112,start=111)
        assert box.page(db,account("bob"),now=300)["items"] == []  # expiry does not require a worker


def test_durable_intent_must_keep_original_consent_after_disable_reenable_or_acl_change(storage):
    box = Inbox([TOPIC])
    with storage.transaction() as db:
        old = enable(box,db,"alice")
        assert old == enable(box,db,"alice") and publish(box,db,"alice",old,1) == "available"
        box.set_preference(db,account("alice"),TOPIC,False,expected=old)
        with pytest.raises(InboxError,match="preference_changed"):
            box.set_preference(db,account("alice"),TOPIC,True,expected=None)
        assert box.page(db,account("alice"),now=102)["items"] == []
        new = enable(box,db,"alice")
        assert new != old
    with storage.transaction() as db:
        assert publish(box,db,"alice",old,1) == "not_subscribed"
        assert publish(box,db,"alice",new,2) == "available"
        db.execute("UPDATE example_acl SET allowed=0 WHERE subject='alice'")
        for fn in (lambda: box.page(db,account("alice"),now=102), lambda: publish(box,db,"alice",new,3)):
            with pytest.raises(InboxError,match="inbox_unavailable"): fn()
        db.execute("UPDATE example_acl SET allowed=1,revision=2 WHERE subject='alice'")
        assert box.page(db,account("alice"),now=102)["items"] == []
        assert publish(box,db,"alice",new,2) == "not_subscribed"
        assert enable(box,db,"alice") not in (old,new)
        assert db.execute("SELECT count(*) FROM inbox_entries").fetchone()[0] == 0


def test_budget_survives_expiry_and_rollbacks_and_is_not_shared_between_recipients(storage):
    box = Inbox([TOPIC],InboxLimits(per_minute=1, per_recipient=2,total=2,preferences=2))
    with storage.transaction() as db:
        a,b = enable(box,db,"alice"), enable(box,db,"bob")
        assert publish(box,db,"alice",a,1,end=102) == "available"
        box.prune_expired(db,now=103)
        box.set_preference(db,account("alice"),TOPIC,False,expected=a)
        a = enable(box,db,"alice")
        assert publish(box,db,"alice",a,2,now=104) == "rate_limited"
        assert publish(box,db,"alice",a,1,now=104,end=102) == "expired"
        assert publish(box,db,"bob",b,1) == "available"
        assert publish(box,db,"alice",a,3,now=161) == "available"
        assert publish(box,db,"bob",b,4,now=161) == "capacity_limited"
        box.erase_recipient(db,account("alice"))
        assert publish(box,db,"alice",a,3,now=161) == "not_subscribed"
    with pytest.raises(RuntimeError), storage.transaction() as db:
        assert publish(box,db,"bob",b,4,now=161) == "available"
        raise RuntimeError("fixture rolls back a business update")
    with storage.transaction() as db:
        assert publish(box,db,"bob",b,4,now=161) == "available"
        assert len(box.page(db,account("bob"),now=161)["items"]) == 2
        assert [db.execute(f"SELECT count(*) FROM {t} WHERE recipient='alice'").fetchone()[0]
                for t in ("inbox_preferences","inbox_budgets","inbox_entries")] == [0,0,0]


def test_pages_and_actions_use_only_the_current_registered_topics_and_scope(storage):
    box = Inbox([TOPIC])
    with storage.transaction() as db:
        a,b = enable(box,db,"alice"), enable(box,db,"bob")
        for n in range(5):
            publish(box,db,"alice",a,n)
            publish(box,db,"bob",b,n)
        page = box.page(db,account("alice"),now=111,limit=3)
        second = box.page(db,account("alice"),now=111,after=page["next"],limit=3)
        assert [r["resource_ref"] for r in page["items"]+second["items"]] == [ref(500+n) for n in reversed(range(5))]
        assert second["next"] is None
        with pytest.raises(InboxError,match="invalid_cursor"):
            box.page(db,account("bob"),now=111,after=page["next"])
        other = Inbox(["other.topic"])
        assert other.page(db,account("alice"),now=111)["items"] == []
        assert other.mark(db,account("alice"),notice_id=page["next"],state="acknowledged",now=111) == "not_visible"
    with sqlite3.connect(storage.database_path) as raw, pytest.raises(InboxError,match="application_transaction_required"):
        box.set_preference(raw,account("alice"),TOPIC,False,expected=None)


def test_reads_and_state_changes_obey_real_scoped_storage_mode_and_admission(storage):
    from packages.application_sdk.scoped_relational import (
        ApplicationScopedStorage, ApplicationRelationalStorageError, _TransactionAdmission,
    )
    from packages.protocol.application_extension import ApplicationRelationalStorageV1
    cfg = ApplicationRelationalStorageV1(contract_version=1,mode="read_write",limit_class="cooperative_v1",
        max_database_bytes=16*1024*1024,auxiliary_pause_bytes=1024*1024,max_statement_bytes=4096,
        max_value_bytes=8192,max_result_bytes=65536,max_result_rows=64,max_transaction_ms=5000,max_busy_ms=500)
    def scoped(allowed):
        return ApplicationScopedStorage(storage.database_path.parent,declaration=cfg,schema_revision="0001",
            admit=(lambda tid,mode,profile,deadline:_TransactionAdmission(tid,mode,profile,deadline)) if allowed else None)
    box = Inbox([TOPIC])
    client = scoped(True)
    with client.transaction() as tx:
        assert publish(box,tx,"alice",enable(box,tx,"alice"),1) == "available"
    with client.read_transaction() as tx:
        notice, = box.page(tx,account("alice"),now=101)["items"]
        assert box.page(tx,account("bob"),now=101)["items"] == []
        assert box.export_metadata(tx, account("alice"))["items"][0]["id"] == notice["id"]
    with pytest.raises(ApplicationRelationalStorageError), client.read_transaction() as tx:
        box.mark(tx,account("alice"),notice_id=notice["id"],state="dismissed",now=101)
    with pytest.raises(ApplicationRelationalStorageError), scoped(False).read_transaction() as tx:
        box.export_metadata(tx,account("alice"))
    with client.read_transaction() as tx:
        assert box.page(tx,account("alice"),now=101)["items"][0]["state"] == "unread"


def test_subject_export_shows_retained_metadata_without_reviving_dismissed_or_expired_notices(storage):
    box = Inbox([TOPIC, "other.topic"])
    with storage.transaction() as db:
        own, other = enable(box,db,"alice"), enable(box,db,"bob")
        hidden = box.set_preference(db,account("alice"),"other.topic",False,expected=None)
        publish(box,db,"alice",own,1,end=120)
        publish(box,db,"alice",own,2,start=280)
        publish(box,db,"alice",own,3)
        publish(box,db,"bob",other,4)
        own_id = box.page(db,account("alice"),now=101)["items"][0]["id"]
        assert box.mark(db,account("alice"),notice_id=own_id,state="dismissed",now=101) == "dismissed"
        assert box.page(db,account("alice"),now=160)["items"] == []
        before = db.total_changes
        first = box.export_metadata(db,account("alice"),limit=2)
        rest = box.export_metadata(db,account("alice"),limit=2,after=first["next"])
        assert first["scope"] == "current_recipient_inbox_metadata"
        assert first["preferences"] == [{"topic":"other.topic","enabled":False},{"topic":TOPIC,"enabled":True}]
        entries = first["items"] + rest["items"]
        assert [(r["state"],r["available"],r["expires"]) for r in entries] == [
            ("dismissed",100,300),("unread",280,300),("unread",100,120)]
        assert all(set(row) == {"id","topic","state","created","available","expires"} for row in entries)
        assert rest["next"] is None and len({row["id"] for row in entries}) == 3
        for private in (own, other, hidden["revision"], "alice","bob",ref(501),ref(2),ref(4)):
            assert private not in json.dumps([first,rest])
        with pytest.raises(InboxError,match="invalid_cursor"):
            box.export_metadata(db,account("bob"),after=first["next"])
        assert db.total_changes == before
    with storage.transaction() as db:
        db.execute("UPDATE example_acl SET allowed=0 WHERE subject='alice'")
        with pytest.raises(InboxError,match="inbox_unavailable"):
            box.export_metadata(db,account("alice"),after=first["next"])
        db.execute("UPDATE example_acl SET allowed=1,revision=2 WHERE subject='alice'")
        assert box.export_metadata(db,account("alice"))["preferences"] == []
        assert box.export_metadata(db,account("alice"))["items"] == []
        with pytest.raises(InboxError,match="invalid_cursor"):
            box.export_metadata(db,account("alice"),after=first["next"])
        box.erase_recipient(db,account("alice"))
        assert box.export_metadata(db,account("alice"))["items"] == []
        assert len(box.export_metadata(db,account("bob"))["items"]) == 1
