"""Exact pure JSON budget/validation boundaries; never authorization caching."""

import json
import math

import pytest

from backend.applications.authority.context import (
    MAX_CONTEXT_BYTES,
    MAX_INTEGER,
    MAX_JSON_DEPTH,
    MAX_JSON_NODES,
    _bounded_json,
    _canonical_bytes,
)


def encoded_size(value):
    return len(json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":")))


@pytest.mark.parametrize(
    "value",
    [
        None, True, False, 0, -1, MAX_INTEGER, -MAX_INTEGER,
        0.0, -0.0, 1.0, -1.5, 1e-7, 1e-6, 1e15, -1e15,
        5e-324, -5e-324, math.nextafter(float(MAX_INTEGER), 0),
        "", 'quote" and \\ slash /', "\b\f\n\r\t\x00\x1f", "\x7f",
        "български é e\u0301 😀", "\ud7ff\ue000\uffff\U0010ffff", "x" * 4096,
        [None, True, False, 0, -0.0, 1e-7, "é", "😀"],
        {"": 1, 'quote"': "\\", "б": {"😀": (True, False, 1.0)}},
    ],
)
def test_json_budget_matches_the_exact_ascii_json_encoding(value):
    size = encoded_size(value)
    budget = [MAX_JSON_NODES, size]
    result = _bounded_json(value, budget=budget)
    assert budget[1] == 0
    assert encoded_size(result) == size
    with pytest.raises(ValueError, match="Context exceeds limits"):
        _bounded_json(value, budget=[MAX_JSON_NODES, size - 1])


@pytest.mark.parametrize("value", ["\ud800", "\udfff", "a\ud800b", "\ud800\udc00"])
@pytest.mark.parametrize("as_key", [False, True])
def test_surrogate_code_units_remain_invalid_even_when_json_would_escape_them(value, as_key):
    with pytest.raises(ValueError, match="invalid Unicode"):
        _bounded_json({value: "text"} if as_key else value)


def test_signed_64_schema_integer_budget_does_not_widen_operational_numbers():
    value = {
        "type": "integer", "minimum": -(2**63), "maximum": 2**63 - 1,
        "enum": [-(2**63), 2**63 - 1],
    }
    size = encoded_size(value)
    budget = [MAX_JSON_NODES, size]
    assert _bounded_json(value, budget=budget, schema_paths=((),)) == value
    assert budget[1] == 0
    with pytest.raises(ValueError, match="Context exceeds limits"):
        _bounded_json(value, budget=[MAX_JSON_NODES, size - 1], schema_paths=((),))
    for invalid in (-(2**63) - 1, 2**63):
        with pytest.raises(ValueError, match="Context number exceeds limits"):
            _bounded_json({"type": "integer", "minimum": invalid}, schema_paths=((),))
    for operational in (-(2**63), 2**63 - 1, MAX_INTEGER + 1, -(MAX_INTEGER + 1)):
        with pytest.raises(ValueError, match="Context number exceeds limits"):
            _bounded_json(operational)


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), float("-inf"), 1e16])
def test_nonfinite_and_out_of_range_float_are_still_rejected(invalid):
    with pytest.raises(ValueError, match="Context number exceeds limits"):
        _bounded_json(invalid)


def test_budget_preserves_exact_scalar_types_and_negative_zero():
    copied = _bounded_json([True, False, 1, 1.0, 0.0, -0.0])
    assert [type(value) for value in copied] == [bool, bool, int, float, float, float]
    assert math.copysign(1, copied[-1]) == -1
    assert _canonical_bytes(True) != _canonical_bytes(1) != _canonical_bytes(1.0)
    assert _canonical_bytes(0.0) != _canonical_bytes(-0.0)


def test_copy_keeps_the_same_node_and_depth_boundaries():
    value = [0] * (MAX_JSON_NODES - 1)
    budget = [MAX_JSON_NODES, MAX_CONTEXT_BYTES]
    assert _bounded_json(value, budget=budget) == value
    assert budget[0] == 0
    with pytest.raises(ValueError, match="Context structure exceeds limits"):
        _bounded_json(value + [0])

    nested = 0
    for _ in range(MAX_JSON_DEPTH):
        nested = [nested]
    assert _bounded_json(nested) == nested
    with pytest.raises(ValueError, match="Context structure exceeds limits"):
        _bounded_json([nested])
