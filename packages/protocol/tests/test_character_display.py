import pytest
from pydantic import ValidationError
from packages.protocol.capability_contracts import CapabilityContractError
from packages.protocol.character_display import CharacterDisplayProfileV1, DISPLAY_CAPABILITY, frame_arguments_schema


def frame(profile, **changes):
    return {'display_id':profile.display_id,'profile_sha256':profile.digest(),
            'text':'\n'.join(['BTC/USD']*profile.rows),'backlight':True,**changes}


@pytest.mark.parametrize('columns,rows', [(16,2),(20,2),(24,2),(17,3),(40,2),(20,4),(80,4)])
def test_geometry_is_data_with_one_command_shape_and_exact_profile_checks(columns,rows):
    from packages.protocol.application_commands import ApplicationCommandBindingV1
    profile=CharacterDisplayProfileV1(columns=columns,rows=rows)
    contract=profile.contract()
    assert contract.actions['write_frame'].arguments_schema == frame_arguments_schema()
    binding=ApplicationCommandBindingV1(binding_id='display',target_device_config_key='DISPLAY_DEVICE_ID',
        capability_id=DISPLAY_CAPABILITY,contract_version='2.0',action='write_frame',arguments_schema=frame_arguments_schema())
    assert binding.arguments_schema == CharacterDisplayProfileV1().contract().actions['write_frame'].arguments_schema
    assert profile.frame(frame(profile)) == (['BTC/USD'.ljust(columns)]*rows,True)
    with pytest.raises(CapabilityContractError):profile.frame(frame(profile,text='x'*(columns+1)))
    assert contract.state_schema['properties']['columns']['enum'] == [columns]
    assert contract.state_schema['properties']['rows']['enum'] == [rows]


@pytest.mark.parametrize('changes',[{'bus':True},{'bus':-1},{'bus':256},{'address':0},{'address':0x78},
    {'columns':0},{'columns':81},{'columns':20.0},{'columns':True},{'rows':0},{'rows':5},{'rows':True},
    {'path':'/dev/i2c-1'},{'display_id':'../../i2c'},{'backlight_active_high':1}])
def test_profile_rejects_unbounded_or_coerced_data(changes):
    with pytest.raises(ValidationError):CharacterDisplayProfileV1(**changes)


@pytest.mark.parametrize('changes',[{'text':'x'*21+'\nok'},{'text':'one row'}, {'text':'hello\n\x00'},
    {'text':'hello\n\x1b[2J'},{'text':'Здравей\nworld'},{'text':42},{'backlight':1},
    {'display_id':'other'},{'profile_sha256':'0'*64},{'bus':2},{'address':0x28},{'raw_bytes':'ff'}])
def test_bad_frame_never_becomes_a_raw_io_contract(changes):
    profile=CharacterDisplayProfileV1()
    with pytest.raises(CapabilityContractError):profile.frame(frame(profile,**changes))


@pytest.mark.parametrize('changes',[{'bus':2},{'address':0x26},{'display_id':'display.other'},
    {'driver':'pcf8574'},{'backlight_active_high':False},{'columns':24},{'rows':4}])
def test_profile_changes_keep_input_schema_but_invalidate_exact_contract_and_old_frame(changes):
    before=CharacterDisplayProfileV1();after=CharacterDisplayProfileV1(**changes)
    assert before.contract().actions['write_frame'].arguments_schema == after.contract().actions['write_frame'].arguments_schema
    assert before.contract().digest() != after.contract().digest()
    with pytest.raises(CapabilityContractError):after.frame(frame(before))
