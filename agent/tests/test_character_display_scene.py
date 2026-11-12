from datetime import UTC, datetime, timedelta
import hashlib
import threading

import pytest

from agent.module_runtime import AgentModuleRuntime, ModuleLifecycleError
from agent.modules.character_display_scene import CharacterDisplaySceneService, character_display_scene_handler
from packages.protocol.character_display_scene import CharacterDisplaySceneProfileV1, SCENE_ENTRYPOINT
from packages.protocol.character_display_package import build_scene_package
from packages.protocol.capability_contracts import validate_value


class Clock:
    wall = datetime(2026, 11, 9, 12, 0, 0, tzinfo=UTC).timestamp()
    mono = 100.0
    def advance(self, seconds): self.wall += seconds; self.mono += seconds


@pytest.fixture
def scene(tmp_path):
    clock = Clock()
    profile = CharacterDisplaySceneProfileV1(columns=16)
    service = CharacterDisplaySceneService(profile, lock_dir=tmp_path, wall_clock=lambda:clock.wall,
        monotonic=lambda:clock.mono, background=False)
    try: yield service, clock, profile
    finally: service.close()


def arguments(profile, clock, **changes):
    return {'display_id':profile.display_id,'profile_sha256':profile.digest(),'scene_id':'a'*32,
        'sequence':1,'text':'00:00:00'.ljust(16)+'\n'+'BTC 123'.ljust(16),'backlight':True,
        'clock_fields':'[[0,0,1,0,8]]','timezone':'UTC',
        'valid_until_ms':int(clock.wall*1000)+30000,**changes}


def test_ticks_are_local_and_delayed_callback_draws_now_without_catchup(scene):
    service, clock, profile = scene
    writes=[]
    original=service._driver.write_frame
    service._driver.write_frame=lambda lines, backlight:(writes.append(list(lines)),original(lines,backlight))
    result=service.invoke('set_scene',arguments(profile,clock))
    validate_value(result,profile.contract().actions['set_scene'].result_schema)
    assert result['text'].startswith('12:00:00') and result['scene_accepted']
    clock.advance(1); service.tick()
    clock.advance(8.5); service.tick()
    assert len(writes)==3 and writes[-1][0].startswith('12:00:09')
    assert service.state_for('display.character')['scene_active']


def test_receipt_duplicate_never_extends_absolute_or_monotonic_lease(scene):
    service,clock,profile=scene
    args=arguments(profile,clock)
    service.invoke('set_scene',args)
    clock.advance(10)
    with pytest.raises(ValueError): service.invoke('set_scene',args)
    clock.wall-=3600; clock.mono+=20
    service.tick()
    assert not service.state_for('display.character')['scene_active']
    frame=service._driver.frame
    clock.advance(100); service.tick()
    assert service._driver.frame==frame


def test_fresh_higher_sequence_renews_but_stop_closes_run_and_rejects_delayed_scene(scene):
    service,clock,profile=scene
    service.invoke('set_scene',arguments(profile,clock))
    clock.advance(10)
    service.invoke('set_scene',arguments(profile,clock,sequence=2))
    clock.advance(21); service.tick()
    assert service.state_for('display.character')['scene_active']
    stop={key:value for key,value in arguments(profile,clock,sequence=3).items()
          if key in {'display_id','profile_sha256','scene_id','sequence'}}
    frame=service._driver.frame
    result=service.invoke('stop_scene',stop)
    validate_value(result,profile.contract().actions['stop_scene'].result_schema)
    assert result['scene_stopped'] and service._driver.frame==frame
    with pytest.raises(ValueError): service.invoke('set_scene',arguments(profile,clock,sequence=4))
    clock.advance(1); service.tick()
    assert service._driver.frame==frame
    service.invoke('set_scene',arguments(profile,clock,scene_id='b'*32))


def test_one_frame_cancels_scene_and_cannot_be_overwritten_by_old_tick(scene):
    service,clock,profile=scene
    service.invoke('set_scene',arguments(profile,clock))
    frame={key:value for key,value in arguments(profile,clock,text='manual\nframe').items()
        if key in {'display_id','profile_sha256','text','backlight'}}
    result=service.invoke('write_frame',frame)
    validate_value(result,profile.contract().actions['write_frame'].result_schema)
    clock.advance(1); service.tick()
    assert not result['scene_active'] and service._driver.frame[0][0].startswith('manual')
    with pytest.raises(ValueError): service.invoke('set_scene',arguments(profile,clock,sequence=2))


def test_failed_tick_forgets_scene_and_maintenance_never_replays_it(scene):
    service,clock,profile=scene
    service.invoke('set_scene',arguments(profile,clock))
    def fail(*_): raise OSError('driver failed')
    service._driver.write_frame=fail
    clock.advance(1); service.tick(); service.maintain(); service.tick()
    state=service.state_for('display.character')
    assert not state['scene_active'] and not state['has_frame'] and not service.is_available()
    stop={key:value for key,value in arguments(profile,clock,sequence=2).items()
          if key in {'display_id','profile_sha256','scene_id','sequence'}}
    assert service.invoke('stop_scene',stop)['scene_stopped']


def test_expired_command_invalid_cells_and_static_scene_never_schedule_extra_writes(scene):
    service,clock,profile=scene
    with pytest.raises(TimeoutError):
        service.invoke('set_scene',arguments(profile,clock),not_after=datetime.now(UTC)-timedelta(seconds=1))
    assert service._driver.frame is None
    with pytest.raises(ValueError): service.invoke('set_scene',arguments(profile,clock,clock_fields='[[0,16,0,0,1]]'))
    assert service._driver.frame is None
    service.invoke('set_scene',arguments(profile,clock,clock_fields='[]'))
    original=service._driver.frame
    service._driver.write_frame=lambda *_:pytest.fail('Static scene tick wrote again')
    clock.advance(1); service.tick(); clock.advance(1); service.tick()
    assert service._driver.frame==original


def test_runtime_disable_and_restart_never_restore_approved_clock_scene(tmp_path):
    profile=CharacterDisplaySceneProfileV1(columns=16)
    blob=build_scene_package(profile)
    handlers={SCENE_ENTRYPOINT:character_display_scene_handler(lock_dir=tmp_path/'locks')}
    runtime=AgentModuleRuntime(tmp_path, architecture='armv6l',runtime_handlers=handlers)
    manifest=runtime.install(blob,expected_sha256=hashlib.sha256(blob).hexdigest())
    kwargs={'contract_version':'3.0','contract_digest':profile.contract().digest()}
    clock=Clock(); clock.wall=datetime.now(UTC).timestamp()
    runtime.invoke('display.character','set_scene',arguments(profile,clock),**kwargs)
    runtime.close()
    restarted=AgentModuleRuntime(tmp_path, architecture='armv6l',runtime_handlers=handlers)
    try:
        restarted.start_active()
        state=restarted.capability_states()['display.character']
        assert not state['scene_active'] and not state['has_frame']
        module_id='org.3mm.character-display.'+profile.digest()
        restarted.disable(module_id)
        with pytest.raises(ModuleLifecycleError): restarted.invoke('display.character','set_scene',arguments(profile,clock),**kwargs)
    finally: restarted.close()


def test_background_clock_ticks_without_any_transport_and_close_joins_thread(tmp_path):
    profile=CharacterDisplaySceneProfileV1(columns=16)
    service=CharacterDisplaySceneService(profile,lock_dir=tmp_path)
    ticked=threading.Event(); calls=[]
    original=service._driver.write_frame
    def write(lines,backlight):
        original(lines,backlight); calls.append(lines)
        if len(calls)>1: ticked.set()
    service._driver.write_frame=write
    clock=Clock(); clock.wall=datetime.now(UTC).timestamp()
    try:
        service.invoke('set_scene',arguments(profile,clock))
        assert ticked.wait(3), 'Local clock worker did not wake for the next second'
    finally: service.close()
    assert not service._thread.is_alive() and not service.is_available()
