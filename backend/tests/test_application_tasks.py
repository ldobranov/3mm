"""Real scoped SDK + separate packaged worker + native application process."""
from datetime import UTC, datetime, timedelta
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import uuid
import zipfile

import pytest
from sqlalchemy import select, update, func
from sqlalchemy.orm import Session
from backend.db.module import ApplicationExtensionInstallation as Installation, ModulePackage
from backend.db.application_task import ApplicationTaskRun as Run
from backend.artifacts.packages import validate_module_package
from backend.applications.tasks import broker as tasks
from backend.applications.tasks.broker import claim_task, dispatch_task, finish_task
from backend.tests.test_application_command_discovery import installed, source_subject, source_installed, vertical, identity
from backend.tests.test_application_consent import preview, allow
from backend.config import ApplicationRuntimeSettings
from examples.task_probe import TaskProbe
from packages.application_sdk import ApplicationPlatformClient, ApplicationPlatformError
from components.system_runtime.application_activation import _application_metadata
from components.system_runtime.application_transport import ApplicationServiceClient, ApplicationTransportError
from components.platform_runtime.tasks import TaskWorker

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Real Unix peers, sealed authority and processes")
REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def native_task_host(tmp_path_factory):
    from deployment.application_host_component import build_component, validate_artifact
    blob, metadata = build_component(REPO)
    _, files = validate_artifact(blob, hashlib.sha256(blob).hexdigest())
    root = tmp_path_factory.mktemp("native-task-host")
    for name, data in files.items():
        path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
    probe = subprocess.run([sys.executable, "-I", "-S", str(root / "host.pyz"), "--component-info"],
        check=True, capture_output=True, text=True)
    assert json.loads(probe.stdout)["build_id"] == metadata["build_id"]
    return root / "host.pyz"


def load_builder():
    spec = importlib.util.spec_from_file_location("task_builder", REPO / "modules/task-probe/build_package.py")
    builder = importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)
    return builder


@pytest.fixture
def task_state(vertical, tmp_path, request, native_task_host):
    s = vertical
    variant = getattr(request, "param", None)
    s.builder = load_builder(); command_mode = variant == "commands"
    if callable(variant):
        blob, scopes = variant()
        assert variant() == (blob, scopes)
    else:
        blob = s.builder.build_package(with_command=command_mode)
        assert s.builder.build_package(with_command=command_mode) == blob
        scopes = ["command:output", "task:switch_output"] if command_mode else ["task:calculate"]
    s.validated = validate_module_package(blob)
    s.archive = s.root / "modules" / (s.validated.sha256 + ".zip"); s.archive.write_bytes(blob)
    s.configuration = {"OUTPUT_DEVICE_ID":"dev_"+"3"*32} if command_mode else {}
    with s.engine.begin() as db:
        db.execute(update(ModulePackage).where(ModulePackage.id == 1).values(module_id=s.validated.manifest.module_id,
            version=s.validated.manifest.version, manifest=s.validated.manifest.model_dump(mode="json"),
            sha256=s.validated.sha256, size_bytes=len(blob), file_path=str(s.archive)))
        db.execute(update(Installation).where(Installation.id == 1).values(module_id=s.validated.manifest.module_id,
            active_version=s.validated.manifest.version, configuration=s.configuration))
    if command_mode:
        from sqlalchemy import delete
        from backend.db.device import Device,DeviceCapabilityProvider,DeviceCapabilityHealth
        from backend.devices.capabilities.registry import capability_catalog
        spec=importlib.util.spec_from_file_location("digital_builder",REPO/"modules/digital-output/build_package.py")
        output=importlib.util.module_from_spec(spec);spec.loader.exec_module(output)
        s.output_blob=output.build_package(versioned=True)
        contract=output.versioned_manifest()["registrations"][0]["contract"]
        with s.engine.begin() as db:
            db.execute(update(DeviceCapabilityProvider).values(provider_type="native",provider_id="org.example.first",
                capabilities=[{"capability_id":"gpio.digital.control","metadata":{},"contract":contract}]))
            db.execute(delete(DeviceCapabilityHealth))
        with Session(s.engine) as db,db.begin():
            offer=capability_catalog(db,db.get(Device,1))[0]
            db.add(DeviceCapabilityHealth(device_id=1,provider_type=offer.provider_type,provider_id=offer.provider_id,
                observed_at=datetime.now(UTC),expires_at=datetime.now(UTC)+timedelta(minutes=5),report={
                    "declaration_digest":offer.declaration_digest,"capabilities":[{"capability_id":offer.capability_id,"healthy":True}]}))
    consent = preview(s)
    assert consent["scopes"] == scopes
    allow(s, consent, scopes=scopes)
    s.task_probe = TaskProbe(s.sdk)
    s.application_root = s.runtime_socket.parent / "apps"; s.instance = s.application_root / ("a" * 24)
    release = s.instance / "releases" / s.validated.sha256; release.mkdir(parents=True)
    with zipfile.ZipFile(s.archive) as archive:
        (release / "service.whl").write_bytes(archive.read(s.validated.application_extension.service.artifact))
    metadata = _application_metadata(s.validated, s.configuration, "a" * 24, s.application_root)
    metadata["platform_socket"] = str(s.runtime_socket)
    (s.instance / "active.json").write_text(json.dumps(metadata))
    (s.instance / "run").mkdir()
    with s.engine.begin() as db:
        db.execute(update(Installation).where(Installation.id == 1).values(socket_path=str(s.instance / "run/service.sock")))
    s.processes = []
    def cleanup():
        for process in reversed(s.processes):
            if process.poll() is None: process.terminate()
            try: process.wait(timeout=3)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=3)
            process.stderr.close()
    request.addfinalizer(cleanup)
    def host():
        process = subprocess.Popen([sys.executable, "-I", "-S", str(native_task_host), "--instance", "a" * 24,
            "--root", str(s.application_root), "--key-root", str(s.runtime_socket.parent)], cwd=REPO,
            env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        s.processes.append(process)
        deadline = time.monotonic() + 5
        while True:
            try:
                assert ApplicationServiceClient(s.instance / "run/service.sock", b"s" * 32, 1).invoke("health", {},
                    {"audience": "internal", "correlation_id": "task-health"}) == {"status": "ready"}
                return process
            except ApplicationTransportError:
                assert process.poll() is None, process.stderr.read().decode()
                assert time.monotonic() < deadline
                time.sleep(.02)
    def worker():
        process = subprocess.Popen([sys.executable, "-I", str(s.runtime_socket.parent / "runtime.pyz"), "--task-worker",
            "--authority-socket", str(s.server.socket_path), "--core-uid", str(os.geteuid()),
            '--readiness-socket', str(s.runtime_socket.parent/'task.sock')], cwd=tmp_path,
            env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        s.processes.append(process)
        return process
    s.start_host, s.start_worker = host, worker
    s.host = host()
    s.settings = ApplicationRuntimeSettings(key_root=s.runtime_socket.parent)
    yield s


def _report_reference():
    from runpy import run_path
    builder = run_path(str(REPO / "libraries/data_tools/examples/report_task/build_reference.py"))
    return builder["build_package"](), ["task:render_table"]


def _notice_worker_reference():
    """Disposable assembly only: no production app gets a task or a new grant."""
    from runpy import run_path
    example = REPO / "libraries/data_tools/examples/report_task"
    builder = run_path(str(example / "build_reference.py"))
    sources, manifest, descriptor = builder["reference_parts"]()
    for member, path in (("notice_integration.py", example / "notice_integration.py"),
                         ("data_tools/inbox.py", example.parents[1] / "application_data_tools/inbox.py")):
        sources["report_example/" + member] = path.read_bytes().replace(b"\r\n", b"\n")
    sources["report_example/notice_worker.py"] = b"""from packages.application_sdk import ApplicationMigration
from .migrations import get_migrations as base
from .notice_integration import migrate, migrate_retry_windows, run_delivery_task
from .service import Service

def get_migrations():
    return [*base(), ApplicationMigration("0002", migrate), ApplicationMigration("0003", migrate_retry_windows)]

class Probe(Service):
    def handle(self, operation_id, payload, context):
        if operation_id == "deliver_notice":
            return run_delivery_task(self.app, payload, context)
        return super().handle(operation_id, payload, context)

def create_service(application):
    return Probe(application)
"""
    notice = "deliver_notice"
    manifest["module_id"] = descriptor["module_id"] = "org.example.notice-probe"
    descriptor["service"]["entrypoint"] = "report_example.notice_worker:create_service"
    descriptor["storage"].update(schema_revision="0003", migration_entrypoint="report_example.notice_worker:get_migrations")
    descriptor["tasks"][0].update(task_id=notice, handler_operation_id=notice)
    descriptor["operations"][1].update(operation_id=notice, output_schema=builder["obj"]({"state": {"type": "string", "maxLength": 24,
        "enum": ["not_scheduled", "waiting", "deferred", "expired", "not_eligible", "not_subscribed", "recorded", "limited"]}}))
    return builder["pack"](sources, manifest, descriptor), ["task:" + notice]


@pytest.mark.parametrize("task_state", [_notice_worker_reference], indirect=True)
def test_native_delayed_inbox_delivery_rechecks_consent_after_scheduling(task_state, monkeypatch):
    from runpy import run_path
    s = task_state
    lib = REPO / "libraries/data_tools"
    monkeypatch.syspath_prepend(str(lib))
    inbox = run_path(str(lib / "examples/report_task/notice_integration.py"))
    path = s.instance / "data/state.sqlite3"
    refs = {owner: uuid.uuid4().hex for owner in ("approved", "opted-out", "revoked")}
    subs = {}
    def audience(name):
        return lambda db: inbox["Audience"](name, 1)
    with sqlite3.connect(path) as db:
        db.execute("BEGIN IMMEDIATE")
        for owner, ref in refs.items():
            db.execute("INSERT INTO report_subjects VALUES(?,1,1,1)", (owner,))
            db.execute("INSERT INTO report_requests(ref,subject_ref,access_revision,data_revision) VALUES(?,?,1,1)", (ref, owner))
            subs[owner] = inbox["INBOX"].set_preference(db,audience(owner),inbox["TOPIC"],True,expected=None)["revision"]
            assert inbox["remember"](db,current_audience=audience(owner),ref=ref,now=int(time.time())) == "waiting"
            # The render is accepted separately. Only the completed synthetic report's marker matters here.
            db.execute("UPDATE report_requests SET original_run=?,sha256=? WHERE ref=?", (uuid.uuid4().hex,"a"*64,ref))
    due = datetime.now(UTC) + timedelta(seconds=1)
    originals = {}
    for owner, ref in refs.items():
        key = originals[owner] = identity()
        result = s.sdk.submit_task("deliver_notice",request_id=key,payload={"report_ref":ref},
                                   due_at=due,not_after=due+timedelta(seconds=25))
        assert result["status"] == "queued"
    with sqlite3.connect(path) as db:
        db.execute("BEGIN IMMEDIATE")
        assert db.execute("SELECT count(*) FROM inbox_entries").fetchone()[0] == 0
        inbox["INBOX"].set_preference(db,audience("opted-out"),inbox["TOPIC"],False,expected=subs["opted-out"])
        db.execute("UPDATE report_subjects SET allowed=0,access_revision=2 WHERE subject_ref='revoked'")
    worker = s.start_worker()
    for owner, state in (("approved","recorded"),("opted-out","not_subscribed"),("revoked","not_eligible")):
        deadline = time.monotonic()+40
        while True:
            row = s.sdk.lookup_task("deliver_notice",request_id=originals[owner])
            if row["status"] not in ("queued","running"):
                break
            assert worker.poll() is None and time.monotonic()<deadline, row
            time.sleep(.12)
        assert (row["status"],row["result"]) == ("succeeded",{"state":state})
        assert s.sdk.lookup_task("deliver_notice",request_id=originals[owner])["result"] == {"state":state}
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT recipient,resource_ref FROM inbox_entries").fetchall() == [("approved",refs["approved"])]
        assert db.execute("SELECT subject,attempts FROM report_notices ORDER BY subject").fetchall() == [
            ("approved",1),("opted-out",0),("revoked",0)]


@pytest.mark.parametrize("task_state", [_notice_worker_reference], indirect=True)
def test_original_deferred_notice_gets_one_bounded_real_retry_window(task_state, monkeypatch):
    """Local rate limit clears; admission ACK lost; observe original only; no second publication."""
    from runpy import run_path
    from packages.application_sdk import ApplicationStorage
    s = task_state
    lib = REPO / "libraries/data_tools"
    monkeypatch.syspath_prepend(str(lib))
    n = run_path(str(lib / "examples/report_task/notice_integration.py"))
    storage = ApplicationStorage(s.instance/"data")
    current = lambda db: n["Audience"]("probe",1)
    ref = uuid.uuid4().hex
    at = int(time.time())-59  # authenticated fixture history, not a clock override in the worker
    with storage.transaction() as db:
        db.execute("INSERT INTO report_subjects VALUES('probe',1,1,1)")
        db.execute("INSERT INTO report_requests(ref,subject_ref,access_revision,data_revision) VALUES(?,'probe',1,1)",(ref,))
        token = n["INBOX"].set_preference(db,current,n["TOPIC"],True,expected=None)["revision"]
        assert n["remember"](db,current_audience=current,ref=ref,now=at) == "waiting"
        assert n["claim_retry_window"](db,current_audience=current,ref=ref,now=at) is None
        for _ in range(n["INBOX"].limits.per_minute):
            assert n["INBOX"].publish(db,current,topic=n["TOPIC"],consent=token,event_ref=uuid.uuid4().hex,
                resource_ref=uuid.uuid4().hex,now=at,available=at,expires=at+900) == "available"
        db.execute("UPDATE report_requests SET original_run=?,sha256=? WHERE ref=?", (uuid.uuid4().hex,"b"*64,ref))
        assert n["deliver_original"](db,ref,now=at) == "deferred"
    with storage.transaction() as db:
        plan = n["claim_retry_window"](db,current_audience=current,ref=ref,now=int(time.time()))
        assert plan["max_occurrences"] == 2 and plan["payload"] == {"report_ref":ref}
    s.sdk.create_task_schedule(**plan)  # reply deliberately unused by the caller
    with storage.transaction() as db:
        common = dict(current_audience=current,ref=ref,now=int(time.time()))
        assert n["claim_retry_window"](db,**common) is None
        original = n["retry_lookup_key"](db,**common)
    assert original == plan["request_id"]
    worker = s.start_worker()
    deadline = time.monotonic()+25
    while True:
        observed = s.sdk.lookup_task_schedule("deliver_notice",request_id=original)
        if observed["last_request_id"]:
            run = s.sdk.lookup_task("deliver_notice",request_id=observed["last_request_id"])
            if run["status"] not in ("queued","running"):
                break
        assert worker.poll() is None and time.monotonic() < deadline, observed
        time.sleep(.1)
    assert observed["admitted"] == 1 and run["result"] == {"state":"recorded"} and run["status"] == "succeeded"
    with storage.transaction() as db:
        assert n["read_status"](db,current_audience=current,ref=ref,now=int(time.time()))["attempts"] == 2
        assert db.execute("SELECT count(*) FROM inbox_entries WHERE event_ref=?",(ref,)).fetchone()[0] == 1
        assert n["deliver_original"](db,ref,now=int(time.time())) == "recorded"
        n["INBOX"].set_preference(db,current,n["TOPIC"],False,expected=token)
        assert n["retry_lookup_key"](db,current_audience=current,ref=ref,now=int(time.time())) is None


@pytest.mark.parametrize("task_state", [_report_reference], indirect=True)
def test_scoped_printable_table_stays_in_app_while_real_worker_returns_only_a_receipt(task_state, monkeypatch):
    s = task_state
    path = s.instance / "data/state.sqlite3"
    alpha, revoked = uuid.uuid4().hex, uuid.uuid4().hex
    # Only the app-side test client imports this optional source library.
    # The real packaged host/worker and platform SDK do not get inbox access.
    from runpy import run_path
    monkeypatch.syspath_prepend(str(REPO/"libraries/data_tools"))
    n = run_path(str(REPO/"libraries/data_tools/examples/report_task/notice_integration.py"))
    def current(name):
        def resolve(db):
            row = db.execute("SELECT access_revision FROM report_subjects WHERE allowed=1 AND subject_ref=?", (name,)).fetchone()
            return n["Audience"](name, row[0]) if row else None
        return resolve
    with sqlite3.connect(path) as db:
        db.execute("BEGIN IMMEDIATE")
        n["migrate"](db)
        db.executemany("INSERT INTO report_subjects VALUES(?,?,?,?)", [("alpha",1,1,1),("beta",1,1,1)])
        db.executemany("INSERT INTO report_items VALUES(?,?,?,?)",
                       [("alpha",1,"Reviewed <label>",7),("beta",1,"Other subject private",15)])
        db.executemany("INSERT INTO report_requests(ref,subject_ref,access_revision,data_revision) VALUES(?,?,1,1)",
                       [(alpha,"alpha"),(revoked,"beta")])
        for name, ref in (("alpha",alpha),("beta",revoked)):
            n["INBOX"].set_preference(db,current(name),n["TOPIC"],True,expected=None)
            assert n["remember"](db,current_audience=current(name),ref=ref,now=10) == "waiting"
    worker = s.start_worker()
    def submit(reference):
        key = identity()
        due = datetime.now(UTC) + timedelta(seconds=.3)
        s.sdk.submit_task("render_table", request_id=key, payload={"report_ref":reference},
                          due_at=due, not_after=due + timedelta(seconds=9))
        return key
    def lookup(key):
        limit = time.monotonic() + 14
        while True:
            result = s.sdk.lookup_task("render_table", request_id=key)
            if result["status"] not in ("queued", "running"):
                return result
            assert worker.poll() is None and time.monotonic() < limit, result
            time.sleep(.08)
    key = submit(alpha)
    first = lookup(key)
    assert first["status"] == "succeeded", first
    with sqlite3.connect(path) as db:
        content, original = db.execute("SELECT content,original_run FROM report_requests WHERE ref=?", (alpha,)).fetchone()
        assert b"Reviewed &lt;label&gt;" in content and b"Other subject" not in content
        assert first["result"] == {"rows":1,"size_bytes":len(content),"sha256":hashlib.sha256(content).hexdigest()}
        assert lookup(key)["result"] == first["result"]  # lost response: observe only the same run
        db.execute("UPDATE report_subjects SET allowed=0, access_revision=2 WHERE subject_ref='beta'")
    assert lookup(submit(alpha))["status"] == "failed"  # different task cannot take over a reviewed intent
    assert lookup(submit(revoked))["status"] == "failed"
    with sqlite3.connect(path) as db:
        db.execute("BEGIN IMMEDIATE")
        assert db.execute("SELECT content,original_run FROM report_requests WHERE ref=?", (revoked,)).fetchone() == (None,None)
        assert db.execute("SELECT content,original_run FROM report_requests WHERE ref=?", (alpha,)).fetchone() == (content,original)
        assert n["deliver_original"](db,alpha,now=20) == "recorded"
        assert n["deliver_original"](db,revoked,now=20) == "not_eligible"
    with sqlite3.connect(path) as db:
        db.execute("BEGIN IMMEDIATE")
        assert n["deliver_original"](db,alpha,now=21) == "recorded"
        item, = n["INBOX"].page(db,current("alpha"),now=21)["items"]
        assert item == {"id":item["id"],"topic":"report.ready","resource_ref":alpha,"available":20,"state":"unread"}
        assert db.execute("SELECT count(*) FROM inbox_entries").fetchone()[0] == 1


def test_resource_observation_uses_native_host_and_live_worker_without_scheduling_a_task(task_state, monkeypatch):
    import backend.config as config
    from backend.applications.resources import providers
    s = task_state
    settings = config.get_settings()
    monkeypatch.setattr(config, 'get_settings', lambda:settings.model_copy(update={'applications':
        settings.applications.model_copy(update={'task_worker_socket':s.runtime_socket.parent/'task.sock'})}))
    monkeypatch.setattr(providers, '_uid', lambda _:os.geteuid())
    worker = s.start_worker()
    deadline = time.monotonic()+5
    while True:
        row = s.sdk.discover_resources(['task:calculate'])['resources'][0]
        if row['readiness'] == 'ready': break
        assert worker.poll() is None, worker.stderr.read().decode() if worker.poll() is not None else ''
        assert time.monotonic() < deadline, row
        time.sleep(.05)
    with Session(s.engine) as db: assert db.scalar(select(func.count()).select_from(Run)) == 0
    worker.terminate(); worker.wait(timeout=3)
    assert s.sdk.discover_resources(['task:calculate'])['resources'][0]['readiness'] == 'unavailable'


def schedule(s, *, request_id=None, upper=100, pause_ms=0, delay=.15):
    due = datetime.now(UTC) + timedelta(seconds=delay)
    key = request_id or identity()
    # Persist before send. Recovery uses this original ID and never schedule().
    (s.root / "task-intent.json").write_text(json.dumps({"request_id": key, "upper": upper}))
    response = s.task_probe.schedule(request_id=key, upper=upper, pause_ms=pause_ms,
        due_at=due, not_after=due + timedelta(seconds=5))
    return key, response


def wait(s, request_id, states=("succeeded",), seconds=5):
    deadline = time.monotonic() + seconds
    while True:
        response = s.task_probe.lookup(request_id)
        if response["status"] in states: return response
        assert time.monotonic() < deadline, response
        time.sleep(.03)


def attempts(s):
    with sqlite3.connect(s.instance / "data/state.sqlite3") as db:
        return db.execute("SELECT COUNT(*) FROM task_probe_attempts").fetchone()[0]


def recurring(s, *, request_id=None, start=None, end=None, every=5, count=3, history=2, window=5, pause_ms=0):
    start=start or datetime.now(UTC)+timedelta(seconds=.2)
    key=request_id or identity()
    body=dict(task_id="calculate",request_id=key,payload={"upper":100,"pause_ms":pause_ms},
        rule={"kind":"interval","every_seconds":every},start_at=start,
        end_at=end or start+timedelta(seconds=60),max_occurrences=count,history_limit=history,start_window_seconds=window)
    return key,s.sdk.create_task_schedule(**body),body


def wait_schedule(s,key,condition,seconds=16):
    limit=time.monotonic()+seconds
    while True:
        result=s.sdk.lookup_task_schedule("calculate",request_id=key)
        if condition(result):return result
        assert time.monotonic()<limit,result
        time.sleep(.05)


def tick_current(s, body, *, due=None):
    from backend.applications.tasks.schedules import tick_schedule,poll_schedules
    from packages.platform_wire.task_time import latest_occurrence
    plan=next(p for p in poll_schedules(s.engine) if p["schedule_id"]==body["schedule_id"])
    candidate=due or latest_occurrence(plan["rule"],plan["start_at"],plan["end_at"],tasks.now())
    return tick_schedule(s.engine,schedule_id=plan["schedule_id"],request_hash=plan["request_hash"],due_at=candidate.isoformat())


def test_interval_worker_retention_restart_and_occurrence_namespace(task_state):
    s=task_state;s.start_worker()
    key,accepted,_=recurring(s)
    first=wait_schedule(s,key,lambda r:r["admitted"]==1)["last_request_id"]
    completed=wait_schedule(s,key,lambda r:r["status"]=="exhausted")
    assert wait(s,completed["last_request_id"])["result"]=={"total":5050}
    assert attempts(s)==3
    with Session(s.engine) as db:
        assert db.scalar(select(func.count()).select_from(Run).where(Run.schedule_id==accepted["schedule_id"]))==2
    assert s.sdk.lookup_task("calculate",request_id=first)["status"]=="not_found"
    with pytest.raises(ValueError):schedule(s,request_id=first)
    for process in s.processes:
        if process.poll() is None:process.terminate();process.wait(timeout=3)
    s.server.stop();s.server.start();s.start_host();s.start_worker()
    assert wait(s,completed["last_request_id"])["result"]=={"total":5050}
    time.sleep(.3);assert attempts(s)==3


def test_schedule_idempotency_and_changed_input_refusal(task_state):
    s=task_state;key,accepted,body=recurring(s)
    assert s.sdk.create_task_schedule(**body)["schedule_id"]==accepted["schedule_id"]
    with pytest.raises(ApplicationPlatformError):s.sdk.create_task_schedule(**{**body,"history_limit":3})
    with pytest.raises(ApplicationPlatformError):s.sdk.create_task_schedule(**{**body,"rule":{"kind":"interval","every_seconds":10}})
    assert s.sdk.cancel_task_schedule("calculate",request_id=key)["status"]=="cancelled"
    assert s.sdk.create_task_schedule(**body)["status"]=="cancelled"


def test_misfires_coalesce_and_clock_rollback_never_reopens_a_cursor(task_state,monkeypatch):
    s=task_state;instant=datetime.now(UTC);monkeypatch.setattr(tasks,"now",lambda:instant)
    key,accepted,_=recurring(s,start=instant-timedelta(seconds=20),end=instant+timedelta(seconds=100),count=10)
    observed=tick_current(s,accepted)
    assert observed["admitted"]==1 and observed["skipped"]==4
    assert tick_current(s,accepted)["admitted"]==1
    monkeypatch.setattr(tasks,"now",lambda:instant-timedelta(seconds=10))
    assert tick_current(s,accepted)["admitted"]==1
    with Session(s.engine) as db:assert db.scalar(select(func.count()).select_from(Run))==1
    assert attempts(s)==0


def test_late_occurrence_is_skipped_and_cancel_retires_queued_work(task_state,monkeypatch):
    s=task_state;instant=datetime.now(UTC);monkeypatch.setattr(tasks,"now",lambda:instant)
    key,accepted,_=recurring(s,start=instant-timedelta(seconds=2),window=1,count=1)
    result=tick_current(s,accepted)
    assert result["skipped"]==1 and result["admitted"]==0
    monkeypatch.setattr(tasks,"now",lambda:instant+timedelta(seconds=3))
    assert tick_current(s,accepted)["admitted"]==1
    assert s.sdk.cancel_task_schedule("calculate",request_id=key)["status"]=="cancelled"
    with Session(s.engine) as db:assert db.scalar(select(Run.state))=="cancelled"
    assert claim_task(s.engine,settings=s.settings,worker_generation="b"*32) is None and attempts(s)==0


def test_schedule_revocation_cannot_resurrect_after_fresh_consent(task_state):
    s=task_state;key,_,_=recurring(s)
    status=s.manager.inspect(1)
    s.manager.revoke(1,actor_token=s.token,request_id=identity(),expected_revision=status["grant_record_revision"])
    assert s.sdk.lookup_task_schedule("calculate",request_id=key)["status"]=="cancelled"
    with pytest.raises(ApplicationPlatformError):recurring(s)
    allow(s,preview(s),scopes=["task:calculate"])
    assert s.sdk.lookup_task_schedule("calculate",request_id=key)["status"]=="cancelled"
    s.start_worker();fresh,_,_=recurring(s,count=1)
    result=wait_schedule(s,fresh,lambda r:r["status"]=="exhausted")
    assert wait(s,result["last_request_id"])["status"]=="succeeded" and attempts(s)==1


def test_worker_loss_blocks_future_occurrences_until_reconciliation(task_state):
    s=task_state;key,_=schedule(s,pause_ms=1500)
    worker=s.start_worker();wait(s,key,("running",))
    limit=time.monotonic()+3
    while s.sdk.lookup_task("calculate",request_id=key)["progress"]!=50:
        assert time.monotonic()<limit;time.sleep(.02)
    worker.kill();worker.wait(timeout=3)
    wait(s,key,("unknown",),seconds=4)
    recurring_key,_,_=recurring(s,count=2)
    s.start_worker()
    result=wait_schedule(s,recurring_key,lambda r:r["status"]=="blocked")
    assert result["error_code"]=="execution_unconfirmed" and result["admitted"]==0 and attempts(s)==1


def test_calendar_uses_the_same_queue_and_rejects_a_forged_worker_instant(task_state,monkeypatch):
    s=task_state;instant=datetime(2026,10,25,0,30,tzinfo=UTC)
    monkeypatch.setattr(tasks,"now",lambda:instant)
    key=identity()
    accepted=s.sdk.create_task_schedule("calculate",request_id=key,payload={"upper":100,"pause_ms":0},
        rule={"kind":"calendar","timezone":"Europe/Sofia","hour":3,"minute":30,"weekdays":[6]},
        start_at=instant-timedelta(days=1),end_at=instant+timedelta(days=2),max_occurrences=1)
    with pytest.raises(ValueError):tick_current(s,accepted,due=instant-timedelta(minutes=1))
    result=tick_current(s,accepted)
    assert result["admitted"]==1 and result["status"]=="exhausted"
    with Session(s.engine) as db:
        assert tasks.utc(db.scalar(select(Run.due_at)))==instant


def start_output_task(s,value=True):
    key=identity();due=datetime.now(UTC)+timedelta(seconds=.15)
    accepted=s.sdk.submit_task("switch_output",request_id=key,payload={"value":value},
        due_at=due,not_after=due+timedelta(seconds=10))
    s.start_worker()
    from backend.db.device import DeviceCommand
    limit=time.monotonic()+4
    while True:
        with Session(s.engine) as db:
            command=db.scalar(select(DeviceCommand))
            if command is not None:return key,accepted,command.command_id
        assert time.monotonic()<limit;time.sleep(.02)


@pytest.mark.parametrize("task_state",["commands"],indirect=True)
@pytest.mark.parametrize("lost_reply",[False,True])
def test_task_command_uses_real_mock_agent_and_cannot_bypass_or_replay(task_state,tmp_path,monkeypatch,lost_reply):
    s=task_state
    from agent.hardware import MockDigitalGpioDriver
    from agent.module_runtime import AgentModuleRuntime
    from agent.modules.gpio import GPIO_ENTRYPOINT,gpio_runtime_handler
    from agent.physical_command_journal import PhysicalCommandJournal
    from backend.db.device import Device,DeviceCommand
    from backend.db.application_command import ApplicationCommandRequest
    from backend.applications.commands.broker import authorize_execution
    from backend.devices.commands.queue import deliver_next_command,command_envelope,record_command_result
    with pytest.raises(ApplicationPlatformError):
        s.sdk.submit_command("output",request_id=identity(),arguments={"channel":"gpio.output.1","value":True},ttl_seconds=5)
    with pytest.raises(ApplicationPlatformError):
        s.sdk.submit_task_command({"task_run_id":"task_"+"f"*32,"task_id":"switch_output","lease_token":"e"*64},
            "output",request_id=identity(),arguments={"channel":"gpio.output.1","value":True},ttl_seconds=5)
    dropped=[];original=s.server._send_encoded
    def send(connection,encoded):
        if lost_reply and not dropped and b'"command_id":"cmd_' in encoded:
            dropped.append(True);return
        return original(connection,encoded)
    monkeypatch.setattr(s.server,"_send_encoded",send)
    key,accepted,command_id=start_output_task(s)
    driver=MockDigitalGpioDriver()
    runtime=AgentModuleRuntime(tmp_path/"task-agent",architecture="x86_64",runtime_handlers={GPIO_ENTRYPOINT:gpio_runtime_handler(driver)})
    try:
        runtime.install(s.output_blob,expected_sha256=hashlib.sha256(s.output_blob).hexdigest())
        journal=PhysicalCommandJournal(tmp_path/"task-agent-journal")
        with Session(s.engine) as db:
            device=db.get(Device,1);command=deliver_next_command(db,device=device)
            assert command.command_id==command_id
            record=db.get(ApplicationCommandRequest,command_id);run=db.get(Run,accepted["task_run_id"])
            assert record.task_run_id==run.task_run_id and tasks.utc(command.expires_at)<=tasks.utc(run.lease_until)
            envelope=command_envelope(command,device.device_id);body=command.payload
            result=journal.execute(envelope,lambda:runtime.invoke(body["capability_id"],body["action"],body["arguments"],
                contract_version=body["contract_version"],contract_digest=body["contract_digest"]),
                authorize=lambda:authorize_execution(db,device,command_id))
            record_command_result(db,device=device,result=result)
            assert result.status=="succeeded" and driver.output("gpio.output.1").read() is True
        limit=time.monotonic()+3
        while True:
            observed=s.sdk.lookup_task("switch_output",request_id=key)
            if observed["status"]=="succeeded":break
            assert time.monotonic()<limit,observed;time.sleep(.02)
        assert observed["result"]["command_id"]==command_id and observed["result"]["value"] is True
        assert journal.execute(envelope,lambda:pytest.fail("Task command replayed a physical effect"))==result
        assert attempts(s)==1
        assert bool(dropped)==lost_reply
        with Session(s.engine) as db:assert db.scalar(select(func.count()).select_from(DeviceCommand))==1
    finally:runtime.close()


@pytest.mark.parametrize("task_state",["commands"],indirect=True)
def test_task_grant_and_live_lease_are_rechecked_at_physical_permit(task_state):
    s=task_state
    from backend.db.device import Device
    from backend.applications.commands.broker import authorize_execution
    from backend.devices.commands.queue import deliver_next_command
    key,accepted,command_id=start_output_task(s)
    with Session(s.engine) as db:
        command=deliver_next_command(db,device=db.get(Device,1));assert command.command_id==command_id
    # A still-granted command scope does not substitute for task authority.
    allow(s,preview(s),scopes=["command:output"])
    with Session(s.engine) as db:
        with pytest.raises(ValueError):authorize_execution(db,db.get(Device,1),command_id)
    assert s.sdk.lookup_task("switch_output",request_id=key)["status"]=="unknown"


@pytest.mark.parametrize("task_state",["commands"],indirect=True)
def test_unconfirmed_physical_result_blocks_later_periodic_effects(task_state):
    s=task_state
    from backend.db.device import Device,DeviceCommand
    from backend.applications.commands.broker import authorize_execution
    from backend.devices.commands.queue import deliver_next_command
    key,_,command_id=start_output_task(s)
    with Session(s.engine) as db:
        device=db.get(Device,1);assert deliver_next_command(db,device=device).command_id==command_id
        authorize_execution(db,device,command_id)
    limit=time.monotonic()+6
    while s.sdk.lookup_task("switch_output",request_id=key)["status"]!="unknown":
        assert time.monotonic()<limit;time.sleep(.03)
    start=datetime.now(UTC)+timedelta(seconds=.1);schedule_key=identity()
    s.sdk.create_task_schedule("switch_output",request_id=schedule_key,payload={"value":False},
        rule={"kind":"interval","every_seconds":5},start_at=start,end_at=start+timedelta(minutes=1))
    limit=time.monotonic()+3
    while True:
        result=s.sdk.lookup_task_schedule("switch_output",request_id=schedule_key)
        if result["status"]=="blocked":break
        assert time.monotonic()<limit;time.sleep(.03)
    assert result["admitted"]==0 and result["error_code"]=="execution_unconfirmed"
    with Session(s.engine) as db:assert db.scalar(select(func.count()).select_from(DeviceCommand))==1


def test_cancelling_a_schedule_leaves_its_already_running_handler_to_finish(task_state):
    s=task_state;s.start_worker()
    key,_,_=recurring(s,pause_ms=800,count=3)
    schedule_state=wait_schedule(s,key,lambda r:r["admitted"]==1)
    wait(s,schedule_state["last_request_id"],("running",))
    assert s.sdk.cancel_task_schedule("calculate",request_id=key)["status"]=="cancelled"
    assert wait(s,schedule_state["last_request_id"])["status"]=="succeeded"
    assert s.sdk.lookup_task_schedule("calculate",request_id=key)["admitted"]==1 and attempts(s)==1


def test_unresolved_task_cannot_be_forgotten_by_uninstall(task_state):
    s=task_state;key,_=schedule(s,pause_ms=1500)
    worker=s.start_worker();wait(s,key,("running",))
    worker.kill();worker.wait(timeout=3)
    from fastapi import HTTPException
    from backend.applications.management.api import _require_no_unresolved_tasks
    with Session(s.engine) as db,tasks._write(db):
        with pytest.raises(HTTPException) as error:_require_no_unresolved_tasks(db,1)
        assert error.value.status_code==409


def test_task_package_staging_is_admin_stopped_cas_bound_and_preserves_results(task_state):
    s=task_state;s.start_worker();old_key,_=schedule(s)
    assert wait(s,old_key)["status"]=="succeeded"
    next_builder=load_builder();next_builder.VERSION="0.2.1"
    blob=next_builder.build_package();target=validate_module_package(blob)
    path=s.root/"modules"/(target.sha256+".zip");path.write_bytes(blob)
    with Session(s.engine) as db,db.begin():
        package=ModulePackage(module_id=target.manifest.module_id,version=target.manifest.version,
            manifest=target.manifest.model_dump(mode="json"),sha256=target.sha256,size_bytes=len(blob),file_path=str(path),registrations=[])
        db.add(package)
    from backend.db.application_authority_grant import ApplicationAuthorityGrant
    with Session(s.engine) as db:
        grant=json.loads(db.get(ApplicationAuthorityGrant,1).payload)
        original_incarnation=db.get(Installation,1).authority_incarnation
    body={"request_id":identity(),"expected_artifact_sha256":s.validated.sha256,
        "expected_revision":grant["revision"],"configuration":{}}
    url='/api/v1/application-extensions/packages/'+target.sha256+'/stage'
    assert s.http.post(url,json=body,headers={'Authorization':'Bearer '+s.user_token}).status_code==403
    assert s.http.post(url,json=body,headers=s.headers).status_code==409
    for process in s.processes:
        if process.poll() is None:process.terminate();process.wait(timeout=3)
    with Session(s.engine) as db,tasks._write(db):
        app=db.get(Installation,1);app.enabled=False;app.status='disabled'
    wrong=s.http.post(url,json={**body,"expected_revision":"f"*32},headers=s.headers)
    assert wrong.status_code==409
    staged=s.http.post(url,json=body,headers=s.headers)
    assert staged.status_code==200,staged.text
    assert staged.json()['execution']=='not_started' and staged.json()['permission_approval']=='required'
    replay=s.http.post(url,json=body,headers=s.headers).json()
    assert replay.pop('historical') and replay.pop('replayed') and replay==staged.json()
    with Session(s.engine) as db:
        app=db.get(Installation,1)
        assert app.authority_incarnation==original_incarnation and app.authority_mode=='review_required'
        assert app.active_version is None and not app.enabled
    assert s.task_probe.lookup(old_key)['result']=={'total':5050}
    from backend.applications.authority.metadata import read_authority_guard
    with Session(s.engine) as db:guard=read_authority_guard(db)
    from backend.applications.authority.management import AuthorityManagementError
    with pytest.raises(AuthorityManagementError):
        with s.manager.native_activation(1,target.sha256,{},guard):pass
    # Fresh artifact-specific approval is saved while stopped, before activation.
    decision=allow(s,preview(s),scopes=['task:calculate'])
    assert decision['saved'] and not decision['effective']
    with Session(s.engine) as db:guard=read_authority_guard(db)
    with s.manager.native_activation(1,target.sha256,{},guard) as lease:
        assert lease is not None
    assert attempts(s)==1 and all(process.poll() is not None for process in s.processes)
    from backend.applications.management.staging import registration_id
    from backend.db.application_authority_grant import ApplicationAuthorityAction
    with Session(s.engine) as db,db.begin():
        package=db.scalar(select(ModulePackage).where(ModulePackage.sha256==target.sha256))
        marker=registration_id(db,1,package.id,target.sha256)
        record=db.get(ApplicationAuthorityAction,marker)
        payload=json.loads(record.payload);payload['data']['binding']['sha256']='f'*64
        record.payload=json.dumps(payload)  # Tamper WITHOUT a new Core seal.
    assert s.manager.inspect(1)['review_available'] is False


def test_real_delayed_result_progress_restart_and_no_replay(task_state):
    from backend.system.diagnostics.work_refs import observe_work
    s = task_state
    key, accepted = schedule(s, pause_ms=250, delay=.4)
    def boundary():
        with Session(s.engine) as db:
            return observe_work(db, db.get(Installation,1), accepted['task_run_id'])['start_boundary']
    assert accepted["status"] == "queued" and accepted["result"] is None and attempts(s) == 0
    assert boundary() == 'no_dispatch_record'
    worker = s.start_worker()
    observed = wait(s, key, ("running",))
    assert observed["result"] is None
    result = wait(s, key)
    assert result["result"] == {"total": 5050} and result["progress"] == 100 and attempts(s) == 1
    assert boundary() == 'start_permit_consumed'
    worker.terminate(); worker.wait(timeout=3)
    s.host.terminate(); s.host.wait(timeout=3)
    s.server.stop(); s.server.start()
    s.start_host(); s.start_worker()
    assert wait(s, key)["task_run_id"] == accepted["task_run_id"]
    time.sleep(.25)
    assert attempts(s) == 1


def test_lost_admission_reply_uses_original_lookup_only(task_state, monkeypatch):
    s = task_state
    original = s.server._send_encoded
    dropped = []
    def send(connection, encoded):
        if not dropped and b'"status":"queued"' in encoded:
            dropped.append(True)
            return
        return original(connection, encoded)
    monkeypatch.setattr(s.server, "_send_encoded", send)
    key = identity()
    with pytest.raises(ApplicationPlatformError): schedule(s, request_id=key, delay=0)
    assert dropped and s.task_probe.lookup(key)["status"] == "queued"
    with Session(s.engine) as db: assert db.scalar(select(func.count()).select_from(Run)) == 1

    # Drive one real worker exchange after observing the original queued row.
    # This scenario tests lost-reply recovery, not cold process startup within
    # the task deadline. Other cases in this suite exercise the packaged worker.
    worker = TaskWorker(s.server.socket_path, core_uid=os.geteuid())
    assert worker.run_once(), "Worker did not claim the original queued task"
    result = s.task_probe.lookup(key)
    assert result["status"] == "succeeded", result
    assert result["result"] == {"total": 5050}
    assert not worker.run_once() and attempts(s) == 1


def test_exact_idempotency_and_queued_cancellation(task_state):
    s = task_state; key = identity(); due = datetime.now(UTC) + timedelta(seconds=1)
    body = dict(task_id="calculate", request_id=key, payload={"upper": 10, "pause_ms": 0},
        due_at=due, not_after=due + timedelta(seconds=5))
    first = s.sdk.submit_task(**body)
    assert s.sdk.submit_task(**body) == first
    with pytest.raises(ApplicationPlatformError): s.sdk.submit_task(**{**body, "payload": {"upper": 11, "pause_ms": 0}})
    with pytest.raises(ApplicationPlatformError): s.sdk.submit_task(**{**body, "due_at": due + timedelta(seconds=.1)})
    cancelled = s.sdk.cancel_task("calculate", request_id=key)
    assert cancelled["status"] == "cancelled"
    assert claim_task(s.engine, settings=s.settings, worker_generation="b" * 32) is None and attempts(s) == 0


def test_revocation_fences_queued_work_even_after_fresh_consent(task_state):
    s = task_state; key, _ = schedule(s)
    status = s.manager.inspect(1)
    s.manager.revoke(1, actor_token=s.token, request_id=identity(), expected_revision=status["grant_record_revision"])
    assert s.task_probe.lookup(key)["status"] == "cancelled"
    with pytest.raises(ApplicationPlatformError): schedule(s)
    allow(s, preview(s), scopes=["task:calculate"])
    assert s.task_probe.lookup(key)["status"] == "cancelled"
    s.start_worker(); fresh, _ = schedule(s)
    assert wait(s, fresh)["status"] == "succeeded" and attempts(s) == 1


def test_withdrawn_scope_foreign_actor_and_transport_fields_cannot_admit(task_state):
    s = task_state
    allow(s, preview(s), scopes=[])
    with pytest.raises(ApplicationPlatformError): schedule(s)
    with Session(s.engine) as db:
        assert db.scalar(select(func.count()).select_from(Run)) == 0
    allow(s, preview(s), scopes=["task:calculate"])
    key, accepted = schedule(s, delay=.5)
    (s.runtime_socket.parent / ("b" * 24 + ".key")).write_bytes(b"b" * 32)
    with Session(s.engine) as db, db.begin():
        db.add(Installation(module_id="org.example.foreign", module_package_id=1, instance_id="b" * 24,
            active_version="0.1.0", enabled=True, status="active", socket_path="unused", configuration={}))
    other = ApplicationPlatformClient(s.runtime_socket, "b" * 24, b"b" * 32)
    assert other.lookup_task("calculate", request_id=key)["status"] == "not_found"
    with pytest.raises(ApplicationPlatformError): other.submit_task("calculate", request_id=identity(), payload={"upper": 1, "pause_ms": 0},
        due_at=datetime.now(UTC), not_after=datetime.now(UTC) + timedelta(seconds=5))
    with pytest.raises(ApplicationPlatformError):
        s.sdk._call("task.lookup", {"lookup": {"task_id": "calculate", "request_id": key}, "installation_id": 2})
    assert "lease_token" not in accepted and "socket_path" not in accepted and "payload" not in accepted


def test_deadline_and_pending_budget_do_not_dispatch(task_state, monkeypatch):
    s = task_state
    keys = [schedule(s, delay=10)[0] for _ in range(8)]
    with pytest.raises(ApplicationPlatformError): schedule(s, delay=10)
    instant = datetime.now(UTC) + timedelta(seconds=20)
    monkeypatch.setattr(tasks, "now", lambda: instant)
    assert s.task_probe.lookup(keys[0])["status"] == "expired"
    assert claim_task(s.engine, settings=s.settings, worker_generation="b" * 32) is None
    assert attempts(s) == 0


def test_worker_loss_stays_unknown_and_requires_stopped_admin_reconciliation(task_state, monkeypatch, capsys):
    from concurrent.futures import Future
    from concurrent.futures import wait as wait_futures
    from pwd import getpwuid
    from sqlalchemy import event
    from backend.applications.resources.providers import observe
    from backend.tests.task_progress_timing import WorkerTimeline, observe_progress

    s = task_state
    probe_settings = s.settings.model_copy(update={"task_worker_socket": s.runtime_socket.parent / "task.sock",
        "runtime_user": getpwuid(os.geteuid()).pw_name})

    def ready_worker():
        process = s.start_worker()
        deadline = time.monotonic() + 10
        while observe("task", probe_settings) != "ready":
            assert process.poll() is None, process.stderr.read().decode(errors="replace")
            assert time.monotonic() < deadline, "Worker did not answer its readiness probe"
            time.sleep(.03)
        return process

    key, interrupted = identity(), Future()
    worker = ready_worker()
    record_progress = tasks.progress_task
    permit = {}
    phase_ms = {}
    timeline = WorkerTimeline()
    real_start = tasks.start_task

    def observe_start(*args, **kwargs):
        receipt = real_start(*args, **kwargs)
        permit.update(at=time.monotonic(), remaining_ms=round(receipt["lease_remaining_seconds"] * 1000))
        return receipt

    # Interrupt the real process after Core commits progress but before the
    # handler receives its reply. No timing window or synthetic task state.
    def interrupt_after_progress(db, installation, payload):
        arrived = time.monotonic()
        def committed(session):
            timeline.mark("progress_committed")
        event.listen(db, "after_commit", committed)
        try:
            with measure():
                result = record_progress(db, installation, payload)
            assert (result["request_id"], result["status"], result["progress"]) == (key, "running", 50)
            assert worker.poll() is None, "Worker exited before the interruption"
            worker.kill()
        except Exception as exc:
            # Admission intentionally masks errors for callers. Report only timing
            # and a fixed category in pytest, never tokens, payloads or grant data.
            inner = exc.__context__
            reason = ("execution_lease_not_current" if isinstance(inner, ValueError)
                and str(inner) == "Task execution lease is not current" else type(inner).__name__)
            elapsed = round((arrived - permit["at"]) * 1000) if "at" in permit else None
            exc.add_note(f"progress refusal: inner={reason}, lease_ms_at_start={permit.get('remaining_ms')}, "
                         f"start_to_progress_ms={elapsed}, progress_check_ms={round((time.monotonic()-arrived)*1000)}, "
                         f"progress_phases_ms={phase_ms}, worker_trace={timeline.snapshot()}")
            interrupted.set_exception(exc)
            raise
        finally:
            event.remove(db, "after_commit", committed)
        interrupted.set_result(result["task_run_id"])
        return result

    with monkeypatch.context() as patch, observe_progress(patch, s.engine, phase_ms, timeline) as measure:
        patch.setattr(tasks, "submit_task", timeline.track(tasks.submit_task, "submit_received", "submit_accepted"))
        patch.setattr(tasks, "dispatch_task", timeline.track(tasks.dispatch_task, "dispatch_received", "dispatch_committed"))
        patch.setattr(tasks, "start_task", timeline.track(observe_start, "start_received", "start_permitted"))
        patch.setattr(tasks, "progress_task", timeline.track(interrupt_after_progress, "progress_received", "observer_returned"))
        _, accepted = schedule(s, request_id=key)
        if not wait_futures((interrupted,), timeout=10).done:
            # Do not query Core on timeout: the very request under observation may
            # be holding the resource needed to answer that second call.
            pytest.fail(f"Progress observation timed out: worker_trace={timeline.snapshot()}, worker={worker.poll()}")
        assert interrupted.result() == accepted["task_run_id"]
        trace = timeline.snapshot()
        assert {"submit_accepted", "dispatch_committed", "start_permitted", "progress_received",
                "progress_committed"} <= trace["events_ms"].keys(), trace
        with capsys.disabled():
            print(f"\nCommitted worker progress (ms, inclusive): {phase_ms}; worker_trace={trace}", flush=True)
    worker.wait(timeout=3)
    assert wait(s, key, ("unknown",), seconds=4)["result"] is None
    ready_worker()
    assert attempts(s) == 1
    # Simulate the existing lifecycle's positive stopped result after actually
    # stopping this native process; no fake "cancelled" execution is claimed.
    path = f'/api/v1/application-extensions/{s.validated.manifest.module_id}/tasks/{accepted["task_run_id"]}/resolve'
    body = {"request_id": identity(), "confirmed_external_outcome_reviewed": True}
    assert s.http.post(path, json=body, headers={"Authorization": "Bearer " + s.user_token}).status_code == 403
    assert s.http.post(path, json=body, headers=s.headers).status_code == 409
    if s.host.poll() is None: s.host.terminate(); s.host.wait(timeout=3)
    with s.engine.begin() as db:
        db.execute(update(Installation).where(Installation.id == 1).values(enabled=False, status="disabled", authority_epoch=identity()))
    assert s.http.post(path, json={"request_id": identity()}, headers=s.headers).status_code == 422
    response = s.http.post(path, json=body, headers=s.headers)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "resolved"
    assert s.http.post(path, json=body, headers=s.headers).json()["replayed"] is True
    assert s.task_probe.lookup(key)["status"] == "resolved" and attempts(s) == 1


def test_foreign_worker_receipt_and_running_cancel_are_fenced(task_state):
    s = task_state
    key, accepted = schedule(s, delay=0)
    plan = claim_task(s.engine, settings=s.settings, worker_generation="b" * 32)
    assert plan is not None and plan["task_run_id"] == accepted["task_run_id"]
    assert s.sdk.cancel_task("calculate", request_id=key)["status"] == "running"
    for generation, token in (("c" * 32, plan["lease_token"]), ("b" * 32, "d" * 64)):
        with pytest.raises(ValueError): finish_task(s.engine, key_root=s.runtime_socket.parent,
            worker_generation=generation, task_run_id=plan["task_run_id"], lease_token=token)
    with pytest.raises(ApplicationPlatformError): s.sdk.task_progress({"task_run_id": plan["task_run_id"],
        "task_id": "calculate", "lease_token": "d" * 64}, 50)
    finish_task(s.engine, key_root=s.runtime_socket.parent, worker_generation="b" * 32,
        task_run_id=plan["task_run_id"], lease_token=plan["lease_token"])
    assert s.task_probe.lookup(key)["status"] == "failed" and attempts(s) == 0
    assert s.task_probe.lookup(key)["error_code"] == "not_dispatched"


def test_live_start_gate_denies_withdrawn_authority_before_application_code(task_state):
    s = task_state
    key, _ = schedule(s, delay=0)
    metadata = claim_task(s.engine, settings=s.settings, worker_generation="b" * 32)
    plan = dispatch_task(s.engine, settings=s.settings, worker_generation="b" * 32,
        task_run_id=metadata["task_run_id"], lease_token=metadata["lease_token"], response=TaskWorker.invoke(metadata))
    status = s.manager.inspect(1)
    s.manager.revoke(1, actor_token=s.token, request_id=identity(), expected_revision=status["grant_record_revision"])
    response = TaskWorker.invoke(plan)
    assert response["ok"] is False and attempts(s) == 0
    assert s.task_probe.lookup(key)["status"] == "unknown"


def test_start_and_dispatch_permits_are_one_use(task_state):
    s = task_state
    key, _ = schedule(s, delay=0)
    metadata = claim_task(s.engine, settings=s.settings, worker_generation="b" * 32)
    response = TaskWorker.invoke(metadata)
    plan = dispatch_task(s.engine, settings=s.settings, worker_generation="b" * 32,
        task_run_id=metadata["task_run_id"], lease_token=metadata["lease_token"], response=response)
    with pytest.raises(ValueError):
        dispatch_task(s.engine, settings=s.settings, worker_generation="b" * 32,
            task_run_id=metadata["task_run_id"], lease_token=metadata["lease_token"], response=response)
    execution = plan["request"]["context"]["task_execution"]
    assert s.sdk.start_task(execution)["task_run_id"] == plan["task_run_id"]
    with pytest.raises(ApplicationPlatformError): s.sdk.start_task(execution)
    # The host's independent start gate also refuses this consumed permit.
    assert TaskWorker.invoke(plan)["ok"] is False and attempts(s) == 0


def test_application_cannot_forge_worker_control(task_state):
    s = task_state
    key, _ = schedule(s)
    with pytest.raises(ApplicationPlatformError):
        s.sdk._call("task.lookup", {"lookup": {"task_id": "calculate", "request_id": key},
            "task_execution_contract": 1})
    assert s.task_probe.lookup(key)["status"] == "queued"
    assert attempts(s) == 0 and s.server.is_running


def test_reinstalled_incarnation_cannot_read_previous_results(task_state):
    s = task_state; key, _ = schedule(s)
    s.start_worker(); assert wait(s, key)["status"] == "succeeded"
    with s.engine.begin() as db:
        db.execute(update(Installation).where(Installation.id == 1).values(authority_incarnation=identity(), authority_epoch=identity()))
    assert s.task_probe.lookup(key)["status"] == "not_found"


def test_boot_and_monotonic_fences_ignore_wall_clock_rollback(task_state, monkeypatch):
    s = task_state; key, _ = schedule(s, delay=0)
    plan = claim_task(s.engine, settings=s.settings, worker_generation="b" * 32)
    with s.engine.begin() as db:
        db.execute(update(Run).where(Run.task_run_id == plan["task_run_id"]).values(lease_monotonic=tasks.lease_clock() - 1))
    monkeypatch.setattr(tasks, "now", lambda: datetime.now(UTC) - timedelta(days=1))
    assert s.task_probe.lookup(key)["status"] == "failed"
    with s.engine.begin() as db:
        db.execute(update(Run).where(Run.task_run_id == plan["task_run_id"]).values(lease_monotonic=tasks.lease_clock() + 100))
    monkeypatch.setattr(tasks, "boot_id", lambda: "a-different-boot")
    assert s.task_probe.lookup(key)["status"] == "failed" and attempts(s) == 0
