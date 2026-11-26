from contextlib import closing
import sqlite3

import pytest

from application_data_tools.search import (
    Document, Hit, IndexErrorCode, PartitionAccess, Rebuild, begin_rebuild, cancel_rebuild,
    create_index_schema, erase_partition, finish_rebuild, index_document, remove_document,
    search_page, stage_documents,
)


@pytest.fixture
def store(tmp_path):
    with closing(sqlite3.connect(tmp_path/"owned.sqlite3")) as db:
        with db:
            create_index_schema(db)
        yield db


def same(partition="mine", revision="acl-1"):
    return lambda: PartitionAccess(partition, revision)


def test_acl_is_evaluated_before_state_pagination_and_cursor_use(store):
    with store:
        # A naive global LIMIT 1 then filter would hide the first authorized hit.
        for ref in ("a0","a1","a2"):
            index_document(store,"other",Document(ref,"Private other title","Изложение годишно"))
        for ref in ("b1","b2","b3"):
            index_document(store,"mine",Document(ref,"Годишно изложение","преглед"))
        index_document(store,"mine",Document("b4","Unrelated","само изложение"))
    auth = [PartitionAccess("mine","acl-1")]
    first = search_page(store,"ИЗЛОЖЕНИЕ годишно",current_access=lambda:auth[0],limit=1)
    assert first.hits == (Hit("b1","Годишно изложение"),) and first.next_cursor
    second = search_page(store,"годишно изложение",current_access=lambda:auth[0],limit=1,cursor=first.next_cursor)
    assert second.hits[0].reference == "b2"
    last = search_page(store,"годишно изложение",current_access=lambda:auth[0],limit=1,cursor=second.next_cursor)
    assert last.hits[0].reference == "b3" and last.next_cursor is None
    auth.clear()
    class NoQueries:
        def execute(self,*_):
            pytest.fail("A denied read must not observe even partition existence")
    with pytest.raises(IndexErrorCode,match="access_denied"):
        search_page(NoQueries(),"",current_access=lambda:None,limit=99,cursor=first.next_cursor)
    for keyword in (dict(current_access=same("mine","acl-2")),dict(current_access=same("other")),
                    dict(limit=2),dict(query="преглед"),dict(cursor="b3."+first.next_cursor.rpartition(".")[2])):
        args = dict(query="годишно изложение",current_access=same(),limit=1,cursor=first.next_cursor)
        with pytest.raises(IndexErrorCode, match="stale_cursor"):
            search_page(store,**(args|keyword))


def test_partial_rebuild_remains_invisible_across_reopen_and_publishes_once(store,tmp_path):
    with store:
        index_document(store,"mine",Document("old","Персона","индекс"))
        stage = begin_rebuild(store,"mine",version=2,source_revision="v5",expected_documents=2)
        assert stage_documents(store,stage,[Document("a","Преглед","индекс")]) == 1
        assert stage_documents(store,stage,[Document("a","Преглед","индекс")]) == 1
    with closing(sqlite3.connect(tmp_path/"owned.sqlite3")) as other:
        assert search_page(other,"индекс",current_access=same()).hits == (Hit("old","Персона"),)
        with pytest.raises(IndexErrorCode,match="reindex_required"):
            search_page(other,"индекс",current_access=same(),version=2)
    with pytest.raises(IndexErrorCode,match="rebuild_incomplete"), store:
        finish_rebuild(store,stage,current_source_revision="v5")
    with pytest.raises(IndexErrorCode,match="rebuild_conflict"), store:
        stage_documents(store,stage,[Document("a","Different")])
    with store:
        stage_documents(store,stage,[Document("b","Следващ","индекс")])
    with pytest.raises(IndexErrorCode,match="source_changed"), store:
        finish_rebuild(store,stage,current_source_revision="v6")
    with store:
        finish_rebuild(store,stage,current_source_revision="v5")
    assert [r.reference for r in search_page(store,"индекс",current_access=same(),version=2).hits] == ["a","b"]
    assert store.execute("SELECT COUNT(*) FROM search_words WHERE ref='old'").fetchone()[0] == 0
    with pytest.raises(IndexErrorCode,match="stale_rebuild"), store:
        finish_rebuild(store,stage,current_source_revision="v5")


def test_retention_and_live_edits_invalidate_pending_publication_and_old_pages(store):
    with store:
        for ref in ("x","y"):
            index_document(store,"mine",Document(ref,ref,"обща"))
        index_document(store,"other",Document("x","Allowed elsewhere","обща"))
    cursor = search_page(store,"обща",current_access=same(),limit=1).next_cursor
    with store:
        st = begin_rebuild(store,"mine",version=2,source_revision="v1",expected_documents=2)
        stage_documents(store,st,[Document("only-staged","retained text")])
        remove_document(store,"mine","only-staged")
    with pytest.raises(IndexErrorCode,match="stale_rebuild"),store:
        stage_documents(store,st,[Document("only-staged","retained text")])
    assert store.execute("SELECT COUNT(*) FROM search_words WHERE word='retained'").fetchone()[0] == 0
    with pytest.raises(IndexErrorCode,match="stale_cursor"):
        search_page(store,"обща",current_access=same(),limit=1,cursor=cursor)
    with store:
        st = begin_rebuild(store,"mine",version=2,source_revision="v2",expected_documents=1)
        index_document(store,"mine",Document("x","Changed","обща"))
    with pytest.raises(IndexErrorCode,match="stale_rebuild"),store:
        finish_rebuild(store,st,current_source_revision="v2")
    with store:
        erase_partition(store,"mine")
    for table in ("search_words","search_documents","search_partitions"):
        assert store.execute(f"SELECT COUNT(*) FROM {table} WHERE scope=?",("mine",)).fetchone()[0] == 0
    assert search_page(store,"обща",current_access=same("other")).hits == (Hit("x","Allowed elsewhere"),)


def test_work_bounds_and_failed_batches_never_replace_visible_results(store):
    with store:
        index_document(store,"mine",Document("old","Old result"))
        st = begin_rebuild(store,"mine",version=2,source_revision="r1",expected_documents=1)
    with pytest.raises(IndexErrorCode,match="batch_limit"),store:
        stage_documents(store,st,[Document(str(i),"record") for i in range(9)])
    with pytest.raises(IndexErrorCode,match="document_limit"),store:
        stage_documents(store,st,[Document("a","One"),Document("b","Two")])
    assert store.execute("SELECT COUNT(*) FROM search_documents WHERE generation=?",(st.generation,)).fetchone() == (0,)
    assert search_page(store,"old",current_access=same()).hits
    with store:
        cancel_rebuild(store,st)
    with pytest.raises(IndexErrorCode,match="stale_rebuild"):
        cancel_rebuild(store,Rebuild("mine","0"*32))
    with pytest.raises(IndexErrorCode,match="term_limit"):
        search_page(store,"one two three four five",current_access=same())
    with pytest.raises(IndexErrorCode,match="text_limit"):
        index_document(store,"mine",Document("a","safe","x"*2049))
    with pytest.raises(IndexErrorCode,match="document_limit"):
        begin_rebuild(store,"mine",version=2,source_revision="r2",expected_documents=129)


def test_search_uses_supplied_scoped_sdk_transaction_without_direct_db_fallback(tmp_path):
    # Real application storage adapter/limits. Admission here is deliberately a
    # test callback, not a real device/user permission grant.
    from packages.application_sdk import ApplicationMigration, ApplicationStorage
    from packages.application_sdk.scoped_relational import (
        ApplicationScopedStorage, ApplicationRelationalStorageError, _TransactionAdmission,
    )
    from packages.protocol.application_extension import ApplicationRelationalStorageV1
    profile = ApplicationRelationalStorageV1(contract_version=1, mode="read_write", limit_class="cooperative_v1",
        max_database_bytes=16*1024*1024, auxiliary_pause_bytes=1024*1024, max_statement_bytes=4096,
        max_value_bytes=8192, max_result_bytes=65536, max_result_rows=32, max_transaction_ms=5000, max_busy_ms=500)
    directory = tmp_path/"approved-namespace"
    ApplicationStorage(directory).migrate([ApplicationMigration("0001",create_index_schema)],"0001")
    def storage(allow=True):
        return ApplicationScopedStorage(directory,declaration=profile,schema_revision="0001",
            admit=(lambda tid,mode,profile,deadline:_TransactionAdmission(tid,mode,profile,deadline)) if allow else None)
    accepted = storage()
    with accepted.transaction() as tx:
        st = begin_rebuild(tx,"mine",version=1,source_revision="one",expected_documents=1)
        stage_documents(tx,st,[Document("sdk","Собствени данни")])
        finish_rebuild(tx,st,current_source_revision="one")
    with accepted.read_transaction() as tx:
        assert search_page(tx,"СОБСТВЕНИ",current_access=same()).hits == (Hit("sdk","Собствени данни"),)
    with pytest.raises(ApplicationRelationalStorageError), storage(False).read_transaction() as tx:
        search_page(tx,"собствени",current_access=same())
