"""Declared input forms use generic preparation, normal consent and no effects."""
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from backend.db.device import DeviceCommand, DeviceRuntimeFeatures
from backend.db.module import ModulePackage
from backend.tests.test_hardware_profile_installation import native  # noqa: F401
from backend.tests.test_hardware_provider_templates import preparation  # noqa: F401
from backend.tests.test_module_lifecycle_idempotency import lifecycle, DEVICE_ID  # noqa: F401
from agent.tests.test_character_display import builder  # noqa: F401
from backend.devices.modules.templates import (
    prepare_provider, provider_templates, sources, package_bytes,
)
from backend.artifacts.packages import validate_module_package
from packages.protocol.gpio_input import GpioInputProfileV1, INPUT_FEATURE
from packages.protocol.gpio_input_package import manifest as input_manifest
from packages.protocol.hardware_templates import TEMPLATE_FILENAME
from packages.protocol.hardware_profiles import HARDWARE_PROFILE_FEATURE
from packages.protocol.node_features import MANDATORY_NODE_FEATURES

PATH = f'/api/v1/modules/devices/{DEVICE_ID}/hardware-profiles'
TEMPLATE = 'gpio-input.gpiod'


def template_source():
    return next(source for source in sources().values() if source.descriptor.template_id == TEMPLATE)


def advertise(ctx):
    row = ctx.db.scalar(select(DeviceRuntimeFeatures).where(DeviceRuntimeFeatures.device_id == ctx.device.id))
    if row is None:
        row = DeviceRuntimeFeatures(device_id=ctx.device.id,revision=1,received_at=datetime.now(UTC),
            declaration={'schema_version':1,'protocol_version':'1.0','device_id':DEVICE_ID,
                'runtime_name':'test-agent','runtime_version':'1.0',
                'features':sorted(MANDATORY_NODE_FEATURES | {'module_lifecycle',HARDWARE_PROFILE_FEATURE,INPUT_FEATURE}),
                'command_types':['capability.invoke','module.install','module.disable']})
        ctx.db.add(row)
    else:
        row.declaration = {**row.declaration, 'features': [*row.declaration['features'], INPUT_FEATURE]}
    ctx.db.commit()


def test_input_template_requires_advertised_handler_and_cannot_prepare_on_old_agent(native, tmp_path, monkeypatch):
    from backend.artifacts import api as modules
    ctx = native
    monkeypatch.setattr(modules, 'get_settings', lambda: SimpleNamespace(backend=SimpleNamespace(uploads_dir=tmp_path)))
    identity = template_source().identity
    assert identity not in {item['template_id'] for item in ctx.client.get(PATH).json()['templates']}
    body = {'template_id':identity,'configuration':{}}
    before = len(list(ctx.db.scalars(select(ModulePackage))))
    assert ctx.client.post(PATH+'/prepare',json=body).status_code == 422
    assert len(list(ctx.db.scalars(select(ModulePackage)))) == before
    assert list(ctx.db.scalars(select(DeviceCommand))) == []
    advertise(ctx)
    assert identity in {item['template_id'] for item in ctx.client.get(PATH).json()['templates']}
    response = ctx.client.post(PATH+'/prepare',json=body)
    assert response.status_code == 200,response.text
    item=response.json()
    assert item['activation']=='not_requested'
    assert ctx.client.post(PATH+'/prepare',json=body).json()==item
    install=f'/api/v1/modules/packages/{item["package_sha256"]}/devices/{DEVICE_ID}/install'
    assert ctx.client.post(install,json={}).status_code==409
    assert list(ctx.db.scalars(select(DeviceCommand)))==[]
    approved=ctx.client.post(install,json={'hardware_profile_approval':{
        'device_id':DEVICE_ID,'package_sha256':item['package_sha256'],'profile_sha256':item['profile_sha256']}},
        headers={'Idempotency-Key':'e'*32})
    assert approved.status_code==200,approved.text
    assert len(list(ctx.db.scalars(select(DeviceCommand))))==1


@pytest.mark.parametrize('configuration', [{'bcm_pin':2},{'bcm_pin':True},{'bcm_pin':'17'},
    {'chip':'/tmp/gpio'},{'active_low':False},{'driver':'shell'},{'pin_map':'raw'},
    {'debounce_ms':-1},{'debounce_ms':1001},{'debounce_ms':True}])
def test_input_template_refuses_raw_or_unsafe_configuration(configuration):
    with pytest.raises(ValueError):
        prepare_provider(template_source().identity,configuration,features={INPUT_FEATURE})


def test_supported_pin_and_debounce_use_exact_generic_profile_without_device_access():
    profile=GpioInputProfileV1(driver='gpiod',inputs={'gpio.input.1':22},debounce_ms=50)
    args={'bcm_pin':22,'debounce_ms':50}
    blob=prepare_provider(template_source().identity,args,features={INPUT_FEATURE})
    assert blob==prepare_provider(template_source().identity,args,features={INPUT_FEATURE})
    package=validate_module_package(blob)
    assert package.manifest.configuration_defaults==profile.model_dump()
    assert package.manifest.registrations[0].contract==profile.contract()
    assert package.manifest.registrations[0].metadata['profile_sha256']==profile.digest()
    assert template_source().identity not in {row['template_id'] for row in provider_templates()}


def third_template():
    """A separately authored contact with a different logical channel/pin."""
    source=template_source()
    profile=GpioInputProfileV1(driver='gpiod',inputs={'door.contact':22})
    manifest=input_manifest(profile)
    manifest['module_id']='org.example.door-profile.'+profile.digest()
    manifest['registrations'][0]['metadata']['profile_template']=True
    descriptor=source.descriptor.model_dump(mode='json')
    descriptor.update(template_id='door.contact-input',name='Door contact input')
    for field in descriptor['fields']:
        if field['key']=='bcm_pin': field['default']=22
    for paths in descriptor['bindings'].values():
        for index,path in enumerate(paths): paths[index]=path.replace('gpio.input.1','door.contact')
    files={**source.files,TEMPLATE_FILENAME:(json.dumps(descriptor,sort_keys=True,indent=2)+'\n').encode()}
    return package_bytes(manifest,files)


def test_uploaded_third_template_appears_and_prepares_without_core_driver_code(preparation):
    ctx=preparation
    advertise(ctx)
    blob=third_template()
    identity='tpl-'+hashlib.sha256(blob).hexdigest()
    before_ids={row['template_id'] for row in ctx.client.get(PATH).json()['templates']}
    uploaded=ctx.client.post('/api/v1/modules/packages',files={'package':('door-template.zip',blob,'application/zip')})
    assert uploaded.status_code==200,uploaded.text
    catalog=ctx.client.get(PATH).json()
    offer=next(row for row in catalog['templates'] if row['template_id']==identity)
    assert offer['name']=='Door contact input' and identity not in before_ids
    defaults=ctx.client.post(PATH+'/prepare',json={'template_id':identity,'configuration':{}})
    assert defaults.status_code==200,defaults.text
    assert ctx.client.post(PATH+'/prepare',json={'template_id':identity,'configuration':{}}).json()==defaults.json()
    source_record=ctx.db.scalar(select(ModulePackage).where(ModulePackage.sha256==hashlib.sha256(blob).hexdigest()))
    configured=ctx.db.scalar(select(ModulePackage).where(ModulePackage.sha256==defaults.json()['package_sha256']))
    assert configured.module_id!=source_record.module_id and configured.version==source_record.version
    prepared=ctx.client.post(PATH+'/prepare',json={'template_id':identity,'configuration':{'bcm_pin':23}})
    assert prepared.status_code==200,prepared.text
    record=ctx.db.scalar(select(ModulePackage).where(ModulePackage.sha256==prepared.json()['package_sha256']))
    package=validate_module_package(Path(record.file_path).read_bytes())
    assert package.manifest.configuration_defaults['inputs']=={'door.contact':23}
    assert package.manifest.registrations[0].contract==GpioInputProfileV1(
        driver='gpiod',inputs={'door.contact':23}).contract()
    assert list(ctx.db.scalars(select(DeviceCommand)))==[]


def test_changed_uploaded_source_is_not_used_under_stale_template_identity(preparation):
    ctx=preparation;advertise(ctx)
    blob=third_template();identity='tpl-'+hashlib.sha256(blob).hexdigest()
    uploaded=ctx.client.post('/api/v1/modules/packages',files={'package':('door.zip',blob,'application/zip')})
    assert uploaded.status_code==200,uploaded.text
    record=ctx.db.scalar(select(ModulePackage).where(ModulePackage.sha256==hashlib.sha256(blob).hexdigest()))
    # Corrupted source is still an inventory record, not a new trusted template.
    Path(record.file_path).write_bytes(blob+b'tampered')
    assert identity not in {row['template_id'] for row in ctx.client.get(PATH).json()['templates']}
    before=len(list(ctx.db.scalars(select(ModulePackage))))
    response=ctx.client.post(PATH+'/prepare',json={'template_id':identity,'configuration':{}})
    assert response.status_code==422,response.text
    assert len(list(ctx.db.scalars(select(ModulePackage))))==before
    assert list(ctx.db.scalars(select(DeviceCommand)))==[]


@pytest.mark.parametrize('damage', ['missing_marker', 'privilege_pointer', 'executable_file', 'missing_descriptor',
                                   'descriptor_crc', 'health_crc'])
def test_invalid_template_upload_never_enters_catalog_or_queues_a_command(preparation, damage):
    import io
    from zipfile import ZipFile
    ctx=preparation
    with ZipFile(io.BytesIO(third_template())) as archive:
        manifest=json.loads(archive.read('manifest.json'))
        files={name:archive.read(name) for name in archive.namelist() if name!='manifest.json'}
    if damage=='missing_marker':
        manifest['registrations'][0]['metadata'].pop('profile_template')
    elif damage=='privilege_pointer':
        descriptor=json.loads(files[TEMPLATE_FILENAME])
        descriptor['bindings']['bcm_pin']=['/permissions/0']
        files[TEMPLATE_FILENAME]=json.dumps(descriptor).encode()
    elif damage=='executable_file':
        files['driver.py']=b'raise RuntimeError("must never load")\n'
    elif damage=='missing_descriptor':
        files.pop(TEMPLATE_FILENAME)
    blob=package_bytes(manifest,files)
    if damage.endswith('_crc'):
        target=TEMPLATE_FILENAME if damage=='descriptor_crc' else manifest['health_check']['path']
        with ZipFile(io.BytesIO(blob)) as archive:
            info=archive.getinfo(target)
            offset=info.header_offset+30+len(info.filename.encode())+len(info.extra)
        broken=bytearray(blob);broken[offset]^=1;blob=bytes(broken)
    before=len(list(ctx.db.scalars(select(ModulePackage))))
    response=ctx.client.post('/api/v1/modules/packages',files={
        'package':('invalid-template.zip',blob,'application/zip')})
    assert response.status_code==422,response.text
    assert len(list(ctx.db.scalars(select(ModulePackage))))==before
    assert list(ctx.db.scalars(select(DeviceCommand)))==[]
