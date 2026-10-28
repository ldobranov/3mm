"""Streaming public Python SDK. No filesystem fallback or mutation replay."""
import base64
import hashlib
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from three_mm_application_sdk.files import ApplicationFileStorageError
from three_mm_protocol.application_extension import ApplicationPrivateFilesV2
from three_mm_application_sdk.scoped_files import ApplicationFileExecutionUnconfirmed
from three_mm_application_sdk.media_wire import CHUNK_BYTES, MUTATIONS, parse_media_request, validate_result
from three_mm_application_sdk.transaction_guard import require_outside_relational_transaction


@dataclass(frozen=True, slots=True)
class ApplicationScopedMediaStorage:
    data_dir: Path
    platform: object = field(repr=False)
    declaration: ApplicationPrivateFilesV2

    def __post_init__(self):
        if not isinstance(self.data_dir, Path) or not isinstance(self.declaration, ApplicationPrivateFilesV2):
            raise ValueError('Streaming storage requires a host-owned context')

    @property
    def mode(self):
        return self.declaration.mode

    @property
    def limits(self):
        return self.declaration

    def execute(self, operation, *, request_id=None, **fields):
        require_outside_relational_transaction()
        value = parse_media_request({'file_request_version': 2, 'request_id': request_id or uuid.uuid4().hex, 'operation': operation, **fields})
        if self.platform is None:
            raise ApplicationFileStorageError('Streaming files require current Core authority')
        try:
            response = self.platform._call('files.execute', {'file_request': value})
            receipt = response['receipt']
            if receipt['request_id'] != value['request_id'] or receipt['outcome'] != 'completed':
                raise RuntimeError()
            result = response.get('file_result', receipt.get('result'))
            validate_result(result, value)
        except (RuntimeError, KeyError, TypeError, ValueError, AttributeError):
            if operation in MUTATIONS or operation == 'append':
                raise ApplicationFileExecutionUnconfirmed(value['request_id']) from None
            raise ApplicationFileStorageError('File authority or runtime is unavailable') from None
        if not result['ok']:
            raise ApplicationFileStorageError('File request refused: ' + result['error_code'])
        return result

    def begin(self, file_id, size_bytes, sha256, *, filename, content_type, expected_sha256=None, request_id=None):
        return self.execute('begin', request_id=request_id, file_id=file_id, size_bytes=size_bytes, sha256=sha256,
            expected_sha256=expected_sha256, filename=filename, content_type=content_type)

    def append(self, upload_id, offset, content):
        if type(content) is not bytes or not 1 <= len(content) <= CHUNK_BYTES:
            raise ValueError('Invalid file chunk')
        return self.execute('append', upload_id=upload_id, offset=offset, content_base64=base64.b64encode(content).decode('ascii'))

    def upload_status(self, upload_id):
        return self.execute('upload_status', upload_id=upload_id)

    def finalize(self, upload_id, *, request_id=None):
        return self.execute('finalize', upload_id=upload_id, request_id=request_id)

    def cancel(self, upload_id, *, request_id=None):
        return self.execute('cancel', upload_id=upload_id, request_id=request_id)

    def stat(self, file_id):
        return self.execute('stat', file_id=file_id)['file']

    def list_files(self, after=''):
        return self.execute('list', after=after)

    def iter_read(self, file_id, sha256, *, offset=0):
        metadata = self.stat(file_id)
        if metadata['sha256'] != sha256:
            raise ApplicationFileStorageError('File revision conflict')
        digest = hashlib.sha256()
        full = offset == 0
        while offset < metadata['size_bytes']:
            value = self.execute('read', file_id=file_id, sha256=sha256, offset=offset, length=CHUNK_BYTES)
            data = base64.b64decode(value['content_base64'], validate=True)
            if not data:
                raise ApplicationFileStorageError('Incomplete file stream')
            digest.update(data)
            offset += len(data)
            yield data
        if full and digest.hexdigest() != sha256:
            raise ApplicationFileStorageError('File checksum mismatch')

    def delete(self, file_id, *, expected_sha256, request_id=None):
        return self.execute('delete', file_id=file_id, expected_sha256=expected_sha256, request_id=request_id)

    def create_link(self, file_id, sha256, *, token, ttl_seconds, max_downloads, request_id=None):
        return self.execute('link', file_id=file_id, sha256=sha256, token=token, ttl_seconds=ttl_seconds,
            max_downloads=max_downloads, request_id=request_id)

    def revoke_link(self, link_id, *, request_id=None):
        return self.execute('unlink', link_id=link_id, request_id=request_id)

    def transform(self, file_id, sha256, *, output_id, width, height, format, request_id=None):
        return self.execute('transform', file_id=file_id, sha256=sha256, output_id=output_id,
            width=width, height=height, format=format, request_id=request_id)

    def job(self, job_id):
        return self.execute('job', job_id=job_id)

    def cleanup(self, *, request_id=None):
        return self.execute('cleanup', request_id=request_id)

    def operation_status(self, request_id):
        require_outside_relational_transaction()
        return self.platform._call('files.status', {'file_request_id': request_id})
