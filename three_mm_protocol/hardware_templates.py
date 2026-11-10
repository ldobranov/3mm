"""Inert provider-package forms and bounded manifest instantiation.

Templates contain data, not executable validators, imports or driver names known
to Core. An exact source package supplies a valid default manifest; parameters
can replace existing scalar values only. Agent handlers remain authoritative for
their supported hardware and exact profile/contract before opening a device.
"""
from __future__ import annotations

import copy
import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from three_mm_protocol.hardware_profiles import hardware_profile, profile_digest
from three_mm_protocol.module_manifest import ModuleManifestV2

TEMPLATE_FILENAME = 'hardware-template.json'
MAX_TEMPLATE_BYTES = 64 * 1024
_INTEGER_LIMIT = 2_147_483_647
_PATTERN_ATOM = re.compile(r'(?:\[[A-Za-z0-9_.-]+\]|[A-Za-z0-9_.-])(?:\{(\d{1,3})(?:,(\d{1,3}))?\})?')


def _bounded_json(value, *, max_bytes, depth=0):
    if depth > 20:
        raise ValueError('Hardware template JSON is too deeply nested')
    if isinstance(value, dict):
        if len(value) > 256 or any(type(key) is not str or len(key) > 240 for key in value):
            raise ValueError('Hardware template JSON object is outside limits')
        for child in value.values():
            _bounded_json(child, max_bytes=max_bytes, depth=depth + 1)
    elif isinstance(value, (list, tuple)):
        if len(value) > 256:
            raise ValueError('Hardware template JSON array is outside limits')
        for child in value:
            _bounded_json(child, max_bytes=max_bytes, depth=depth + 1)
    elif value is not None and type(value) not in {str, int, float, bool}:
        raise ValueError('Hardware template requires plain JSON values')
    if depth == 0:
        try:
            raw = json.dumps(value, allow_nan=False, ensure_ascii=True).encode('ascii')
        except (ValueError, TypeError, OverflowError, RecursionError) as error:
            raise ValueError('Hardware template is not bounded JSON') from error
        if len(raw) > max_bytes:
            raise ValueError('Hardware template JSON is too large')


def _check_pattern(pattern):
    # Bounded concatenated character classes/literals only: no groups,
    # alternatives, lookaround, recursion, unbounded repeats or backreferences.
    if not pattern.startswith('^') or not pattern.endswith('$'):
        raise ValueError('Hardware template pattern must be anchored')
    body, position, atoms, variable_repeats = pattern[1:-1], 0, 0, 0
    while position < len(body):
        match = _PATTERN_ATOM.match(body, position)
        if match is None:
            raise ValueError('Unsupported hardware template pattern')
        if match[1] is not None:
            low, high = int(match[1]), int(match[2] or match[1])
            if not 0 <= low <= high <= 512:
                raise ValueError('Hardware template pattern repeat is outside limits')
            variable_repeats += low != high
            if variable_repeats > 1:
                raise ValueError('Hardware template pattern permits only one variable repeat')
        atoms += 1
        if atoms > 16:
            raise ValueError('Hardware template pattern has too many atoms')
        position = match.end()
    if atoms == 0:
        raise ValueError('Hardware template pattern is empty')
    try:
        re.compile(pattern)
    except re.error as error:
        raise ValueError('Hardware template character class is invalid') from error


class _Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True)


class HardwareTemplateOptionV1(_Strict):
    value: str = Field(max_length=256)
    label: str = Field(min_length=1, max_length=120)


class HardwareTemplateFieldV1(_Strict):
    key: str = Field(pattern=r'^[a-z][a-z0-9_]{0,63}$')
    label: str = Field(min_length=1, max_length=120)
    type: Literal['text', 'number', 'select', 'checkbox']
    default: str | int | bool
    min: int | None = Field(default=None, ge=-_INTEGER_LIMIT, le=_INTEGER_LIMIT)
    max: int | None = Field(default=None, ge=-_INTEGER_LIMIT, le=_INTEGER_LIMIT)
    maxlength: int | None = Field(default=None, ge=1, le=512)
    pattern: str | None = Field(default=None, min_length=1, max_length=128)
    options: list[HardwareTemplateOptionV1] | None = Field(default=None, min_length=1, max_length=256)

    @model_validator(mode='after')
    def bounded_field(self):
        expected = bool if self.type == 'checkbox' else int if self.type == 'number' else str
        if self.type != 'select' and type(self.default) is not expected:
            raise ValueError('Hardware template default has the wrong type')
        if self.type == 'select':
            if type(self.default) not in {str, int} or not self.options:
                raise ValueError('Hardware template select requires string/integer options')
            values = [option.value for option in self.options]
            if len(values) != len(set(values)):
                raise ValueError('Hardware template select options must be unique')
            if type(self.default) is int and any(
                    re.fullmatch(r'-?(0|[1-9][0-9]*)', value) is None
                    or str(int(value)) != value or abs(int(value)) > _INTEGER_LIMIT for value in values):
                raise ValueError('Hardware template integer options are invalid')
        elif self.options is not None:
            raise ValueError('Only hardware template selects have options')
        if self.type == 'number' and (self.min is None or self.max is None):
            raise ValueError('Hardware template numbers require bounds')
        if self.type == 'text' and self.maxlength is None:
            raise ValueError('Hardware template text requires a length bound')
        if self.type not in {'number', 'select'} and (self.min is not None or self.max is not None):
            raise ValueError('Numeric bounds require a numeric hardware template field')
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError('Hardware template numeric bounds are reversed')
        if self.type != 'text' and (self.maxlength is not None or self.pattern is not None):
            raise ValueError('Text bounds require a text hardware template field')
        if self.pattern is not None:
            _check_pattern(self.pattern)
        self.checked_value(self.default)
        return self

    def checked_value(self, value):
        if type(value) is not type(self.default):
            raise ValueError('Hardware template parameter type does not match')
        if type(value) is int:
            if abs(value) > _INTEGER_LIMIT or self.min is not None and value < self.min or self.max is not None and value > self.max:
                raise ValueError('Hardware template parameter is outside numeric bounds')
        if type(value) is str and (not value or len(value) > (self.maxlength or 256)
                or self.pattern is not None and re.fullmatch(self.pattern, value) is None):
            raise ValueError('Hardware template parameter is outside text bounds')
        if self.type == 'select' and str(value) not in {option.value for option in self.options}:
            raise ValueError('Hardware template parameter is not a declared option')
        return value


class HardwareTemplateV1(_Strict):
    hardware_template_version: Literal[1] = 1
    template_id: str = Field(pattern=r'^[a-z0-9.-]{1,80}$')
    name: str = Field(min_length=1, max_length=120)
    help: str | None = Field(default=None, min_length=1, max_length=1000)
    required_features: list[str] = Field(default_factory=list, max_length=16)
    fields: list[HardwareTemplateFieldV1] = Field(min_length=1, max_length=16)
    bindings: dict[str, list[str]] = Field(min_length=1, max_length=16)

    @model_validator(mode='after')
    def bounded_bindings(self):
        keys = [field.key for field in self.fields]
        if len(keys) != len(set(keys)) or set(keys) != set(self.bindings):
            raise ValueError('Hardware template fields and bindings must match exactly')
        features = self.required_features
        if len(features) != len(set(features)) or any(re.fullmatch(r'[a-z][a-z0-9_.-]{0,99}', value) is None for value in features):
            raise ValueError('Hardware template runtime features are invalid')
        targets = [path for paths in self.bindings.values() for path in paths]
        if any(not paths or len(paths) > 16 for paths in self.bindings.values()) or len(targets) > 128 or len(targets) != len(set(targets)):
            raise ValueError('Hardware template pointer bindings are outside limits')
        return self


def _tokens(pointer):
    if not pointer.startswith('/') or len(pointer) > 512:
        raise ValueError('Hardware template requires a bounded JSON pointer')
    tokens = pointer[1:].split('/')
    if len(tokens) > 16 or any(not token or re.search(r'~(?![01])', token) for token in tokens):
        raise ValueError('Hardware template JSON pointer is invalid')
    return [token.replace('~1', '/').replace('~0', '~') for token in tokens]


def _parent(value, tokens):
    parent = value
    for token in tokens[:-1]:
        if isinstance(parent, dict) and token in parent:
            parent = parent[token]
        elif isinstance(parent, list) and re.fullmatch(r'0|[1-9][0-9]*', token) and int(token) < len(parent):
            parent = parent[int(token)]
        else:
            raise ValueError('Hardware template pointer does not exist')
    token = tokens[-1]
    if isinstance(parent, dict) and token in parent:
        return parent, token
    if isinstance(parent, list) and re.fullmatch(r'0|[1-9][0-9]*', token) and int(token) < len(parent):
        return parent, int(token)
    raise ValueError('Hardware template pointer does not exist')


def _allowed(tokens):
    if tokens[0] == 'configuration_defaults' and len(tokens) >= 2:
        return True
    if len(tokens) < 4 or tokens[0] != 'registrations' or re.fullmatch(r'0|[1-9][0-9]*', tokens[1]) is None:
        return False
    if tokens[2] == 'metadata':
        return len(tokens) == 4 and tokens[3] not in {'profile_sha256', 'simulated'}
    if tokens[2] != 'contract':
        return False
    rest = tokens[3:]
    if rest[0] == 'state_schema':
        rest = rest[1:]
    elif len(rest) >= 3 and rest[0] == 'actions' and rest[2] in {'arguments_schema', 'result_schema'}:
        rest = rest[3:]
    elif len(rest) >= 2 and rest[0] == 'events':
        rest = rest[2:]
    else:
        return False
    while len(rest) > 2 and rest[0] == 'properties':
        rest = rest[2:]
    return len(rest) == 2 and rest[0] == 'enum' and re.fullmatch(r'0|[1-9][0-9]*', rest[1]) is not None


def _manifest(value):
    value = value.model_dump(mode='json') if isinstance(value, ModuleManifestV2) else copy.deepcopy(value)
    _bounded_json(value, max_bytes=128 * 1024)
    manifest = ModuleManifestV2.model_validate(value)
    profile = hardware_profile(manifest)
    if profile is None or set(manifest.runtimes) != {'agent'}:
        raise ValueError('Hardware template requires an exact Agent-only hardware profile')
    suffix = '.' + profile.profile_sha256
    if not manifest.module_id.endswith(suffix) or len(manifest.module_id) <= len(suffix):
        raise ValueError('Hardware template module identity must end with its profile digest')
    return manifest.model_dump(mode='json'), profile


def validate_template(manifest, descriptor) -> HardwareTemplateV1:
    """Validate one exact baseline without instantiating a driver or executing code."""
    descriptor = descriptor.model_dump(mode='json') if isinstance(descriptor, HardwareTemplateV1) else descriptor
    _bounded_json(descriptor, max_bytes=MAX_TEMPLATE_BYTES)
    template = HardwareTemplateV1.model_validate(descriptor)
    value, profile = _manifest(manifest)
    for field in template.fields:
        for pointer in template.bindings[field.key]:
            tokens = _tokens(pointer)
            if not _allowed(tokens):
                raise ValueError('Hardware template cannot change identity, privilege or contract structure')
            parent, key = _parent(value, tokens)
            old = parent[key]
            if type(old) not in {str, int, bool} or type(old) is not type(field.default) or old != field.default:
                raise ValueError('Hardware template parameter does not match an existing scalar default')
            if old == profile.profile_sha256:
                raise ValueError('Hardware template profile digest is derived, not a parameter')
    return template


def _replace_digest(value, previous, current):
    if isinstance(value, dict):
        return {key: _replace_digest(child, previous, current) for key, child in value.items()}
    if isinstance(value, list):
        return [_replace_digest(child, previous, current) for child in value]
    return current if value == previous else value


def instantiate_template(manifest, descriptor, configuration) -> dict:
    """Return a new manifest. Callers package/validate it before normal consent."""
    template = validate_template(manifest, descriptor)
    value, profile = _manifest(manifest)
    _bounded_json(configuration, max_bytes=8192)
    if not isinstance(configuration, dict) or set(configuration) != set(template.bindings):
        raise ValueError('Hardware template configuration fields do not match')
    for field in template.fields:
        replacement = field.checked_value(configuration[field.key])
        for pointer in template.bindings[field.key]:
            parent, key = _parent(value, _tokens(pointer))
            parent[key] = replacement
    current = profile_digest(value['configuration_defaults'])
    value['module_id'] = value['module_id'][:-64] + current
    for registration in value['registrations']:
        for key in ('metadata', 'contract'):
            if key in registration:
                registration[key] = _replace_digest(registration[key], profile.profile_sha256, current)
    result = ModuleManifestV2.model_validate(value)
    if hardware_profile(result).profile_sha256 != current:
        raise ValueError('Hardware template produced an invalid profile')
    return result.model_dump(mode='json')


def describe_template(manifest, descriptor) -> dict:
    """Existing generic administrator-form shape; source package pins identity."""
    template = validate_template(manifest, descriptor)
    _, profile = _manifest(manifest)
    return {'template_id': template.template_id, 'name': template.name, 'simulated': profile.simulated,
        'fields': [field.model_dump(exclude_none=True) for field in template.fields],
        **({'help': template.help} if template.help is not None else {})}
