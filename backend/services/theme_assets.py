"""Bounded static asset containers. No extraction, executable content or URLs.

WOFF2/WebP codecs are decoded by the browser's font/image sandbox, not by Core.
These checks validate their bounded containers, not arbitrary font glyph tables.
"""

import hashlib
import stat
import struct
import zipfile
import zlib

from three_mm_protocol.theme_extension_v2 import (
    MAX_FONT_BYTES, MAX_IMAGE_BYTES, MAX_IMAGE_DIMENSION, MAX_THEME_ASSET_BYTES,
    ThemeExtensionV2,
)


def _dimensions(width: int, height: int) -> None:
    if not 1 <= width <= MAX_IMAGE_DIMENSION or not 1 <= height <= MAX_IMAGE_DIMENSION:
        raise ValueError("image dimensions exceed theme limits")


def _png(data: bytes) -> None:
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("invalid PNG signature")
    offset, chunks, compressed = 8, [], bytearray()
    width = height = channels = 0
    while offset < len(data):
        if offset + 12 > len(data):
            raise ValueError("truncated PNG")
        size, = struct.unpack_from(">I", data, offset)
        kind = data[offset + 4:offset + 8]
        end = offset + 12 + size
        if end > len(data) or kind not in (b"IHDR", b"IDAT", b"IEND", b"sRGB", b"gAMA", b"pHYs"):
            raise ValueError("unsupported PNG chunk")
        payload = data[offset + 8:end - 4]
        crc, = struct.unpack_from(">I", data, end - 4)
        if zlib.crc32(kind + payload) != crc:
            raise ValueError("invalid PNG checksum")
        if kind == b"IHDR":
            if chunks or size != 13:
                raise ValueError("invalid PNG header")
            width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", payload)
            _dimensions(width, height)
            # A deliberately small logo profile: non-interlaced 8-bit RGB/RGBA.
            if depth != 8 or color not in (2, 6) or compression or filtering or interlace:
                raise ValueError("PNG must be non-interlaced 8-bit RGB or RGBA")
            channels = 3 if color == 2 else 4
        elif not chunks:
            raise ValueError("PNG header is missing")
        elif kind == b"IDAT":
            if b"IEND" in chunks or (b"IDAT" in chunks and chunks[-1] != b"IDAT"):
                raise ValueError("non-contiguous PNG image data")
            compressed.extend(payload)
        elif kind == b"IEND":
            if size or end != len(data) or b"IDAT" not in chunks:
                raise ValueError("invalid PNG end")
        chunks.append(kind)
        offset = end
    if not chunks or chunks[-1] != b"IEND":
        raise ValueError("PNG end is missing")
    expected = (width * channels + 1) * height
    decoder = zlib.decompressobj()
    pixels = decoder.decompress(compressed, expected + 1)
    if len(pixels) != expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise ValueError("PNG expanded data exceeds its declared dimensions")
    if any(pixels[row * (width * channels + 1)] > 4 for row in range(height)):
        raise ValueError("invalid PNG scanline filter")


def _webp(data: bytes) -> None:
    if len(data) < 20 or data[:4] != b"RIFF" or data[8:12] != b"WEBP" or int.from_bytes(data[4:8], "little") + 8 != len(data):
        raise ValueError("invalid WebP container")
    offset, image_count, canvas = 12, 0, None
    while offset < len(data):
        if offset + 8 > len(data):
            raise ValueError("truncated WebP chunk")
        kind, size = data[offset:offset + 4], int.from_bytes(data[offset + 4:offset + 8], "little")
        end = offset + 8 + size
        if end + (size % 2) > len(data) or (size % 2 and data[end] != 0):
            raise ValueError("invalid WebP chunk length")
        value = data[offset + 8:end]
        if kind == b"VP8X":
            if offset != 12 or size != 10 or value[0] & ~0x10 or any(value[1:4]):
                raise ValueError("animated or metadata WebP is not allowed")
            canvas = (int.from_bytes(value[4:7], "little") + 1, int.from_bytes(value[7:10], "little") + 1)
            _dimensions(*canvas)
        elif kind == b"VP8 ":
            if size < 10 or value[0] & 1 or value[3:6] != b"\x9d\x01\x2a":
                raise ValueError("invalid WebP image")
            dimensions = (int.from_bytes(value[6:8], "little") & 0x3fff, int.from_bytes(value[8:10], "little") & 0x3fff)
            _dimensions(*dimensions)
            if canvas and canvas != dimensions:
                raise ValueError("WebP canvas does not match image")
            image_count += 1
        elif kind == b"VP8L":
            if size < 5 or value[0] != 0x2f or value[4] & 0xe0:
                raise ValueError("invalid lossless WebP")
            bits = int.from_bytes(value[1:5], "little")
            dimensions = ((bits & 0x3fff) + 1, ((bits >> 14) & 0x3fff) + 1)
            _dimensions(*dimensions)
            if canvas and canvas != dimensions:
                raise ValueError("WebP canvas does not match image")
            image_count += 1
        elif kind != b"ALPH" or not canvas or image_count or size < 1:
            raise ValueError("unsupported WebP chunk")
        offset = end + size % 2
    if image_count != 1:
        raise ValueError("WebP must contain one still image")


def _woff2(data: bytes) -> None:
    if len(data) < 48 or data[:4] != b"wOF2" or data[4:8] not in (b"\x00\x01\x00\x00", b"OTTO"):
        raise ValueError("invalid WOFF2 signature or collection font")
    length, tables, reserved, expanded, compressed = struct.unpack_from(">IHHII", data, 8)
    if length != len(data) or not 1 <= tables <= 128 or reserved or not 12 <= expanded <= MAX_THEME_ASSET_BYTES or not compressed:
        raise ValueError("WOFF2 exceeds its container limits")
    # No metadata/private blocks: all bytes must belong to the bounded font.
    if any(data[28:48]):
        raise ValueError("WOFF2 metadata/private blocks are not allowed")
    offset, original_total, transformed_total, seen = 48, 0, 0, set()

    def base128():
        nonlocal offset
        result = 0
        for index in range(5):
            if offset >= len(data):
                raise ValueError("truncated WOFF2 table directory")
            byte = data[offset]
            offset += 1
            if (index == 0 and byte == 0x80) or result & 0xfe000000:
                raise ValueError("invalid WOFF2 integer")
            result = (result << 7) | (byte & 0x7f)
            if not byte & 0x80:
                return result
        raise ValueError("invalid WOFF2 integer")

    for _ in range(tables):
        if offset >= len(data):
            raise ValueError("truncated WOFF2 directory")
        flags = data[offset]
        offset += 1
        index, transform = flags & 63, flags >> 6
        if index == 63:
            if offset + 4 > len(data):
                raise ValueError("truncated WOFF2 tag")
            tag = data[offset:offset + 4]
            offset += 4
        else:
            tag = index
        if tag in seen:
            raise ValueError("duplicate WOFF2 tables")
        seen.add(tag)
        original = base128()
        transformed = (transform != 3) if index in (10, 11) or tag in (b"glyf", b"loca") else transform != 0
        stored = base128() if transformed else original
        original_total += original
        transformed_total += stored
    if original_total > expanded or transformed_total > MAX_THEME_ASSET_BYTES or offset + compressed != len(data):
        raise ValueError("WOFF2 expanded tables or stream length exceed limits")


def validate_theme_assets(archive: zipfile.ZipFile, theme: ThemeExtensionV2) -> None:
    allowed = {"manifest.json", "theme-extension.json", *(asset.path for asset in theme.assets)}
    total = 0
    for item in archive.infolist():
        if item.is_dir():
            if item.filename != "assets/":
                raise ValueError("unexpected theme directory")
            continue
        mode = stat.S_IFMT(item.external_attr >> 16)
        if item.filename not in allowed or mode not in (0, stat.S_IFREG):
            raise ValueError("undeclared or non-canonical theme asset path")
    for asset in theme.assets:
        info = archive.getinfo(asset.path)
        limit = MAX_FONT_BYTES if asset.role == "font" else MAX_IMAGE_BYTES
        total += info.file_size
        if not 0 < info.file_size <= limit or total > MAX_THEME_ASSET_BYTES:
            raise ValueError("theme assets exceed their size budget")
        data = archive.read(asset.path)
        if hashlib.sha256(data).hexdigest() != asset.sha256:
            raise ValueError("theme asset checksum does not match")
        try:
            {"font/woff2": _woff2, "image/png": _png, "image/webp": _webp}[asset.media_type](data)
        except (struct.error, zlib.error) as exc:
            raise ValueError("theme asset container is invalid") from exc
