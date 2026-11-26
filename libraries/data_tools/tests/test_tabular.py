import csv
from dataclasses import asdict
import io
import json
import sqlite3

import pytest
from application_data_tools import Column, DataError, Limits, export_rows, preview_import, reviewed_rows

COLUMNS = (Column("name", max_length=64), Column("units", "integer"),
           Column("enabled", "boolean", nullable=True), Column("comment", nullable=True))
RECORD = dict(name="Проба", units=-32, enabled=True, comment=None)


@pytest.mark.parametrize("fmt", ["csv", "json"])
def test_exact_preview_and_confirm_without_echoing_business_values(fmt):
    blob = export_rows([RECORD], COLUMNS, fmt)
    report = preview_import(blob, COLUMNS, fmt)
    assert report.ready and not report.sample and not report.issues and report.rows_checked == 1
    assert "Проба" not in repr(report)
    assert preview_import(blob, COLUMNS, fmt, sample_size=1).sample == (RECORD,)
    assert reviewed_rows(blob, COLUMNS, fmt, report.review_key) == (RECORD,)
    for source, columns, form, limits in (
        (blob + b' ', COLUMNS, fmt, Limits()), (blob, COLUMNS[::-1], fmt, Limits()),
        (blob, COLUMNS, "csv" if fmt == "json" else "json", Limits()),
        (blob, COLUMNS, fmt, Limits(max_bytes=1024)), (blob, COLUMNS[:-1], fmt, Limits()),
    ):
        with pytest.raises(DataError, match="review_mismatch"):
            reviewed_rows(source, columns, form, report.review_key, limits=limits)


def test_csv_header_order_multiline_bom_null_and_literal_marker():
    source = '\ufeffcomment,name,units,enabled\r\n"line1\r\nline2","A, B",-3,false\r\n\\\\N,plain,0,\\N\r\n'.encode()
    review = preview_import(source, COLUMNS, "csv")
    assert review.ready
    rows = reviewed_rows(source, COLUMNS, "csv", review.review_key)
    assert rows[0] == dict(comment="line1\r\nline2", name="A, B", units=-3, enabled=False)
    assert rows[1] == dict(comment="\\N", name="plain", units=0, enabled=None)
    exported = export_rows(rows, COLUMNS, "csv")
    assert reviewed_rows(exported, COLUMNS, "csv", preview_import(exported, COLUMNS, "csv").review_key) == rows


@pytest.mark.parametrize(("fmt","source","code"), [
    ("csv", b"name,name,enabled,comment\n", "invalid_header"),
    ("csv", b"name,units,enabled,comment\nabc,2,junk,x\n", "wrong_type"),
    ("csv", b'name,units,enabled,comment\n"unfinished', "invalid_csv"),
    ("csv", b"name,units,enabled,comment\none,two\n", "columns_mismatch"),
    ("csv", b"name,units,enabled,comment\nbad,\xff,true,\n", "not_utf8"),
    ("json", b'[{"name":"x","name":"y"}]', "duplicate_key"),
    ("json", b'[{"name":[]}]', "expected_scalar"),
    ("json", b'[{"name":"x","units":true,"enabled":false,"comment":null}]', "wrong_type"),
    ("json", b'[{"name":"x","units":9007199254740992,"enabled":false,"comment":null}]', "wrong_type"),
    ("json", b'[{"name":"\\ud800","units":1,"enabled":true,"comment":null}]', "invalid_text"),
    ("json", b'[{"private_extra":3}]', "columns_mismatch"),
    ("json", b'[{"name":NaN}]', "invalid_json"),
    ("json", b"[{},]", "invalid_json"),
    ("json", b"[] extra", "invalid_json"),
    ("json", b"{}", "expected_rows"),
])
def test_invalid_import_never_offers_confirmation_or_includes_raw_input(fmt, source, code):
    review = preview_import(source, COLUMNS, fmt)
    assert not review.ready and code in {issue.code for issue in review.issues}
    assert "private_extra" not in repr(review)


def test_file_row_error_and_progress_budgets():
    limits = Limits(max_bytes=4096, max_rows=150)
    cols = [Column("n", "integer")]
    raw = b"n\n" + b"1\n" * 128 + b"private\n" * 23
    progress = []
    result = preview_import(raw, cols, "csv", limits=limits, progress=progress.append)
    assert not result.ready and result.rows_checked == 150 and result.rows_invalid == 22
    assert len(result.issues) == 21 and result.issues[-1].code == "row_limit"
    assert result.issues[0].row == 129 and result.issues[0].column == "n"
    assert [item.rows_checked for item in progress] == [128,150] and progress[-1].complete
    assert "private" not in str([asdict(item) for item in progress]) + repr(result)
    assert preview_import(b" " * 4097, cols, "json", limits=limits).issues[0].code == "invalid_or_oversize_input"
    consumed = []
    def records():
        for i in range(10000):
            consumed.append(i)
            yield {"n": i}
    with pytest.raises(DataError, match="row_limit"):
        export_rows(records(), cols, "json", limits=Limits(max_rows=2))
    assert len(consumed) == 3
    with pytest.raises(DataError, match="byte_limit"):
        export_rows([{"n": 100}], cols, "json", limits=Limits(max_bytes=5))
    with pytest.raises(DataError, match="wrong_type") as exc:
        export_rows([{"n": "private"}], cols, "csv")
    assert exc.value.issue.row == 1 and "private" not in str(exc.value)


def test_spreadsheet_safe_csv_and_lossless_json_are_different_contracts():
    values = ("=1+1", " \t+42", "-10", "@example", "\rcontent", "\tplain", "'=literal", "normal", "\\N", "")
    records = [dict(RECORD, comment=val) for val in values]
    csv_data = list(csv.DictReader(io.StringIO(export_rows(records, COLUMNS, "csv").decode(), newline="")))
    assert [r["comment"] for r in csv_data] == ["'" + val if i < 6 else "\\\\N" if val == "\\N" else val
                                                 for i,val in enumerate(values)]
    assert all(row["units"] == "-32" for row in csv_data)
    assert json.loads(export_rows(records, COLUMNS, "json")) == records


def test_disposable_application_transaction_can_revoke_and_reject_partial_import():
    # An application example, not an assertion that a content digest grants access.
    db = sqlite3.connect(":memory:")
    try:
        with db:
            db.execute("CREATE TABLE notes (subject INTEGER NOT NULL, name TEXT NOT NULL, UNIQUE(subject,name))")
            db.executemany("INSERT INTO notes VALUES (?,?)", [(1,"existing"), (2,"other subject")])
        columns = [Column("name", max_length=40)]
        duplicate = b'[{"name":"new"},{"name":"existing"}]'
        key = preview_import(duplicate, columns, "json").review_key
        allowed = {1}
        def apply(subject, raw, reviewed):
            if subject not in allowed:
                raise PermissionError
            validated = reviewed_rows(raw, columns, "json", reviewed)
            with db:
                db.executemany("INSERT INTO notes VALUES (?,?)", ((subject,r["name"]) for r in validated))
        allowed.remove(1)
        with pytest.raises(PermissionError):
            apply(1, duplicate, key)
        allowed.add(1)
        with pytest.raises(sqlite3.IntegrityError):
            apply(1, duplicate, key)
        assert list(db.execute("SELECT * FROM notes ORDER BY subject")) == [(1,"existing"), (2,"other subject")]
        good = b'[{"name":"new"}]'
        apply(1, good, preview_import(good,columns,"json").review_key)
        selected = ({"name":r[0]} for r in db.execute("SELECT name FROM notes WHERE subject=? ORDER BY name",(1,)))
        assert json.loads(export_rows(selected,columns,"json")) == [{"name":"existing"},{"name":"new"}]
    finally:
        db.close()
