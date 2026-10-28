import base64
import hashlib
import os

import pytest
from three_mm_application_sdk.media_store import ApplicationMediaStore
from three_mm_application_sdk.tests.test_media import declaration, execute, upload
from three_mm_runtime.application_files_snapshot import capture_private_files, restore_private_files
from three_mm_runtime.tests.test_application_files_snapshot import installed, run_candidate
from three_mm_runtime import application_activation as activation
from three_mm_runtime.tests.test_application_activation import Supervisor

pytestmark=pytest.mark.skipif(os.name!='posix',reason='Descriptor-relative POSIX rollback')


def test_media_rollback_preserves_large_original_upload_progress_and_link_fence(tmp_path):
    data=tmp_path/'data';data.mkdir()
    backup=tmp_path/'rollback';backup.mkdir()
    store=ApplicationMediaStore(data,declaration())
    original=upload(store,b'original'*200000)
    ongoing=execute(store,'begin',file_id='unfinished',size_bytes=4,sha256=hashlib.sha256(b'abcd').hexdigest(),filename='draft',content_type='text/plain',expected_sha256=None)
    execute(store,'append',upload_id=ongoing['upload_id'],offset=0,content_base64='YWI=')
    link=execute(store,'link',file_id='sample',sha256=original['sha256'],token='b'*64,ttl_seconds=60,max_downloads=1)
    capture_private_files(data,backup)
    execute(store,'delete',file_id='sample',expected_sha256=original['sha256'])
    execute(store,'append',upload_id=ongoing['upload_id'],offset=2,content_base64='Y2Q=')
    restore_private_files(data,backup,None,None)
    assert execute(store,'stat',file_id='sample')['file']==original
    assert execute(store,'upload_status',upload_id=ongoing['upload_id'])['upload']['offset']==2
    assert execute(store,'public_stat',link_id=link['link_id'],token='b'*64,epoch='c'*64)['error_code']=='denied'
    assert (backup/'candidate-sdk-media').is_dir()


def test_corrupt_media_preimage_refuses_before_candidate_switch(tmp_path):
    data=tmp_path/'data';data.mkdir()
    backup=tmp_path/'rollback';backup.mkdir()
    store=ApplicationMediaStore(data,declaration())
    original=upload(store)
    capture_private_files(data,backup)
    next((backup/'sdk-media').glob('blob_*')).write_bytes(b'corrupt')
    with pytest.raises(RuntimeError):restore_private_files(data,backup,None,None)
    assert execute(store,'stat',file_id='sample')['file']==original
    assert not (backup/'candidate-sdk-media').exists()


def test_activation_rollback_and_uninstall_retain_media_until_explicit_erasure(installed):
    store=ApplicationMediaStore(installed.data,declaration())
    original=upload(store,b'original'*200000)
    def mutation():
        execute(store,'delete',file_id='sample',expected_sha256=original['sha256'])
    with pytest.raises(activation.ApplicationActivationError,match='previous version was restored'):
        run_candidate(installed,mutation)
    assert execute(store,'stat',file_id='sample')['file']==original
    instance_id=installed.instance.name
    activation.uninstall_application_instance(instance_id,root=installed.options['root'],key_root=installed.options['key_root'],supervisor=Supervisor())
    assert execute(store,'stat',file_id='sample')['file']==original
    activation.erase_application_instance_data(instance_id,root=installed.options['root'],supervisor=Supervisor())
    assert not installed.data.exists()
