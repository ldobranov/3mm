import copy
import json
from datetime import datetime, UTC
from io import BytesIO
from zipfile import ZipFile

import pytest

from packages.protocol.character_clock import clock_zone, parse_clock_fields, render_clock_fields
from packages.protocol.character_display import CharacterDisplayProfileV1
from packages.protocol.character_display_scene import CharacterDisplaySceneProfileV1
from packages.protocol.character_display_package import build_package, build_scene_package
from packages.protocol.hardware_templates import instantiate_template
from packages.protocol.module_manifest import ModuleManifestV2
from tools.hardware_template_catalog import clock_documents


def test_cells_use_explicit_zone_and_only_declared_visible_slices():
    fields = parse_clock_fields('[[0,0,1,0,8],[1,0,2,0,10]]', columns=16, rows=2)
    lines = ['00:00:00 PRICE  >', '00.00.0000   OLD']
    instant = datetime(2026, 3, 29, 0, 59, 59, tzinfo=UTC).timestamp()
    assert render_clock_fields(lines, fields, clock_zone('Europe/Sofia'), instant) == ['02:59:59 PRICE  >','29.03.2026   OLD']
    assert render_clock_fields(lines, fields, clock_zone('Europe/Sofia'), instant+1) == ['04:00:00 PRICE  >','29.03.2026   OLD']
    assert lines[0].startswith('00:00:00')
    partial = parse_clock_fields('[[0,10,1,2,3]]', columns=16, rows=1)
    assert render_clock_fields(['123.45    000OLD'], partial, clock_zone('UTC'), instant)[0] == '123.45    :59OLD'


@pytest.mark.parametrize('raw', [
    '{}', 'null', '[[0,0,3,0,1]]', '[[false,0,0,0,1]]', '[[0,0,0,0,0]]',
    '[[2,0,0,0,1]]', '[[0,16,0,0,1]]', '[[0,15,0,0,2]]', '[[0,0,0,4,2]]',
    '[[0,0,0,0,5],[0,4,1,0,8]]', '[[0,0,0,0,1,1]]', '[{"row":0}]', '['*1000,
    '['+','.join(['[0,0,0,0,1]']*33)+']',
])
def test_invalid_cells_are_refused_before_transport(raw):
    with pytest.raises(ValueError): parse_clock_fields(raw, columns=16, rows=2)


def test_maximum_disjoint_cells_fit_existing_scalar_budget():
    cells = [[row, column*2, 0, 0, 1] for row in range(4) for column in range(8)]
    raw = json.dumps(cells, separators=(',',':'))
    assert len(raw) <= 512
    assert len(parse_clock_fields(raw, columns=16, rows=4)) == 32


def test_scene_contract_and_inert_package_are_generic_current_core_data():
    from backend.artifacts.packages import validate_module_package
    profile = CharacterDisplaySceneProfileV1(driver='pcf8574', columns=16)
    blob = build_scene_package(profile)
    assert blob == build_scene_package(profile)
    parsed = validate_module_package(blob, architecture='armv6l').manifest
    assert parsed.registrations[0].contract == profile.contract()
    assert parsed.configuration_defaults['max_scene_lease_seconds'] == 30
    assert parsed.entrypoints['agent'] == 'builtin:display.character.scene.v1'
    with ZipFile(BytesIO(blob)) as archive:
        assert set(archive.namelist()) == {'manifest.json','health/ready'}
    assert profile.digest() != CharacterDisplayProfileV1(driver='pcf8574',columns=16).digest()
    assert build_package(CharacterDisplayProfileV1(driver='pcf8574',columns=16)) != blob


@pytest.mark.parametrize('changes', [
    {'valid_until_ms':1000}, {'valid_until_ms':31001}, {'scene_id':'Z'*32},
    {'sequence':True}, {'sequence':0}, {'timezone':'../../UTC'}, {'timezone':'No/Zone'},
    {'profile_sha256':'0'*64}, {'clock_fields':'[[0,16,0,0,1]]'}, {'text':'Курс\nok'},
    {'raw_address':39},
])
def test_scene_lease_identity_profile_and_content_are_checked(changes):
    profile = CharacterDisplaySceneProfileV1(columns=16)
    args = {'display_id':profile.display_id,'profile_sha256':profile.digest(), 'text':'00:00:00\nprice',
        'backlight':True,'clock_fields':'[[0,0,1,0,8]]','timezone':'UTC',
        'scene_id':'a'*32,'sequence':1,'valid_until_ms':31000,**changes}
    with pytest.raises(ValueError): profile.scene(args, now_ms=1000)


@pytest.mark.parametrize('identity,source', list(clock_documents()))
def test_admin_template_changes_geometry_without_core_clock_registry(identity, source):
    parameters = {field['key']:field['default'] for field in source['template']['fields']}
    parameters.update(columns=20, display_id='front.clock')
    before = copy.deepcopy(source)
    value = instantiate_template(source['manifest'],source['template'],parameters)
    manifest = ModuleManifestV2.model_validate(value)
    profile = CharacterDisplaySceneProfileV1.model_validate(manifest.configuration_defaults)
    assert manifest.registrations[0].contract == profile.contract()
    assert manifest.module_id.endswith(profile.digest())
    assert source == before
    assert source['template']['required_features'] == ['display.character.scenes.v1']
