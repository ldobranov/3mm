"""Explicit disposable root/systemd test of the helper's real network boundary."""
import http.server
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import unittest
import uuid


@unittest.skipUnless(sys.platform == 'linux' and os.geteuid() == 0
    and os.getenv('THREE_MM_RUN_COMPONENT_NETWORK_TESTS') == '1'
    and Path('/run/systemd/system').is_dir(), 'Explicit owned root/systemd acceptance only')
class ComponentHelperNetworkTests(unittest.TestCase):
    def test_agent_readiness_allows_only_loopback_not_external_traffic(self):
        source = (Path(os.environ['THREE_MM_HELPER_TEST_SOURCE']) if 'THREE_MM_HELPER_TEST_SOURCE' in os.environ
                  else Path(__file__).resolve().parents[2])
        unit = source / 'deployment/systemd/3mm-update-helper.service'
        policy = {}
        for line in unit.read_text().splitlines():
            if '=' in line and not line.startswith('#'):
                key, value = line.split('=', 1)
                if key in ('RestrictAddressFamilies', 'IPAddressDeny', 'IPAddressAllow'):
                    policy.setdefault(key, []).append(value)

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                body = b'{"component":"agent","build_id":"test","pid":123}'
                self.send_response(200)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            code = '''import errno,json,socket,sys
source,mode,port=sys.argv[1:];sys.path.insert(0,source)
from deployment.service_component import _http_identity
if mode=='before':
 try:_http_identity('http://127.0.0.1:'+port+'/component-health')
 except OSError as e:assert e.errno in (errno.EAFNOSUPPORT,errno.EPERM),repr(e)
 else:raise AssertionError('Unix-only policy unexpectedly permitted TCP')
elif mode=='local':
 assert _http_identity('http://127.0.0.1:'+port+'/component-health')=={'component':'agent','build_id':'test','pid':123}
else:
 with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:
  try:s.sendto(b'CAP03-policy-check',('192.0.2.1',9))
  except OSError as e:assert e.errno in (errno.EACCES,errno.EPERM),repr(e)
  else:raise AssertionError('Non-local traffic was not denied')
print(json.dumps({'boundary':mode,'passed':True}))
'''
            for mode in ('before', 'local', 'denied'):
                with self.subTest(boundary=mode):
                    properties = ['--property=RestrictAddressFamilies=AF_UNIX'] if mode == 'before' else [
                        '--property=' + key + '=' + value for key, values in policy.items() for value in values]
                    command = ['systemd-run', '--quiet', '--wait', '--pipe', '--collect', '--service-type=exec',
                        '--unit=3mm-cap03-network-' + uuid.uuid4().hex, '--property=NoNewPrivileges=true',
                        '--property=RuntimeMaxSec=15s', '--property=ProtectSystem=strict', *properties,
                        sys.executable, '-B', '-I', '-c', code, str(source), mode, str(server.server_port)]
                    result = subprocess.run(command, capture_output=True, text=True, timeout=25)
                    self.assertEqual(result.returncode, 0, result.stderr[-3000:])
                    self.assertEqual(json.loads(result.stdout), {'boundary': mode, 'passed': True})
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
