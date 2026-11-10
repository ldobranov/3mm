"""Finite, declarative clock cells; no application templates or transport calls."""
from dataclasses import dataclass
from datetime import datetime
import json
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MAX_CLOCK_FIELDS = 32
MAX_CLOCK_FIELDS_BYTES = 512
CLOCK_FORMATS = {'hm': '%H:%M', 'hms': '%H:%M:%S', 'dmy': '%d.%m.%Y'}
CLOCK_WIDTHS = {'hm': 5, 'hms': 8, 'dmy': 10}


@dataclass(frozen=True)
class ClockField:
    row: int
    column: int
    format: str
    offset: int
    length: int


def clock_zone(name):
    if type(name) is not str or re.fullmatch(r'[A-Za-z0-9_+/-]{1,80}', name) is None:
        raise ValueError('Invalid clock timezone')
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError('Clock timezone is unavailable') from None


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate clock field property')
        result[key] = value
    return result


def parse_clock_fields(raw, *, columns, rows):
    """A bounded JSON scalar keeps the generic flat command-schema contract.

    Each wire tuple is [row, column, format_index, offset, length], where formats
    are hm/hms/dmy in that order. 32 tuples fit the existing 512-byte scalar
    budget; Core needs no schema expansion or clock-specific interpretation.
    Only fixed clock formats and explicit visible cell spans are interpreted.
    Clipping/OLD markers and all business formatting remain the application's job.
    """
    if (type(raw) is not str or not 2 <= len(raw.encode('utf-8')) <= MAX_CLOCK_FIELDS_BYTES
            or type(columns) is not int or not 1 <= columns <= 80
            or type(rows) is not int or not 1 <= rows <= 4):
        raise ValueError('Invalid clock field budget')
    try:
        values = json.loads(raw, object_pairs_hook=_unique_object)
    except (ValueError, RecursionError):
        raise ValueError('Invalid clock fields') from None
    if type(values) is not list or len(values) > MAX_CLOCK_FIELDS:
        raise ValueError('Too many clock fields')
    result, cells = [], set()
    for value in values:
        if (type(value) is not list or len(value) != 5 or any(type(part) is not int for part in value)
                or not 0 <= value[2] <= 2):
            raise ValueError('Clock fields require bounded integer tuples')
        item = dict(zip(('row', 'column', 'format', 'offset', 'length'), value))
        item['format'] = tuple(CLOCK_FORMATS)[value[2]]
        if (any(type(item[key]) is not int for key in ('row', 'column', 'offset', 'length'))
                or type(item['format']) is not str or item['format'] not in CLOCK_FORMATS
                or not 0 <= item['row'] < rows or not 0 <= item['column'] < columns
                or not 1 <= item['length'] <= CLOCK_WIDTHS[item['format']]
                or not 0 <= item['offset'] <= CLOCK_WIDTHS[item['format']] - item['length']
                or item['column'] + item['length'] > columns):
            raise ValueError('Clock field exceeds its exact geometry')
        occupied = {(item['row'], column) for column in range(item['column'], item['column'] + item['length'])}
        if cells & occupied:
            raise ValueError('Clock fields overlap')
        cells.update(occupied)
        result.append(ClockField(**item))
    return tuple(result)


def render_clock_fields(lines, fields, zone, utc_seconds):
    local = datetime.fromtimestamp(utc_seconds, zone)
    values = {kind: local.strftime(pattern) for kind, pattern in CLOCK_FORMATS.items()}
    output = [list(line) for line in lines]
    for field in fields:
        output[field.row][field.column:field.column + field.length] = values[field.format][
            field.offset:field.offset + field.length]
    return [''.join(line) for line in output]
