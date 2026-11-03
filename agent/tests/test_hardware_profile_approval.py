"""Isolated native-profile lifecycle. No device access, activation I/O or network."""
import hashlib
import json
import io
from zipfile import ZipFile
import pytest
from agent.module_runtime import AgentModuleRuntime, ModuleLifecycleError
from agent.tests.test_character_display import builder, DEVICE_ID  # noqa: F401
from agent.modules.character_display import character_display_handler
from three_mm_protocol.character_display import CharacterDisplayProfileV1, DISPLAY_ENTRYPOINT, DISPLAY_CAPABILITY


@pytest.fixture
def setup_profile(tmp_path, builder, monkeypatch):
    profile = CharacterDisplayProfileV1(driver='pcf8574')
    blob = builder.build_package(profile)
    sha = hashlib.sha256(blob).hexdigest()
    calls = []
    monkeypatch.setattr('agent.hardware.character_display.NativeCharacterDisplay.write_frame',
                        lambda *args, **kw: calls.append(args))
    monkeypatch.setattr('agent.hardware.character_display.NativeCharacterDisplay.is_available', lambda _: True)
    def runtime(device=DEVICE_ID):
        return AgentModuleRuntime(tmp_path, architecture='armv6l', device_id=device,
            runtime_handlers={DISPLAY_ENTRYPOINT: character_display_handler(
                native_allowed=True, lock_dir=tmp_path/'locks')})
    approval = {'device_id': DEVICE_ID, 'package_sha256': sha, 'profile_sha256': profile.digest()}
    return runtime, blob, sha, approval, profile, calls


@pytest.mark.parametrize('field', ['missing', 'device_id', 'package_sha256', 'profile_sha256'])
def test_wrong_consent_refused_before_extraction_or_driver(setup_profile, field):
    factory, blob, sha, approval, _, calls = setup_profile
    value = None if field == 'missing' else {**approval, field: ('dev_' if field == 'device_id' else '') + 'f'*(32 if field == 'device_id' else 64)}
    runtime = factory()
    with pytest.raises(ModuleLifecycleError, match='approval'):
        runtime.install(blob, expected_sha256=sha, hardware_profile_approval=value)
    assert not (runtime.root/'releases').exists()
    assert calls == []


def test_install_restart_disable_preserve_consent_without_replaying_a_frame(setup_profile):
    factory, blob, sha, approval, _, calls = setup_profile
    runtime = factory()
    installed = runtime.install(blob, expected_sha256=sha, hardware_profile_approval=approval)
    assert runtime.capability_healthy(DISPLAY_CAPABILITY)
    assert not runtime.capability_states()[DISPLAY_CAPABILITY]['has_frame']
    assert runtime.state(installed.module_id)['hardware_profile_approval']['package_sha256'] == sha
    runtime.close()
    again = factory(); again.start_active()
    assert again.capability_healthy(DISPLAY_CAPABILITY)
    again.disable(installed.module_id)
    again.close()
    stopped = factory(); stopped.start_active()
    assert not stopped.capability_healthy(DISPLAY_CAPABILITY)
    # Disabled state cannot implicitly approve a new installation.
    with pytest.raises(ModuleLifecycleError, match='required'):
        stopped.install(blob, expected_sha256=sha)
    assert calls == []


@pytest.mark.parametrize('change', ['device', 'manifest', 'approval'])
def test_restored_native_provider_cannot_escape_identity_or_exact_review(setup_profile, change):
    factory, blob, sha, approval, _, calls = setup_profile
    runtime = factory()
    installed = runtime.install(blob, expected_sha256=sha, hardware_profile_approval=approval)
    runtime.close()
    if change == 'manifest':
        path = runtime.root/'releases'/installed.module_id/'1.0.0/manifest.json'
        value = json.loads(path.read_text()); value['description'] = 'changed since approval'
        path.write_text(json.dumps(value))
    elif change == 'approval':
        path = runtime.root/'state'/(installed.module_id+'.json')
        value = json.loads(path.read_text()); value['hardware_profile_approval'] = None
        path.write_text(json.dumps(value))
    again = factory('dev_'+'e'*32 if change == 'device' else DEVICE_ID)
    again.start_active()
    assert not again.capability_healthy(DISPLAY_CAPABILITY)
    assert again.state(installed.module_id)['runtime_error']
    assert calls == []


@pytest.mark.parametrize('metadata', [{}, {'simulated': True}])
def test_native_handler_cannot_hide_its_profile_to_bypass_consent(setup_profile, metadata):
    factory, blob, _, _, _, calls = setup_profile
    with ZipFile(io.BytesIO(blob)) as source:
        manifest = json.loads(source.read('manifest.json'))
    original = manifest['registrations'][0]['metadata']
    manifest['registrations'][0]['metadata'] = ({**original, **metadata} if metadata else {})
    output = io.BytesIO()
    with ZipFile(output, 'w') as archive:
        archive.writestr('manifest.json', json.dumps(manifest))
        archive.writestr('health/ready', 'ready')
    package = output.getvalue()
    with pytest.raises(ModuleLifecycleError, match='profile-bound'):
        factory().install(package, expected_sha256=hashlib.sha256(package).hexdigest())
    assert calls == []
