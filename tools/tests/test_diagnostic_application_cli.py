"""Exercise the shipped support reader over a real loopback HTTP transport."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import warnings

import pytest
from tools import diagnostics


OWNER = 'org.example.local'
CMD = 'cmd_'+'a'*32


@pytest.fixture
def endpoint():
    value = dict(schema_version=1, kind='application_support', status='ready', cases=[],
                 application=dict(module_id=OWNER, instance_id='1'*24, artifact_sha256='2'*64,
                                  observation_revision='3'*64), service=dict(state='not_running'),
                 coverage=dict(failure_history='ready'), internal='PRIVATE TEST CONTENT')
    state = dict(value=value, seen=[], status=200)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            state['seen'].append((self.path, self.headers.get('Authorization') == 'Bearer fixture-only'))
            self.send_response(state['status'])
            if state['status'] == 302:
                self.send_header('Location','/unexpected-second-request')
            self.end_headers()
            self.wfile.write(json.dumps(state['value']).encode())

    with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server:
        worker = Thread(target=server.serve_forever, kwargs={'poll_interval':0.02}, daemon=True)
        worker.start()
        try:
            yield f'http://127.0.0.1:{server.server_port}', state
        finally:
            server.shutdown()
            worker.join(timeout=2)


def test_named_read_is_one_get_and_rechecks_current_access_without_retry(endpoint, monkeypatch, capsys):
    url, state = endpoint
    state['value']['work'] = dict(reference=CMD, status='not_found_in_scope')
    monkeypatch.setattr(diagnostics, '_private_token', lambda: 'fixture-only')
    args = ['application','--url',url,'--module-id',OWNER,'--reference',CMD,'--json']
    assert diagnostics.main(args)==0
    out = capsys.readouterr().out
    summary = json.loads(out)
    assert summary['application']['module_id']==OWNER and summary['work']==state['value']['work']
    assert 'fixture-only' not in out and 'PRIVATE' not in out
    expected=(f'/api/v1/application-extensions/{OWNER}/support-snapshot?reference={CMD}', True)
    assert state['seen']==[expected]
    state['status']=403
    assert diagnostics.main(args)==1
    captured=capsys.readouterr()
    assert not captured.out and '403' in captured.err and 'PRIVATE' not in captured.err
    assert state['seen']==[expected,expected]


@pytest.mark.parametrize('change', ['module','reference','missing-reference','unexpected-reference','kind','browser','redirect'])
def test_refuses_wrong_scope_or_redirect_and_never_reads_again(endpoint, change):
    url, state = endpoint
    value=state['value']
    reference=None
    if change=='module': value['application']['module_id']='org.example.other'
    elif change=='kind': value['kind']='not_application_support'
    elif change=='browser': value['browser']={}
    elif change=='redirect': state['status']=302
    elif change=='missing-reference': reference=CMD
    else:
        reference = CMD if change=='reference' else None
        value['work']=dict(reference='cmd_'+'b'*32,status='not_found_in_scope')
    with pytest.raises(ValueError):
        diagnostics.inspect_application(url,'fixture-only',module_id=OWNER,reference=reference)
    assert len(state['seen'])==1


def test_unsafe_parameters_or_visible_token_prompt_cannot_start_a_request(monkeypatch, capsys):
    monkeypatch.setattr(diagnostics.urllib.request,'build_opener',lambda *_:pytest.fail('No network'))
    monkeypatch.setattr(diagnostics.getpass,'getpass',lambda *_:pytest.fail('No prompt for malformed target'))
    for module, ref in [('../other',None), (OWNER,'not a reference')]:
        args=['application','--url','http://127.0.0.1','--module-id',module]
        assert diagnostics.main(args+(['--reference',ref] if ref else []))==1
    monkeypatch.setattr(diagnostics.getpass,'getpass',
        lambda *_:warnings.warn('PRIVATE PROMPT DETAIL', diagnostics.getpass.GetPassWarning))
    assert diagnostics.main(['application','--url','http://127.0.0.1','--module-id',OWNER])==1
    err=capsys.readouterr().err
    assert 'Private token input is unavailable' in err and 'PRIVATE PROMPT DETAIL' not in err


def test_bad_origins_and_case_ids_never_prompt_or_save(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(diagnostics, '_private_token', lambda: pytest.fail('No prompt for invalid requests'))
    output = tmp_path / 'evidence.json'
    for origin in ('https://@example.com', 'http://local\nhost', 'https://example.com:70000',
                   'http://[::1]suffix', 'http://127.0.0.1:0', 'http://rasp-3mm.local',
                   'https://example.com?private', 'https://example.com/path'):
        for args in (['collect','--output',str(output)], ['application','--module-id',OWNER]):
            assert diagnostics.main([*args, '--url',origin]) == 1
    assert diagnostics.main(['collect','--url','https://example.com','--trace-id','bad','--output',str(output)]) == 1
    assert not output.exists() and 'private' not in capsys.readouterr().err


def test_trace_collection_accepts_only_its_own_kind_and_selection(endpoint, tmp_path, monkeypatch, capsys):
    url, state = endpoint
    monkeypatch.setattr(diagnostics, '_private_token', lambda: 'fixture-only')
    trace = 'invoke_'+'e'*32
    output = tmp_path/'cases.json'
    args = ['collect','--url',url,'--trace-id',trace,'--output',str(output)]
    assert diagnostics.main(args) == 1 and not output.exists()  # actual application snapshot, not a case collection
    value = dict(schema_version=1,status='ready',cases=[],selection=dict(trace_id=trace,result='not_found_in_retained_evidence'))
    state['value'] = {**value,'selection':{**value['selection'],'trace_id':None}}
    assert diagnostics.main(args) == 1 and not output.exists()
    state['value'] = {**value,'trace_records':[{'trace_id':'invoke_'+'f'*32}]}
    assert diagnostics.main(args) == 1 and not output.exists()
    state['value'] = value
    assert diagnostics.main(args) == 0 and json.loads(output.read_text()) == value
    assert state['seen'] == [('/api/v1/diagnostics/cases?trace_id='+trace,True)] * 4
    captured = capsys.readouterr()
    assert 'fixture-only' not in captured.out+captured.err
