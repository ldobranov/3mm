"""Metadata number exceptions cannot become operational JSON permissions."""
import copy
import json

import pytest

from backend.services import application_authority_context as context
from backend.tests.test_application_authority_context import context as baseline, selection
from three_mm_protocol.application_extension import ApplicationOperationV1


BIG = 2**63 - 1


def schema():
    return {'type':'object', 'properties':{'ticks':{
        'type':'integer', 'minimum':0, 'maximum':BIG, 'enum':[BIG, 0]}},
        'required':['ticks'], 'additionalProperties':False}


def operation():
    return {'operation_id':'receive', 'kind':'command', 'audiences':['internal'],
        'idempotency':'required', 'audit':'redacted', 'input_schema':schema(),
        'output_schema':{'type':'object','properties':{},'required':[], 'additionalProperties':False}}


class Operational(context.ContextModel):
    # Names alone are not metadata: these are unconstrained operational maps.
    configuration: dict
    request: dict
    input_schema: dict


def test_default_plain_json_and_canonicalizer_do_not_recognize_schema_names():
    value = {'configuration':{'input_schema':schema()}, 'contract':schema(), 'maximum':BIG}
    with pytest.raises(ValueError): context._bounded_json(value)
    with pytest.raises(ValueError): context._canonical_bytes(value)


def test_explicit_schema_slot_preserves_integer_bound_and_its_enum_without_coercion():
    value = {'schema':schema(), 'revision':1}
    bounded = context._bounded_json(value, schema_paths=(('schema',),))
    assert bounded == value and type(bounded['schema']['properties']['ticks']['maximum']) is int
    encoded = context._canonical_bytes(value, schema_paths=(('schema',),))
    assert ('["int","'+str(BIG)+'"]').encode() in encoded
    changed = copy.deepcopy(value); changed['schema']['properties']['ticks']['enum'] = [0, BIG]
    assert context._canonical_bytes(changed, schema_paths=(('schema',),)) != encoded
    # Ordinary arrays keep order; metadata support does not normalize all arrays.


@pytest.mark.parametrize('input_mode', ['dict','json','typed'])
def test_typed_operation_slots_roundtrip_large_bounds_and_exact_types(input_mode):
    value = operation()
    supplied = json.dumps(value) if input_mode == 'json' else (
        ApplicationOperationV1.model_validate(value) if input_mode == 'typed' else value)
    result = context._parse(ApplicationOperationV1, supplied)
    actual = result.input_schema['properties']['ticks']
    assert actual['maximum'] == BIG and type(actual['maximum']) is int
    assert actual['enum'] == [BIG, 0]
    assert context._parse(ApplicationOperationV1, result).input_schema == result.input_schema


def test_untyped_operational_models_cannot_acquire_schema_paths_by_spoofed_keys():
    value = {'configuration':{'input_schema':schema()}, 'request':{'contract':schema()}, 'input_schema':schema()}
    assert not context._schema_paths(Operational, value)
    with pytest.raises(ValueError): context._parse(Operational, value)
    forged = Operational.model_construct(**value)
    with pytest.raises(ValueError): context._parse(Operational, forged)


@pytest.mark.parametrize('part', ['configuration','request'])
def test_explicit_schema_slot_does_not_widen_an_unrelated_operational_map(part):
    value = {'declaration':operation(), part:{'input_schema':schema()}}
    with pytest.raises(ValueError):
        context._bounded_json(value, schema_paths=(('declaration','input_schema'),))


def test_schema_exception_does_not_widen_other_numbers_or_bad_schema_keywords():
    value = {'schema':schema(), 'revision':BIG}
    with pytest.raises(ValueError): context._bounded_json(value, schema_paths=(('schema',),))
    invalid = operation()
    invalid['input_schema']['properties']['ticks'] = {'type':'string','maxLength':BIG}
    with pytest.raises(ValueError): context._parse(ApplicationOperationV1, invalid)
    invalid = operation(); invalid['timeout_seconds'] = BIG
    with pytest.raises(ValueError): context._parse(ApplicationOperationV1, invalid)


def test_context_uses_typed_schema_slots_but_keeps_revision_and_clock_limits():
    value = baseline()
    prop = value['commands'][0]['declaration']['arguments_schema']['properties']['duration_ms']
    prop.update(maximum=BIG, enum=[BIG, 1])
    reviewed = context.review_authority_context(value, selection(), now_ms=150_000)
    assert reviewed.reviewable and reviewed.context_fingerprint
    parsed = context._parse(context.AuthorityReviewContextV1, value)
    assert context._parse(context.AuthorityReviewContextV1, parsed).commands[0].declaration.arguments_schema == parsed.commands[0].declaration.arguments_schema
    for path in [('policy','adapter_revision'), ('issued_at_ms',), ('expires_at_ms',)]:
        invalid = copy.deepcopy(value)
        owner = invalid
        for key in path[:-1]: owner = owner[key]
        owner[path[-1]] = BIG
        refused = context.review_authority_context(invalid, selection(), now_ms=150_000)
        assert not refused.reviewable


def test_existing_fingerprint_and_primitive_type_tags_are_unchanged():
    reviewed = context.review_authority_context(baseline(), selection(), now_ms=150_000)
    assert reviewed.context_fingerprint == 'cd88d66bdd44cdbba482e40d19f1d8d39bef5014a6452ad9e65e5681037b8c59'
    assert context._canonical_bytes(1) != context._canonical_bytes(1.0) != context._canonical_bytes(True)
    assert context._canonical_bytes(0.0) != context._canonical_bytes(-0.0)
    assert context._canonical_bytes({'x':1,'y':2}) == context._canonical_bytes({'y':2,'x':1})


@pytest.mark.parametrize('value', [float('inf'), float('-inf'), float('nan'), 2**63, -(2**63)-1])
def test_metadata_exceptions_still_have_finite_bounded_numeric_leaves(value):
    data = {'schema':schema()}
    data['schema']['properties']['ticks']['maximum'] = value
    with pytest.raises(ValueError): context._bounded_json(data, schema_paths=(('schema',),))


def test_schema_signed_integer_lower_endpoint_is_metadata_not_an_operational_value():
    data = {'schema':schema()}
    prop = data['schema']['properties']['ticks']
    prop.update(minimum=-(2**63), enum=[-(2**63), BIG])
    assert context._bounded_json(data, schema_paths=(('schema',),)) == data
    with pytest.raises(ValueError): context._bounded_json(-(2**63))
    with pytest.raises(ValueError): context._canonical_bytes(-(2**63))


def test_schema_path_collection_cannot_allocate_unbounded_event_or_enum_paths(monkeypatch):
    from three_mm_protocol.capability_contracts import CapabilityContractV1
    monkeypatch.setattr(context, 'MAX_JSON_NODES', 12)
    with pytest.raises(ValueError):
        context._schema_paths(CapabilityContractV1, {'events':{
            'event'+str(index):schema() for index in range(13)}})
    with pytest.raises(ValueError):
        context._bounded_json({'schema':{'type':'integer','enum':list(range(13))}},
            schema_paths=(('schema',),))


@pytest.mark.parametrize('kind', ['plan','grant'])
def test_sealed_review_slots_survive_json_roundtrip_without_widening_request_maps(kind):
    review = baseline()
    review['commands'][0]['declaration']['arguments_schema'] = schema()
    envelope = {'version':1, 'kind':kind, 'record_id':'r', 'installation_id':1,
        'revision':'r1', 'state':'prepared', 'data':{'context':review}}
    decoded = json.loads(json.dumps(envelope))
    paths = context._record_schema_paths(kind, decoded)
    assert paths and context._bounded_json(decoded, schema_paths=paths) == envelope
    signed = {'kind':kind, 'key_id':'key', 'payload':decoded}
    assert context._canonical_bytes(signed,
        schema_paths=context._record_schema_paths(kind, decoded, ('payload',)))
    assert not context._record_schema_paths('action', decoded)
    with pytest.raises(ValueError):
        context._bounded_json(decoded, schema_paths=context._record_schema_paths('action', decoded))
    decoded['data']['request'] = {'context':review, 'input_schema':schema()}
    with pytest.raises(ValueError):
        context._bounded_json(decoded, schema_paths=context._record_schema_paths(kind, decoded))


def test_all_schema_and_ordinary_paths_share_the_same_byte_node_and_depth_budgets():
    for extra in ({'bulk':['x'*4096]*40}, {'bulk':[0]*context.MAX_JSON_NODES}):
        with pytest.raises(ValueError):
            context._bounded_json({'schema':schema(), **extra}, schema_paths=(('schema',),))
    deep = 0
    for _ in range(context.MAX_JSON_DEPTH+1): deep = [deep]
    with pytest.raises(ValueError):
        context._bounded_json({'schema':schema(), 'bulk':deep}, schema_paths=(('schema',),))
