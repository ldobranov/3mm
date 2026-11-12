"""New WP4 executors/build provenance must be present before target activation."""

import json
from pathlib import Path

import pytest

from deployment.deployment_contract import DeploymentContractError, validate_deployment_contract


WP4_FILES = (
    'backend/applications/checkpoints.py',
    'backend/applications/runtime/identity.py',
    'backend/applications/runtime/peers.py',
    'backend/applications/runtime/status.py',
    'backend/artifacts/compiled_ui.py',
    'backend/artifacts/provenance.py',
    'backend/installation/peer_listing.py',
    'backend/installation/peer_read_sources.py',
    'backend/installation/status_binding.py',
    'frontend/compiler/compile-ui-extension.mjs',
    'packages/protocol/application_peer_read.py',
    'packages/protocol/__init__.py',
    'packages/protocol/theme_design_defaults.json',
    'backend/system/updates/components_api.py',
    'backend/system/updates/components.py',
    'components/system_runtime/component_updates.py',
)


@pytest.mark.parametrize('missing', WP4_FILES)
def test_incomplete_wp4_release_is_rejected_by_target_contract(missing):
    root = Path(__file__).resolve().parents[2]
    raw = (root / 'deployment/deployment-contract.json').read_bytes()
    required = set(json.loads(raw)['required_files'])
    assert set(WP4_FILES) <= required
    assert all((root / item).is_file() for item in WP4_FILES)
    assert validate_deployment_contract(raw, required).schema_version == 2
    with pytest.raises(DeploymentContractError, match='incomplete'):
        validate_deployment_contract(raw, required - {missing})
