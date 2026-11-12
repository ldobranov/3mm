"""Exercise the actual selected native interpreter/vendor builder, not a shell double."""
import hashlib
import os
from pathlib import Path
import pytest
from components.system_runtime import component_updates as web
from deployment import application_host_component as hosts, service_component as services

pytestmark=pytest.mark.skipif(os.name!='posix',reason='Native Linux interpreter and vendor closure')
SOURCE=Path(__file__).resolve().parents[3]


@pytest.mark.parametrize('kind',['agent','application_host'])
def test_preparation_reuses_selected_native_vendor_without_core_dependencies(tmp_path,monkeypatch,kind):
    if kind=='agent':
        blob, metadata=services.build_component(SOURCE,'agent')
        store=services.ServiceStore('agent',tmp_path/'component',tmp_path/'journal')
    else:
        blob, metadata=hosts.build_component(SOURCE)
        store=hosts.HostStore(tmp_path/'component',tmp_path/'journal',tmp_path/'releases')
    build=store.bootstrap(blob,hashlib.sha256(blob).hexdigest())
    adapter=web.InstalledComponent.__new__(web.InstalledComponent)
    adapter.component=kind;adapter.store=store
    adapter.pointer=lambda name:store.target(name)
    checked=[]
    # Only the source ownership boundary is doubled: this checkout is not an
    # installed root-owned release. Native validation and subprocess stay real.
    def owned_source(source,names):
        assert source==SOURCE and all((source/name).is_file() for name in names)
        checked.extend(names)
    monkeypatch.setattr(web,'_protected_sources',owned_source)
    artifact=tmp_path/'candidate.tar'
    bytecode_before=set(store.releases.rglob('*.pyc'))
    adapter.build(SOURCE,artifact)
    result=artifact.read_bytes()
    assert result==blob and adapter.validate(result,hashlib.sha256(result).hexdigest())['build_id']==build
    assert checked and store.target('current')==metadata['build_id']
    assert set(store.releases.rglob('*.pyc'))==bytecode_before


@pytest.mark.parametrize('damage',['writable','symlink','oversize','hardlink'])
def test_metadata_reads_refuse_unsafe_files(tmp_path,damage):
    path=tmp_path/'metadata.json';path.write_text('{"build_id":"safe"}')
    if damage=='writable':path.chmod(0o666)
    elif damage=='symlink':
        original=tmp_path/'original';path.rename(original);path.symlink_to(original)
    elif damage=='oversize':path.write_bytes(b'x'*1025)
    else:os.link(path,tmp_path/'second-link')
    with pytest.raises((ValueError,OSError)):web._json_file(path,uid=os.getuid(),maximum=1024)
