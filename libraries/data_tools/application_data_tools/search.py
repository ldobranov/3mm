"""An application-owned exact-word index, operating only on the supplied SDK transaction.

The caller supplies a *currently authorized*, single visibility partition and
access revision, never a client-chosen tenant filter. This module owns no DB
connections, permissions, background tasks, or application configuration.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import re
import secrets
import unicodedata

MAX_SCOPES = 32
MAX_DOCUMENTS = 128  # per partition per generation; at most one staged generation
MAX_BATCH = 8
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}\Z")
_GEN = re.compile(r"[0-9a-f]{32}\Z")
_WORDS = re.compile(r"[^\W_]+", re.UNICODE)


class IndexErrorCode(ValueError):
    """Fixed operational code, never an identifier, search string or content."""


@dataclass(frozen=True, slots=True)
class Document:
    reference: str
    label: str
    searchable_text: str = ""


@dataclass(frozen=True, slots=True)
class Hit:
    reference: str
    label: str


@dataclass(frozen=True, slots=True)
class Page:
    hits: tuple[Hit, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class Rebuild:
    scope: str
    generation: str


@dataclass(frozen=True, slots=True)
class PartitionAccess:
    scope: str
    revision: str


@dataclass(frozen=True, slots=True)
class _State:
    active: str
    version: int
    cursor_key: str
    stage: str | None
    stage_version: int | None
    source_revision: str | None
    expected: int | None


def create_index_schema(db):
    """Call once from the application's explicit forward migration, never from a request."""
    db.execute("""CREATE TABLE search_partitions (
        scope TEXT PRIMARY KEY, active TEXT NOT NULL, version INTEGER NOT NULL, cursor_key TEXT NOT NULL,
        stage TEXT, stage_version INTEGER, source_revision TEXT, expected INTEGER)""")
    db.execute("""CREATE TABLE search_documents (
        scope TEXT NOT NULL, generation TEXT NOT NULL, ref TEXT NOT NULL, label TEXT NOT NULL, digest TEXT NOT NULL,
        PRIMARY KEY(scope,generation,ref))""")
    db.execute("""CREATE TABLE search_words (
        scope TEXT NOT NULL, generation TEXT NOT NULL, word TEXT NOT NULL, ref TEXT NOT NULL,
        PRIMARY KEY(scope,generation,word,ref))""")
    db.execute("CREATE INDEX search_words_by_ref ON search_words(scope,generation,ref)")


def _id(value):
    if type(value) is not str or not _ID.fullmatch(value):
        raise IndexErrorCode("invalid_selector")
    return value


def _version(version):
    if type(version) is not int or not 1 <= version <= 2**31 - 1:
        raise IndexErrorCode("invalid_version")


def _text(text, n):
    if (type(text) is not str or len(text) > n or
        any(ord(c) < 32 and c not in "\t\r\n" or 0xD800 <= ord(c) <= 0xDFFF for c in text)):
        raise IndexErrorCode("text_limit")
    return text


def _words(value, max_words):
    norm = unicodedata.normalize("NFKC", value).casefold()
    terms = set()
    for match in _WORDS.finditer(norm):
        word = match[0]
        if len(word) > 64:
            raise IndexErrorCode("term_limit")
        terms.add(word)
        if len(terms) > max_words:
            raise IndexErrorCode("term_limit")
    return tuple(sorted(terms))


def _encode(items):
    return json.dumps(items, ensure_ascii=True, separators=(",", ":")).encode("ascii")


def _prepared(doc):
    if type(doc) is not Document:
        raise IndexErrorCode("invalid_document")
    _id(doc.reference)
    label = _text(doc.label, 160)
    if not label.strip():
        raise IndexErrorCode("empty_label")
    terms = _words(label + " " + _text(doc.searchable_text, 2048), 64)
    digest = hashlib.sha256(_encode((label, terms))).hexdigest()
    return doc.reference, label, terms, digest


def _state(db, scope):
    _id(scope)
    row = db.execute("""SELECT active,version,cursor_key,stage,stage_version,source_revision,expected
                      FROM search_partitions WHERE scope=?""", (scope,)).fetchone()
    return _State(*row) if row else None


def _ensure(db, scope, version):
    _version(version)
    state = _state(db, scope)
    if state is not None:
        return state
    if db.execute("SELECT COUNT(*) FROM search_partitions").fetchone()[0] >= MAX_SCOPES:
        raise IndexErrorCode("partition_limit")
    state = _State(secrets.token_hex(16), version, secrets.token_hex(32), None, None, None, None)
    db.execute("INSERT INTO search_partitions(scope,active,version,cursor_key) VALUES(?,?,?,?)",
               (scope, state.active, version, state.cursor_key))
    return state


def _drop_generation(db, scope, generation):
    db.execute("DELETE FROM search_words WHERE scope=? AND generation=?", (scope, generation))
    db.execute("DELETE FROM search_documents WHERE scope=? AND generation=?", (scope, generation))


def _cancel(db, scope, state):
    if state.stage is not None:
        _drop_generation(db, scope, state.stage)
        db.execute("""UPDATE search_partitions SET stage=NULL,stage_version=NULL,source_revision=NULL,expected=NULL
                       WHERE scope=?""", (scope,))


def _size(db, scope, generation):
    return db.execute("SELECT COUNT(*) FROM search_documents WHERE scope=? AND generation=?",
                      (scope, generation)).fetchone()[0]


def _write(db, scope, generation, doc, *, ceiling, staging):
    ref, label, terms, digest = doc
    identity = (scope, generation, ref)
    old = db.execute("SELECT digest FROM search_documents WHERE scope=? AND generation=? AND ref=?", identity).fetchone()
    if old:
        if old[0] == digest:
            return False
        if staging:
            raise IndexErrorCode("rebuild_conflict")
        db.execute("UPDATE search_documents SET label=?,digest=? WHERE scope=? AND generation=? AND ref=?",
                   (label, digest, *identity))
        db.execute("DELETE FROM search_words WHERE scope=? AND generation=? AND ref=?", identity)
    else:
        if _size(db, scope, generation) >= ceiling:
            raise IndexErrorCode("document_limit")
        db.execute("INSERT INTO search_documents(scope,generation,ref,label,digest) VALUES(?,?,?,?,?)",
                   (scope, generation, ref, label, digest))
    db.executemany("INSERT INTO search_words(scope,generation,ref,word) VALUES(?,?,?,?)",
                   [(scope,generation,ref,term) for term in terms])
    return True


def index_document(db, scope, document: Document, *, version=1):
    """Call in the same normal write transaction as the source change."""
    doc = _prepared(document)
    state = _ensure(db, scope, version)
    if state.version != version:
        raise IndexErrorCode("reindex_required")
    if _write(db, scope, state.active, doc, ceiling=MAX_DOCUMENTS, staging=False):
        _cancel(db, scope, state)
        db.execute("UPDATE search_partitions SET cursor_key=? WHERE scope=?", (secrets.token_hex(32), scope))


def remove_document(db, scope, reference):
    """Retention / access loss: remove terms and label; invalidate even a staged-only copy."""
    _id(reference)
    state = _state(db, scope)
    if state is None:
        return
    _cancel(db, scope, state)
    db.execute("DELETE FROM search_words WHERE scope=? AND ref=? AND generation=?", (scope,reference,state.active))
    db.execute("DELETE FROM search_documents WHERE scope=? AND ref=? AND generation=?", (scope,reference,state.active))
    db.execute("UPDATE search_partitions SET cursor_key=? WHERE scope=?", (secrets.token_hex(32), scope))


def erase_partition(db, scope):
    """Remove active/staged index data and cursor state in the caller's erasure transaction."""
    _id(scope)
    db.execute("DELETE FROM search_words WHERE scope=?", (scope,))
    db.execute("DELETE FROM search_documents WHERE scope=?", (scope,))
    db.execute("DELETE FROM search_partitions WHERE scope=?", (scope,))


def begin_rebuild(db, scope, *, version, source_revision, expected_documents):
    """One explicitly requested staged rebuild, never an automatic scan of application data."""
    _version(version)
    _id(source_revision)
    if type(expected_documents) is not int or not 0 <= expected_documents <= MAX_DOCUMENTS:
        raise IndexErrorCode("document_limit")
    state = _ensure(db, scope, version)
    if state.stage is not None:
        raise IndexErrorCode("rebuild_in_progress")
    generation = secrets.token_hex(16)
    db.execute("UPDATE search_partitions SET stage=?,stage_version=?,source_revision=?,expected=? WHERE scope=?",
               (generation,version,source_revision,expected_documents,scope))
    return Rebuild(scope, generation)


def _current_stage(db, rebuild):
    if type(rebuild) is not Rebuild or type(rebuild.generation) is not str or not _GEN.fullmatch(rebuild.generation):
        raise IndexErrorCode("stale_rebuild")
    state = _state(db, rebuild.scope)
    if state is None or state.stage != rebuild.generation:
        raise IndexErrorCode("stale_rebuild")
    return state


def stage_documents(db, rebuild: Rebuild, documents):
    """One bounded task step. A repeated identical reference does not count twice."""
    if type(documents) not in (list, tuple) or not 1 <= len(documents) <= MAX_BATCH:
        raise IndexErrorCode("batch_limit")
    state = _current_stage(db, rebuild)
    batch = tuple(map(_prepared, documents))
    for doc in batch:
        _write(db, rebuild.scope, state.stage, doc, ceiling=state.expected, staging=True)
    return _size(db, rebuild.scope, state.stage)


def finish_rebuild(db, rebuild: Rebuild, *, current_source_revision):
    """Publish only a complete current snapshot, within the same transaction as its revision read."""
    _id(current_source_revision)
    state = _current_stage(db, rebuild)
    if state.source_revision != current_source_revision:
        raise IndexErrorCode("source_changed")
    if _size(db, rebuild.scope, state.stage) != state.expected:
        raise IndexErrorCode("rebuild_incomplete")
    _drop_generation(db, rebuild.scope, state.active)
    db.execute("""UPDATE search_partitions SET active=stage,version=stage_version,cursor_key=?,
               stage=NULL,stage_version=NULL,source_revision=NULL,expected=NULL WHERE scope=?""",
               (secrets.token_hex(32),rebuild.scope))


def cancel_rebuild(db, rebuild: Rebuild):
    _cancel(db, rebuild.scope, _current_stage(db, rebuild))


def search_page(db, query, *, current_access, version=1, limit=10, cursor=None):
    """An exact-word AND search *within* one authorized partition, before order/limit."""
    # Derive access in application code on every request, before disclosing any
    # index state, even for a previously valid cursor or a malformed query.
    access = current_access()
    if type(access) is not PartitionAccess:
        raise IndexErrorCode("access_denied")
    scope, access_revision = _id(access.scope), _id(access.revision)
    _version(version)
    terms = _words(_text(query, 160), 4)
    if not terms or type(limit) is not int or not 1 <= limit <= 10:
        raise IndexErrorCode("invalid_query")
    state = _state(db, scope)
    if state is None:
        if cursor is not None:
            raise IndexErrorCode("stale_cursor")
        return Page((), None)
    if state.version != version:
        raise IndexErrorCode("reindex_required")
    def mac(ref):
        return hmac.digest(bytes.fromhex(state.cursor_key),
                           _encode(("index-page-v1",scope,access_revision,terms,limit,ref)), "sha256").hex()
    after = ""
    if cursor is not None:
        if type(cursor) is not str or len(cursor) > 161:
            raise IndexErrorCode("stale_cursor")
        after, dot, signature = cursor.rpartition(".")
        if not dot or not _ID.fullmatch(after) or not re.fullmatch("[a-f0-9]{64}", signature) or not hmac.compare_digest(mac(after), signature):
            raise IndexErrorCode("stale_cursor")
    # Only the number of placeholders (one to four) varies. No supplied SQL,
    # paths, aliases, global totals, or titles from other partitions are used.
    params = ",".join("?" for _ in terms)
    hits = db.execute(f"""SELECT d.ref,d.label FROM search_documents d
        WHERE d.scope=? AND d.generation=? AND d.ref>? AND d.ref IN
          (SELECT w.ref FROM search_words w WHERE w.scope=? AND w.generation=? AND w.word IN ({params})
           GROUP BY w.ref HAVING COUNT(*)=?)
        ORDER BY d.ref LIMIT ?""",
        (scope,state.active,after,scope,state.active,*terms,len(terms),limit+1)).fetchall()
    page = tuple(Hit(ref, label) for ref,label in hits[:limit])
    token = page[-1].reference + "." + mac(page[-1].reference) if len(hits) > limit else None
    return Page(page,token)
