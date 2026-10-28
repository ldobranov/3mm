"""CAP11 streaming control protocol. File bytes occupy bounded chunks only."""
import base64
import hashlib
import json
import re

CHUNK_BYTES = 256 * 1024
IDENTIFIER = re.compile(r'^[0-9a-f]{32}$')
DIGEST = re.compile(r'^[0-9a-f]{64}$')
FILE = re.compile(r'^[a-z][a-z0-9_]{0,63}$')
SCOPES = {
    'list': 'read', 'stat': 'read', 'read': 'read', 'upload_status': 'write',
    'begin': 'write', 'append': 'write', 'finalize': 'write', 'cancel': 'write',
    'delete': 'write', 'cleanup': 'write', 'job': 'transform', 'transform': 'transform',
    'link': 'publish', 'unlink': 'publish', 'public_stat': 'publish', 'public_read': 'publish',
}
MUTATIONS = {'begin', 'finalize', 'cancel', 'delete', 'cleanup', 'transform', 'link', 'unlink'}
FIELDS = {
    'list': {'after'}, 'stat': {'file_id'},
    'read': {'file_id', 'sha256', 'offset', 'length'},
    'begin': {'file_id', 'size_bytes', 'sha256', 'expected_sha256', 'filename', 'content_type'},
    'append': {'upload_id', 'offset', 'content_base64'},
    'upload_status': {'upload_id'}, 'finalize': {'upload_id'}, 'cancel': {'upload_id'},
    'delete': {'file_id', 'expected_sha256'}, 'cleanup': set(),
    'transform': {'file_id', 'sha256', 'output_id', 'width', 'height', 'format'},
    'job': {'job_id'},
    'link': {'file_id', 'sha256', 'token', 'ttl_seconds', 'max_downloads'},
    'unlink': {'link_id'}, 'public_stat': {'link_id', 'token'},
    'public_read': {'link_id', 'token', 'sha256', 'offset', 'length', 'download_id'},
}


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('File integer is outside its bounds')


def parse_media_request(value):
    if type(value) is not dict or type(value.get('file_request_version')) is not int or value['file_request_version'] != 2:
        raise ValueError('Streaming file request version is invalid')
    op = value.get('operation')
    if type(op) is not str or op not in FIELDS or set(value) != FIELDS[op] | {'file_request_version', 'request_id', 'operation'}:
        raise ValueError('Streaming file request fields are invalid')
    value = dict(value)
    for key in ('request_id', 'upload_id', 'job_id', 'link_id', 'download_id'):
        if key in value and (type(value[key]) is not str or not IDENTIFIER.fullmatch(value[key])):
            raise ValueError('Streaming identity is invalid')
    for key in ('file_id', 'output_id', 'after'):
        if key in value and (type(value[key]) is not str or (value[key] != '' or key != 'after') and not FILE.fullmatch(value[key])):
            raise ValueError('Logical file identity is invalid')
    for key in ('sha256', 'expected_sha256', 'token'):
        if key in value and not (key == 'expected_sha256' and op == 'begin' and value[key] is None):
            if type(value[key]) is not str or not DIGEST.fullmatch(value[key]):
                raise ValueError('File digest/token is invalid')
    for key, ceiling in (('offset', 1024**3), ('size_bytes', 1024**3), ('length', CHUNK_BYTES),
                         ('ttl_seconds', 86400), ('max_downloads', 1000), ('width', 4096), ('height', 4096)):
        if key in value:
            integer(value[key], 0 if key in {'offset', 'size_bytes'} else 1, ceiling)
    if 'filename' in value:
        if type(value['filename']) is not str or not 1 <= len(value['filename'].encode('utf-8')) <= 240 or any(ord(c) < 32 or c in '/\\' for c in value['filename']):
            raise ValueError('Display filename is invalid')
        if type(value['content_type']) is not str or not re.fullmatch(r'[a-z0-9.+-]{1,64}/[a-z0-9.+-]{1,64}', value['content_type']):
            raise ValueError('Content type is invalid')
    if 'format' in value and value['format'] not in {'png', 'jpeg', 'webp'}:
        raise ValueError('Image format is unsupported')
    if 'content_base64' in value:
        encoded = value['content_base64']
        if type(encoded) is not str or len(encoded) > (CHUNK_BYTES + 2) // 3 * 4:
            raise ValueError('File chunk exceeds its bound')
        data = base64.b64decode(encoded, validate=True)
        if not data or len(data) > CHUNK_BYTES or base64.b64encode(data).decode('ascii') != encoded:
            raise ValueError('File chunk is invalid')
    return value


def request_identity(value):
    metadata = dict(value)
    for name in ('content_base64', 'token'):
        if name in metadata:
            metadata[name] = hashlib.sha256(metadata[name].encode('ascii')).hexdigest()
    return hashlib.sha256(json.dumps(metadata, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def validate_result(result, request):
    if type(result) is not dict or type(result.get('ok')) is not bool or len(json.dumps(result)) > 512 * 1024:
        raise ValueError('File result is invalid')
    if not result['ok']:
        if set(result) != {'ok', 'error_code'} or result['error_code'] not in {'conflict', 'quota', 'not_found', 'expired', 'denied', 'checksum', 'provider_unavailable', 'transform_failed', 'recovery_required'}:
            raise ValueError('File failure is invalid')
    if request['operation'] in {'read', 'public_read'} and result['ok']:
        content = base64.b64decode(result['content_base64'], validate=True)
        if len(content) > request['length'] or result['offset'] != request['offset'] or result['chunk_sha256'] != hashlib.sha256(content).hexdigest() or result['sha256'] != request['sha256']:
            raise ValueError('File chunk result is invalid')


def receipt(request, result=None, *, outcome='execution_unconfirmed'):
    # Never persist bearer capabilities or file bytes in Core's sealed journal.
    safe = None if result is None else {k: v for k, v in result.items() if k not in {'content_base64', 'token'}}
    return {'request_id': request['request_id'], 'operation': request['operation'],
            'file_id': request.get('file_id'), 'outcome': outcome, 'result': safe}
