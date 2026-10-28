import copy
import pytest
from three_mm_protocol import ApplicationExtensionV1, ApplicationPrivateFilesV2
from three_mm_protocol.tests.test_application_extension import definition
from three_mm_application_sdk.tests.test_media import declaration


def application():
    value=definition()
    value['service']['sdk_version']='1.3'
    value['storage']['private_files']=declaration().model_dump(mode='json')
    value['routes'][1]['private_files']={'contract_version':1,'read_permission':'records_manage','write_permission':'records_manage','publish_permission':'records_manage','transform_permission':'records_manage'}
    return value


def test_streaming_profile_roundtrip_and_explicit_human_scopes():
    value=ApplicationExtensionV1.model_validate(application())
    assert value.storage.private_files.operations()==('read','write','publish','transform')
    assert ApplicationExtensionV1.model_validate_json(value.model_dump_json())==value


@pytest.mark.parametrize('fault',['public_route','kiosk_route','missing_permission','undeclared_publish','undeclared_transform','old_sdk'])
def test_browser_file_opt_in_cannot_borrow_other_route_or_service_permissions(fault):
    value=application()
    if fault.endswith('_route'):
        value['routes'][1].update(audience=fault.split('_')[0],required_permissions=[])
    if fault=='missing_permission':value['routes'][1]['private_files']['write_permission']='missing'
    if fault=='undeclared_publish':value['storage']['private_files']['public_links']=False
    if fault=='undeclared_transform':value['storage']['private_files']['media_transforms']=False
    if fault=='old_sdk':value['service']['sdk_version']='1.2'
    with pytest.raises(ValueError):ApplicationExtensionV1.model_validate(value)


@pytest.mark.parametrize('field,value',[('file_contract_version',True),('file_contract_version',2.0),('max_file_bytes',True),
    ('max_total_bytes',4*1024**3+1),('max_uploads',17),('max_staging_bytes',1),('upload_ttl_seconds',59),
    ('public_links',1),('media_transforms','yes')])
def test_streaming_limits_are_explicit_strict_and_coherent(field,value):
    data=declaration().model_dump(mode='json');data[field]=value
    with pytest.raises(ValueError):ApplicationPrivateFilesV2.model_validate(data)
