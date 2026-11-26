"""Optional app-owned, in-app notices. No worker, external delivery or Core permission.

Every operation uses the caller's existing application transaction and a resolver
for its current authorized recipient. It never takes recipient identity from a
browser payload. Message text and links are not stored: the application maps a
reviewed topic to a localized label and checks current access on opening a resource.
"""
from dataclasses import dataclass
import re
from uuid import uuid4


class InboxError(ValueError):
    """Fixed application-safe reason; never put business data in exceptions."""


@dataclass(frozen=True, slots=True)
class Audience:
    recipient: str
    access_revision: int


@dataclass(frozen=True, slots=True)
class InboxLimits:
    per_recipient: int = 64
    total: int = 4096
    preferences: int = 1024
    per_minute: int = 12
    lifetime_seconds: int = 7 * 24 * 3600


def _integer(value, minimum, maximum):
    return type(value) is int and minimum <= value <= maximum


def _opaque(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{32}", value) is not None


def initialize(db):
    """Use only in an explicit app migration (never on list/publish)."""
    for sql in (
        """CREATE TABLE inbox_preferences(
            recipient TEXT NOT NULL, topic TEXT NOT NULL, access_revision INTEGER NOT NULL,
            generation TEXT NOT NULL, enabled INTEGER NOT NULL CHECK(enabled IN (0,1)), PRIMARY KEY(recipient,topic))""",
        """CREATE TABLE inbox_budgets(recipient TEXT PRIMARY KEY, window_start INTEGER NOT NULL, used INTEGER NOT NULL)""",
        """CREATE TABLE inbox_entries(
            sequence INTEGER PRIMARY KEY, notice_id TEXT UNIQUE NOT NULL, recipient TEXT NOT NULL,
            topic TEXT NOT NULL, generation TEXT NOT NULL, event_ref TEXT NOT NULL, resource_ref TEXT NOT NULL,
            created INTEGER NOT NULL, available INTEGER NOT NULL, expires INTEGER NOT NULL,
            state TEXT NOT NULL CHECK(state IN ('unread','read','acknowledged','dismissed')),
            UNIQUE(recipient,topic,generation,event_ref))""",
        "CREATE INDEX inbox_visible ON inbox_entries(recipient,sequence)",
        "CREATE INDEX inbox_expiry ON inbox_entries(expires,sequence)",
    ):
        db.execute(sql)


class Inbox:
    def __init__(self, topics, limits=InboxLimits()):
        if (type(topics) not in (list,tuple) or not 1 <= len(topics) <= 32 or any(
                type(t) is not str or not re.fullmatch(r"[a-z][a-z0-9_.-]{0,63}", t) for t in topics)
                or len(set(topics)) != len(topics)):
            raise InboxError("invalid_topics")
        if (not isinstance(limits, InboxLimits) or not _integer(limits.per_recipient,1,256)
                or not _integer(limits.total,limits.per_recipient,16384) or not _integer(limits.preferences,1,4096)
                or not _integer(limits.per_minute,1,256) or not _integer(limits.lifetime_seconds,1,31*86400)):
            raise InboxError("invalid_limits")
        self.topics, self.limits = frozenset(topics), limits

    @staticmethod
    def _subject(db, resolve):
        if getattr(db, "in_transaction", True) is False:
            raise InboxError("application_transaction_required")
        scope = resolve(db)
        if (not isinstance(scope, Audience) or type(scope.recipient) is not str or not
                re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,95}",scope.recipient) or
                not _integer(scope.access_revision,1,2**63-1)):
            raise InboxError("inbox_unavailable")
        return scope

    def _topic(self, topic):
        if type(topic) is not str or topic not in self.topics:
            raise InboxError("invalid_topic")

    @staticmethod
    def _clock(now):
        if not _integer(now, 0, 2**53-1):
            raise InboxError("invalid_time")

    @staticmethod
    def _binding(db, subject, topic):
        row = db.execute("SELECT generation FROM inbox_preferences WHERE recipient=? AND topic=? AND access_revision=? AND enabled=1",
                         (subject.recipient,topic,subject.access_revision)).fetchone()
        return row[0] if row is not None else None

    def capture_consent(self, db, resolve, topic):
        """Internal producer handle. Capture when reviewing the intent, not when retrying it."""
        self._topic(topic)
        return self._binding(db, self._subject(db,resolve), topic)

    @staticmethod
    def _preference(db, s, topic):
        row = db.execute("SELECT enabled,generation FROM inbox_preferences WHERE recipient=? AND topic=? AND access_revision=?",
                         (s.recipient,topic,s.access_revision)).fetchone()
        return {"enabled":bool(row[0]), "revision":row[1]} if row else {"enabled":False, "revision":None}

    def preference(self, db, resolve, topic):
        self._topic(topic)
        return self._preference(db,self._subject(db,resolve),topic)

    def set_preference(self, db, resolve, topic, enabled, *, expected):
        self._topic(topic)
        if type(enabled) is not bool or (expected is not None and not _opaque(expected)):
            raise InboxError("invalid_preference")
        s = self._subject(db, resolve)
        previous = self._preference(db,s,topic)
        if previous["revision"] != expected:
            raise InboxError("preference_changed")
        if expected is not None and previous["enabled"] is enabled:
            return previous
        existing = db.execute("SELECT 1 FROM inbox_preferences WHERE recipient=? AND topic=?", (s.recipient,topic)).fetchone()
        if not existing and db.execute("SELECT count(*) FROM inbox_preferences").fetchone()[0] >= self.limits.preferences:
            raise InboxError("preference_limit")
        # Never attach old rows or pending intents to a new consent generation.
        db.execute("DELETE FROM inbox_entries WHERE recipient=? AND topic=?", (s.recipient,topic))
        revision = uuid4().hex
        # Keep the disabled revision: a delayed opt-in from before opt-out
        # must not turn the checkbox back on after a lost browser response.
        db.execute("""INSERT INTO inbox_preferences(recipient,topic,access_revision,generation,enabled) VALUES(?,?,?,?,?)
                      ON CONFLICT(recipient,topic) DO UPDATE SET access_revision=excluded.access_revision,
                      generation=excluded.generation,enabled=excluded.enabled""",
                   (s.recipient,topic,s.access_revision,revision,int(enabled)))
        # The recipient's rate budget survives preference changes just like
        # expiry and dismissal. At most one budget per registered recipient;
        # explicit local erasure removes it together with their preferences.
        return {"enabled":enabled, "revision":revision}

    @staticmethod
    def _expire(db, now, limit):
        db.execute("""DELETE FROM inbox_entries WHERE sequence IN
                      (SELECT sequence FROM inbox_entries WHERE expires<=? ORDER BY expires,sequence LIMIT ?)""", (now,limit))

    def prune_expired(self, db, *, now, limit=64):
        """Explicit app-owned retention; reads never erase rows or mark them read."""
        self._clock(now)
        if not _integer(limit,1,256):
            raise InboxError("invalid_limit")
        if getattr(db, "in_transaction", True) is False:
            raise InboxError("application_transaction_required")
        self._expire(db,now,limit)

    def publish(self, db, resolve, *, topic, consent, event_ref, resource_ref, now, available, expires):
        """One local transaction; a deliberate skip, quota or duplicate is not external delivery."""
        s = self._subject(db,resolve)
        self._topic(topic)
        self._clock(now)
        if not _opaque(consent) or consent != self._binding(db,s,topic):
            return "not_subscribed"
        if not _opaque(event_ref) or not _opaque(resource_ref):
            raise InboxError("invalid_reference")
        if not (_integer(available,0,2**53-1) and _integer(expires,0,2**53-1) and available < expires):
            raise InboxError("invalid_time")
        if expires <= now:
            return "expired"
        if expires - now > self.limits.lifetime_seconds:
            raise InboxError("expiry_limit")
        row = db.execute("""SELECT resource_ref,available,expires FROM inbox_entries
            WHERE recipient=? AND topic=? AND generation=? AND event_ref=?""", (s.recipient,topic,consent,event_ref)).fetchone()
        if row is not None:
            if tuple(row) != (resource_ref,available,expires):
                raise InboxError("reference_conflict")
            return "already_recorded"
        self._expire(db,now,64)
        if (db.execute("SELECT count(*) FROM inbox_entries WHERE recipient=?", (s.recipient,)).fetchone()[0] >= self.limits.per_recipient
                or db.execute("SELECT count(*) FROM inbox_entries").fetchone()[0] >= self.limits.total):
            return "capacity_limited"
        budget = db.execute("SELECT window_start,used FROM inbox_budgets WHERE recipient=?", (s.recipient,)).fetchone()
        start, used = (now,0) if budget is None or now-budget[0] >= 60 else tuple(budget)
        if used >= self.limits.per_minute:
            return "rate_limited"
        db.execute("""INSERT INTO inbox_budgets(recipient,window_start,used) VALUES(?,?,?)
            ON CONFLICT(recipient) DO UPDATE SET window_start=excluded.window_start,used=excluded.used""",
                   (s.recipient,start,used+1))
        db.execute("""INSERT INTO inbox_entries(notice_id,recipient,topic,generation,event_ref,resource_ref,created,available,expires,state)
            VALUES(?,?,?,?,?,?,?,?,?,'unread')""", (uuid4().hex,s.recipient,topic,consent,event_ref,resource_ref,now,available,expires))
        return "available" if available <= now else "scheduled"

    def _subscribed_rows(self, s):
        slots = ','.join('?' for _ in self.topics)
        return (""" FROM inbox_entries n JOIN inbox_preferences p ON p.recipient=n.recipient AND p.topic=n.topic
                    AND p.generation=n.generation WHERE n.recipient=? AND p.access_revision=? AND p.enabled=1
                    AND n.topic IN (""" + slots + ")", (s.recipient,s.access_revision,*sorted(self.topics)))

    def _visible(self, s, now):
        sql, args = self._subscribed_rows(s)
        return sql+" AND n.available<=? AND n.expires>? AND n.state!='dismissed'", (*args, now, now)

    @staticmethod
    def _continue(db, sql, args, after):
        if after is None:
            return sql, args
        if not _opaque(after):
            raise InboxError("invalid_cursor")
        # Only an anchor still in this reader's exact current scope may continue.
        anchor = db.execute("SELECT n.sequence"+sql+" AND n.notice_id=?", (*args,after)).fetchone()
        if anchor is None:
            raise InboxError("invalid_cursor")
        return sql+" AND n.sequence<?", (*args, anchor[0])

    def page(self, db, resolve, *, now, after=None, limit=20):
        s = self._subject(db,resolve)
        self._clock(now)
        if not _integer(limit,1,32):
            raise InboxError("invalid_limit")
        sql, args = self._continue(db, *self._visible(s, now), after)
        rows = db.execute("SELECT n.notice_id,n.topic,n.resource_ref,n.state,n.available"+sql+
                          " ORDER BY n.sequence DESC LIMIT ?", (*args,limit+1)).fetchall()
        return {"items":[dict(zip(("id","topic","resource_ref","state","available"),r)) for r in rows[:limit]],
                "next":rows[limit-1][0] if len(rows)>limit else None}

    def export_metadata(self, db, resolve, *, after=None, limit=16):
        """Personal export fragment for the app's separately authorized self-export operation.

        Only current subject/ACL/topics. Includes retained dismissed, scheduled
        and not-yet-pruned expired metadata, without granting access to a resource.
        Refreshes authority on every page; never deletes, marks or delivers.
        """
        s = self._subject(db, resolve)
        if not _integer(limit, 1, 16):
            raise InboxError("invalid_limit")
        topics = sorted(self.topics)
        slots = ",".join("?" for _ in topics)
        prefs = db.execute("SELECT topic,enabled FROM inbox_preferences WHERE recipient=? AND access_revision=?"
                           f" AND topic IN ({slots}) ORDER BY topic", (s.recipient, s.access_revision, *topics)).fetchall()
        sql, args = self._continue(db, *self._subscribed_rows(s), after)
        rows = db.execute("SELECT n.notice_id,n.topic,n.state,n.created,n.available,n.expires"+sql+
                          " ORDER BY n.sequence DESC LIMIT ?", (*args, limit+1)).fetchall()
        return {
            "scope": "current_recipient_inbox_metadata",
            "preferences": [{"topic": topic, "enabled": bool(enabled)} for topic, enabled in prefs],
            "items": [dict(zip(("id","topic","state","created","available","expires"), row)) for row in rows[:limit]],
            "next": rows[limit-1][0] if len(rows) > limit else None,
        }

    def mark(self, db, resolve, *, notice_id, state, now):
        s = self._subject(db,resolve)
        self._clock(now)
        order = ("unread","read","acknowledged","dismissed")
        if type(state) is not str or state not in order[1:] or not _opaque(notice_id):
            raise InboxError("invalid_change")
        sql,args = self._visible(s,now)
        row = db.execute("SELECT n.sequence,n.state"+sql+" AND n.notice_id=?", (*args,notice_id)).fetchone()
        if row is None:
            return "not_visible"
        if order.index(state) > order.index(row[1]):
            db.execute("UPDATE inbox_entries SET state=? WHERE sequence=?",(state,row[0]))
            return state
        return row[1]

    def erase_recipient(self, db, resolve):
        """Only this app's current subject. Existing exported copies are outside this store."""
        s = self._subject(db,resolve)
        db.execute("DELETE FROM inbox_entries WHERE recipient=?", (s.recipient,))
        db.execute("DELETE FROM inbox_preferences WHERE recipient=?", (s.recipient,))
        db.execute("DELETE FROM inbox_budgets WHERE recipient=?", (s.recipient,))
