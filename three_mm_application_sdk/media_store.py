"""Target-owned durable CAP11 store, outside Core. Cooperating reviewed code.

Only flat generated names beneath a descriptor-pinned private namespace. The
atomic bounded manifest commits metadata; incomplete bytes are never visible as
files. Committed blobs and old originals survive interrupted finalization.
"""
from contextlib import contextmanager
import base64
import hashlib
import json
import os
from pathlib import Path
import time
import uuid

from three_mm_application_sdk.files import ApplicationFileStorage, ApplicationFileStorageError
from three_mm_application_sdk.media_wire import CHUNK_BYTES, MUTATIONS, parse_media_request, request_identity
from three_mm_protocol.application_extension import ApplicationPrivateFilesV2

INDEX_LIMIT = 4 * 1024 * 1024
HISTORY_LIMIT = 2048


class MediaError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class _Namespace(ApplicationFileStorage):
    _namespace = 'sdk-media'


class ApplicationMediaStore:
    def __init__(self, data_dir, declaration, *, clock=time.time, provider=None):
        self.storage = _Namespace(Path(data_dir))
        self.declaration = ApplicationPrivateFilesV2.model_validate(declaration)
        self.clock, self.provider = clock, provider

    @staticmethod
    def _open(directory, name, flags=os.O_RDONLY):
        fd = os.open(name, flags | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, 0o600, dir_fd=directory)
        try:
            ApplicationFileStorage._regular(fd)
        except BaseException:
            os.close(fd)
            raise
        return fd

    def _load(self, directory):
        try:
            fd = self._open(directory, 'index.json')
        except FileNotFoundError:
            if set(os.listdir(directory)) != {'.lock'}:
                raise MediaError('recovery_required')
            return {'version': 2, 'files': {}, 'uploads': {}, 'links': {}, 'jobs': {}, 'receipts': {}}
        with os.fdopen(fd, 'rb') as stream:
            if os.fstat(stream.fileno()).st_size > INDEX_LIMIT:
                raise MediaError('recovery_required')
            data = stream.read(INDEX_LIMIT + 1)
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise MediaError('recovery_required')
                result[key] = value
            return result
        try:
            value = json.loads(data, object_pairs_hook=unique)
            if set(value) != {'version', 'files', 'uploads', 'links', 'jobs', 'receipts'} or type(value['version']) is not int or value['version'] != 2:
                raise ValueError()
            for key in ('files', 'uploads', 'links', 'jobs', 'receipts'):
                if type(value[key]) is not dict or len(value[key]) > (4096 if key == 'files' else HISTORY_LIMIT):
                    raise ValueError()
            # Validate generated disk names before any unlink/open from metadata.
            from three_mm_application_sdk.media_wire import IDENTIFIER, FILE
            for key, item in value['files'].items():
                if not FILE.fullmatch(key) or not IDENTIFIER.fullmatch(item['blob']):
                    raise ValueError()
            for key in value['uploads']:
                if not IDENTIFIER.fullmatch(key):
                    raise ValueError()
        except (ValueError, TypeError, KeyError, AttributeError):
            raise MediaError('recovery_required') from None
        return value

    @staticmethod
    def _save(directory, index):
        data = json.dumps(index, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
        if len(data) > INDEX_LIMIT:
            raise MediaError('quota')
        name = 'idx_' + uuid.uuid4().hex
        fd = ApplicationMediaStore._open(directory, name, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.rename(name, 'index.json', src_dir_fd=directory, dst_dir_fd=directory)
            os.fsync(directory)
        finally:
            try:
                os.unlink(name, dir_fd=directory)
            except FileNotFoundError:
                pass

    def _audit(self, directory, index, *, collect=False):
        from three_mm_application_sdk.media_wire import IDENTIFIER
        live = {'blob_' + item['blob'] for item in index['files'].values()}
        live |= {'part_' + key for key in index['uploads']}
        for entry in os.scandir(directory):
            if entry.name in {'.lock', 'index.json'}:
                continue
            prefix, _, identifier = entry.name.partition('_')
            if prefix not in {'blob', 'part', 'idx'} or not IDENTIFIER.fullmatch(identifier):
                raise MediaError('recovery_required')
            fd = self._open(directory, entry.name)
            os.close(fd)
            if collect and entry.name not in live:
                os.unlink(entry.name, dir_fd=directory)
        if collect:
            os.fsync(directory)

    def _expire(self, directory, index):
        now = int(self.clock())
        for key, upload in list(index['uploads'].items()):
            if not upload['created_at'] <= now < upload['expires_at']:
                del index['uploads'][key]
        # Expired links remain tombstones; clock rollback cannot revive them.
        for link in index['links'].values():
            if not link['created_at'] <= now < link['expires_at']:
                link['revoked'] = True

    def _file(self, index, request):
        item = index['files'].get(request['file_id'])
        if item is None:
            raise MediaError('not_found')
        if 'sha256' in request and item['sha256'] != request['sha256']:
            raise MediaError('conflict')
        return item

    def _upload(self, index, request, owner):
        item = index['uploads'].get(request['upload_id'])
        if item is None:
            raise MediaError('expired')
        if item['owner'] != owner:
            raise MediaError('denied')
        return item

    @staticmethod
    def _metadata(item):
        return {key: value for key, value in item.items() if key != 'blob'}

    def _quota(self, index, size, file_id):
        previous = index['files'].get(file_id, {}).get('size_bytes', 0)
        if size > self.declaration.max_file_bytes or sum(i['size_bytes'] for i in index['files'].values()) - previous + size > self.declaration.max_total_bytes or len(index['files']) + (file_id not in index['files']) > self.declaration.max_files:
            raise MediaError('quota')

    def _copy_blob(self, directory, source_name, blob, size, digest):
        src = self._open(directory, source_name)
        dst = self._open(directory, 'blob_' + blob, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        actual, count = hashlib.sha256(), 0
        with os.fdopen(src, 'rb') as source, os.fdopen(dst, 'wb') as target:
            while chunk := source.read(CHUNK_BYTES):
                count += len(chunk)
                if count > size:
                    raise MediaError('checksum')
                actual.update(chunk)
                target.write(chunk)
            target.flush()
            os.fsync(target.fileno())
        if count != size or actual.hexdigest() != digest:
            raise MediaError('checksum')
        os.fsync(directory)

    def execute(self, request, owner, epoch):
        request = parse_media_request(request)
        op = request['operation']
        if self.declaration.mode == 'read' and op not in {'read', 'stat', 'list'}:
            return {'ok': False, 'error_code': 'denied'}
        if op in {'link', 'unlink', 'public_stat', 'public_read'} and not self.declaration.public_links or op in {'transform', 'job'} and not self.declaration.media_transforms:
            return {'ok': False, 'error_code': 'denied'}
        # Metadata/expiry changes also need the exclusive cooperative lock. This
        # never turns read access into permission for a user-requested mutation.
        with self.storage._locked(write=True) as directory:
            index = self._load(directory)
            self._audit(directory, index)
            self._expire(directory, index)
            self._save(directory, index)
            self._audit(directory, index, collect=True)
            identity = request_identity(request)
            key = request['request_id']
            previous = index['receipts'].get(key)
            if previous is not None:
                if previous['owner'] != owner or previous['identity'] != identity:
                    return {'ok': False, 'error_code': 'conflict'}
                return previous['result']
            if op in MUTATIONS and len(index['receipts']) >= HISTORY_LIMIT:
                return {'ok': False, 'error_code': 'quota'}
            try:
                result = self._execute(directory, index, request, owner, epoch)
            except MediaError as error:
                result = {'ok': False, 'error_code': error.code}
            if op in MUTATIONS:
                index['receipts'][key] = {'owner': owner, 'identity': identity, 'result': result}
            self._save(directory, index)
            self._audit(directory, index, collect=True)
            return result

    def _execute(self, directory, index, req, owner, epoch):
        op, now = req['operation'], int(self.clock())
        if op == 'list':
            keys = sorted(key for key in index['files'] if key > req['after'])[:100]
            return {'ok': True, 'items': [self._metadata(index['files'][key]) for key in keys], 'after': keys[-1] if len(keys) == 100 else None,
                    'used_bytes': sum(i['size_bytes'] for i in index['files'].values()), 'file_count': len(index['files'])}
        if op == 'stat':
            return {'ok': True, 'file': self._metadata(self._file(index, req))}
        if op == 'begin':
            current = index['files'].get(req['file_id'])
            if (current['sha256'] if current else None) != req['expected_sha256']:
                raise MediaError('conflict')
            self._quota(index, req['size_bytes'], req['file_id'])
            if len(index['uploads']) >= self.declaration.max_uploads or sum(i['size_bytes'] for i in index['uploads'].values()) + req['size_bytes'] > self.declaration.max_staging_bytes:
                raise MediaError('quota')
            upload_id = uuid.uuid4().hex
            fd = self._open(directory, 'part_' + upload_id, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
            os.fsync(fd)
            os.close(fd)
            index['uploads'][upload_id] = {k: req[k] for k in ('file_id', 'size_bytes', 'sha256', 'expected_sha256', 'filename', 'content_type')}
            index['uploads'][upload_id].update(owner=owner, offset=0, created_at=now, expires_at=now + self.declaration.upload_ttl_seconds, last_chunk=None)
            return {'ok': True, 'upload_id': upload_id, 'offset': 0, 'expires_at': now + self.declaration.upload_ttl_seconds}
        if op in {'upload_status', 'append', 'cancel', 'finalize'}:
            upload = self._upload(index, req, owner)
            if op == 'upload_status':
                return {'ok': True, 'upload': {k: v for k, v in upload.items() if k not in {'owner', 'last_chunk'}}, 'upload_id': req['upload_id']}
            if op == 'cancel':
                del index['uploads'][req['upload_id']]
                return {'ok': True}
            if op == 'append':
                data = base64.b64decode(req['content_base64'], validate=True)
                chunk = {'offset': req['offset'], 'size_bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                if req['offset'] != upload['offset']:
                    if chunk == upload['last_chunk']:
                        return {'ok': True, 'offset': upload['offset'], 'chunk_sha256': chunk['sha256']}
                    raise MediaError('conflict')
                if req['offset'] + len(data) > upload['size_bytes']:
                    raise MediaError('quota')
                fd = self._open(directory, 'part_' + req['upload_id'], os.O_RDWR)
                with os.fdopen(fd, 'r+b') as stream:
                    if os.fstat(stream.fileno()).st_size < upload['offset']:
                        raise MediaError('recovery_required')
                    # A crash before manifest commit may leave only an unconfirmed
                    # tail. Truncate it to the last fsynced acknowledged offset.
                    stream.truncate(upload['offset'])
                    stream.seek(upload['offset'])
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                upload['offset'] += len(data)
                upload['last_chunk'] = chunk
                return {'ok': True, 'offset': upload['offset'], 'chunk_sha256': chunk['sha256']}
            current = index['files'].get(upload['file_id'])
            if upload['offset'] != upload['size_bytes'] or (current['sha256'] if current else None) != upload['expected_sha256']:
                raise MediaError('conflict')
            self._quota(index, upload['size_bytes'], upload['file_id'])
            blob = uuid.uuid4().hex
            self._copy_blob(directory, 'part_' + req['upload_id'], blob, upload['size_bytes'], upload['sha256'])
            item = {key: upload[key] for key in ('file_id', 'size_bytes', 'sha256', 'filename', 'content_type')}
            item.update(blob=blob, created_at=now, origin=None)
            index['files'][upload['file_id']] = item
            del index['uploads'][req['upload_id']]
            return {'ok': True, 'file': self._metadata(item)}
        if op in {'read', 'public_read'}:
            if op == 'public_read':
                link = self._link(index, req, epoch)
                if req['download_id'] not in link['downloads']:
                    if len(link['downloads']) >= link['max_downloads']:
                        raise MediaError('quota')
                    link['downloads'].append(req['download_id'])
                item = index['files'].get(link['file_id'])
                if item is None or item['sha256'] != link['sha256'] or req['sha256'] != item['sha256']:
                    raise MediaError('conflict')
            else:
                item = self._file(index, req)
            if req['offset'] > item['size_bytes']:
                raise MediaError('conflict')
            fd = self._open(directory, 'blob_' + item['blob'])
            with os.fdopen(fd, 'rb') as stream:
                if os.fstat(stream.fileno()).st_size != item['size_bytes']:
                    raise MediaError('recovery_required')
                stream.seek(req['offset'])
                data = stream.read(min(req['length'], item['size_bytes'] - req['offset']))
            return {'ok': True, 'offset': req['offset'], 'sha256': item['sha256'], 'chunk_sha256': hashlib.sha256(data).hexdigest(), 'content_base64': base64.b64encode(data).decode('ascii')}
        if op == 'delete':
            item = self._file(index, req)
            if req['expected_sha256'] != item['sha256']:
                raise MediaError('conflict')
            del index['files'][req['file_id']]
            return {'ok': True}
        if op == 'cleanup':
            return {'ok': True, 'active_uploads': len(index['uploads']), 'staging_bytes': sum(i['size_bytes'] for i in index['uploads'].values())}
        if op == 'link':
            item = self._file(index, req)
            if len(index['links']) >= HISTORY_LIMIT:
                raise MediaError('quota')
            identifier = uuid.uuid4().hex
            index['links'][identifier] = {'file_id': item['file_id'], 'sha256': item['sha256'], 'owner': owner, 'epoch': epoch,
                'token_hash': hashlib.sha256(req['token'].encode()).hexdigest(), 'created_at': now, 'expires_at': now + req['ttl_seconds'],
                'revoked': False, 'downloads': [], 'max_downloads': req['max_downloads']}
            return {'ok': True, 'link_id': identifier, 'expires_at': now + req['ttl_seconds']}
        if op == 'unlink':
            link = index['links'].get(req['link_id'])
            if link is None or link['owner'] != owner:
                raise MediaError('denied')
            link['revoked'] = True
            return {'ok': True}
        if op == 'public_stat':
            link = self._link(index, req, epoch)
            if len(link['downloads']) >= link['max_downloads']:
                raise MediaError('quota')
            item = index['files'].get(link['file_id'])
            if item is None or item['sha256'] != link['sha256']:
                raise MediaError('not_found')
            return {'ok': True, 'file': self._metadata(item)}
        if op == 'job':
            job = index['jobs'].get(req['job_id'])
            if job is None or job['owner'] != owner:
                raise MediaError('not_found')
            if job['status'] == 'running':
                # The serial executor cannot observe an active transform while
                # it owns the namespace lock. A surviving running record is an
                # interrupted worker, never permission to repeat the effect.
                job['status'] = 'execution_unconfirmed'
            return {'ok': True, 'job': {k: v for k, v in job.items() if k != 'owner'}}
        if op == 'transform':
            return self._transform(directory, index, req, owner, now)
        raise MediaError('denied')

    @staticmethod
    def _link(index, req, epoch):
        import hmac
        link = index['links'].get(req['link_id'])
        if link is None or link['revoked'] or link['epoch'] != epoch or not hmac.compare_digest(link['token_hash'], hashlib.sha256(req['token'].encode()).hexdigest()):
            raise MediaError('denied')
        return link

    def _transform(self, directory, index, req, owner, now):
        from three_mm_application_sdk.media_provider import transform_image
        item = self._file(index, req)
        if req['output_id'] in index['files']:
            raise MediaError('conflict')
        self._quota(index, 0, req['output_id'])
        if len(index['jobs']) >= HISTORY_LIMIT:
            raise MediaError('quota')
        identifier = req['request_id']
        if identifier in index['jobs']:
            raise MediaError('conflict')
        job = {'job_id': identifier, 'owner': owner, 'status': 'running', 'source': {'file_id': item['file_id'], 'sha256': item['sha256']},
               'output_id': req['output_id'], 'provider': 'pillow_image_v1', 'parameters': {k: req[k] for k in ('width', 'height', 'format')}, 'created_at': now}
        index['jobs'][identifier] = job
        self._save(directory, index)  # Crash leaves an explicit uncertain job, never replayed.
        temporary = 'part_' + uuid.uuid4().hex
        source_fd = self._open(directory, 'blob_' + item['blob'])
        output_fd = self._open(directory, temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        try:
            if item['size_bytes'] > min(self.declaration.max_file_bytes, 16 * 1024 * 1024):
                raise MediaError('quota')
            (self.provider or transform_image)(source_fd, output_fd, req, min(self.declaration.max_file_bytes, 16 * 1024 * 1024))
            os.fsync(output_fd)
        except (RuntimeError, OSError, ValueError) as error:
            job.update(status='failed', error_code='provider_unavailable' if str(error) == 'provider_unavailable' else 'transform_failed')
            return {'ok': True, 'job': {k: v for k, v in job.items() if k != 'owner'}}
        finally:
            os.close(source_fd)
            os.close(output_fd)
        fd = self._open(directory, temporary)
        digest, size = hashlib.sha256(), 0
        with os.fdopen(fd, 'rb') as stream:
            while chunk := stream.read(CHUNK_BYTES):
                size += len(chunk)
                digest.update(chunk)
        try:
            self._quota(index, size, req['output_id'])
        except MediaError:
            job.update(status='failed', error_code='quota')
            return {'ok': True, 'job': {k: v for k, v in job.items() if k != 'owner'}}
        blob = uuid.uuid4().hex
        os.rename(temporary, 'blob_' + blob, src_dir_fd=directory, dst_dir_fd=directory)
        mime = 'image/' + req['format']
        derivative = {'file_id': req['output_id'], 'size_bytes': size, 'sha256': digest.hexdigest(), 'filename': req['output_id'] + '.' + req['format'],
                      'content_type': mime, 'created_at': now, 'origin': {'file_id': item['file_id'], 'sha256': item['sha256'], 'job_id': identifier}, 'blob': blob}
        index['files'][req['output_id']] = derivative
        job.update(status='succeeded', file=self._metadata(derivative))
        return {'ok': True, 'job': {k: v for k, v in job.items() if k != 'owner'}}
