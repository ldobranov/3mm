"""Build a local Contacts candidate with the optional shared CRUD dependency.

No upload, activation, overwrite of a published artifact or Core import.
"""
import argparse,base64,csv,hashlib,io,json,sys,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent
LIBRARY=ROOT.parents[1]/'libraries/three_mm_crud'
VERSION='1.0.0'
MODULE_ID='org.3mm.contacts'

def descriptors():
    sys.path.insert(0,str(LIBRARY))
    try:
        from three_mm_crud.descriptors import obj,declarations,storage_declaration
    finally:sys.path.remove(str(LIBRARY))
    definition=json.loads((ROOT/'crud.json').read_text())
    permissions,operations=declarations(definition)
    manifest=dict(manifest_version=2,module_id=MODULE_ID,name='Contacts',version=VERSION,
        description='Shared contact directory with application-owned data.',runtimes=['core','ui'],
        entrypoints={'core':'application-extension.json','ui':'compiled-ui.json'},
        compatibility={'protocol':'1.0','core':'>=0.3.0','agent':'>=0.1.0','architectures':['any']},
        capabilities={'provides':[],'consumes':[]},permissions=['data.read','data.write','process.spawn'],
        configuration_schema=obj({}),configuration_defaults={},registrations=[],
        health_check={'type':'json_file','path':'application-extension.json'})
    application=dict(application_extension_version=1,module_id=MODULE_ID,version=VERSION,
        service=dict(artifact=f'service/contacts_app-{VERSION}-py3-none-any.whl',artifact_sha256='0'*64,
            entrypoint='contacts_app.service:create_service',health_operation_id='health',sdk_version='1.3'),
        permissions=permissions,operations=operations,storage=storage_declaration(),
        routes=[dict(route_id='contacts',entrypoint_id='contacts',audience='operator',required_permissions=['contact_read'],order=40)])
    ui=dict(compiled_ui_version=1,module_id=MODULE_ID,version=VERSION,entrypoints=[dict(entrypoint_id='contacts',kind='route',source='source/frontend/Contacts.vue',route='/contacts',label=definition['name'])])
    return manifest,application,ui

def write(archive,name,data):
    info=zipfile.ZipInfo(name,(2026,1,1,0,0,0));info.create_system=3;info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
    archive.writestr(info,data)

def build_package():
    # One source owner for the engine and renderer. Dependencies are bundled in
    # the normal isolated service wheel; they are never installed into Core.
    added=str(LIBRARY)
    sys.path.insert(0,added)
    try:
        manifest,application,ui=descriptors()
    finally:sys.path.remove(added)
    files={'contacts_app/'+p.name:p.read_bytes().replace(b'\r\n',b'\n') for p in (ROOT/'service/contacts_app').glob('*.py')}
    definition=json.loads((ROOT/'crud.json').read_text())
    files['contacts_app/definition.py']=('DEFINITION = '+repr(definition)+'\n').encode()
    files.update({'three_mm_crud/'+p.name:p.read_bytes().replace(b'\r\n',b'\n') for p in (LIBRARY/'three_mm_crud').glob('*.py')})
    dist=f'contacts_app-{VERSION}.dist-info'
    files[dist+'/METADATA']=f'Metadata-Version: 2.1\nName: contacts-app\nVersion: {VERSION}\n'.encode()
    files[dist+'/WHEEL']=b'Wheel-Version: 1.0\nGenerator: 3mm\nRoot-Is-Purelib: true\nTag: py3-none-any\n'
    record=io.StringIO(newline='');writer=csv.writer(record,lineterminator='\n')
    for name,data in sorted(files.items()):writer.writerow([name,'sha256='+base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode(),len(data)])
    writer.writerow([dist+'/RECORD','','']);files[dist+'/RECORD']=record.getvalue().encode()
    wheel=io.BytesIO()
    with zipfile.ZipFile(wheel,'w') as archive:
        for name,data in sorted(files.items()):write(archive,name,data)
    application['service']['artifact_sha256']=hashlib.sha256(wheel.getvalue()).hexdigest()
    result=io.BytesIO()
    with zipfile.ZipFile(result,'w') as archive:
        for name,value in [('manifest.json',manifest),('application-extension.json',application),('compiled-ui.json',ui)]:write(archive,name,json.dumps(value,ensure_ascii=False,sort_keys=True).encode())
        write(archive,application['service']['artifact'],wheel.getvalue())
        write(archive,'source/frontend/CrudPage.vue',(LIBRARY/'frontend/CrudPage.vue').read_bytes())
        write(archive,'source/frontend/Contacts.vue',(ROOT/'source/frontend/Contacts.vue').read_bytes())
        write(archive,'source/frontend/definition.ts',('export default '+json.dumps(definition,ensure_ascii=False)+'\n').encode())
    return result.getvalue()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    payload=build_package();args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('xb') as saved:saved.write(payload)
    print('SHA256 '+hashlib.sha256(payload).hexdigest())
