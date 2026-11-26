"""Review bytes first; apply the caller's own authority and transaction at confirmation."""
from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
import hashlib
import hmac
import io
import json
import re
from typing import Callable, Iterable, Literal

SAFE_INT = 2**53 - 1  # identical exact integer values in ordinary JSON UIs
_KEY = re.compile(r"[a-zA-Z][a-zA-Z0-9_]{0,62}\Z")
_INTEGER = re.compile(r"-?(?:0|[1-9][0-9]{0,15})\Z")
_SPACES = re.compile(r"[ \t\r\n]*")
Format = Literal["csv", "json"]


def _int(value, low, high):
    return type(value) is int and low <= value <= high


@dataclass(frozen=True, slots=True)
class Column:
    key: str
    kind: Literal["text", "integer", "boolean"] = "text"
    nullable: bool = False
    max_length: int = 1024

    def __post_init__(self):
        if (type(self.key) is not str or not _KEY.fullmatch(self.key) or self.kind not in ("text", "integer", "boolean")
                or type(self.nullable) is not bool or not _int(self.max_length, 1, 4096)):
            raise ValueError("Invalid application column declaration")


@dataclass(frozen=True, slots=True)
class Limits:
    max_bytes: int = 1024 * 1024
    max_rows: int = 1000

    def __post_init__(self):
        if not _int(self.max_bytes, 2, 4 * 1024 * 1024) or not _int(self.max_rows, 1, 4096):
            raise ValueError("Invalid application data limits")


@dataclass(frozen=True, slots=True)
class Issue:
    row: int | None  # one-based data row, not a physical line in a multiline CSV
    column: str | None  # only a key from the trusted application schema
    code: str


@dataclass(frozen=True, slots=True)
class Progress:
    phase: Literal["review", "validate", "export"]
    rows_checked: int
    rows_invalid: int
    complete: bool


@dataclass(frozen=True, slots=True)
class Review:
    rows_checked: int
    rows_invalid: int
    issues: tuple[Issue, ...]
    review_key: str | None
    sample: tuple[dict, ...]

    @property
    def ready(self):
        return self.review_key is not None


class DataError(ValueError):
    """Only a fixed code and an optional trusted field/row; never source data."""
    def __init__(self, code, *, row=None, column=None):
        self.issue = Issue(row, column, code)
        super().__init__(code)


def _plan(columns, fmt, limits):
    if type(columns) not in (list, tuple) or not 1 <= len(columns) <= 32 or any(type(c) is not Column for c in columns):
        raise ValueError("Declare one to 32 columns")
    if len({c.key for c in columns}) != len(columns) or fmt not in ("csv", "json") or type(limits) is not Limits:
        raise ValueError("Invalid tabular data plan")
    return tuple(columns)


def _key(blob, columns, fmt, limits):
    plan = json.dumps(["tabular-v1", fmt, [asdict(c) for c in columns], asdict(limits)],
                      sort_keys=True, separators=(",", ":")).encode()
    h = hashlib.sha256(plan)
    h.update(b"\0")
    h.update(blob)
    return h.hexdigest()


def _validate_value(value, c, fmt):
    if fmt == "csv":
        if value == "\\N" or value == "" and c.kind != "text":
            value = None
        elif c.kind == "text" and value.startswith("\\\\"):
            value = value[1:]
        elif c.kind == "integer" and _INTEGER.fullmatch(value):
            value = int(value)
        elif c.kind == "boolean" and value in ("true", "false"):
            value = value == "true"
    if value is None:
        if c.nullable:
            return None
        raise DataError("required", column=c.key)
    if c.kind == "text" and type(value) is str:
        if len(value) > c.max_length:
            raise DataError("text_too_long", column=c.key)
        if any(ord(ch) < 32 and ch not in "\t\r\n" or 0xD800 <= ord(ch) <= 0xDFFF for ch in value):
            raise DataError("invalid_text", column=c.key)
        return value
    if c.kind == "integer" and _int(value, -SAFE_INT, SAFE_INT) or c.kind == "boolean" and type(value) is bool:
        return value
    raise DataError("wrong_type", column=c.key)


def _normalize(row, columns, fmt):
    if type(row) is not dict or len(row) != len(columns) or any(c.key not in row for c in columns):
        raise DataError("columns_mismatch")
    return {c.key: _validate_value(row[c.key], c, fmt) for c in columns}


def _input(blob, fmt, keys):
    try:
        text = blob.decode("utf-8-sig", "strict")
    except UnicodeError:
        raise DataError("not_utf8") from None
    if fmt == "csv":
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        try:
            names = next(reader, ())
            if len(names) != len(keys) or set(names) != keys:
                raise DataError("invalid_header")
            for values in reader:
                yield dict(zip(names, values)) if len(values) == len(names) else None
        except csv.Error:
            raise DataError("invalid_csv") from None
        return
    # Decode one *flat* record at a time so max_rows is reached before the rest
    # of a JSON array is materialized. Arbitrary nested structures are not part
    # of a tabular column and are never handed to the recursive decoder.
    def reject_constant(_):
        raise DataError("invalid_json")
    decoder = json.JSONDecoder(parse_constant=reject_constant)
    def space(pos):
        return _SPACES.match(text, pos).end()
    def take(pos, ch):
        if not text.startswith(ch, pos):
            raise DataError("invalid_json")
        return space(pos + 1)
    def scalar(pos):
        if pos >= len(text) or text[pos] in "{[":
            raise DataError("expected_scalar")
        value, end = decoder.raw_decode(text, pos)
        return value, space(end)
    try:
        pos = space(0)
        if not text.startswith("[", pos):
            raise DataError("expected_rows")
        pos = space(pos + 1)
        if not text.startswith("]", pos):
            while True:
                pos = take(pos, "{")
                row = {}
                if not text.startswith("}", pos):
                    while True:
                        if not text.startswith('"', pos):
                            raise DataError("invalid_json")
                        key, pos = scalar(pos)
                        if key in row:
                            raise DataError("duplicate_key")
                        if len(row) >= 32:
                            raise DataError("columns_mismatch")
                        value, pos = scalar(take(pos, ":"))
                        row[key] = value
                        if text.startswith("}", pos):
                            break
                        pos = take(pos, ",")
                pos = take(pos, "}")
                yield row
                if text.startswith("]", pos):
                    break
                pos = take(pos, ",")
        if take(pos, "]") != len(text):
            raise DataError("invalid_json")
    except DataError:
        raise
    except (ValueError, RecursionError):
        raise DataError("invalid_json") from None


def _read(blob, columns, fmt, limits, sample_size, progress, *, confirmed_key=None):
    confirmed = confirmed_key is not None
    phase = "validate" if confirmed else "review"
    issues, rows, count, invalid = [], [], 0, 0
    def progress_at_end():
        if progress:
            progress(Progress(phase, count, invalid, True))
    try:
        if type(blob) is not bytes or len(blob) > limits.max_bytes:
            raise DataError("invalid_or_oversize_input")
        for raw in _input(blob, fmt, {c.key for c in columns}):
            if count >= limits.max_rows:
                raise DataError("row_limit")
            count += 1
            try:
                record = _normalize(raw, columns, fmt)
            except DataError as exc:
                invalid += 1
                if len(issues) < 20:
                    issues.append(Issue(count, exc.issue.column, exc.issue.code))
            else:
                if confirmed or len(rows) < sample_size:
                    rows.append(record)
            if progress and count % 128 == 0:
                progress(Progress(phase, count, invalid, False))
    except DataError as exc:
        issues.append(exc.issue)  # a file-level error after any sampled row errors
    progress_at_end()
    key = (confirmed_key or _key(blob, columns, fmt, limits)) if not issues else None
    return Review(count, invalid, tuple(issues), key, tuple(rows[:sample_size])), rows


def preview_import(blob: bytes, columns, fmt: Format, *, limits=Limits(), sample_size=0,
                   progress: Callable[[Progress], None] | None = None) -> Review:
    """No mutation; by default even a successful review contains no data values."""
    columns = _plan(columns, fmt, limits)
    if not _int(sample_size, 0, 3):
        raise ValueError("Choose zero to three explicit preview records")
    return _read(blob, columns, fmt, limits, sample_size, progress)[0]


def reviewed_rows(blob: bytes, columns, fmt: Format, review_key: str, *, limits=Limits(), progress=None) -> tuple[dict, ...]:
    """All rows or none. A review key binds bytes and plan; it does NOT grant write permission."""
    columns = _plan(columns, fmt, limits)
    if (type(review_key) is not str or not re.fullmatch("[0-9a-f]{64}", review_key) or type(blob) is not bytes
            or len(blob) > limits.max_bytes or not hmac.compare_digest(review_key, _key(blob, columns, fmt, limits))):
        raise DataError("review_mismatch")
    report, rows = _read(blob, columns, fmt, limits, 0, progress, confirmed_key=review_key)
    if not report.ready:
        raise DataError("validation_failed")
    return tuple(rows)


def _csv_cell(value):
    if value is None:
        return "\\N"
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) is int:
        return str(value)
    if value.startswith("\\"):
        return "\\" + value
    # Spreadsheet output is for display, not lossless round-trip of formula-like text.
    # Prefix rather than strip content; never convert signed numeric columns to text.
    if value.startswith(("\t", "\r", "\n")) or value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def export_rows(records: Iterable[dict], columns, fmt: Format, *, limits=Limits(), progress=None) -> bytes:
    """Only pass already authorized records. Enforce the whole result's bound, never truncate silently."""
    columns = _plan(columns, fmt, limits)
    out, count = bytearray(), 0
    def append(s):
        part = s.encode("utf-8")
        if len(part) > limits.max_bytes - len(out):
            raise DataError("byte_limit")
        out.extend(part)
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    def csv_row(values):
        buffer.seek(0); buffer.truncate(0); writer.writerow(values)
        append(buffer.getvalue())
    if fmt == "csv":
        csv_row([c.key for c in columns])
    else:
        append("[")
    for item in records:
        if count >= limits.max_rows:
            raise DataError("row_limit")
        try:
            row = _normalize(item, columns, "json")
        except DataError as exc:
            raise DataError(exc.issue.code, row=count + 1, column=exc.issue.column) from None
        if fmt == "csv":
            csv_row([_csv_cell(row[c.key]) for c in columns])
        else:
            append(("," if count else "") + json.dumps(row, ensure_ascii=False, separators=(",", ":")))
        count += 1
        if progress and count % 128 == 0:
            progress(Progress("export", count, 0, False))
    if fmt == "json":
        append("]")
    if progress:
        progress(Progress("export", count, 0, True))
    return bytes(out)
