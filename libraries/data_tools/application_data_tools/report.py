"""Standalone printable table. No browser, template language, file, URL, font or network loader."""
from dataclasses import dataclass
from hashlib import sha256
from html import escape
import re

from .tabular import Column, DataError, Limits, Progress, _normalize, _plan, _validate_value

_STYLE = (
    "body{font:1rem/1.5 system-ui,sans-serif;margin:1.5rem;color:#18222c;background:white}"
    "table{border-collapse:collapse;text-align:start;max-width:100%}"
    "caption{text-align:start;font-weight:bold;font-size:1.3rem;margin-bottom:.5rem}"
    "th,td{border:1px solid #85949f;padding:.35rem .6rem;text-align:start;vertical-align:top;"
    "white-space:pre-wrap;overflow-wrap:anywhere}thead{background:#edf0f4}"
    "@media print{body{margin:0}thead{display:table-header-group}tr{break-inside:avoid}}"
)


@dataclass(frozen=True, slots=True)
class TableReport:
    content: bytes
    row_count: int
    sha256: str

    def metadata(self):
        """Content stays in the application's approved namespace, not in the task result."""
        return {"rows": self.row_count, "size_bytes": len(self.content), "sha256": self.sha256}


def render_table(records, columns, *, title, headings=None, language="en",
                 limits=Limits(max_bytes=64 * 1024, max_rows=128), progress=None):
    """Render only caller-authorized rows and labels; no implicit file write, totals or truncation."""
    columns = _plan(columns, "json", limits)
    label_type = Column("label", max_length=160)
    def label(value):
        result = _validate_value(value, label_type, "json")
        if not result.strip():
            raise DataError("empty_label")
        return escape(result)
    heading = label(title)
    if type(language) is not str or not re.fullmatch(r"[a-z]{2,3}(?:-[A-Z]{2})?", language):
        raise DataError("invalid_language")
    if headings is None:
        headers = [label(c.key) for c in columns]
    elif type(headings) in (list,tuple) and len(headings) == len(columns):
        headers = [label(h) for h in headings]
    else:
        raise DataError("columns_mismatch")
    data = bytearray()
    def add(text):
        chunk = text.encode("utf-8")
        if len(chunk) > limits.max_bytes - len(data):
            raise DataError("byte_limit")
        data.extend(chunk)
    add('<!doctype html><html lang="' + language + '"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; '
        'base-uri \'none\'; form-action \'none\'"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>' + heading + '</title><style>' + _STYLE + '</style></head><body><main><table><caption>' +
        heading + '</caption><thead><tr>' + ''.join('<th scope="col">' + h + '</th>' for h in headers) +
        '</tr></thead><tbody>')
    count = 0
    for item in records:
        if count >= limits.max_rows:
            raise DataError("row_limit")
        try:
            row = _normalize(item, columns, "json")
        except DataError as exc:
            raise DataError(exc.issue.code, row=count + 1, column=exc.issue.column) from None
        add("<tr>")
        for c in columns:
            val = row[c.key]
            cell = "—" if val is None else ("true" if val else "false") if type(val) is bool else str(val)
            add("<td>" + escape(cell) + "</td>")
        add("</tr>")
        count += 1
        if progress and count % 128 == 0:
            progress(Progress("export", count, 0, False))
    add("</tbody></table></main></body></html>")
    if progress:
        progress(Progress("export", count, 0, True))
    return TableReport(bytes(data), count, sha256(data).hexdigest())
