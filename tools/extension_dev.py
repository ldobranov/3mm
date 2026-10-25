"""Reviewed extension development through current validation/admin APIs; no grants or release controls."""
import argparse
import getpass
import hashlib
import json
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request
from backend.services.module_packages import validate_module_package, MAX_PACKAGE_BYTES
from three_mm_protocol.diagnostic_snapshot import read_regular


class DevelopmentError(ValueError): pass


def inspect_package(path):
    blob=read_regular(Path(path),MAX_PACKAGE_BYTES)
    validated=validate_module_package(blob)
    return blob,{'module_id':validated.manifest.module_id,'version':validated.manifest.version,
                 'sha256':validated.sha256,'bytes':len(blob)}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


class DevelopmentClient:
    def __init__(self,url,token):
        parsed=urllib.parse.urlsplit(url)
        if (parsed.scheme not in {'http','https'} or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment or parsed.path not in {'','/'}
                or parsed.scheme=='http' and parsed.hostname not in {'127.0.0.1','localhost','::1'}):
            raise DevelopmentError('Use HTTPS or an explicit loopback HTTP development server')
        if not isinstance(token,str) or not token or any(c in token for c in '\r\n'):
            raise DevelopmentError('A current admin token is required')
        self.url=url.rstrip('/');self.token=token
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())

    def request(self,method,path,body=None,content_type='application/json'):
        request=urllib.request.Request(self.url+path,data=body,method=method,
            headers={'Authorization':'Bearer '+self.token,'Content-Type':content_type})
        try:
            with self.opener.open(request,timeout=30) as response:
                data=response.read(4*1024*1024+1)
                if len(data)>4*1024*1024:raise DevelopmentError('Development response exceeds budget')
                return data
        except urllib.error.HTTPError as exc:
            raise DevelopmentError('Admin request refused (HTTP '+str(exc.code)+'); inspect current state before another action') from None
        except (OSError,urllib.error.URLError):
            raise DevelopmentError('Transport outcome is unconfirmed; do not replay a mutation') from None

    def upload(self,path):
        blob,identity=inspect_package(path)
        boundary='3mmDevelopment'+hashlib.sha256(blob).hexdigest()
        body=('--'+boundary+'\r\nContent-Disposition: form-data; name="package"; filename="candidate.zip"\r\nContent-Type: application/zip\r\n\r\n').encode()+blob+('\r\n--'+boundary+'--\r\n').encode()
        data=json.loads(self.request('POST','/api/v1/modules/packages',body,'multipart/form-data; boundary='+boundary))
        if data.get('sha256')!=identity['sha256']:raise DevelopmentError('Uploaded identity differs; inspect state')
        return identity

    def activate(self,sha256):
        if re.fullmatch('[0-9a-f]{64}',sha256) is None:raise DevelopmentError('Use an exact candidate or previous archive SHA256')
        # Existing server-side review/lifecycle/grants are mandatory. No bypass.
        self.request('POST','/api/v1/application-extensions/packages/'+sha256+'/activate',b'{}')
        return {'requested_sha256':sha256,'status':'active'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',help='Explicit isolated development Core URL')
    commands=parser.add_subparsers(dest='action',required=True)
    for action in ('validate','upload'):
        commands.add_parser(action).add_argument('archive',type=Path)
    for action in ('activate','rollback'):
        commands.add_parser(action).add_argument('sha256',help='Exact archive hash; rollback explicitly selects the previous package')
    trace=commands.add_parser('trace-start');trace.add_argument('--instance-id');trace.add_argument('--operation');trace.add_argument('--ttl',type=int,default=600)
    commands.add_parser('trace-stop');records=commands.add_parser('trace-export');records.add_argument('--output',type=Path,required=True)
    commands.add_parser('status')
    args=parser.parse_args()
    try:
        if args.action=='validate':print(json.dumps(inspect_package(args.archive)[1]));return
        if args.url is None:parser.error('--url must select an explicit isolated development Core')
        client=DevelopmentClient(args.url,getpass.getpass('Current admin token: '))
        if args.action=='upload':result=client.upload(args.archive)
        elif args.action in ('activate','rollback'):result=client.activate(args.sha256)
        elif args.action=='trace-start':
            result=json.loads(client.request('POST','/api/v1/diagnostics/session',json.dumps({'profile':'development','ttl_seconds':args.ttl,'instance_id':args.instance_id,'operation':args.operation}).encode()))
        elif args.action=='trace-stop':result=json.loads(client.request('DELETE','/api/v1/diagnostics/session'))
        elif args.action=='trace-export':
            data=client.request('GET','/api/v1/diagnostics/session/records')
            from three_mm_protocol.diagnostic_snapshot import read_export
            read_export(data)
            with args.output.open('xb') as stream:stream.write(data)
            result={'status':'exported'}
        else:result=json.loads(client.request('GET','/api/v1/diagnostics/workspace'))
        print(json.dumps(result,sort_keys=True))
    except (ValueError,OSError):raise SystemExit('Development action failed. Inspect current state; no action was retried.') from None


if __name__=='__main__':main()
