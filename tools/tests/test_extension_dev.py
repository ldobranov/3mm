import importlib.util
import json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import threading
import pytest
from tools.extension_dev import DevelopmentClient,DevelopmentError,inspect_package

ROOT=Path(__file__).resolve().parents[2]


def package(tmp_path):
    spec=importlib.util.spec_from_file_location('public_builder',ROOT/'modules/public-web-reference/build_reference_package.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    path=tmp_path/'candidate.zip';path.write_bytes(module.build_package());return path


@pytest.mark.parametrize('url',['http://device.local','https://user:password@example.com','https://example.com?token=secret','https://example.com/path'])
def test_client_rejects_unsafe_origins_before_request(url):
    with pytest.raises(DevelopmentError):DevelopmentClient(url,'token')


def test_real_local_upload_pins_exact_bytes_and_refusals_never_retry(tmp_path):
    candidate=package(tmp_path);blob,identity=inspect_package(candidate);seen=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            body=self.rfile.read(int(self.headers['Content-Length']));seen.append((self.path,body,self.headers.get('Authorization')))
            if self.path.endswith('/packages'):
                assert blob in body
                payload=json.dumps({'sha256':identity['sha256']}).encode();self.send_response(200)
            else:payload=b'{"detail":"password=never-echo"}';self.send_response(409)
            self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    try:
        client=DevelopmentClient('http://127.0.0.1:'+str(server.server_port),'current-admin')
        assert client.upload(candidate)==identity
        with pytest.raises(DevelopmentError,match='HTTP 409') as error:client.activate(identity['sha256'])
        assert 'never-echo' not in str(error.value)
        assert len(seen)==2 and all(item[2]=='Bearer current-admin' for item in seen)
        with pytest.raises(DevelopmentError):client.activate('bad')
        assert len(seen)==2
    finally:server.shutdown();server.server_close();worker.join(timeout=2)


def test_redirect_does_not_forward_credentials_or_replay_a_mutation():
    seen=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            seen.append(self.path);self.send_response(307);self.send_header('Location','/other');self.send_header('Content-Length','0');self.end_headers()
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    try:
        client=DevelopmentClient('http://127.0.0.1:'+str(server.server_port),'private-token')
        with pytest.raises(DevelopmentError):client.request('POST','/effect',b'{}')
        assert seen==['/effect']
    finally:server.shutdown();server.server_close();worker.join(timeout=2)


def test_remote_action_requires_an_explicit_target_before_prompt_or_network():
    import subprocess,sys
    result=subprocess.run([sys.executable,'-m','tools.extension_dev','status'],cwd=ROOT,capture_output=True,text=True,timeout=5)
    assert result.returncode==2 and 'explicit isolated development Core' in result.stderr
    assert 'Current admin token' not in result.stderr
