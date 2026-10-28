"""Real CLI/HTTP smoke on an isolated loopback port; no systemd or network mutation."""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def test_real_host_setup_process_closes_access_after_setup_without_core(tmp_path):
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1',0))
        port=reservation.getsockname()[1]
    data=tmp_path/'provisioning'
    env={**os.environ,'DATABASE_URL':'sqlite:///'+str(tmp_path/'missing-core.db'),
         'THREE_MM_NETWORK_BACKEND':'host'}
    root=Path(__file__).resolve().parents[2]
    command=[sys.executable,'-m','setup_service','--data-dir',str(data)]
    process=subprocess.Popen([*command,'--port',str(port),'--log-level','warning'],cwd=root,env=env,
                             stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    def call(path,body=None):
        headers={'Content-Type':'application/json'}
        request=Request('http://127.0.0.1:'+str(port)+path,
                        data=json.dumps(body).encode() if body is not None else None,headers=headers)
        try:
            with urlopen(request,timeout=2) as response:
                return response.status,json.load(response)
        except HTTPError as error:
            return error.code,json.load(error)
    try:
        deadline=time.monotonic()+15
        while True:
            try:
                assert call('/ready')[0]==200
                break
            except (URLError,TimeoutError):
                if process.poll() is not None or time.monotonic()>deadline:
                    raise AssertionError('Isolated setup process did not start')
                time.sleep(.05)
        assert call('/api/v1/setup/capabilities')[1]['network_modes']==['preserve','local']
        status,outcome=call('/api/v1/setup/configure',body=dict(network_mode='preserve',role='node',
            hub_endpoint='https://hub.test',locale='en-US',device_name='node',administrator_name='operator'))
        assert status==200 and outcome['enrollment']=='awaiting_pairing'
        assert call('/api/v1/setup/capabilities')[0]==403
        assert not (tmp_path/'missing-core.db').exists()
        assert json.loads((data/'provisioning.json').read_text())['role']=='node'
    finally:
        process.terminate()
        process.communicate(timeout=10)
        assert process.poll() is not None
