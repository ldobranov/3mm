"""Independent Runtime artifact safety and durable update/rollback transactions."""
from pathlib import Path
import hashlib
import io
import json
import os
import shutil
import subprocess
import tarfile
import zipfile

import pytest
from deployment.platform_runtime_component import (
    INPUTS,RUNTIME_SOURCES,RuntimeStore,build_component,validate_artifact,validate_metadata,MAX_ARTIFACT,
)

ROOT=Path(__file__).resolve().parents[2]

def digest(blob):return hashlib.sha256(blob).hexdigest()

def test_shipped_core_runtime_contract_admits_task_sdk_actions():
    from deployment.deployment_contract import validate_platform_runtime_contract
    value = validate_platform_runtime_contract((ROOT / 'deployment/platform-runtime-contract.json').read_bytes())
    assert {'task.submit', 'task.lookup', 'task.cancel', 'task.start', 'task.progress',
        'task.schedule.create','task.schedule.lookup','task.schedule.cancel'} <= set(value['operations'])


def test_immutable_runtime_file_sets_can_evolve_without_breaking_independent_rollback(tmp_path,monkeypatch):
    import deployment.platform_runtime_component as component
    original=component.INPUTS
    monkeypatch.setattr(component,'INPUTS',tuple(name for name in original if not name.endswith('/task_time.py')))
    old=build_component(ROOT)
    source=tmp_path/'new-source'
    for name in original:
        target=source/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/name,target)
    extra='components/platform_runtime/future_worker.py'
    (source/extra).write_text('"""A newer optional stdlib-only worker."""\n')
    # A later updater can ship another worker without requiring it in a valid
    # earlier immutable artifact. Both current input declarations evolve here.
    monkeypatch.setattr(component,'RUNTIME_SOURCES',(*component.RUNTIME_SOURCES,extra))
    monkeypatch.setattr(component,'INPUTS',(*original,extra))
    new=build_component(source)
    assert old[1]['build_id']!=new[1]['build_id']
    store=RuntimeStore(tmp_path/'component',tmp_path/'journal');control=Control()
    store.activate(old[0],digest(old[0]),control=control,health=health,fingerprint=fingerprint)
    store.activate(new[0],digest(new[0]),control=control,health=health,fingerprint=fingerprint)
    store.rollback(control=control,health=health,fingerprint=fingerprint)
    assert store.target('current')==old[1]['build_id'] and store.target('previous')==new[1]['build_id']


def test_self_describing_runtime_still_rejects_core_payload_and_missing_entrypoint(monkeypatch):
    import deployment.platform_runtime_component as component
    original=component.INPUTS
    monkeypatch.setattr(component,'INPUTS',(*original,'backend/main.py'))
    with pytest.raises(ValueError,match='payload'):build_component(ROOT)
    monkeypatch.setattr(component,'INPUTS',tuple(name for name in original if name!='packages/__init__.py'))
    with pytest.raises(ValueError,match='payload'):build_component(ROOT)
    monkeypatch.setattr(component,'INPUTS',tuple(name for name in original if not name.endswith('/server.py')))
    with pytest.raises(ValueError,match='payload'):build_component(ROOT)


def variant(tmp_path,name):
    source=tmp_path/name
    for file in INPUTS:
        target=source/file;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/file,target)
    with (source/'components/platform_runtime/server.py').open('a') as stream:stream.write('\n# '+name+'\n')
    return build_component(source)


@pytest.fixture
def artifacts(tmp_path):return variant(tmp_path,'a'),variant(tmp_path,'b'),variant(tmp_path,'c')


def test_component_is_deterministic_stdlib_only_and_has_no_core_payload():
    first,metadata=build_component(ROOT);assert first==build_component(ROOT)[0]
    parsed,code=validate_artifact(first,digest(first));assert parsed==metadata
    with zipfile.ZipFile(io.BytesIO(code)) as archive:
        assert not any(n.startswith(('backend/','packages/application_sdk/','three_mm_application_sdk/','components/system_runtime/')) for n in archive.namelist())
        assert set(archive.namelist())==set(INPUTS)|{'__main__.py','runtime-build.json'}
        assert 'packages/platform_wire/event_delivery.py' in archive.namelist()
        assert 'packages/__init__.py' in archive.namelist()
        assert not any(n.startswith('three_mm_platform_wire/') for n in archive.namelist())
        assert {name for name in archive.namelist() if name.startswith('components/')} == set(RUNTIME_SOURCES)
        assert not any(name.startswith(('packages/protocol/', 'packages/application_sdk/', 'three_mm_platform_runtime/')) for name in archive.namelist())


@pytest.mark.parametrize('change', [
    'components/__init__.py', 'components/platform_runtime/__init__.py',
    'components/platform_runtime/__main__.py', 'components/platform_runtime/server.py',
    'components/admin_web/server.py', 'components/public_web/server.py', 'components/setup/main.py',
    'components/platform_runtime_other/server.py', 'packages/protocol/__init__.py',
    'components/system_runtime/__init__.py','components/system_runtime/update_helper.py',
    'packages/application_sdk/__init__.py', 'backend/main.py', 'three_mm_platform_runtime/server.py'])
def test_valid_container_cannot_hide_a_missing_runtime_or_unrelated_component(change):
    """Recompute every digest so failure must come from the source boundary."""
    import deployment.platform_runtime_component as component
    blob, metadata = build_component(ROOT)
    _, code = validate_artifact(blob, digest(blob))
    with zipfile.ZipFile(io.BytesIO(code)) as archive:
        sources = {name: archive.read(name) for name in archive.namelist() if name != 'runtime-build.json'}
    if change in RUNTIME_SOURCES:
        del sources[change]
    else:
        sources[change] = b'# unrelated source\n'
    build_id = digest(component._json({name: digest(value) for name, value in sources.items()}))
    identity = {'build_id': build_id, 'authority_contract': component.AUTHORITY_CONTRACT}
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        for name, value in {**sources, 'runtime-build.json': component._json(identity)}.items():
            entry = zipfile.ZipInfo(name); entry.create_system = 3; entry.external_attr = 0o100644 << 16
            archive.writestr(entry, value)
    code = output.getvalue()
    metadata = {**metadata, 'build_id': build_id, 'runtime_sha256': digest(code), 'runtime_bytes': len(code)}
    with pytest.raises(ValueError, match='payload'):
        validate_metadata(metadata, code)


@pytest.mark.skipif(os.name!='posix',reason='Target-owned Unix environment')
def test_staged_runtime_has_its_own_environment_without_core_dependencies(tmp_path,artifacts):
    store=RuntimeStore(tmp_path/'runtime',tmp_path/'journal')
    blob,metadata=artifacts[0];identifier=store.stage(blob,digest(blob))
    python=store.releases/identifier/'.venv/bin/python'
    assert 'include-system-site-packages = false' in python.parent.parent.joinpath('pyvenv.cfg').read_text()
    executable = store.releases/identifier/'runtime.pyz'
    for arguments, option in [(['--help'], '--authority-socket'),
            (['--connector-worker', '--help'], '--socket'),
            (['--task-worker', '--help'], '--readiness-socket')]:
        result=subprocess.run([str(python),'-I',str(executable),*arguments],capture_output=True,text=True,timeout=10)
        assert result.returncode==0 and option in result.stdout, result.stderr
    isolated = """import importlib,importlib.util,sys
sys.path.insert(0,sys.argv[1])
for name in ('server','public_web','events','responses','tasks','connector_worker','connector_execute'):
    module=importlib.import_module('components.platform_runtime.'+name)
    assert sys.argv[1] in module.__file__
for name in ('components.admin_web','components.public_web','components.system_runtime','backend','three_mm_platform_runtime','packages.protocol','packages.application_sdk'):
    assert importlib.util.find_spec(name) is None,name
"""
    result=subprocess.run([str(python),'-I','-c',isolated,str(executable)],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr
    result=subprocess.run([str(python),'-I','-c','import pydantic'],capture_output=True,timeout=5)
    assert result.returncode!=0
    assert store.stage(blob,digest(blob))==identifier


class Control:
    def __init__(self):self.running=False;self.calls=[];self.interrupt=False
    def active(self):return self.running
    def stop(self):self.calls.append('stop-runtime');self.running=False
    def start(self):
        self.calls.append('start-runtime');self.running=True
        if self.interrupt:raise KeyboardInterrupt('simulated updater death')


def fingerprint():return {'pid':1234,'generation':'a'*32,'release':'fixed-core','metadata_sha256':'b'*64}
def health(identifier):return {'build_id':identifier,'core_pid':1234,'core_process_generation':'a'*32}


@pytest.mark.skipif(os.name!='posix',reason='POSIX component transaction')
def test_update_and_rollback_mutate_only_runtime_pointer(tmp_path,artifacts):
    store=RuntimeStore(tmp_path/'runtime',tmp_path/'journal');control=Control()
    for blob,metadata in artifacts[:2]:
        result=store.activate(blob,digest(blob),control=control,health=health,fingerprint=fingerprint)
        assert result['core_pid']==1234 and store.target('current')==metadata['build_id']
    assert store.target('previous')==artifacts[0][1]['build_id']
    store.rollback(control=control,health=health,fingerprint=fingerprint)
    assert store.target('current')==artifacts[0][1]['build_id']
    assert store.target('previous')==artifacts[1][1]['build_id']
    assert set(control.calls)=={'stop-runtime','start-runtime'} and store.pending() is None


@pytest.mark.skipif(os.name!='posix',reason='POSIX component transaction')
@pytest.mark.parametrize('failure',['health','core_changed','interrupted','committed'])
def test_failed_or_interrupted_update_retains_conservative_journal_and_recovers(tmp_path,artifacts,failure):
    store=RuntimeStore(tmp_path/'runtime',tmp_path/'journal');control=Control()
    first,second=artifacts[:2]
    store.activate(first[0],digest(first[0]),control=control,health=health,fingerprint=fingerprint)
    old=store.target('current')
    if failure=='health':
        def fail(identifier):
            if identifier==second[1]['build_id']:raise ValueError('candidate unhealthy')
            return health(identifier)
        with pytest.raises(ValueError):store.activate(second[0],digest(second[0]),control=control,health=fail,fingerprint=fingerprint)
    elif failure=='core_changed':
        calls=[]
        def changed():
            calls.append(1);return {**fingerprint(),'metadata_sha256':'c'*64 if len(calls)>1 else 'b'*64}
        with pytest.raises(ValueError,match='continuity'):store.activate(second[0],digest(second[0]),control=control,health=health,fingerprint=changed)
    elif failure=='interrupted':
        control.interrupt=True
        with pytest.raises(KeyboardInterrupt):store.activate(second[0],digest(second[0]),control=control,health=health,fingerprint=fingerprint)
        assert store.pending()['phase']=='switching' and store.target('current')==second[1]['build_id']
        control.interrupt=False
        RuntimeStore(store.root,store.state).recover(control,health)
    else:
        candidate=store.stage(second[0],digest(second[0]));store.link('current',candidate)
        store.journal.write_text(json.dumps({'schema_version':1,'phase':'committed','previous':old,
            'previous_previous':None,'candidate':candidate,'was_active':True}))
        store.recover(control,health)
        assert store.target('current')==candidate and store.target('previous')==old
        assert store.pending() is None;return
    assert store.target('current')==old and store.pending() is None and control.running


@pytest.mark.skipif(os.name!='posix',reason='POSIX component paths')
def test_bootstrap_retains_an_existing_compatible_independent_runtime(tmp_path,artifacts):
    store=RuntimeStore(tmp_path/'runtime',tmp_path/'journal')
    a,b=artifacts[:2];first=store.bootstrap(a[0],digest(a[0]))
    assert store.bootstrap(b[0],digest(b[0]))==first
    outside=tmp_path/'outside';outside.mkdir()
    store.root.joinpath('current').unlink();store.root.joinpath('current').symlink_to(outside)
    with pytest.raises(ValueError,match='escapes'):store.target('current')
    assert outside.is_dir()


@pytest.mark.parametrize('damage',['digest','contract','traversal','duplicate','symlink','oversize'])
def test_invalid_artifact_is_refused_before_any_service_or_pointer_mutation(tmp_path,artifacts,damage):
    blob,_=artifacts[0]
    if damage=='digest':
        with pytest.raises(ValueError):validate_artifact(blob,'f'*64)
        return
    with tarfile.open(fileobj=io.BytesIO(blob)) as archive:
        files={m.name:archive.extractfile(m).read() for m in archive}
    if damage=='contract':
        value=json.loads(files['component.json']);value['authority_contract']=999
        files['component.json']=json.dumps(value).encode()
    elif damage=='oversize':
        with pytest.raises(ValueError):validate_artifact(b'x'*(MAX_ARTIFACT+1),digest(b'x'*(MAX_ARTIFACT+1)))
        return
    output=io.BytesIO()
    with tarfile.open(fileobj=output,mode='w') as archive:
        for name,value in files.items():
            info=tarfile.TarInfo(name);info.size=len(value);archive.addfile(info,io.BytesIO(value))
        if damage in {'traversal','duplicate','symlink'}:
            name='../escape' if damage=='traversal' else 'runtime.pyz'
            info=tarfile.TarInfo(name)
            if damage=='symlink':info.type=tarfile.SYMTYPE;info.linkname='/etc/3mm'
            archive.addfile(info)
    invalid=output.getvalue()
    with pytest.raises(ValueError):validate_artifact(invalid,digest(invalid))


@pytest.mark.parametrize("contract",[None,True,1,999,"2"])
def test_component_pair_metadata_rejects_unknown_versions(contract):
    from deployment.deployment_contract import validate_platform_runtime_contract
    value={'schema_version':1,'authority_contract':contract,
        'operations':['installation.identity.get','platform.discover']}
    with pytest.raises(ValueError):validate_platform_runtime_contract(json.dumps(value).encode())
