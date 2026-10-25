import json
import os
from pathlib import Path
import pytest
from three_mm_protocol import diagnostics as module
from three_mm_protocol.diagnostics import DiagnosticSession, MAX_EXPORT_BYTES
from three_mm_protocol.diagnostic_snapshot import read_export, timeline, component_inventory, read_regular
from tools.debug_snapshot import snapshot

TRACE='platform_'+'a'*32
INSTANCE='b'*24


def emit(session,**changes):
    session.record(**dict(trace_id=TRACE,stage='sdk.call',result='ok',reason='ok',duration_ms=1,
                         operation='checkpoint.get',instance_id=INSTANCE,**changes))


def exported(session):
    with session.export() as chunks:return b''.join(chunks)


def test_exact_scope_ttl_and_restart_do_not_enable_execution(monkeypatch):
    clock=[1.0];monkeypatch.setattr(module.time,'monotonic',lambda:clock[0])
    session=DiagnosticSession('sdk','1.3');session.start(2,profile='development',operation='checkpoint.get',instance_id=INSTANCE,trace_id=TRACE)
    emit(session)
    session.record(trace_id=TRACE,stage='sdk.call',result='denied',reason='operation_denied',duration_ms=2,operation='checkpoint.put',instance_id=INSTANCE)
    session.record(trace_id=TRACE,stage='sdk.call',result='ok',reason='ok',duration_ms=1,operation='checkpoint.get',instance_id='c'*24)
    assert len(read_export(exported(session))['records'])==1
    clock[0]=4
    assert session.snapshot()['records']==[] and not session.status()['active']
    assert not DiagnosticSession('sdk','1.3').status()['active']


@pytest.mark.parametrize('change',[{'payload':'password=secret'},{'reason':'Bearer token'},{'component':'foreign'},{'timestamp':True},{'duration_ms':float('inf')},{'parent_span_id':'secret/path'},{'instance_id':'private'}, {'operation':'arbitrary.payload'}])
def test_import_rejects_non_metadata_before_retaining_it(change):
    session=DiagnosticSession('sdk','1.3');session.start();emit(session)
    lines=exported(session).splitlines();value=json.loads(lines[1]);value.update(change)
    bad=lines[0]+b'\n'+json.dumps(value).encode()+b'\n'
    with pytest.raises(ValueError):read_export(bad)


def test_export_import_and_shared_timeline_keep_source_and_missing_observations():
    sdk=DiagnosticSession('sdk','1.3');sdk.start();emit(sdk)
    core=DiagnosticSession('core','1.0');core.start();core.record(trace_id=TRACE,stage='core.request',result='denied',reason='operation_denied',duration_ms=2,operation='checkpoint.get',instance_id=INSTANCE)
    combined=timeline(core.snapshot(),read_export(exported(sdk)))
    assert len(combined['records'])==2 and {r['trace_id'] for r in combined['records']}=={TRACE}
    assert {r['source'] for r in combined['records']}=={'local','imported'}
    assert combined['missing_components'] and 'runtime' in combined['missing_components']
    assert len(timeline(core.snapshot(),read_export(exported(sdk)),limit=1)['records'])==1
    assert timeline(core.snapshot(),read_export(exported(sdk)),limit=1)['truncated']
    assert snapshot(exported(sdk))['core_connection']=='not_requested'
    assert 'password' not in json.dumps(combined)


@pytest.mark.parametrize('payload',[b'',b'x'*(MAX_EXPORT_BYTES+1),b'{"session":{},"session":{}}\n',b'{"session":{}}\n',b'{}\n'+b'x'*2049])
def test_import_framing_and_memory_are_bounded(payload):
    with pytest.raises(ValueError):read_export(payload)


def test_inventory_only_reads_bounded_component_metadata_and_rejects_foreign_pins(tmp_path):
    root=tmp_path/'agent';release=root/'releases'/('a'*64);release.mkdir(parents=True)
    (release/'component.json').write_text(json.dumps({'component':'agent','build_id':'a'*64,'secret':'never-export'}))
    (root/'current').symlink_to(release,target_is_directory=True)
    row,=component_inventory({'agent':root})
    assert row['state']=='installed' and row['health']=='unknown' and 'never-export' not in json.dumps(row)
    (release/'component.json').write_text(json.dumps({'component':'public-web','build_id':'a'*64}))
    assert component_inventory({'agent':root})[0]['state']=='unavailable'
    link=tmp_path/'link';link.symlink_to(release/'component.json')
    if hasattr(os,'O_NOFOLLOW'):
        with pytest.raises(OSError):read_regular(link,8192)


def test_offline_command_runs_with_core_and_sqlalchemy_imports_blocked(tmp_path):
    import subprocess,sys
    source=Path(__file__).resolve().parents[2]
    output=tmp_path/'snapshot.json'
    code="""import importlib.abc,runpy,sys
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self,name,*args):
  if name.split('.')[0] in {'backend','sqlalchemy'}:raise AssertionError('Core imported by offline diagnostics')
sys.meta_path.insert(0,Block())
sys.argv=['diagnostic_snapshot','--output',sys.argv[1]]
runpy.run_module('three_mm_protocol.diagnostic_snapshot',run_name='__main__')
"""
    result=subprocess.run([sys.executable,'-c',code,str(output)],cwd=source,capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr
    value=json.loads(output.read_text())
    assert value['core_connection']=='not_requested' and 'core' in value['timeline']['missing_components']
