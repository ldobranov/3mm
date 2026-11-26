"""Exercise the actual vendored wheel and two independent app DB connections."""
from contextlib import closing
from importlib import import_module
import io
from pathlib import Path
from runpy import run_path
import sqlite3
from types import SimpleNamespace
import zipfile

import pytest
from packages.application_sdk import ApplicationStorage
from application_data_tools.inbox import Audience, InboxError


@pytest.fixture(scope="module")
def worker(tmp_path_factory):
    from sys import modules, path
    root = Path(__file__).resolve().parents[1] / "examples/report_task"
    blob = run_path(str(root / "build_reference.py"))["build_package"]()
    wheel = tmp_path_factory.mktemp("table-report") / "service.whl"
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        wheel.write_bytes(z.read(next(n for n in z.namelist() if n.endswith(".whl"))))
    assert not any(k.split('.')[0] == 'report_example' for k in modules)
    path.insert(0, str(wheel))
    try:
        yield import_module("report_example.service"), import_module("report_example.migrations")
    finally:
        path.remove(str(wheel))
        for mod in list(modules):
            if mod.split('.')[0] == 'report_example':
                del modules[mod]


@pytest.fixture
def scenario(tmp_path, worker):
    service, migrations = worker
    storage = ApplicationStorage(tmp_path / "owned")
    storage.migrate(migrations.get_migrations(), "0001")
    ref = "a" * 32
    with storage.transaction() as db:
        db.execute("INSERT INTO report_subjects VALUES('alpha',1,1,2)")
        db.execute("INSERT INTO report_items VALUES('alpha',1,'private scoped content',3)")
        db.execute("INSERT INTO report_requests(ref,subject_ref,access_revision,data_revision) VALUES(?,'alpha',1,2)", (ref,))
    platform = SimpleNamespace(task_progress=lambda *_: None)
    app = SimpleNamespace(storage=storage, platform=platform)
    task = SimpleNamespace(task_id="render_table", task_run_id="task_"+"1"*32)
    context = SimpleNamespace(audience="internal", task_execution=task)
    return storage, platform, service, service.create_service(app), task, context, ref


@pytest.mark.parametrize("change", ["revoke", "edit", "erase"])
def test_changed_business_authority_between_render_and_publication_blocks_output(scenario, change):
    storage, platform, _, service, task, context, ref = scenario
    def while_rendering(execution, progress):
        assert execution is task and progress == 50
        # Represents an independent legitimate change, without being blocked by the render.
        with closing(sqlite3.connect(storage.database_path, timeout=.05)) as other, other:
            if change == "revoke":
                other.execute("UPDATE report_subjects SET allowed=0,access_revision=2")
            elif change == "edit":
                other.execute("UPDATE report_subjects SET data_revision=3")
            else:
                other.execute("DELETE FROM report_requests")
    platform.task_progress = while_rendering
    with pytest.raises(ValueError, match="report_not_available"):
        service.handle("render_table", {"report_ref":ref}, context)
    with storage.transaction() as db:
        assert db.execute("SELECT COUNT(*) FROM report_requests WHERE content IS NOT NULL").fetchone()[0] == 0


def test_completed_report_cannot_change_owner_and_is_not_readable_after_revocation(scenario):
    storage, platform, module, service, _, context, ref = scenario
    result = service.handle("render_table", {"report_ref":ref}, context)
    platform.task_progress = lambda *_: pytest.fail("A completed original is not regenerated")
    assert service.handle("render_table", {"report_ref":ref}, context) == result
    with storage.transaction() as db:
        assert b"private scoped content" in module.read_for_subject(db, current_subject="alpha", ref=ref)
        with pytest.raises(ValueError, match="report_not_available"):
            module.read_for_subject(db, current_subject="beta", ref=ref)
        with pytest.raises(sqlite3.IntegrityError, match="new_report_request_required"):
            db.execute("UPDATE report_requests SET subject_ref='beta'")
        db.execute("UPDATE report_subjects SET allowed=0,access_revision=2")
        with pytest.raises(ValueError, match="report_not_available"):
            module.read_for_subject(db, current_subject="alpha", ref=ref)
    with pytest.raises(ValueError, match="report_not_available"):
        service.handle("render_table", {"report_ref":ref}, context)


def current_subject(subject):
    def resolve(db):
        row = db.execute("SELECT access_revision FROM report_subjects WHERE subject_ref=? AND allowed=1",
                         (subject,)).fetchone()
        return Audience(subject, row[0]) if row else None
    return resolve


@pytest.fixture
def delivery(scenario):
    import importlib.util
    source = Path(__file__).resolve().parents[1] / "examples/report_task/notice_integration.py"
    spec = importlib.util.spec_from_file_location("report_notice_example", source)
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    storage, _, _, render, _, ctx, old = scenario
    ref = "b" * 32
    with storage.transaction() as db:
        adapter.migrate(db)  # do not recreate or retroactively subscribe existing reports
        db.execute("INSERT INTO report_requests(ref,subject_ref,access_revision,data_revision) VALUES(?,'alpha',1,2)",(ref,))
        db.execute("INSERT INTO report_subjects VALUES('other',1,1,1)")
    return adapter, storage, current_subject("alpha"), ref, old, lambda: render.handle("render_table", {"report_ref":ref}, ctx)


def test_review_is_not_a_subscription_and_cannot_retroactively_enroll_old_work(delivery):
    n, store, viewer, ref, old, render = delivery
    with store.transaction() as db:
        assert n.remember(db,current_audience=viewer,ref=ref,now=10) == "not_subscribed"
        n.INBOX.set_preference(db,viewer,n.TOPIC,True,expected=None)
        assert n.remember(db,current_audience=viewer,ref=ref,now=11) == "not_subscribed"
        assert n.remember(db,current_audience=viewer,ref=old,now=11) == "not_requested"
        with pytest.raises(InboxError,match="report_not_available"):
            n.read_status(db,current_audience=current_subject("other"),ref=ref,now=12)
    render()
    with store.transaction() as db:
        assert n.deliver_original(db,ref,now=12) == "not_scheduled"
        assert not n.INBOX.page(db,viewer,now=12)["items"]


@pytest.mark.parametrize("change,expected", [("off_on","not_subscribed"),("revoke","not_eligible"),
    ("edit","not_eligible"),("erase","not_scheduled"),("timeout","expired")])
def test_delivery_uses_original_consent_and_current_report_or_does_nothing(delivery,change,expected):
    n, store, viewer, ref, _, render = delivery
    with store.transaction() as db:
        original = n.INBOX.set_preference(db,viewer,n.TOPIC,True,expected=None)["revision"]
        assert n.remember(db,current_audience=viewer,ref=ref,now=10) == "waiting"
    render()
    with store.transaction() as db:
        if change == "off_on":
            off = n.INBOX.set_preference(db,viewer,n.TOPIC,False,expected=original)
            n.INBOX.set_preference(db,viewer,n.TOPIC,True,expected=off["revision"])
        elif change == "revoke":
            db.execute("UPDATE report_subjects SET allowed=0,access_revision=2 WHERE subject_ref='alpha'")
        elif change == "edit":
            db.execute("UPDATE report_subjects SET data_revision=3 WHERE subject_ref='alpha'")
        elif change == "erase":
            db.execute("DELETE FROM report_requests WHERE ref=?",(ref,))
            db.execute("INSERT INTO report_requests(ref,subject_ref,access_revision,data_revision) VALUES(?,'alpha',1,2)",(ref,))
        now = 10+n.RETENTION if change=="timeout" else 15
        assert n.deliver_original(db,ref,now=now) == expected
        assert db.execute("SELECT count(*) FROM inbox_entries").fetchone()[0] == 0


def test_notification_and_receipt_commit_together_after_render_and_erasure_cleans_both(delivery):
    n, store, viewer, ref, _, render = delivery
    with store.transaction() as db:
        n.INBOX.set_preference(db,viewer,n.TOPIC,True,expected=None)
        assert n.remember(db,current_audience=viewer,ref=ref,now=10) == "waiting"
        assert n.deliver_original(db,ref,now=15) == "waiting"
        db.execute("""CREATE TRIGGER fixture_cancel BEFORE UPDATE OF status ON report_notices
                      BEGIN SELECT RAISE(ABORT,'fixture_rollback'); END""")
    render()
    with pytest.raises(sqlite3.IntegrityError,match="fixture_rollback"),store.transaction() as db:
        n.deliver_original(db,ref,now=15)
    with store.transaction() as db:
        assert not n.INBOX.page(db,viewer,now=15)["items"]
        db.execute("DROP TRIGGER fixture_cancel")
        assert n.deliver_original(db,ref,now=16) == "recorded"
    with store.transaction() as db:
        assert n.deliver_original(db,ref,now=17) == "recorded"
        notices = n.INBOX.page(db,viewer,now=17)["items"]
        assert [x["resource_ref"] for x in notices] == [ref]
        assert n.read_status(db,current_audience=viewer,ref=ref,now=17) == {
            "state":"recorded","attempts":1,"retry_not_before":None}
        db.execute("DELETE FROM report_requests WHERE ref=?",(ref,))
        assert not n.INBOX.page(db,viewer,now=17)["items"]
        assert not db.execute("SELECT 1 FROM report_notices WHERE ref=?",(ref,)).fetchone()


def test_retries_have_deadline_budget_and_are_never_consumed_by_status_reads(delivery):
    from application_data_tools.inbox import Inbox, InboxLimits
    n, store, viewer, ref, _, render = delivery
    n.INBOX = Inbox([n.TOPIC], InboxLimits(per_recipient=1,total=1,per_minute=2))
    with store.transaction() as db:
        consent = n.INBOX.set_preference(db,viewer,n.TOPIC,True,expected=None)["revision"]
        assert n.remember(db,current_audience=viewer,ref=ref,now=10) == "waiting"
        assert n.INBOX.publish(db,viewer,topic=n.TOPIC,consent=consent,event_ref="9"*32,resource_ref="7"*32,
                               now=10,available=10,expires=1000) == "available"
    render()
    with store.transaction() as db:
        for at,attempts,next_due,state in ((10,1,70,"deferred"),(12,1,70,"deferred"),(70,2,190,"deferred"),
                                           (190,3,None,"limited"),(310,3,None,"limited")):
            assert n.deliver_original(db,ref,now=at) == state
            before = db.total_changes
            assert n.read_status(db,current_audience=viewer,ref=ref,now=at) == {
                "state":state,"attempts":attempts,"retry_not_before":next_due}
            assert db.total_changes == before
        n.prune(db,now=10+n.RETENTION)
        assert n.deliver_original(db,ref,now=10+n.RETENTION) == "not_scheduled"


def test_retry_window_is_claimed_once_only_for_the_current_deferred_original(delivery):
    from application_data_tools.inbox import Inbox, InboxLimits
    n, store, viewer, ref, _, render = delivery
    n.INBOX = Inbox([n.TOPIC],InboxLimits(per_recipient=1,total=1))
    with store.transaction() as db:
        n.migrate_retry_windows(db)
        token = n.INBOX.set_preference(db,viewer,n.TOPIC,True,expected=None)["revision"]
        assert n.remember(db,current_audience=viewer,ref=ref,now=1000) == "waiting"
        assert n.INBOX.publish(db,viewer,topic=n.TOPIC,consent=token,event_ref="8"*32,resource_ref="7"*32,
                               now=1000,available=1000,expires=4000) == "available"
        assert n.claim_retry_window(db,current_audience=viewer,ref=ref,now=1000) is None
    render()
    def claim(db, at=1000):
        return n.claim_retry_window(db,current_audience=viewer,ref=ref,now=at)
    with store.transaction() as db:
        assert n.deliver_original(db,ref,now=1000) == "deferred"
        assert claim(db,500) is None
    with pytest.raises(RuntimeError,match="rolled back"),store.transaction() as db:
        lost = claim(db)
        raise RuntimeError("rolled back")
    with store.transaction() as db:
        with pytest.raises(InboxError,match="report_not_available"):
            n.claim_retry_window(db,current_audience=current_subject("other"),ref=ref,now=1000)
        plan = claim(db)
        assert plan["request_id"] != lost["request_id"] and plan["max_occurrences"] == 2
        assert int(plan["start_at"].timestamp()) == 1060
        assert claim(db) is None
        assert n.retry_lookup_key(db,current_audience=viewer,ref=ref,now=1000) == plan["request_id"]
        n.INBOX.set_preference(db,viewer,n.TOPIC,False,expected=token)
        assert n.retry_lookup_key(db,current_audience=viewer,ref=ref,now=1000) is None
        assert claim(db) is None


def test_retry_window_never_exceeds_remaining_attempts_or_original_expiry(delivery):
    from application_data_tools.inbox import Inbox, InboxLimits
    n, store, viewer, ref, _, render = delivery
    n.INBOX = Inbox([n.TOPIC],InboxLimits(per_recipient=1,total=1))
    with store.transaction() as db:
        n.migrate_retry_windows(db)
        token = n.INBOX.set_preference(db,viewer,n.TOPIC,True,expected=None)["revision"]
        assert n.remember(db,current_audience=viewer,ref=ref,now=10) == "waiting"
    render()
    end = 10 + n.RETENTION
    with store.transaction() as db:
        assert n.INBOX.publish(db,viewer,topic=n.TOPIC,consent=token,event_ref="8"*32,resource_ref="7"*32,
                               now=end-200,available=end-200,expires=end+60) == "available"
        assert n.deliver_original(db,ref,now=end-190) == "deferred"
        assert n.deliver_original(db,ref,now=end-130) == "deferred"
        plan = n.claim_retry_window(db,current_audience=viewer,ref=ref,now=end-130)
        assert plan["max_occurrences"] == plan["history_limit"] == 1
        assert int(plan["end_at"].timestamp()) == end
        assert n.deliver_original(db,ref,now=end) == "expired"
        assert n.retry_lookup_key(db,current_audience=viewer,ref=ref,now=end) is None
