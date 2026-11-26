"""Real authenticated portable archives; only disposable data, no privilege or live services."""
import hashlib
import json
import os
import platform
import shutil
import sqlite3
import stat
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from backend.tests.test_application_file_backup import _backup, _files, _seed_installation, _settings
from backend.tests.test_application_file_backup import Controller, _restore
from backend.system.backups import service
from deployment import portable_backup, restore_backup
from tools import recovery_check as check


pytestmark = pytest.mark.skipif(sys.platform!="linux",reason="Offline, private Linux staging")
PASSWORD = "synthetic verifier password"


@pytest.mark.parametrize(("case", "reason"), [
    ("ambiguous_revision", "restore_core_revision_invalid"),
    ("other_identity", "restore_device_identity_mismatch"),
    ("invalid_identity", "restore_device_state_invalid"),
    ("other_role", "restore_role_invalid"),
])
def test_inconsistent_older_capture_has_actionable_private_refusal_before_stop(tmp_path, monkeypatch, case, reason):
    settings = _settings(tmp_path)
    context = service._read_device_context(settings)
    database = tmp_path / "core/3mm.db"
    revision = service._read_database_revision(database)
    with monkeypatch.context() as historical_capture:
        if case == "ambiguous_revision":
            with sqlite3.connect(database) as db:
                db.execute("INSERT INTO alembic_version VALUES (?)", ("second-head-for-fixture",))
            readiness = service.build_backup_preview(settings)
            assert not readiness.ready and "compatibility.database" in {item.code for item in readiness.issues}
            # Rehearse an archive made when capture read only the first row.
            historical_capture.setattr(service, "_read_database_revision", lambda _: revision)
        else:
            path = (settings.backups.agent_data_dir / "identity.json" if case.endswith("identity")
                    else settings.backups.provisioning_data_dir / "provisioning.json")
            payload = json.loads(path.read_text())
            if case.endswith("identity"):
                payload["device_id"] = "dev_" + "b" * (32 if case == "other_identity" else 24)
            else:
                payload["role"] = "hub"
            path.write_text(json.dumps(payload))
            # Real checksummed files, but an inconsistent previous capture's identity claim.
            historical_capture.setattr(service, "_read_device_context", lambda _: context)
        backup, key = _backup(settings, tmp_path)
    export = portable_backup.create_portable_export(settings.backups.storage_dir, key, backup.backup_id, PASSWORD)
    copy_sha = hashlib.sha256(export.path.read_bytes()).digest()
    verdict = check.verify_portable(export.path, PASSWORD, target_architecture=platform.machine())
    assert verdict["state"] == "not_verified" and verdict["reason"] == reason
    assert hashlib.sha256(export.path.read_bytes()).digest() == copy_sha
    controller = Controller()
    with pytest.raises(restore_backup.RestoreStateError):
        _restore(settings, tmp_path, backup.backup_id, key, controller)
    status = service.read_backup_operation_status(settings.backups.storage_dir / "status.json")
    assert status.error_code == reason and status.state == "failed" and not controller.calls
    assert not any(s in json.dumps(verdict) + status.message for s in (
        context[0], "second-head-for-fixture", str(tmp_path), PASSWORD))


def fingerprint(folder):
    return {p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in folder.rglob("*") if p.is_file()}


@pytest.fixture
def sample(tmp_path):
    scratch = tmp_path/"scratch"; scratch.mkdir(mode=0o700)
    settings = _settings(tmp_path)
    _seed_installation(settings)
    _files(settings).put("restricted",b"fixture private content",expected_sha256=None)
    backup, key = _backup(settings,tmp_path)
    export = portable_backup.create_portable_export(settings.backups.storage_dir,key,backup.backup_id,PASSWORD)
    return tmp_path,scratch,export.path


def test_real_archive_validates_from_export_only_and_never_changes_source_files(sample,monkeypatch):
    root,scratch,source = sample
    original=fingerprint(root)
    def refused(*args,**kwargs):
        pytest.fail("Verification must not import, replace data, allocate a key or operate the live controller")
    monkeypatch.setattr(portable_backup,"_load_or_create_key",refused)
    monkeypatch.setattr(portable_backup,"write_backup_catalog_item",refused)
    monkeypatch.setattr(restore_backup,"_switch_state",refused)
    monkeypatch.setattr(restore_backup,"SystemRestoreRuntime",refused)
    validate = check._stage_for_target
    def observed(plain,stage,*args,**kwargs):
        assert stage.parent.parent==scratch
        assert stat.S_IMODE(stage.parent.stat().st_mode)==stat.S_IMODE(stage.stat().st_mode)==0o700
        assert stat.S_IMODE(plain.stat().st_mode)==0o600
        return validate(plain,stage,*args,**kwargs)
    monkeypatch.setattr(check,"_stage_for_target",observed)
    result=check.verify_portable(source,PASSWORD,target_architecture=platform.machine(),scratch=scratch)
    assert result==dict(schema_version=1,kind="portable_recovery_check",scope=check.SCOPE,
        state="validated",service_activation_tested=False,target_architecture=platform.machine(),
        entry_count=result["entry_count"],payload_size_bytes=result["payload_size_bytes"],application_access_followup="none_observed")
    assert result["entry_count"]>=8 and result["payload_size_bytes"]>=1024
    assert fingerprint(root)==original and not list(scratch.iterdir())


def test_protected_app_is_a_followup_not_a_failed_archive_or_an_export_of_grants(tmp_path, capsys):
    from tools import diagnostics
    settings=_settings(tmp_path)
    _seed_installation(settings)
    database=settings.backups.agent_data_dir.parent/'core/3mm.db'
    with sqlite3.connect(database) as db:
        db.execute("UPDATE application_extension_installations SET authority_mode='enforced'")
    backup,key=_backup(settings,tmp_path)
    export=portable_backup.create_portable_export(settings.backups.storage_dir,key,backup.backup_id,PASSWORD)
    before=fingerprint(tmp_path)
    result=check.verify_portable(export.path,PASSWORD,target_architecture=platform.machine())
    assert result['state']=='validated' and result['application_access_followup']=='fresh_review_needed'
    assert fingerprint(tmp_path)==before and 'module_id' not in json.dumps(result)
    saved=tmp_path/'result.json'
    result['next_check']='untrusted private content'
    saved.write_text(json.dumps(result))
    assert diagnostics.main(['explain',str(saved)])==0
    text=capsys.readouterr().out
    assert 'exact package' in text and 'untrusted private content' not in text
    result['application_access_followup']='arbitrary private instructions'
    saved.write_text(json.dumps(result))
    assert diagnostics.main(['explain',str(saved)])==1
    captured=capsys.readouterr()
    assert 'arbitrary private instructions' not in captured.out+captured.err


def test_unknown_review_schema_is_not_reported_as_no_review_or_created(tmp_path):
    db_path=tmp_path/'payload/core/3mm.db'
    db_path.parent.mkdir(parents=True)
    assert check._application_access_followup(tmp_path)=='not_checked' and not db_path.exists()
    with sqlite3.connect(db_path) as db:
        db.execute("CREATE TABLE application_extension_installations(enabled,status,authority_mode)")
        db.executemany("INSERT INTO application_extension_installations VALUES(?,?,?)",
                       [(0,'disabled','enforced'),(1,'active','future-or-corrupt')])
    assert check._application_access_followup(tmp_path)=='not_checked'
    with sqlite3.connect(db_path) as db:
        db.execute("DELETE FROM application_extension_installations WHERE enabled=1")
    assert check._application_access_followup(tmp_path)=='none_observed'


def test_interface_check_honors_limits_and_never_implies_an_existing_build(sample, monkeypatch, capsys):
    from tools import diagnostics, recovery_interfaces
    _, scratch, source = sample
    monkeypatch.setattr(check.getpass, "getpass", lambda _: PASSWORD)
    args = [str(source),"--scratch",str(scratch),"--check-interfaces","--json"]
    assert check.main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["state"] == "validated" and result["interface_builds"] == "no_active_ui_observed"
    monkeypatch.setattr(recovery_interfaces, "MAX_ACTIVE", 0)
    assert check.main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["state"] == "validated" and result["interface_builds"] == "not_checked"
    assert diagnostics.explain(result)["interface_builds"] == "not_checked"
    with pytest.raises(ValueError):
        diagnostics.explain({**result,"interface_builds":"untrusted text"})


@pytest.mark.parametrize("case,reason",[
    ("password","password_or_envelope_invalid"),("damaged","password_or_envelope_invalid"),
    ("other_arch","target_incompatible"),("space","insufficient_scratch_space"),
    ("shared_scratch","scratch_unavailable"),("entry_budget","payload_invalid"),
    ("link","input_unavailable"),("fifo","input_unavailable")])
def test_refusal_is_private_does_not_consume_input_and_leaves_no_staging(sample,monkeypatch,case,reason):
    root,scratch,source=sample
    password=PASSWORD
    arch=platform.machine()
    if case=="password": password="wrong test password"
    elif case=="damaged":
        data=bytearray(source.read_bytes()); data[-1]^=1; source.write_bytes(data)
    elif case=="other_arch": arch=next(a for a in check.SUPPORTED_ARCHITECTURES if a!=arch)
    elif case=="space": monkeypatch.setattr(shutil,"disk_usage",lambda _:SimpleNamespace(free=32))
    elif case=="shared_scratch": scratch.chmod(0o777)
    elif case=="entry_budget": monkeypatch.setattr(check,"MAX_ENTRIES",2)
    elif case=="link":
        link=root/"chosen.link"; link.symlink_to(source); source=link
    elif case=="fifo":
        source=root/"chosen.pipe"; os.mkfifo(source)
    result=check.verify_portable(source,password,target_architecture=arch,scratch=scratch)
    assert (result["state"],result["reason"],result["service_activation_tested"])==("not_verified",reason,False)
    assert source.exists() and not list(scratch.iterdir())
    assert not any(v in json.dumps(result) for v in (str(root),"restricted",PASSWORD,"fixture private content"))


def test_target_arch_is_explicit_and_does_not_relax_the_live_import_gate(tmp_path,monkeypatch):
    settings=_settings(tmp_path)
    host=platform.machine()
    target=next(a for a in check.SUPPORTED_ARCHITECTURES if a!=host)
    with monkeypatch.context() as simulated_source:
        simulated_source.setattr(platform,"machine",lambda:target)
        backup,key=_backup(settings,tmp_path)
    export=portable_backup.create_portable_export(settings.backups.storage_dir,key,backup.backup_id,PASSWORD)
    assert check.verify_portable(export.path,PASSWORD,target_architecture=target)["state"]=="validated"
    assert check.verify_portable(export.path,PASSWORD,target_architecture=host)["reason"]=="target_incompatible"
    staged=tmp_path/"upload"; shutil.copyfile(export.path,staged)
    with pytest.raises(ValueError,match="architecture"):
        portable_backup.import_portable_backup(staged,tmp_path/"new-catalog",tmp_path/"new-key",PASSWORD,
                                               max_archive_bytes=32*1024*1024)
    assert not (tmp_path/"new-catalog").exists() and not (tmp_path/"new-key").exists() and export.path.is_file()


def test_cli_returns_machine_readable_result_without_disclosing_private_input(sample,monkeypatch,capsys):
    _,scratch,source=sample
    monkeypatch.setattr(check.getpass,"getpass",lambda _:PASSWORD)
    assert check.main([str(source),"--scratch",str(scratch),"--json"])==0
    output=capsys.readouterr()
    assert json.loads(output.out)["state"]=="validated" and not output.err
    def no_tty(_):
        raise check.getpass.GetPassWarning("raw machine detail should not escape")
    monkeypatch.setattr(check.getpass,"getpass",no_tty)
    assert check.main([str(source),"--json"])==1
    output=capsys.readouterr()
    assert json.loads(output.out)["reason"]=="password_prompt_unavailable" and not output.err


def test_real_operator_prompt_and_offline_handoff(sample):
    """Exercise the real password prompt (not a pipe) and a second offline reader."""
    import select
    import termios

    root, scratch, source = sample
    original = fingerprint(root)
    master, slave = os.openpty()
    try:
        with subprocess.Popen(
            [sys.executable, "-m", "tools.recovery_check", str(source),
             "--scratch", str(scratch), "--json"],
            stdin=slave, stderr=slave, stdout=subprocess.PIPE, start_new_session=True,
        ) as child:
            try:
                # Wait for actual echo suppression, without putting the password
                # in arguments, environment, a log, or a file.
                seen = b""
                deadline = time.monotonic() + 40
                while b"Recovery password (not saved): " not in seen:
                    ready, _, _ = select.select([master], [], [], max(0, deadline-time.monotonic()))
                    assert ready and len(seen) < 1024, "No private operator prompt"
                    seen += os.read(master, 1024)
                assert not termios.tcgetattr(slave)[3] & termios.ECHO
                os.write(master, PASSWORD.encode("ascii") + b"\n")
                output, _ = child.communicate(timeout=40)
            finally:
                if child.poll() is None:
                    child.kill()
            assert child.returncode == 0
    finally:
        os.close(master)
        os.close(slave)
    assert fingerprint(root) == original and not list(scratch.iterdir())
    evidence = root / "support.json"
    evidence.write_bytes(output)
    reader = subprocess.run([sys.executable, "-m", "tools.diagnostics", "explain",
                             str(evidence), "--json"], capture_output=True, check=True, timeout=35)
    result = json.loads(reader.stdout)
    assert result["state"] == "validated" and result["service_activation_tested"] is False
    for secret in (PASSWORD.encode(), os.fsencode(str(source)), b"fixture private content"):
        assert secret not in output + reader.stdout + reader.stderr
