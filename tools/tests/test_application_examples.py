"""Source discovery never imports a sample or implies its tests passed."""
import hashlib
import json
import sys

import pytest

from tools import application_examples as examples, extension_dev


def test_full_checkout_lists_only_present_and_matches_exact_originals():
    from tools.checks import AUTHORING_GUIDES, select_checks
    from tools.deploy import validation_inputs
    simple = examples.example_catalog()
    assert simple['tests_run'] is False and simple['installation'] == 'not_requested'
    ids = [row['id'] for row in simple['examples']]
    guides = {row['guide'] for row in simple['examples']}
    assert guides == AUTHORING_GUIDES
    assert set(validation_inputs({k:'example' for k in [*guides, 'docs/unrelated.md']})) == guides
    for guide in guides:
        plan = select_checks([guide])
        assert plan.tooling and not plan.frontend and not plan.python
    assert ids == sorted(set(ids)) and {'starter','inbox','report-task'} <= set(ids)
    for row in simple['examples']:
        assert row['state'] == 'present' and 'source_sha256' not in row
        detail = examples.example_catalog(row['id'])['examples'][0]
        for name in (row['guide'], *row['sources'], *row['test_files']):
            assert detail['source_sha256'][name] == hashlib.sha256((examples.REPOSITORY / name).read_bytes()).hexdigest()


def test_partial_checkout_reports_which_example_is_usable_without_executing_it(tmp_path, monkeypatch):
    monkeypatch.setattr(examples, 'REPOSITORY', tmp_path)
    row = examples.example_catalog('inbox')['examples'][0]
    assert row['state'] == 'incomplete_checkout' and 'source_sha256' not in row
    for path in (row['guide'], *row['sources'], *row['test_files']):
        target = tmp_path / path
        target.parent.mkdir(exist_ok=True, parents=True)
        target.write_bytes(('## '+row['heading']).encode() if path==row['guide'] else b'raise AssertionError("never import")')
    all_rows = examples.example_catalog()['examples']
    assert [r['id'] for r in all_rows if r['state']=='present'] == ['inbox']
    (tmp_path / row['guide']).write_text('## Other topic')
    assert examples.example_catalog('inbox')['examples'][0]['state'] == 'incomplete_checkout'


@pytest.mark.parametrize('selection,expect', [('inbox',0), ('an/arbitrary/input',1)])
def test_examples_cli_uses_no_device_or_credentials(monkeypatch, capsys, selection, expect):
    monkeypatch.setattr(extension_dev.getpass,'getpass',lambda *_:pytest.fail('No credentials'))
    monkeypatch.setattr(extension_dev,'DevelopmentClient',lambda *_:pytest.fail('No remote contact'))
    monkeypatch.setattr(sys,'argv',['extension-dev','examples',selection,'--json'])
    if expect:
        with pytest.raises(SystemExit) as stopped:
            extension_dev.main()
        assert stopped.value.code == expect
        out = capsys.readouterr().out
        assert json.loads(out)['stage']=='examples' and selection not in out
    else:
        extension_dev.main()
        out = json.loads(capsys.readouterr().out)
        assert out['scope']=='authoring_source_only' and out['examples'][0]['id']==selection
