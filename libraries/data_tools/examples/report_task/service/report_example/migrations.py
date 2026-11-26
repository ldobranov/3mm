from packages.application_sdk import ApplicationMigration


def initialize(db):
    db.execute("""CREATE TABLE report_subjects(
        subject_ref TEXT PRIMARY KEY, allowed INTEGER NOT NULL CHECK(allowed IN(0,1)),
        access_revision INTEGER NOT NULL, data_revision INTEGER NOT NULL)""")
    db.execute("""CREATE TABLE report_items(
        subject_ref TEXT NOT NULL, item_id INTEGER NOT NULL, label TEXT NOT NULL,
        quantity INTEGER NOT NULL, PRIMARY KEY(subject_ref,item_id))""")
    db.execute("""CREATE TABLE report_requests(
        ref TEXT PRIMARY KEY, subject_ref TEXT NOT NULL, access_revision INTEGER NOT NULL,
        data_revision INTEGER NOT NULL, original_run TEXT, content BLOB, rows INTEGER,
        size_bytes INTEGER, sha256 TEXT)""")
    db.execute("CREATE INDEX report_requests_by_subject ON report_requests(subject_ref)")
    # A new approval is a new request. Never rebind existing report bytes to
    # another audience or to later ACL/data revisions.
    db.execute("""CREATE TRIGGER report_intent_immutable BEFORE UPDATE OF
        ref,subject_ref,access_revision,data_revision ON report_requests BEGIN
        SELECT RAISE(ABORT,'new_report_request_required'); END""")


def get_migrations():
    return [ApplicationMigration("0001", initialize)]
