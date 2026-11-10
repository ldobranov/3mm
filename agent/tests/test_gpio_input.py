"""Generic input profiles: edges, exact consent and lifecycle without hardware."""
import hashlib
import io
from zipfile import ZipFile

import pytest
from pydantic import ValidationError
from agent.hardware.gpio import MockDigitalGpioDriver, DigitalInputEvent
from agent.module_runtime import AgentModuleRuntime, ModuleLifecycleError
from agent.modules.gpio_input import GpioInputService, gpio_input_handler
from three_mm_protocol.gpio_input import (
    GpioInputProfileV1, INPUT_CAPABILITY, INPUT_ENTRYPOINT, INPUT_EVENT, INPUT_FEATURE,
)
from three_mm_protocol.gpio_input_package import build_package
from three_mm_protocol.hardware_profiles import hardware_profile
from three_mm_protocol.capability_contracts import validate_value
from backend.services.module_packages import validate_module_package

DEVICE = 'dev_' + 'b'*32


def test_only_agents_with_the_installed_handler_advertise_input_profiles(tmp_path, monkeypatch):
    from agent.core_client import CorePublisher, DeviceCredential, CommandJournal, ReconciliationStore, OutboxStore
    monkeypatch.setattr('agent.session_support.session_link_available', lambda _: False)
    runtime = AgentModuleRuntime(tmp_path, architecture='armv6l', device_id=DEVICE)
    publisher = CorePublisher(core_url='http://core', credential=DeviceCredential(device_id=DEVICE,
        credential_id='cred_'+'a'*32, credential_secret='s'*43), inventory_provider=lambda: None,
        command_journal=CommandJournal(tmp_path), reconciliation_store=ReconciliationStore(tmp_path),
        outbox=OutboxStore(tmp_path), started_monotonic=0, module_runtime=runtime)
    assert INPUT_FEATURE not in publisher._runtime_declaration()['features']
    runtime.runtime_handlers[INPUT_ENTRYPOINT] = gpio_input_handler()
    assert INPUT_FEATURE in publisher._runtime_declaration()['features']


def test_multiple_channels_emit_both_raw_edges_without_button_policy_or_polling():
    profile = GpioInputProfileV1(inputs={'door.contact':17, 'selector.contact':22})
    driver = MockDigitalGpioDriver(inputs={channel:False for channel in profile.inputs})
    events, clock = [], [100_000_000_000]
    service = GpioInputService(profile, driver, events.append, clock=lambda: clock[0])
    assert events == []
    driver.set_input('door.contact', True)
    driver.set_input('door.contact', True)
    clock[0] += 20_000_000_000  # Agent has no short/long-press interpretation.
    driver.set_input('selector.contact', True)
    driver.set_input('door.contact', False)
    assert [(e['payload']['channel'],e['payload']['value'],e['payload']['sequence']) for e in events] == [
        ('door.contact', True, 1), ('selector.contact', True, 1), ('door.contact', False, 2)]
    for event in events:
        assert event['event_type'] == INPUT_EVENT
        validate_value(event['payload'], profile.contract().events[INPUT_EVENT])
    assert events[2]['payload']['monotonic_ns'] == clock[0]
    assert events[0]['payload']['stream_id'] == events[2]['payload']['stream_id'] == service.stream_id
    assert len(service.stream_id) == 32
    assert service.state_for(INPUT_CAPABILITY)['inputs'] == {'door.contact':False, 'selector.contact':True}
    service.close()
    driver.set_input('door.contact', True)
    assert len(events) == 3 and not service.is_available()


def test_native_clock_is_preserved_and_missing_timestamp_does_not_get_guessed():
    profile = GpioInputProfileV1(driver='gpiod')
    driver = MockDigitalGpioDriver(inputs={'gpio.input.1':False})
    events = []
    def forbidden_clock(): raise AssertionError('native fallback must not use Python scheduling time')
    service = GpioInputService(profile, driver, events.append, clock=forbidden_clock)
    service._edge(DigitalInputEvent('gpio.input.1', True, 1, 100_000_000_000))
    service._edge(DigitalInputEvent('gpio.input.1', False, 2, 120_000_000_000))
    assert [event['payload']['monotonic_ns'] for event in events] == [100_000_000_000,120_000_000_000]
    assert service.is_available()
    service._edge(DigitalInputEvent('gpio.input.1', True, 3))
    assert len(events) == 2 and not service.is_available()
    service.close()


def test_held_input_startup_is_observation_only_and_new_activation_has_distinct_stream():
    profile = GpioInputProfileV1()
    driver = MockDigitalGpioDriver(inputs={'gpio.input.1':True})
    events = []
    first = GpioInputService(profile, driver, events.append)
    assert first.state_for(INPUT_CAPABILITY)['inputs']['gpio.input.1'] is True and events == []
    driver.set_input('gpio.input.1', False)
    assert len(events) == 1 and events[0]['payload']['value'] is False
    first.close()
    second = GpioInputService(profile, MockDigitalGpioDriver(inputs={'gpio.input.1':False}), events.append)
    assert second.stream_id != first.stream_id
    second.close()


@pytest.mark.parametrize('value', [{'inputs':{}}, {'inputs':{'input.one':2}},
    {'inputs':{'input.one':17.0}}, {'inputs':{'input.one':True}},
    {'inputs':{'input.one':17,'input.two':17}}, {'inputs':{'not a channel':17}},
    {'driver':'shell'}, {'chip':'/tmp/fake'}, {'active_low':False}, {'pull_up':False},
    {'debounce_ms':True}, {'debounce_ms':-1}, {'debounce_ms':1001}])
def test_profile_refuses_unsafe_or_ambiguous_settings(value):
    with pytest.raises(ValidationError): GpioInputProfileV1(**value)


def test_package_is_inert_reproducible_and_matches_real_core_validator():
    profile = GpioInputProfileV1(driver='gpiod', inputs={'selector':22})
    blob = build_package(profile)
    assert blob == build_package(profile)
    validated = validate_module_package(blob)
    assert hardware_profile(validated.manifest).profile_sha256 == profile.digest()
    assert validated.manifest.registrations[0].contract.actions == {}
    assert INPUT_EVENT in validated.manifest.registrations[0].contract.events
    assert validated.manifest.configuration_defaults['inputs'] == {'selector':22}
    with ZipFile(io.BytesIO(blob)) as archive:
        assert set(archive.namelist()) == {'manifest.json','health/ready'}


@pytest.mark.parametrize('mismatch', ['missing','device_id','profile_sha256','package_sha256'])
def test_native_consent_checked_before_opening_any_line(tmp_path, mismatch):
    profile = GpioInputProfileV1(driver='gpiod')
    blob, opens = build_package(profile), []
    digest = hashlib.sha256(blob).hexdigest()
    runtime = AgentModuleRuntime(tmp_path, architecture='armv6l', device_id=DEVICE,
        runtime_handlers={INPUT_ENTRYPOINT:gpio_input_handler(native_allowed=True,
            model='Raspberry Pi Zero W Rev 1.1', driver_factory=lambda p:opens.append(p))})
    approval = {'device_id':DEVICE,'profile_sha256':profile.digest(),'package_sha256':digest}
    if mismatch != 'missing': approval[mismatch] = ('dev_'+'c'*32) if mismatch=='device_id' else 'f'*64
    with pytest.raises(ModuleLifecycleError, match='approval'):
        runtime.install(blob, expected_sha256=digest,
            hardware_profile_approval=None if mismatch=='missing' else approval)
    assert opens == [] and not (runtime.root/'releases').exists()


def test_install_restart_disable_keeps_profile_without_synthetic_edges(tmp_path):
    profile, drivers, events = GpioInputProfileV1(driver='gpiod'), [], []
    blob = build_package(profile); digest = hashlib.sha256(blob).hexdigest()
    def factory(p):
        drivers.append(MockDigitalGpioDriver(inputs={channel:False for channel in p.inputs}))
        return drivers[-1]
    def runtime():
        return AgentModuleRuntime(tmp_path, architecture='armv6l', device_id=DEVICE,
            runtime_handlers={INPUT_ENTRYPOINT:gpio_input_handler(native_allowed=True,
                model='Raspberry Pi Zero W Rev 1.1', driver_factory=factory, event_sink=events.append)})
    first = runtime()
    result = first.install(blob, expected_sha256=digest, hardware_profile_approval={
        'device_id':DEVICE,'profile_sha256':profile.digest(),'package_sha256':digest})
    assert first.capability_healthy(INPUT_CAPABILITY)
    original_stream = first.capability_states()[INPUT_CAPABILITY]['stream_id']; first.close()
    second = runtime(); second.start_active()
    assert second.capability_healthy(INPUT_CAPABILITY) and events == []
    assert second.capability_states()[INPUT_CAPABILITY]['stream_id'] != original_stream
    second.disable(result.module_id); second.close()
    third = runtime(); third.start_active()
    assert not third.capability_healthy(INPUT_CAPABILITY) and len(drivers)==2


def test_profile_metadata_and_unsupported_board_fail_before_line_open(tmp_path):
    profile = GpioInputProfileV1(driver='gpiod')
    source = validate_module_package(build_package(profile)).manifest
    opened = []
    handler = gpio_input_handler(native_allowed=True, model='Raspberry Pi 5 Model B Rev 1',
                                driver_factory=lambda p:opened.append(p))
    with pytest.raises(ModuleLifecycleError, match='unsupported'): handler(source,tmp_path)
    source = source.model_copy(update={'registrations':[source.registrations[0].model_copy(update={'metadata':{}})]})
    with pytest.raises(ModuleLifecycleError, match='profile-bound'): handler(source,tmp_path)
    assert opened==[]


def test_distinct_profiles_cannot_claim_same_capability_until_previous_disabled(tmp_path):
    runtime = AgentModuleRuntime(tmp_path, architecture='armv6l', device_id=DEVICE,
        runtime_handlers={INPUT_ENTRYPOINT:gpio_input_handler()})
    first, second = build_package(), build_package(GpioInputProfileV1(inputs={'second':22}))
    installed = runtime.install(first, expected_sha256=hashlib.sha256(first).hexdigest())
    with pytest.raises(ModuleLifecycleError, match='owned by another module'):
        runtime.install(second, expected_sha256=hashlib.sha256(second).hexdigest())
    assert runtime.capability_healthy(INPUT_CAPABILITY)
    runtime.disable(installed.module_id)
    runtime.install(second, expected_sha256=hashlib.sha256(second).hexdigest())
    assert runtime.capability_states()[INPUT_CAPABILITY]['inputs']=={'second':False}
    runtime.close()
