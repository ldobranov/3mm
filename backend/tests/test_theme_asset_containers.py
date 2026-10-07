"""WOFF2 alignment compatibility must not allow hidden or unbounded data."""

import struct

import pytest

from backend.services.theme_assets import _woff2


def container(stream_length, padding=b""):
    # One untransformed cmap table; container validation does not decode Brotli.
    directory = b"\x00\x0c"
    stream = b"x" * stream_length
    header = struct.pack(
        ">4sIIHHIIHHIIIII", b"wOF2", 0x00010000,
        48 + len(directory) + len(stream) + len(padding),
        1, 0, 40, len(stream), 1, 0, 0, 0, 0, 0, 0,
    )
    return header + directory + stream + padding


@pytest.mark.parametrize("length", [1, 2, 3, 4])
def test_woff2_accepts_unpadded_or_exact_zero_alignment(length):
    _woff2(container(length))
    _woff2(container(length, b"\0" * (-(50 + length) % 4)))


@pytest.mark.parametrize("padding", [b"\1", b"xx", b"\0\1\0", b"\0" * 4, b"\0" * 5, b"\0"])
def test_woff2_rejects_payload_excess_or_wrong_alignment(padding):
    with pytest.raises(ValueError):
        _woff2(container(4, padding))


def test_woff2_rejects_truncated_stream_and_metadata_even_with_alignment():
    data = bytearray(container(4, b"\0\0"))
    struct.pack_into(">I", data, 20, 100)
    with pytest.raises(ValueError):
        _woff2(bytes(data))
    data = bytearray(container(4, b"\0\0"))
    struct.pack_into(">I", data, 28, 4)
    with pytest.raises(ValueError):
        _woff2(bytes(data))
