"""Build the local CAP10 demo ZIP; no install, start or access changes."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile

from backend.artifacts.packages import validate_module_package
from packages.protocol import public_http_request_schema_v1, public_http_response_schema_v1
from packages.protocol.public_forms import public_form_result_schema
from tools.application_project import REPOSITORY, write_member

MODULE = 'org.3mm.public-form-reference'
VERSION = '1.0.0'
SERVICE = 'public_form_reference'
GUEST_MODULE = 'org.3mm.public-guest-reference'


def object_schema(**fields):
    return {'type': 'object', 'additionalProperties': False, 'properties': fields, 'required': list(fields)}


def build_package(*, guest: bool = False) -> bytes:
    service = 'public_guest_reference' if guest else SERVICE
    project = service.replace('_', '-')
    module = GUEST_MODULE if guest else MODULE
    wheel = io.BytesIO()
    dist = f'{service}-{VERSION}.dist-info'
    with zipfile.ZipFile(wheel, 'w') as archive:
        source = REPOSITORY / 'modules' / project / 'service' / service
        for path in sorted(source.glob('*.py')):
            write_member(archive, f'{service}/{path.name}', path.read_bytes())
        write_member(archive, f'{dist}/METADATA', f'Metadata-Version: 2.1\nName: {project}\nVersion: {VERSION}\n'.encode())
        write_member(archive, f'{dist}/WHEEL', b'Wheel-Version: 1.0\nGenerator: 3mm\nRoot-Is-Purelib: true\nTag: py3-none-any\n')
        write_member(archive, f'{dist}/RECORD', b'')
    artifact = f'service/{service}-{VERSION}-py3-none-any.whl'
    identity = {'module_id': module, 'version': VERSION}
    name = 'Public guest reference' if guest else 'Public form reference'
    manifest = dict(identity, manifest_version=2, name=name, runtimes=['core'],
        entrypoints={'core': 'application-extension.json'}, compatibility={'protocol': '1.0', 'architectures': ['any']},
        permissions=['data.read', 'data.write', 'process.spawn'], configuration_schema=object_schema(),
        health_check={'type': 'json_file', 'path': 'application-extension.json'})
    definition = dict(identity, application_extension_version=1, service={
        'artifact': artifact, 'artifact_sha256': hashlib.sha256(wheel.getvalue()).hexdigest(),
        'entrypoint': f'{service}.service:create_service', 'health_operation_id': 'health', 'sdk_version': '1.3'},
        storage={'schema_revision': '0001', 'migration_entrypoint': f'{service}.service:get_migrations'},
        operations=[
            {'operation_id': 'health', 'kind': 'query', 'audiences': ['internal'], 'idempotency': 'forbidden',
             'output_schema': object_schema(status={'type': 'string', 'enum': ['ready']})},
            {'operation_id': 'show_form', 'kind': 'query', 'audiences': ['public'], 'idempotency': 'forbidden',
             'input_schema': public_http_request_schema_v1(), 'output_schema': public_http_response_schema_v1()},
            {'operation_id': 'submit_form', 'kind': 'command', 'audiences': ['public'], 'idempotency': 'required',
             'input_schema': object_schema(choice={'type': 'string', 'maxLength': 9, 'enum': ['morning', 'afternoon']}),
             'output_schema': public_form_result_schema(), 'timeout_seconds': 5},
        ], public_http_routes=[{'route_id': 'demo_form', 'path': '/demo-guest' if guest else '/demo-request',
            'handler_operation_id': 'show_form', 'form_operation_id': 'submit_form',
            'content_types': ['text/html; charset=utf-8'], 'max_response_bytes': 4096,
            **({'methods': ['GET'], 'guest_session': True} if guest else {})}])
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        for name, content in [('manifest.json', manifest), ('application-extension.json', definition)]:
            write_member(archive, name, json.dumps(content, sort_keys=True, separators=(',', ':')).encode())
        write_member(archive, artifact, wheel.getvalue())
    return output.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--guest', action='store_true', help='Build the separate guest draft example')
    args = parser.parse_args()
    blob = build_package(guest=args.guest)
    validated = validate_module_package(blob)
    with args.output.open('xb') as stream:
        stream.write(blob)
    print(json.dumps({'module_id': validated.manifest.module_id, 'version': VERSION, 'sha256': validated.sha256,
                      'bytes': len(blob), 'installation': 'not_requested'}))


if __name__ == '__main__':
    main()
