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
from backend.artifacts.packages import validate_module_package, MAX_PACKAGE_BYTES
from packages.protocol.diagnostic_snapshot import read_regular


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
    create=commands.add_parser('init',help='Create a new local application source project; never overwrite')
    create.add_argument('destination',type=Path)
    create.add_argument('--module-id',required=True)
    create.add_argument('--name',required=True)
    create.add_argument('--route',required=True)
    preview=commands.add_parser('preview',help='Loopback-only mock UI preview; no Core or installation')
    preview.add_argument('project',type=Path)
    preview.add_argument('--frontend',type=Path,help='Existing Core frontend toolchain directory')
    preview.add_argument('--port',type=int,default=5178)
    commands.add_parser('schemas',help='Export current public structural schemas; not semantic approval')
    catalog=commands.add_parser('catalog',help='Export current authoring contracts, or validate project declarations; no execution or installation')
    catalog.add_argument('project',type=Path,nargs='?',help='Optional local source project; never imports application code')
    compare=commands.add_parser('compare',help='Review declaration changes between two local ZIPs for the same application')
    compare.add_argument('previous',type=Path)
    compare.add_argument('candidate',type=Path)
    compare.add_argument('--json',action='store_true',help='Machine-readable comparison')
    client=commands.add_parser('generate-client',help='Generate a typed local UI client; no application execution or API login')
    client.add_argument('project',type=Path)
    client.add_argument('--output',type=Path,help='Project-relative source/frontend/*.ts; defaults to generated_client in development.json')
    client.add_argument('--replace',action='store_true',help='Explicitly replace only this generator\'s existing client for the same application')
    check=commands.add_parser('check',help='Check/build a local application project; no installation or API login')
    check.add_argument('project',type=Path)
    check.add_argument('--output',type=Path,required=True,help='New ZIP outside the source project')
    check.add_argument('--frontend',type=Path,help='Existing Core frontend toolchain directory')
    check.add_argument('--json',action='store_true',help='Machine-readable check result')
    check.add_argument('--previous-archive',type=Path,help='Explicit trusted previous ZIP; executes the project upgrade fixture on disposable data')
    for action in ('validate','upload'):
        commands.add_parser(action).add_argument('archive',type=Path)
    for action in ('activate','rollback'):
        commands.add_parser(action).add_argument('sha256',help='Exact archive hash; rollback explicitly selects the previous package')
    trace=commands.add_parser('trace-start');trace.add_argument('--instance-id');trace.add_argument('--operation');trace.add_argument('--ttl',type=int,default=600)
    commands.add_parser('trace-stop');records=commands.add_parser('trace-export');records.add_argument('--output',type=Path,required=True)
    commands.add_parser('status')
    args=parser.parse_args()
    try:
        if args.action=='init':
            from tools.application_scaffold import create_project
            result=create_project(args.destination,module_id=args.module_id,name=args.name,route=args.route)
            print(json.dumps(result,ensure_ascii=False,sort_keys=True))
            return
        if args.action=='preview':
            from tools.application_preview import preview_project
            preview_project(args.project,frontend=args.frontend,port=args.port)
            return
        if args.action=='schemas':
            from packages.protocol.extension_schemas import extension_schema_catalog
            print(json.dumps(extension_schema_catalog(),ensure_ascii=False,sort_keys=True))
            return
        if args.action=='catalog':
            from tools.application_catalog import application_catalog
            from tools.application_project import ProjectCheckError
            try:
                result=application_catalog(args.project)
            except (ProjectCheckError,OSError,ValueError) as error:
                print(json.dumps({'status':'failed','stage':getattr(error,'stage','catalog'),
                    'message':str(error) if isinstance(error,ProjectCheckError) else 'Catalog inputs are invalid or unavailable.',
                    'installation':'not_requested'},ensure_ascii=False,sort_keys=True))
                raise SystemExit(1) from None
            print(json.dumps(result,ensure_ascii=False,sort_keys=True))
            return
        if args.action=='compare':
            from tools.application_package_review import compare_application_packages, PackageReviewError
            try:
                result=compare_application_packages(args.previous,args.candidate)
            except PackageReviewError as error:
                if args.json:
                    print(json.dumps({'status':'failed','message':str(error),'installation':'not_requested'}))
                else:
                    print('Package comparison stopped: '+str(error))
                raise SystemExit(1) from None
            if args.json:
                print(json.dumps(result,sort_keys=True))
            else:
                print('Application package comparison (declarations only): '+result['module_id'])
                for side in ('previous','candidate'):
                    identity=result[side]
                    print(f"{side.title()}: {identity['version']} | data revision {identity['schema_revision']} | SHA256 {identity['sha256']}")
                print('Service artifact bytes: '+('changed' if result['service_artifact_changed'] else 'unchanged'))
                for document, change in result['changes'].items():
                    print(document+': '+', '.join(change['fields']))
                    for field, items in change['items'].items():
                        for key in ('added','removed'):
                            if items[key]:print(f"  {field} {key}: "+', '.join(items[key]))
                        for item, fields in items.get('changed',{}).items():
                            print(f"  {field} {item}: "+', '.join(fields))
                if not result['changes']:print('No declaration differences (excluding version and artifact identity).')
                print('No code was run. This comparison is not migration verification, approval or installation.')
            return
        if args.action=='generate-client':
            from tools.application_client import generate_client
            from tools.application_project import configuration, ProjectCheckError
            try:
                output=args.output
                if output is None:
                    declared=configuration(args.project).get('generated_client')
                    if not declared:
                        raise ProjectCheckError('client', 'Declare generated_client or provide --output source/frontend/*.ts.')
                    output=Path(declared)
                result=generate_client(args.project,output,replace=args.replace)
            except (ProjectCheckError,OSError,ValueError) as error:
                print(json.dumps({'status':'failed','stage':getattr(error,'stage','client'),
                    'message':str(error) if isinstance(error,ProjectCheckError) else 'Client inputs are invalid or unavailable.',
                    'installation':'not_requested'},ensure_ascii=False,sort_keys=True))
                raise SystemExit(1) from None
            print(json.dumps(result,ensure_ascii=False,sort_keys=True))
            return
        if args.action=='check':
            from tools.application_project import check_project, ProjectCheckError
            try:
                result=check_project(args.project,args.output,frontend=args.frontend,previous_archive=args.previous_archive)
            except (ProjectCheckError,OSError,ValueError) as error:
                result={'status':'failed','stage':getattr(error,'stage','project'),
                    'message':str(error) if isinstance(error,ProjectCheckError) else 'Project inputs are invalid or unavailable.',
                    'installation':'not_requested'}
            if args.json:
                print(json.dumps(result,sort_keys=True,ensure_ascii=False))
            else:
                print('Application check: '+result['status'].upper())
                if result['status']=='passed':
                    package=result['package']
                    print(f"{package['module_id']} {package['version']}")
                    print(f"Python: {result['python_passed']} passed | UI: {result['ui_passed']} passed | TypeScript and compiler: passed")
                    migrations=result['migrations']
                    print(f"Packaged migrations: {migrations['target_revision']} | reopen and rollback: passed | prefix upgrades: {migrations['prefix_upgrade_count']}")
                    if 'generated_client' in result:
                        print('Generated client: current')
                    print('Previous package upgrade: '+result.get('upgrade',{}).get('status','not_requested'))
                    print('Project scenarios: missing permission, revoked access, unavailable provider - passed')
                    print('Package SHA256: '+package['sha256'])
                    print('Package: '+package['path'])
                    print('Human permissions to review: '+', '.join(result['review']['human_permissions']))
                    print('Optional resources to select/review: '+', '.join(result['review']['optional_resources']))
                else:
                    print('Stopped at '+result['stage']+': '+result['message'])
                    if result.get('package_publication') in {'published','unconfirmed'}:
                        print('Package publication: '+result['package_publication'])
                        print('Package SHA256: '+result['package']['sha256'])
                        print('Package: '+result['package']['path'])
                    for issue in result.get('issues',[]):
                        print('  '+'.'.join(str(part) for part in issue['path'])+': '+issue['code'])
                print('No installation, grants or live-device acceptance. Local tests are not native-code isolation.')
                if 'report' in result:print('Report: '+result['report'])
                if 'log' in result:print('Local check log: '+result['log'])
            if result['status']!='passed':raise SystemExit(1)
            return
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
            from packages.protocol.diagnostic_snapshot import read_export
            read_export(data)
            with args.output.open('xb') as stream:stream.write(data)
            result={'status':'exported'}
        else:result=json.loads(client.request('GET','/api/v1/diagnostics/workspace'))
        print(json.dumps(result,sort_keys=True))
    except (ValueError,OSError) as error:
        if args.action in ('init','preview'):
            from tools.application_project import ProjectCheckError
            message=str(error) if isinstance(error,ProjectCheckError) else 'Local project or toolchain is unavailable.'
            raise SystemExit(message+' No installation or remote action was performed.') from None
        raise SystemExit('Development action failed. Inspect current state; no action was retried.') from None


if __name__=='__main__':main()
