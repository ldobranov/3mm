# Application data tools

Optional, standard-library-only helpers for an application's **own** data. Bundle
`application_data_tools` in its service wheel, as for the optional CRUD library.
Nothing is installed in Core, Agent, or the shared host. There is no upload
endpoint, fallback database, network client or general filesystem access here.

## Import in two steps

1. In an authorized preview operation, read the bounded bytes using the app's
   normal file grant. Declare the column names and types in application code:

   ```python
   from application_data_tools import Column, Limits, preview_import, reviewed_rows

   columns = (Column("label", max_length=80), Column("quantity", "integer"))
   limits = Limits(max_bytes=256_000, max_rows=500)
   review = preview_import(source_bytes, columns, "csv", limits=limits)
   ```

   Show the number of checked/invalid rows and the fixed row/field error codes.
   There are no data values in a review unless the app **explicitly** asks for
   `sample_size=1..3` and has already authorized disclosure. Reported row numbers
   start at 1 **after** a CSV header. A malformed file or an exceeded limit has
   a file-level issue, even when earlier rows were valid. At most twenty row
   issues plus one file issue are returned.
2. Recheck the current actor and destination on confirmation. Read the selected
   file again; pass the reviewed key back to `reviewed_rows(source_bytes,
   columns, "csv", review_key, limits=limits)`. This binds the exact bytes,
   format, ordered schema and limits, and validates *all* rows before returning
   any. The key is a checksum, **not** a session, signature, grant or durable
   command receipt. Apply authorized rows using the app's normal transaction
   and same-request receipt. Recheck domain constraints there; rollback the
   whole import if one row conflicts. Do not retry an ambiguous commit.

Use `progress=callback` only in the reviewed application task: it receives
phase, checked/invalid counts and completion, every 128 rows and at completion.
It carries no data and creates no polling job. An empty valid input is a no-op,
not a delete instruction. There is no partial success after reaching a limit.

## Export

`export_rows(authorized_rows, columns, "json", limits=limits)` or `"csv"`
returns bounded UTF-8 bytes. Select only records **and fields** the current actor
may see, *before* calling it. Inputs must contain exactly the declared fields;
extra business fields aren't serialized. The helper raises on overflow instead
of saving a truncated report. The app decides whether to deliver bytes using
its existing file/task contract. Downloaded copies are outside local erasure.

JSON is the lossless format: a flat array of objects with distinct keys;
strict text, boolean, null, or integer in the interoperable 53-bit range. CSV
requires one exact set of distinct headers (order may differ), lower-case
`true`/`false`, plain decimal integers and a literal `\N` for null. Double
a leading backslash for literal backslash-prefixed text. Empty text stays empty;
empty numeric/boolean cells mean null only for nullable columns. UTF-8 BOM,
escaped quotes, commas and multiline CSV fields are supported. In CSV **export**,
formula-like text and text beginning with a tab or line break receive a leading
apostrophe; numeric columns retain their type. This changes some text for safer
spreadsheet display. Do not use a spreadsheet re-import as a financial or
lossless backup.

Check from the platform root: `python -m pytest -q libraries/data_tools/tests`.
The disposable transaction example covers revoked access, a duplicate on the
last row, whole-import rollback and subject-scoped export. The library does
not implement the application's own permission checks for it.

## Search only a currently visible partition

Use `application_data_tools.search.create_index_schema` in an explicit app
migration. Use `index_document(tx, scope, Document(ref, label, searchable_text))`
in the **same transaction** as a source write. A partition is one group of rows
with exactly the same visibility; do not treat a whole tenant as one partition
if its users cannot all see the same rows. A searchable label is app data too.

```python
page = search_page(tx, query, limit=10, cursor=cursor, current_access=lambda:
    resolve_partition_for_current_subject(tx, operation_context))
```

The app resolver returns `PartitionAccess(scope, revision)` from trusted
current identity and app policy, or `None` when denied. Do not take either
value directly from the browser. Change the revision when that audience
changes. Search checks access before it reads the index; its continuation
belongs only to that revision, partition, query, page size and current index.
The small profile matches up to four Unicode-normalized exact words. It does
not search across applications, rank documents, expose global totals or open
its own database. Return a fresh first page on `stale_cursor`.

For a schema/tokenization change, call `begin_rebuild` with the new version,
source revision and expected record count. Persist its handle in the app. Use
`stage_documents` in batches of at most eight; call `finish_rebuild` only
after reading the current source revision **inside that final transaction**.
The last complete index stays visible until the replacement is complete.
Limits: 32 partitions, 128 documents per partition per generation. Use smaller
batches if the selected SDK profile has tighter transaction or result budgets.
`remove_document` and `erase_partition` remove active data and invalidate a
pending rebuild in the caller's transaction. This is logical local removal,
not a claim about backups, independently exported files or physical media.

## Printable table as a bounded task

The [worker-only reference](examples/report_task/build_reference.py) packages
the renderer into the application's wheel. It takes one opaque reviewed intent
reference, not arbitrary SQL, rows, a filename or a template. The app binds
the first original task run, reads only the intended audience's records, and
rechecks its own approval and data revision before saving the report. The
result is a small receipt (rows, bytes, SHA-256); the artifact remains in the
app's own storage. A subsequent download must **again** check the current actor.
New audience/revision = new reviewed intent. The example seeds no users, data,
rights or scheduled work.

`render_table` returns escaped, self-contained printable HTML, not a PDF or
browser rendering service. It doesn't open URLs or files. The reference limits
one report to 64 rows and 32 KiB. Select only authorized fields before calling
it; rendering is not a security filter. A lost task response is observed using
the original request ID, never by submitting a replacement. The packaged
Linux acceptance test runs the native host and task worker and checks their
actual returned receipt and private artifact.

## Opt-in, in-app notifications

Use [the inbox](application_data_tools/inbox.py) in the application's own
database. Register a short list of topic codes (e.g. `report.ready`) and
initialize the tables in a **new, explicit application migration**. Map each
code to app-localized UI text; an entry contains an opaque resource reference,
not a message body, URL or report. There is no global inbox, automatic
subscription, background poll, email or hardware effect.

1. In an authorized user operation, resolve the recipient **from the current
   actor and current app ACL inside the transaction**, never from a browser
   field. `preference` is initially off. Submit a deliberate
   `set_preference(..., expected=previous["revision"])`; on
   `preference_changed`, reload the choice, do not automatically confirm.
2. When reviewing the business operation, bind its original opaque event and
   resource IDs to `capture_consent`, the intended recipient and ACL revision.
   Keep this intent in the app. A later opt-in is not permission to send an old
   event. Resolve current authority again before publication. Persist the
   delivery result **in the same write transaction** as `publish`.
3. Read `page` on request, not on a timer. Pages only contain this recipient's
   available, unexpired, undismissed entries under the current subscription.
   On `invalid_cursor` reload the first page. Reading never marks, sends or
   retries. Explicit `mark` advances, never reverses, read/acknowledged/dismissed.
   Opening the business record must independently check its current ACL.
4. Prefer an approved task or the original business transaction for deferred
   notices. The [report integration](examples/report_task/notice_integration.py)
   shows durable original-intent delivery, a read-only status, opt-out and
   revocation. At most three delivery attempts, with 60/120-second backoff on
   temporary limits; after a day pending notices are ineligible and their
   receipt rows can be reclaimed by explicit cleanup.
   Merely installing the source does **not** schedule a task. Invoke
   `deliver_original` and `prune` from the app's authorized workflow.

   If delivery must run later, the reference also supplies `run_delivery_task`.
   Package it beside the service with the vendored inbox and declare an
   internal, bounded `deliver_notice` task. Its only input is the original
   `report_ref`; no caller-supplied time, recipient or destination. Submit
   through the normal approved task binding and keep the original request ID
   for lookup. A finished worker returns only a disposition (e.g. `recorded`,
   `not_subscribed`, or `not_eligible`), not the report or recipient. Platform
   task success means the check ran, not that the notice was delivered. A
   `deferred` disposition does not enqueue another task; any later authorized
   attempt still uses the same local intent, deadline and delivery budget.

   To opt into a bounded retry schedule, apply the separate app migration
   `migrate_retry_windows` and enable the normal schedule binding for this task.
   After a real deferral, in an authorized app operation:

   ```python
   with application.storage.transaction() as tx:
       plan = claim_retry_window(tx, current_audience=resolve_actor, ref=ref, now=now)
   if plan is not None:  # commit the original ID BEFORE calling the platform
       client.create_task_schedule(**plan)
   ```

   The plan permits at most two more occurrences and never extends the original
   expiry. On a lost response or process restart use `retry_lookup_key` under
   fresh authority and `client.lookup_task_schedule("deliver_notice", request_id=key)` if there
   is a key. An absent schedule is not proof of non-execution: do not create
   a replacement. Opt-out or loss of report access stops delivery even if the
   scheduler already admitted the work. No background polling is needed.

Defaults are 64 entries per recipient, 4,096 per app, 1,024 preferences,
12 deliveries per recipient per minute, and seven days maximum lifetime.
Retention deletes bounded batches; an expired entry immediately disappears on
read even before cleanup. Dismissed entries still deduplicate until expiry.
The sample deletes a notice and pending intent when its original report is
deleted. Use the app's own personal-data declaration, export and erase flow
for **all** data it owns. Local erasure does not remove backups or other copies.

For an application's separately permission-checked **self-export**, call
`Inbox.export_metadata(tx, resolve_current_recipient, after=cursor)`. It
returns up to 16 entries per page (newest first) and the current saved topic
preferences. Unlike the display inbox, it includes scheduled, dismissed and
expired-but-not-pruned metadata that the current audience still owns.
It returns timestamps and state, never business content, resource/event
references, consent tokens or another subject's rows. Recheck permission
and audience on **every** page. If a continuation becomes invalid after
opt-out, revision change or erasure, restart from a newly authorized first
page; do not stitch in stale pages. For a consistent bounded snapshot use a
single read transaction within the application's existing limits.
This is only an inbox fragment: authors must account for other retained data
(including restricted older records, intents and already exported copies) in
their own policy. Do not attach the user's export to general support logs.
