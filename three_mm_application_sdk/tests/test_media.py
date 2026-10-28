import base64
import hashlib
import io
import json
import os
import uuid

import pytest
from three_mm_protocol.application_extension import ApplicationPrivateFilesV2
from three_mm_application_sdk.media_store import ApplicationMediaStore
from three_mm_application_sdk.media_wire import CHUNK_BYTES, parse_media_request

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='POSIX descriptor-pinned store')


def declaration(**changes):
    return ApplicationPrivateFilesV2.model_validate(dict(file_contract_version=2, namespace='private_files', mode='read_write',
        max_file_bytes=2*1024*1024, max_total_bytes=4*1024*1024, max_files=10, max_uploads=2,
        max_staging_bytes=4*1024*1024, upload_ttl_seconds=60, public_links=True, media_transforms=True, **changes))


def request(op, **fields):
    return dict(file_request_version=2, request_id=uuid.uuid4().hex, operation=op, **fields)


@pytest.fixture
def store(tmp_path):
    return ApplicationMediaStore(tmp_path, declaration())


def execute(store, op, *, actor='owner', epoch='a'*64, **fields):
    return store.execute(request(op, **fields), actor, epoch)


def upload(store, content=b'hello', file_id='sample', expected=None):
    digest = hashlib.sha256(content).hexdigest()
    value = execute(store, 'begin', file_id=file_id, size_bytes=len(content), sha256=digest, filename='example.txt', content_type='text/plain', expected_sha256=expected)
    assert value['ok'], value
    identity = value['upload_id']
    for offset in range(0, len(content), CHUNK_BYTES):
        result = execute(store, 'append', upload_id=identity, offset=offset, content_base64=base64.b64encode(content[offset:offset+CHUNK_BYTES]).decode())
        assert result['ok'], result
    result = execute(store, 'finalize', upload_id=identity)
    assert result['ok'], result
    return result['file']


def test_large_stream_resume_restart_and_atomic_visibility(store):
    content = bytes(range(256)) * 6000  # > 1 MiB; never a whole RPC payload.
    begin = execute(store, 'begin', file_id='sample', size_bytes=len(content), sha256=hashlib.sha256(content).hexdigest(),
        filename='данни.bin', content_type='application/octet-stream', expected_sha256=None)
    identity = begin['upload_id']
    chunk = base64.b64encode(content[:CHUNK_BYTES]).decode()
    assert execute(store, 'append', upload_id=identity, offset=0, content_base64=chunk)['offset'] == CHUNK_BYTES
    # Lost acknowledgement and worker restart: resume verifies persisted offset.
    store = ApplicationMediaStore(store.storage.data_dir, store.declaration)
    assert execute(store, 'append', upload_id=identity, offset=0, content_base64=chunk)['offset'] == CHUNK_BYTES
    assert execute(store, 'list', after='')['items'] == []
    assert execute(store, 'upload_status', upload_id=identity, actor='other')['error_code'] == 'denied'
    for offset in range(CHUNK_BYTES, len(content), CHUNK_BYTES):
        assert execute(store, 'append', upload_id=identity, offset=offset, content_base64=base64.b64encode(content[offset:offset+CHUNK_BYTES]).decode())['ok']
    final = request('finalize', upload_id=identity)
    metadata = store.execute(final, 'owner', 'a'*64)['file']
    assert store.execute(final, 'owner', 'a'*64)['file'] == metadata
    result = bytearray()
    for offset in range(0, len(content), CHUNK_BYTES):
        result.extend(base64.b64decode(execute(store, 'read', file_id='sample', sha256=metadata['sha256'], offset=offset, length=CHUNK_BYTES)['content_base64']))
    assert result == content


def test_bad_checksum_never_replaces_old_file(store):
    previous = upload(store)
    value = execute(store, 'begin', file_id='sample', size_bytes=3, sha256='b'*64, filename='new.txt', content_type='text/plain', expected_sha256=previous['sha256'])
    execute(store, 'append', upload_id=value['upload_id'], offset=0, content_base64=base64.b64encode(b'bad').decode())
    assert execute(store, 'finalize', upload_id=value['upload_id'])['error_code'] == 'checksum'
    assert execute(store, 'stat', file_id='sample')['file'] == previous


def test_interrupted_final_manifest_keeps_previous_file_and_resumable_upload(store, monkeypatch):
    previous=upload(store)
    data=b'new'
    begin=execute(store,'begin',file_id='sample',size_bytes=3,sha256=hashlib.sha256(data).hexdigest(),filename='new',content_type='text/plain',expected_sha256=previous['sha256'])
    execute(store,'append',upload_id=begin['upload_id'],offset=0,content_base64=base64.b64encode(data).decode())
    original=store._save
    def crash(directory,index):
        if index['files']['sample']['sha256']!=previous['sha256']:raise OSError('interrupted before atomic manifest')
        original(directory,index)
    monkeypatch.setattr(store,'_save',crash)
    with pytest.raises(RuntimeError):execute(store,'finalize',upload_id=begin['upload_id'])
    restarted=ApplicationMediaStore(store.storage.data_dir,store.declaration)
    assert execute(restarted,'stat',file_id='sample')['file']==previous
    assert execute(restarted,'upload_status',upload_id=begin['upload_id'])['upload']['offset']==3


def test_missing_manifest_never_collects_committed_blobs(store):
    upload(store)
    namespace=store.storage.data_dir/'sdk-media'
    (namespace/'index.json').unlink()
    with pytest.raises(ValueError):execute(store,'list',after='')
    assert list(namespace.glob('blob_*'))


def test_concurrent_cas_and_reservations(store):
    first = execute(store, 'begin', file_id='sample', size_bytes=1, sha256=hashlib.sha256(b'a').hexdigest(), filename='a', content_type='text/plain', expected_sha256=None)
    second = execute(store, 'begin', file_id='sample', size_bytes=1, sha256=hashlib.sha256(b'b').hexdigest(), filename='b', content_type='text/plain', expected_sha256=None)
    assert execute(store, 'begin', file_id='third', size_bytes=1, sha256='a'*64, filename='c', content_type='text/plain', expected_sha256=None)['error_code'] == 'quota'
    for value, data in ((first, b'a'), (second, b'b')):
        execute(store, 'append', upload_id=value['upload_id'], offset=0, content_base64=base64.b64encode(data).decode())
    assert execute(store, 'finalize', upload_id=first['upload_id'])['ok']
    assert execute(store, 'finalize', upload_id=second['upload_id'])['error_code'] == 'conflict'


def test_interrupted_tail_expiry_and_cancel(store):
    now = [100]
    store.clock = lambda: now[0]
    value = execute(store, 'begin', file_id='sample', size_bytes=4, sha256='a'*64, filename='a', content_type='text/plain', expected_sha256=None)
    path = store.storage.data_dir / 'sdk-media' / ('part_' + value['upload_id'])
    path.write_bytes(b'unconfirmed tail')
    assert execute(store, 'append', upload_id=value['upload_id'], offset=0, content_base64='YWI=')['offset'] == 2
    assert path.read_bytes() == b'ab'
    now[0] = 160
    assert execute(store, 'cleanup')['active_uploads'] == 0
    assert not path.exists()
    assert execute(store, 'upload_status', upload_id=value['upload_id'])['error_code'] == 'expired'


@pytest.mark.parametrize('kind', ['symlink', 'hardlink', 'unknown'])
def test_namespace_refuses_unsafe_entries(store, tmp_path, kind):
    upload(store)
    namespace = tmp_path / 'sdk-media'
    original = next(namespace.glob('blob_*'))
    if kind == 'unknown':
        (namespace / 'arbitrary').write_bytes(b'x')
    elif kind == 'symlink':
        (namespace / ('part_' + 'f'*32)).symlink_to(original)
    else:
        os.link(original, namespace / ('part_' + 'f'*32))
    with pytest.raises((ValueError, RuntimeError)):
        execute(store, 'list', after='')


def test_link_token_expiry_revision_revoke_and_limit(store):
    item = upload(store)
    value = execute(store, 'link', file_id='sample', sha256=item['sha256'], token='b'*64, ttl_seconds=30, max_downloads=1)
    fields = {'link_id': value['link_id'], 'token': 'b'*64}
    assert execute(store, 'public_stat', **fields)['ok']
    assert execute(store, 'public_stat', **fields, epoch='c'*64)['error_code'] == 'denied'
    assert execute(store, 'public_stat', link_id=value['link_id'], token='c'*64)['error_code'] == 'denied'
    read = dict(**fields, sha256=item['sha256'], offset=0, length=10)
    assert execute(store, 'public_read', **read, download_id='1'*32)['ok']
    assert execute(store, 'public_read', **read, download_id='2'*32)['error_code'] == 'quota'
    assert execute(store, 'unlink', link_id=value['link_id'], actor='other')['error_code'] == 'denied'
    assert execute(store, 'unlink', link_id=value['link_id'])['ok']
    assert execute(store, 'public_stat', **fields)['error_code'] == 'denied'


def test_expired_link_cannot_revive_after_clock_rollback(store):
    now = [100]
    store.clock = lambda: now[0]
    item = upload(store)
    link = execute(store, 'link', file_id='sample', sha256=item['sha256'], token='b'*64, ttl_seconds=10, max_downloads=1)
    now[0] = 110
    assert execute(store, 'public_stat', link_id=link['link_id'], token='b'*64)['error_code'] == 'denied'
    now[0] = 105
    assert execute(store, 'public_stat', link_id=link['link_id'], token='b'*64)['error_code'] == 'denied'


def test_media_provider_real_image_original_and_derivative(store):
    Image = pytest.importorskip('PIL.Image', reason='Optional image-provider dependency')
    stream = io.BytesIO()
    Image.new('RGB', (40, 20), 'red').save(stream, format='PNG')
    item = upload(store, stream.getvalue())
    job = execute(store, 'transform', file_id='sample', sha256=item['sha256'], output_id='thumbnail', width=10, height=10, format='jpeg')['job']
    assert job['status'] == 'succeeded', job
    assert job['file']['origin']['sha256'] == item['sha256']
    assert execute(store, 'stat', file_id='sample')['file'] == item
    result = execute(store, 'read', file_id='thumbnail', sha256=job['file']['sha256'], offset=0, length=CHUNK_BYTES)
    with Image.open(io.BytesIO(base64.b64decode(result['content_base64']))) as image:
        assert image.size == (10, 5) and image.format == 'JPEG'


@pytest.mark.parametrize('unavailable', [False, True])
def test_failed_provider_does_not_break_files(store, unavailable):
    item = upload(store, b'not an image')
    if unavailable:
        def provider(*_):
            raise RuntimeError('provider_unavailable')
        store.provider = provider
    result = execute(store, 'transform', file_id='sample', sha256=item['sha256'], output_id='thumbnail', width=10, height=10, format='png')
    assert result['job']['status'] == 'failed'
    assert execute(store, 'stat', file_id='sample')['file'] == item


@pytest.mark.parametrize('changes', [{'file_request_version': True}, {'offset': True}, {'offset': 0.5}, {'length': CHUNK_BYTES+1}, {'file_id': '../escape'}])
def test_strict_wire(changes):
    value = request('read', file_id='sample', sha256='a'*64, offset=0, length=1)
    value.update(changes)
    with pytest.raises(ValueError):
        parse_media_request(value)
