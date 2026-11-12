"""Presentation checks with disposable data; no setup/network changes."""
from copy import deepcopy
import json
from pathlib import Path
import re

import pytest
from fastapi.testclient import TestClient

from components.setup.config import SetupSettings
from components.setup.main import create_app
from components.setup.product import FALLBACK, load_product_metadata
from packages.provisioning import MemoryProvisioningStore
from packages.provisioning.mock_network import MockNetworkAdapter


def metadata():
    path = Path(__file__).resolve().parents[3] / 'config_templates/product.json'
    return json.loads(path.read_text(encoding='utf-8'))


def test_alternate_brand_renders_text_and_safe_script_data_without_setup_effects(tmp_path):
    product = metadata()
    hostile = '</script><script>alert("not executable")</script> & <img src=x>'
    product.update(name='Example', display_name='Example console')
    product['setup']['page_title'] = 'Example </title><script>alert(1)</script>'
    product['setup']['header'] = hostile
    product['setup']['labels']['bg']['title'] = hostile
    path = tmp_path/'product.json'
    path.write_text(json.dumps(product), encoding='utf-8')
    network, store = MockNetworkAdapter(), MemoryProvisioningStore()
    app = create_app(network, store, SetupSettings(data_dir=tmp_path/'state'), product_path=path)
    with TestClient(app) as client:
        response = client.get('/setup')
        assert response.status_code == 200
        assert 'Example &lt;/title&gt;&lt;script&gt;' in response.text
        assert '<header>&lt;/script&gt;' in response.text
        assert response.text.count('<script>') == 1
        assert '<img src=x>' not in response.text
        embedded = re.search(r'const productLabels = (.+);', response.text).group(1)
        assert '<' not in embedded and '&' not in embedded
        assert json.loads(embedded)['bg']['title'] == hostile
        assert client.get('/ready').json() == {'status': 'ready'}
        assert network.calls == [] and store.load() is None


@pytest.mark.parametrize('contents', [None, b'{', b'[]', b'{}', b' ' * 16385,
                                     b'[' * 1100 + b'0' + b']' * 1100])
def test_missing_or_malformed_product_does_not_disable_setup(tmp_path, contents):
    path = tmp_path/'product.json'
    if contents is not None:
        path.write_bytes(contents)
    product = load_product_metadata(path)
    assert product == FALLBACK
    product['setup']['labels']['en']['title'] = 'Local mutation'
    assert load_product_metadata(path) == FALLBACK
    app = create_app(MockNetworkAdapter(), MemoryProvisioningStore(),
                     SetupSettings(data_dir=tmp_path/'state'), product_path=path)
    with TestClient(app) as client:
        assert client.get('/setup').status_code == 200
        assert '<title>Device setup</title>' in client.get('/setup').text
        assert client.get('/ready').status_code == 200


@pytest.mark.parametrize('change', [
    {'schema_version': True}, {'schema_version': 2}, {'favicon_url': '//foreign.test/icon'},
    {'favicon_url': 'javascript:alert(1)'}, {'default_logo_url': '/../private'},
    {'name': 'bad\nname'}, {'name': 'bad\ud800name'}, {'setup': None},
])
def test_unsupported_metadata_and_unsafe_assets_use_neutral_defaults(tmp_path, change):
    product = {**deepcopy(metadata()), **change}
    path = tmp_path/'product.json'
    path.write_text(json.dumps(product), encoding='utf-8')
    assert load_product_metadata(path) == FALLBACK
