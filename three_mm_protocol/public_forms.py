"""Bounded form contracts; no Core accounts, files or effect providers."""
from dataclasses import dataclass
import hashlib
import re
from urllib.parse import urlsplit

MAX_FORM_BYTES = 4096
MAX_FORM_FIELDS = 8
FORM_REQUEST_ID = '_request_id'
FORM_ID = re.compile(r'[0-9a-f]{32}')
FORM_RESULTS = ('accepted', 'conflict', 'capacity_reached')
GUEST_PROOF_FIELD = '_guest_id'
GUEST_TTL_SECONDS = 15 * 60
GUEST_COOKIE = re.compile(r'([0-9a-f]{32})\.([1-9][0-9]{0,10})\.([0-9a-f]{64})')


def public_form_origin_host(value: str) -> str:
    parts = urlsplit(value)
    host = parts.hostname
    if (parts.scheme not in {'http', 'https'} or host is None
            or re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?', host) is None
            or (parts.scheme == 'http' and host not in {'127.0.0.1', 'localhost'})
            or parts.port == (443 if parts.scheme == 'https' else 80)):
        raise ValueError('Configure an exact HTTPS origin or a loopback HTTP origin')
    authority = host + (f':{parts.port}' if parts.port is not None else '')
    if value != f'{parts.scheme}://{authority}':
        raise ValueError('Public form origin must be canonical, with no path or credentials')
    return authority


def guest_cookie_name(origin: str, path: str) -> str:
    # Cookies ignore ports, so use an origin-specific name even on loopback.
    prefix = '__Host-' if origin.startswith('https://') else 'lab-'
    suffix = hashlib.sha256(f'{origin}\n{path}'.encode('utf-8')).hexdigest()[:24]
    return f'{prefix}3mm-guest-{suffix}'


@dataclass(frozen=True, slots=True)
class PublicFormGuest:
    guest_id: str
    expires_at: int

    @classmethod
    def from_platform(cls, value: object) -> 'PublicFormGuest':
        if (not isinstance(value, dict) or set(value) != {'guest_id', 'expires_at'}
                or not isinstance(value['guest_id'], str) or FORM_ID.fullmatch(value['guest_id']) is None
                or type(value['expires_at']) is not int or not 0 < value['expires_at'] < 10**11):
            raise ValueError('Public form guest context is invalid')
        return cls(**value)


def public_form_result_schema() -> dict:
    return {'type': 'object', 'additionalProperties': False,
            'properties': {'status': {'type': 'string', 'enum': list(FORM_RESULTS)}},
            'required': ['status']}


def validate_form_schema(schema: dict) -> None:
    fields = schema.get('properties')
    required = schema.get('required')
    if (set(schema) != {'type', 'properties', 'required', 'additionalProperties'}
            or schema['type'] != 'object' or schema['additionalProperties'] is not False
            or not isinstance(fields, dict) or not 1 <= len(fields) <= MAX_FORM_FIELDS
            or not isinstance(required, list) or not all(isinstance(key, str) for key in required)
            or len(required) != len(fields) or set(required) != set(fields)):
        raise ValueError('Public form requires a closed object with all fields required')
    for name, field in fields.items():
        if (re.fullmatch(r'[a-z][a-z0-9_]{0,63}', name) is None or not isinstance(field, dict)
                or set(field) - {'type', 'minLength', 'maxLength', 'enum'}
                or field.get('type') != 'string'
                or type(field.get('maxLength')) is not int
                or type(field.get('minLength', 1)) is not int
                or not 1 <= field.get('minLength', 1) <= field['maxLength'] <= 512):
            raise ValueError('Public form fields must be bounded single-line strings')
        choices = field.get('enum')
        if 'enum' in field and (not isinstance(choices, list) or not 1 <= len(choices) <= 16
                or not all(_valid_value(item, field) for item in choices)
                or len(set(choices)) != len(choices)):
            raise ValueError('Public form choices are invalid')


def _valid_value(value, field):
    return (isinstance(value, str) and field.get('minLength', 1) <= len(value) <= field['maxLength']
            and not any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value))


def public_form_payload(form: dict, schema: dict) -> tuple[str, dict]:
    """Revalidate the adapter's bounded, decoded data before Core dispatches."""
    if not isinstance(form, dict) or set(form) != schema['properties'].keys() | {FORM_REQUEST_ID}:
        raise ValueError('Public form fields do not match the declaration')
    request_id = form[FORM_REQUEST_ID]
    if not isinstance(request_id, str) or FORM_ID.fullmatch(request_id) is None:
        raise ValueError('Public form request ID is invalid')
    payload = {}
    for name, field in schema['properties'].items():
        value = form[name]
        if not _valid_value(value, field) or ('enum' in field and value not in field['enum']):
            raise ValueError('Public form value is invalid')
        payload[name] = value
    if sum(len(key.encode('utf-8')) + len(value.encode('utf-8')) for key, value in form.items()) > MAX_FORM_BYTES:
        raise ValueError('Public form exceeds the byte limit')
    return request_id, payload
