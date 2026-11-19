"""Real disposable data, bounded app identities and explicit admin-only preflight."""
import sqlite3
import tarfile
from types import SimpleNamespace
import pytest

from backend.system.backups import api
from backend.system.backups.readiness import MAX_APPLICATIONS, summarize_backup
from backend.system.backups.service import BackupPreviewIssue, build_backup_preview
from backend.tests.test_backup_preview import _settings
from backend.tests.test_backup_routes import _client, use_test_jwt_secret
from components.system_runtime.update_helper_client import UpdateHelperClient, UpdateHelperError
from deployment import create_backup as writer


def test_bounded_inventory_separates_installed_retained_and_unmatched_without_private_names(tmp_path):
    settings = _settings(tmp_path)
    ids = [f'{i:024x}' for i in range(MAX_APPLICATIONS+2)]
    for instance in ids:
        data = settings.backups.application_extensions_dir / instance / 'data'
        data.mkdir(parents=True)
        (data/'private-customer-name.txt').write_bytes(b'private value')
    preview = build_backup_preview(settings)
    assert preview.ready and preview.manifest is not None
    catalog = tmp_path/'catalog.db'
    with sqlite3.connect(catalog) as db:
        db.executescript('''
          CREATE TABLE application_extension_installations (instance_id TEXT UNIQUE,module_id TEXT,module_package_id INTEGER);
          CREATE TABLE module_packages (id INTEGER PRIMARY KEY,module_id TEXT,version TEXT);
          CREATE TABLE application_retained_data (instance_id TEXT UNIQUE,module_id TEXT);
          INSERT INTO module_packages VALUES(1,'org.example.one','1.2.3');
        ''')
        db.execute("INSERT INTO application_extension_installations VALUES(?,'org.example.one',1)",(ids[0],))
        db.execute("INSERT INTO application_retained_data VALUES(?,'org.example.two')",(ids[1],))
    result = summarize_backup(preview,'sqlite:///'+str(catalog))
    assert result.inventory == 'available' and len(result.applications)==MAX_APPLICATIONS
    assert result.unlisted_application_files == 2 and result.applications[2].catalog_state == 'unmatched'
    assert (result.applications[0].package_version,result.applications[1].catalog_state) == ('1.2.3','retained')
    assert result.applications[1].package_version is None and result.applications[0].size_bytes == len(b'private value')
    assert 'private' not in result.model_dump_json() and '3mm.db' not in result.model_dump_json()
    unopened=tmp_path/'missing.db'
    missing=summarize_backup(preview,'sqlite:///'+str(unopened))
    assert not unopened.exists() and missing.applications[0].catalog_state=='unavailable'


def test_unavailable_manifest_is_not_a_zero_app_inventory_and_issue_text_is_never_exported(tmp_path):
    settings=_settings(tmp_path)
    issue=BackupPreviewIssue(severity='error',code='state.read_failed',message='/private-person/file')
    preview=build_backup_preview(settings).model_copy(update={'ready':False,'manifest':None,'issues':(issue,issue,issue)})
    result=summarize_backup(preview,settings.database_url)
    assert not result.ready and result.inventory=='not_available' and result.unlisted_application_files is None
    assert len(result.issues)==1 and result.issues[0].occurrences==3 and 'private-person' not in result.model_dump_json()


def test_admin_only_compact_helper_no_fallback_on_refusal(monkeypatch,tmp_path):
    client,db,admin,viewer=_client()
    settings=_settings(tmp_path)
    socket=tmp_path/'reviewed-helper.sock';socket.touch()
    monkeypatch.setattr(api,'get_settings',lambda: SimpleNamespace(updates=SimpleNamespace(helper_socket=socket)))
    calls=[]
    doc=summarize_backup(build_backup_preview(settings),settings.database_url).model_dump(mode='json')
    def read(_self,user_id,*,summary=False):
        calls.append((user_id,summary))
        assert not db.in_transaction()
        return doc
    monkeypatch.setattr(UpdateHelperClient,'request_backup_preview',read)
    def unexpected(_settings):
        raise AssertionError('Do not try to read protected data after a helper refusal')
    monkeypatch.setattr(api,'build_backup_preview',unexpected)
    headers=lambda token:{'Authorization':'Bearer '+token}
    try:
        assert client.get('/api/v1/backups/readiness').status_code==401
        assert client.get('/api/v1/backups/readiness',headers=headers(viewer)).status_code==403 and not calls
        good=client.get('/api/v1/backups/readiness',headers=headers(admin))
        assert good.status_code==200 and good.headers['cache-control']=='no-store'
        body=good.json()
        share=body.pop('support_summary')
        assert body==doc and share['file_count']==doc['entry_count'] and share['archive_verified'] is False
        assert not {'applications','available_bytes','manifest','storage_path'} & share.keys()
        assert all(set(row)=={'code','severity','occurrences'} for row in share['issues'])
        assert 'manifest' not in doc and 'storage_path' not in doc and len(calls)==1 and calls[0][1]
        with api._preview_slot:
            for path in ('/readiness','/preview'):
                assert client.get('/api/v1/backups'+path,headers=headers(admin)).status_code==429
        assert len(calls)==1
        def fail(*args,**kwargs):raise UpdateHelperError('/private/file')
        monkeypatch.setattr(UpdateHelperClient,'request_backup_preview',fail)
        denied=client.get('/api/v1/backups/readiness',headers=headers(admin))
        assert denied.status_code==503 and '/private/file' not in denied.text
        def revoke(*args,**kwargs):
            from backend.db.user import User
            db.get(User,1).token_version += 1
            db.commit()
            return doc
        monkeypatch.setattr(UpdateHelperClient,'request_backup_preview',revoke)
        revoked=client.get('/api/v1/backups/readiness',headers=headers(admin))
        assert revoked.status_code==401 and 'inventory' not in revoked.json()
    finally:
        client.close()
        db.close()


def test_archive_verifies_the_bytes_actually_copied_and_does_not_publish_partial_data(tmp_path,monkeypatch):
    settings=_settings(tmp_path)
    preview=build_backup_preview(settings)
    assert preview.ready
    target=tmp_path/'candidate.3mmbak'
    add=tarfile.TarFile.addfile
    def saving_while_copying(archive, member, fileobj=None):
        if member.name=='payload/core/uploads/logo.png':
            (settings.backend.uploads_dir/'logo.png').write_bytes(b'newer')  # Same size, different content.
        return add(archive,member,fileobj)
    monkeypatch.setattr(tarfile.TarFile,'addfile',saving_while_copying)
    with pytest.raises(ValueError,match='changed after backup preflight'):
        writer._write_archive(target,b'k'*32,settings,preview)
    assert not target.exists() and not list(tmp_path.glob('.backup-*.tmp'))


def test_collision_preserves_original_archive_and_still_resumes_services(tmp_path,monkeypatch):
    settings=_settings(tmp_path)
    preview=build_backup_preview(settings)
    settings.backups.storage_dir.mkdir()
    saved=settings.backups.storage_dir/(preview.manifest.backup_id+'.3mmbak')
    saved.write_bytes(b'previous archive')
    def quiesced_preview(_settings, *, review_reactivation):
        assert review_reactivation is False  # optional package advice should not extend a service outage
        return preview
    monkeypatch.setattr(writer,'build_backup_preview',quiesced_preview)
    calls=[]
    controller=SimpleNamespace(stop=lambda _:calls.append('stop'), start=lambda _:calls.append('start'))
    with pytest.raises(FileExistsError):
        writer.create_backup(settings,key_file=tmp_path/'key',requested_by_user_id=1,controller=controller)
    assert saved.read_bytes()==b'previous archive' and calls==['stop','start']


def test_archive_enumerates_allowlisted_roots_once_for_many_files(tmp_path,monkeypatch):
    from backend.system.backups import service
    settings=_settings(tmp_path)
    for n in range(8):
        data=settings.backups.application_extensions_dir / f'{n:024x}' / 'data'
        data.mkdir(parents=True)
        for i in range(8): (data/f'note-{i}.txt').write_bytes(b'note')
    preview=build_backup_preview(settings)
    assert preview.ready and preview.entry_count>=64
    original=service._backup_sources
    counts=[]
    def count(*args):
        counts.append(1)
        return original(*args)
    monkeypatch.setattr(service,'_backup_sources',count)
    writer._write_archive(tmp_path/'indexed.3mmbak',b'k'*32,settings,preview)
    assert counts == [1]
