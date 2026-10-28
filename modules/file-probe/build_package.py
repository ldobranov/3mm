"""Build a deterministic, local manifest-v2 CAP11 acceptance application."""
import argparse
import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent
MODULE_ID, VERSION = 'org.3mm.file-probe', '1.0.0'


def obj(properties):
    return dict(type='object', properties=properties, required=list(properties), additionalProperties=False)


def descriptors():
    manifest = dict(manifest_version=2, module_id=MODULE_ID, version=VERSION, name='File and media probe',
        description='CAP11 streaming files and optional image transformations.', runtimes=['core','ui'],
        entrypoints={'core':'application-extension.json','ui':'compiled-ui.json'},
        compatibility={'protocol':'1.0','core':'>=0.3.0','agent':'>=0.1.0','architectures':['any']},
        capabilities={'provides':[],'consumes':[]},permissions=['data.read','data.write','process.spawn'],
        configuration_schema=obj({}),configuration_defaults={},registrations=[],
        health_check={'type':'json_file','path':'application-extension.json'})
    labels={'read':'Read files','write':'Upload and delete files','publish':'Create public download links','transform':'Create image derivatives'}
    definition=dict(application_extension_version=1,module_id=MODULE_ID,version=VERSION,
        service=dict(artifact=f'service/file_probe-{VERSION}-py3-none-any.whl',artifact_sha256='0'*64,
            entrypoint='file_probe.service:create_service',health_operation_id='health',sdk_version='1.3'),
        permissions=[dict(permission_id='files_'+key,label={'en':value},description={'en':value+' in this application.'}) for key,value in labels.items()],
        operations=[dict(operation_id='health',kind='query',audiences=['internal'],idempotency='forbidden',output_schema=obj({'status':{'type':'string','enum':['ready']}}))],
        storage=dict(schema_revision='0001',migration_entrypoint='file_probe.service:get_migrations',classifications=['private'],contains_personal_data=False,
            private_files=dict(file_contract_version=2,namespace='private_files',mode='read_write',max_file_bytes=8*1024*1024,
                max_total_bytes=32*1024*1024,max_files=64,max_uploads=2,max_staging_bytes=16*1024*1024,
                upload_ttl_seconds=3600,public_links=True,media_transforms=True)),
        routes=[dict(route_id='files',entrypoint_id='files',audience='operator',required_permissions=['files_read'],
            private_files=dict(contract_version=1,**{key+'_permission':'files_'+key for key in labels}))])
    ui=dict(compiled_ui_version=1,module_id=MODULE_ID,version=VERSION,entrypoints=[dict(entrypoint_id='files',kind='route',
        source='source/frontend/Files.vue',route='/file-probe',label={'en':'File and media probe'})])
    return manifest,definition,ui


def write(archive,name,data):
    info=zipfile.ZipInfo(name,(2026,1,1,0,0,0));info.create_system=3
    info.external_attr=0o100644<<16;info.compress_type=zipfile.ZIP_DEFLATED
    archive.writestr(info,data)


def build_package():
    manifest,definition,ui=descriptors()
    files={'file_probe/'+p.name:p.read_bytes().replace(b'\r\n',b'\n') for p in (ROOT/'service/file_probe').glob('*.py')}
    dist=f'file_probe-{VERSION}.dist-info'
    files[dist+'/METADATA']=f'Metadata-Version: 2.1\nName: file-probe\nVersion: {VERSION}\n'.encode()
    files[dist+'/WHEEL']=b'Wheel-Version: 1.0\nGenerator: 3mm\nRoot-Is-Purelib: true\nTag: py3-none-any\n'
    record=io.StringIO(newline='');writer=csv.writer(record,lineterminator='\n')
    for name,data in sorted(files.items()):writer.writerow([name,'sha256='+base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode(),len(data)])
    writer.writerow([dist+'/RECORD','','']);files[dist+'/RECORD']=record.getvalue().encode()
    wheel=io.BytesIO()
    with zipfile.ZipFile(wheel,'w') as archive:
        for name,data in sorted(files.items()):write(archive,name,data)
    definition['service']['artifact_sha256']=hashlib.sha256(wheel.getvalue()).hexdigest()
    result=io.BytesIO()
    with zipfile.ZipFile(result,'w') as archive:
        for name,value in [('manifest.json',manifest),('application-extension.json',definition),('compiled-ui.json',ui)]:
            write(archive,name,json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())
        write(archive,definition['service']['artifact'],wheel.getvalue())
        write(archive,'source/frontend/Files.vue',(ROOT/'source/frontend/Files.vue').read_bytes().replace(b'\r\n',b'\n'))
    return result.getvalue()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();blob=build_package();args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('xb') as stream:stream.write(blob)
    print(hashlib.sha256(blob).hexdigest())
