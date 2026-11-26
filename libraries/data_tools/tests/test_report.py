from hashlib import sha256
from html.parser import HTMLParser

import pytest
from application_data_tools import Column, DataError, Limits
from application_data_tools.report import render_table


class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.texts = []
    def handle_starttag(self,tag,attrs):
        self.tags.append((tag,dict(attrs)))
    def handle_data(self,data):
        self.texts.append(data)


def test_printable_report_is_only_escaped_cells_and_local_fixed_presentation():
    columns = (Column("label"),Column("qty","integer"),Column("known","boolean",nullable=True))
    rows = [dict(label="Алиса <mark> & 'А'",qty=-2,known=True),dict(label="=1+2",qty=0,known=None)]
    report = render_table(rows,columns,title="Отчет <данни>",headings=["Име","Брой","Факт"],language="bg")
    doc = Tags(); doc.feed(report.content.decode())
    assert "Алиса <mark> & 'А'" in doc.texts
    assert len([tag for tag in doc.tags if tag[0]=="td"]) == 6
    assert len([tag for tag in doc.tags if tag==("th",{"scope":"col"})]) == 3
    assert not {t for t,_ in doc.tags} & {"mark","данни","script","img","link","iframe","a","form"}
    assert "true" in doc.texts and "—" in doc.texts and "=1+2" in doc.texts
    assert report.metadata()=={"rows":2,"size_bytes":len(report.content),"sha256":sha256(report.content).hexdigest()}
    assert b"default-src 'none'" in report.content
    assert render_table(rows,columns,title="Отчет <данни>",headings=["Име","Брой","Факт"],language="bg") == report


def test_report_never_emits_a_partial_or_oversized_attachment():
    columns = [Column("n","integer")]
    calls = []
    with pytest.raises(DataError,match="byte_limit"):
        render_table([],columns,title="Summary",limits=Limits(max_bytes=260))
    with pytest.raises(DataError,match="row_limit"):
        render_table([{"n":1},{"n":2}],columns,title="Summary",limits=Limits(max_rows=1),progress=calls.append)
    assert not any(p.complete for p in calls)
    with pytest.raises(DataError,match="columns_mismatch"):
        render_table([{"n":3,"private":"not selected"}],columns,title="Summary")
    result = render_table([],columns,title="Empty",progress=calls.append)
    assert result.row_count == calls[-1].rows_checked == 0 and calls[-1].complete
