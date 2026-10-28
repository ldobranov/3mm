# Application files and media — CAP11

The streaming profile is `storage.private_files.file_contract_version: 2` in a
manifest-v2 application using service SDK 1.3. Browser host version 1 exposes
`useApplicationHost().files` from `@3mm/application-ui/v1`. Version axes are
independent. Core admits operations; the application's separate `files.sock`
worker owns bytes, metadata, uploads and image jobs. Core never accepts a host
filesystem path. Existing small, native SDK file-contract-v1 access remains a
separate supported profile; browser file access requires profile 2.

## Declaration and authority

```json
{
  "file_contract_version": 2,
  "namespace": "private_files",
  "mode": "read_write",
  "max_file_bytes": 8388608,
  "max_total_bytes": 33554432,
  "max_files": 64,
  "max_uploads": 2,
  "max_staging_bytes": 16777216,
  "upload_ttl_seconds": 3600,
  "public_links": true,
  "media_transforms": true
}
```

Hard profile ceilings: 1 GiB/file, 4 GiB committed content, 4096 files, 16 active
uploads, 2 GiB reserved staging, upload lifetime 60–86400 seconds. The staging
budget must hold a maximum-size file. Filenames are display metadata, up to 240
UTF-8 bytes without separators/control characters; logical IDs match
`[a-z][a-z0-9_]{0,63}`. MIME metadata does not authorize active inline content.

The existing sealed authority family now distinguishes
`storage:private_files_read`, `_write`, `_publish` and `_transform`. The last two
require their explicit declaration flags and start unselected in fresh normal
package consent. Saved choices remain exact. A writable grant does not grant
public sharing or image processing. Native-code consent and same-origin UI risk
remain explicit; this cooperative helper is not hostile-code isolation or an OS
disk quota.

An operator/administrator UI route additionally opts into `private_files` with
`contract_version: 1`, `read_permission`, and optional `write_permission`,
`publish_permission`, `transform_permission`, each naming a declared human
permission. Public/kiosk application routes cannot opt in. Every browser request
pins the source package, compiled UI build and entrypoint and checks a live user
session plus current route/permission access. Platform administrators can pass
human permission checks; they still require the application's current service
grant. Upload ownership binds user and application incarnation; another user or
installation cannot resume it. Completed files belong to the application
namespace and are shared according to its declared human read permission.

## Streaming, interruption and receipts

`begin` reserves bounded staging and returns an opaque upload ID with expiry.
It records total size, SHA-256, logical file ID, filename/MIME and expected old
digest (`null` means create only). `append` accepts at most 256 KiB at an exact
offset. File data uses raw HTTP bodies; bounded internal chunks travel over the
separate signed file transport. No unlimited base64 operation payload is used.

The target fsyncs each chunk and atomically commits the acknowledged offset.
Explicit `uploadStatus` after reconnect/restart observes that offset. Repeating
the last exact chunk is idempotent; a different chunk or old offset conflicts.
An unacknowledged crash tail is truncated to the committed offset before the
next admitted append. The SDK does not retry a failed mutation automatically.
The caller must reselect/verify the same source file before resuming.

`finalize` verifies the full size/checksum, current CAS revision and committed
quotas, writes an immutable blob and switches the atomic metadata index. The old
file remains visible until that switch. Interrupted/bad uploads never appear in
the file list and never replace the old file. Expired/cancelled uploads release
their reservation; known orphan temporary files are collected on the next file
operation or explicit `cleanup`. No cleanup daemon or device network dependency
is needed. Missing/corrupt metadata and unknown/symlink/hardlink entries fail
closed for recovery review; they are not silently reset.

Core retains sealed metadata receipts for non-idempotent mutations before target
dispatch, including begin/finalize/delete/link/transform. Reusing their request
ID yields historical metadata, never another dispatch. A lost acknowledgement
stays `execution_unconfirmed`; `operationStatus(requestId)` observes it. Inspect
the file/upload/job before a fresh user intent; an old receipt is not a right to
read bytes. Append offsets are durable in the target and do not spend one Core
journal entry per chunk. Target receipt/link/job histories are bounded at 2048
each, the metadata index at 4 MiB, and the existing Core installation action
journal at 4096. Exhaustion refuses new work rather than forgetting uncertainty.

Committed quotas cover originals and derivatives; staging reservations are
separate. Durable finalization may temporarily need an additional copy of one
file; metadata, journals, snapshots and rollback evidence also consume disk.
Administrators must provision that headroom. This is not a hard filesystem quota.

## Download, preview and sharing

`list(after)` returns up to 100 metadata records; its cursor is a logical ID,
not a snapshot, so changes between pages may alter the listing. `stat` returns
the pinned revision. HTTP full downloads stream bounded chunks; SDK `download`
returns a `ReadableStream` and verifies chunk and full-file checksums when the
consumer reads to EOF. Partial reads do not claim whole-file verification.
Python uses `iter_read(file_id, sha256)`. Browser hashing works on HTTP LAN
without `SubtleCrypto`/`randomUUID`; capability IDs use `getRandomValues` only.
The public host exposes neither account credentials nor a raw HTTP client.

All files download as attachments with no-store/nosniff headers. The consumer
may preview a verified generated image derivative as an image Blob; arbitrary
HTML/SVG/PDF is not executed in a Core page. Full HTTP downloads expose the
checksum header for other clients to verify. Current user/service/link access
is checked per chunk; already admitted bytes cannot be recalled.

`createLink` requires publish authority and creates an exact-file-revision
capability with a 1–86400 second lifetime and 1–1000 download sessions. It does
not make the application UI public. A 256-bit random secret lives in the URL
fragment, never a query string or server access-log URL. The small Core landing
page clears the fragment and submits it in a bounded POST body when the visitor
chooses Download. Only a secret hash is stored. The landing page has a restrictive
CSP and no referrer; content remains an attachment. Read-only public admission
does not grant upload, list or account access. Link metadata/IDs alone are not
bearer secrets. Do not paste a full capability link into logs.

The creator can revoke a link. Expiry is persisted as revoked when observed, so
clock rollback cannot revive an observed-expired link. Links pin application
incarnation, source package, current authority epoch/grant revision and file SHA.
File replacement/deletion, grant revoke/regrant, disable, uninstall, native trust
loss or recovery fencing stops new link admissions. A failed creation reply does
not automatically mint another secret/link. Reuse its request ID to inspect the
receipt and explicitly revoke/create a new link if needed.

## Optional image provider

The built-in `pillow_image_v1` profile thumbnails/resizes one PNG/JPEG/WebP image
to at most 4096×4096, and converts to PNG/JPEG/WebP. Input/output are at most
16 MiB and 16 megapixels; animation is refused. EXIF orientation is applied and
embedded metadata is stripped. A separate child has CPU, address-space, output
size and wall-clock bounds (5 CPU seconds, 512 MiB, 10 wall seconds). Core never
imports Pillow or decodes images. Missing/broken provider or corrupt input fails
the job while ordinary files and Core administration remain available.

Jobs retain source logical ID/SHA, parameters, provider revision and output
logical ID/SHA. Originals remain untouched. Derivatives count against ordinary
file quotas and retain an `origin`/job reference even if the original is later
deleted. A worker interruption leaves an explicit `execution_unconfirmed` job;
there is no automatic transform replay. Other media provider profiles can be
added independently of an application's business operations.

The optional dependency is separately locked in
`deployment/application-media-requirements.txt`. A native application-host build
can include it with `python -m deployment.application_host_component build
--source <source> --output <artifact> --image-provider`. The normal host/Core
dependency closure remains unchanged when that flag is absent. Building is
separate from installing an artifact; no host update is implicit.

An administrator can explicitly publish an already verified native artifact for
future instances with `deployment.application_host_component publish-default`.
It uses the shared release lock and a pointer journal, retains the previous
default and preserves every existing per-instance pin. `recover-default`
reconciles an interrupted publication; it starts no services. A Core upgrade's
bootstrap deliberately does not replace an existing default automatically.

## Data lifecycle and local acceptance

The target owns `data/sdk-media`, independent of SQLite and small-profile
`data/sdk-files`. Choosing profile 2 does not import, erase or rename existing
profile-1 data; an application changing its storage layout needs an explicit
quiescent application migration. No Core DB schema/reset is involved here.
Existing disable/uninstall retains application data pending explicit erasure;
retention never grants access or preserves an old public capability. Explicit
application-data erasure removes the owned namespace with the rest of its data.
Activation snapshots include media metadata, originals, derivatives and partial
uploads through bounded streaming copies and validate before rollback switching.
Candidate data remains as recovery evidence. Existing immutable release/rollback
and authority-fence rules apply.

`modules/file-probe` is a separate manifest-v2 consumer with no device commands,
connectors or automatic menu additions. It demonstrates <=8 MiB uploads,
pause/reselect/resume, checksum-confirmed finalize/download, metadata, temporary
links/revoke and optional image derivatives/preview. Its ZIP is built locally;
it requires the new Core/host and explicit application access. Device/browser
acceptance belongs to the owner; this CAP11 scope performs no deployment.
