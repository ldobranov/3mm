"""Opt-in character-display scenes: finite local execution, not a frame replay."""
from typing import Literal
import re
from three_mm_protocol.capability_contracts import CapabilityContractV1, validate_value
from three_mm_protocol.character_display import CharacterDisplayProfileV1, frame_arguments_schema, _object
from three_mm_protocol.character_clock import MAX_CLOCK_FIELDS_BYTES, clock_zone, parse_clock_fields

SCENE_ENTRYPOINT = 'builtin:display.character.scene.v1'
SCENE_FEATURE = 'display.character.scenes.v1'
SCENE_CONTRACT_VERSION = '3.0'
MAX_SCENE_LEASE_SECONDS = 30
MAX_SCENE_SEQUENCE = 2_147_483_647
MAX_SAFE_INTEGER = 9_007_199_254_740_991


def _identity():
    return {
        'display_id': {'type': 'string', 'maxLength': 64},
        'profile_sha256': {'type': 'string', 'minLength': 64, 'maxLength': 64},
        'scene_id': {'type': 'string', 'minLength': 32, 'maxLength': 32},
        'sequence': {'type': 'integer', 'minimum': 1, 'maximum': MAX_SCENE_SEQUENCE},
    }


def scene_arguments_schema():
    return _object({**frame_arguments_schema()['properties'], **_identity(),
        'clock_fields': {'type': 'string', 'minLength': 2, 'maxLength': MAX_CLOCK_FIELDS_BYTES},
        'timezone': {'type': 'string', 'minLength': 1, 'maxLength': 80},
        'valid_until_ms': {'type': 'integer', 'minimum': 1, 'maximum': MAX_SAFE_INTEGER}})


def stop_scene_arguments_schema():
    return _object(_identity())


class CharacterDisplaySceneProfileV1(CharacterDisplayProfileV1):
    """New separately reviewed provider; static-only profiles remain distinct."""
    schema_version: Literal[3] = 3
    max_scene_lease_seconds: Literal[30] = 30

    def contract(self):
        frame = super().contract()
        properties = {**frame.state_schema['properties'],
            'scene_id': {'type': 'string', 'maxLength': 32},
            'scene_sequence': {'type': 'integer', 'minimum': 0, 'maximum': MAX_SCENE_SEQUENCE},
            'scene_active': {'type': 'boolean'},
            'scene_valid_until_ms': {'type': 'integer', 'minimum': 0, 'maximum': MAX_SAFE_INTEGER}}
        stop_result = _object({
            **{key: value for key, value in _identity().items() if key != 'sequence'},
            'display_id': properties['display_id'],
            'profile_sha256': properties['profile_sha256'],
            'scene_sequence': {'type': 'integer', 'minimum': 1, 'maximum': MAX_SCENE_SEQUENCE},
            'scene_stopped': {'type': 'boolean', 'enum': [True]},
            'simulated': {'type': 'boolean', 'enum': [self.driver == 'mock']}})
        return CapabilityContractV1.model_validate({
            'schema_version': 1, 'capability_id': frame.capability_id,
            'contract_version': SCENE_CONTRACT_VERSION, 'state_schema': _object(properties),
            'actions': {
                'write_frame': {'arguments_schema': frame_arguments_schema(),
                    'result_schema': _object({**properties, 'has_frame': {'type': 'boolean', 'enum': [True]},
                        'scene_active': {'type': 'boolean', 'enum': [False]}})},
                'set_scene': {'arguments_schema': scene_arguments_schema(),
                    'result_schema': _object({**properties, 'has_frame': {'type': 'boolean', 'enum': [True]},
                        'scene_active': {'type': 'boolean', 'enum': [True]},
                        'scene_accepted': {'type': 'boolean', 'enum': [True]}})},
                'stop_scene': {'arguments_schema': stop_scene_arguments_schema(), 'result_schema': stop_result}}})

    def scene(self, arguments, *, now_ms):
        validate_value(arguments, scene_arguments_schema())
        if re.fullmatch('[0-9a-f]{32}', arguments['scene_id']) is None:
            raise ValueError('Invalid scene identity')
        frame = self.frame({key: arguments[key] for key in frame_arguments_schema()['properties']})
        remaining = arguments['valid_until_ms'] - now_ms
        if not 0 < remaining <= MAX_SCENE_LEASE_SECONDS * 1000:
            raise ValueError('Scene lease expired or exceeds the local execution budget')
        fields = parse_clock_fields(arguments['clock_fields'], columns=self.columns, rows=self.rows)
        return frame, fields, clock_zone(arguments['timezone']), remaining / 1000

    def stop(self, arguments):
        validate_value(arguments, stop_scene_arguments_schema())
        if re.fullmatch('[0-9a-f]{32}', arguments['scene_id']) is None:
            raise ValueError('Invalid scene identity')
        if arguments['display_id'] != self.display_id or arguments['profile_sha256'] != self.digest():
            raise ValueError('Display profile changed; review the selected provider')
