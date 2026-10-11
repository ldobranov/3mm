# WP4 Test — Manifest v2 / Application SDK 1.3

Neutral test package: `org.3mm.wp4-test` · `1.0.0` · Core runtime · any architecture.
Manifest v2 is the outer package format; `application_extension_version: 1`
is the separate application-definition contract, not a downgrade of the manifest.

No own frontend or navigation entry, devices, connectors, event publications,
subscriptions, peer access, secrets, jobs or automatic actions. Installing starts
only the usual application host and its health check. It creates a minimal **own**
bootstrap SQLite schema, not business data or Core tables. It does not declare
scoped relational access and does not prove that unfinished WP4 boundary.

The only requested scoped resources are the application's private files:

| Limit | Value |
| --- | --- |
| Mode | Read/write |
| Per file | 1,024 bytes |
| Total content | 4,096 bytes |
| File count | 4 |

The manual probe uses one logical file, `probe`, with synthetic text at most 256
characters. Code refuses a legacy direct-file adapter: missing authority never
becomes a filesystem fallback. Native Python code is **not sandboxed**; inspect
the source before recording any local code trust. No trust or grants are shipped.

## 1. Safe first test on the backed-up disposable VM

1. In **Extensions → Inspect package**, select `wp4-test-1.0.0.zip`. Confirm Manifest
   v2, identity/version and the bounds above. Inspection alone must not install it.
2. Upload/install using the ordinary Extensions workflow. Require `Active` and a
   healthy application. CME, Fleet, themes, device identity and their modes must
   remain unchanged. No new menu link for this headless fixture is expected.
3. Run the helper from WSL (no sudo, no extra Python packages):

   ```bash
   cd /mnt/c/Users/LAZ-DELL/Desktop/3mm
   python3 modules/wp4-test/probe.py echo
   python3 modules/wp4-test/probe.py get
   python3 modules/wp4-test/probe.py status
   ```

   Enter the **Core administrator email/password**, not the Linux account. The
   helper talks only to `http://127.0.0.1:8887`; credentials are prompted and are
   never printed, persisted or sent to another origin. Each invocation creates
   an ordinary Core login session. It does not retry requests or approve rights.

   Expected: echo returns `{"message":"WP4 test"}`; get returns `blocked` before
   explicit scoped adoption. This refusal is a successful negative test.

4. Open **Application access** for this fixture. On beta.45, a missing review key
   still produces the known generic error/HTTP 409. Core beta.46 instead shows the actual mode and
   a blocked-review reason. Neither creates a key or grants. A supported fixture
   does not make CME/Fleet eligible for the same scoped adapter.
5. Disable/re-enable the test package and restart Core on the disposable VM;
   repeat echo/get and recheck unrelated applications and identities. No extra
   file write or grant is expected just from installation, restart or inspection.

## 2. Explicit rights test — separate administrative step

Use the local Core key/native-review administration and Authority Apply guide
linked below. Do not edit grant rows or provision keys merely to suppress an
unsupported business application's warning. Review this exact test artifact and
record a real code-review document; this README is instructions, not an attestation.

Verify backup, disable the **test** application, create the native review, then
review/approve/apply the exact read and write bindings. Approval alone must not
apply access. Re-enabling changes the authority epoch; make a fresh review after
start before expecting effective access. No helper here automates that sequence.

With current effective rights:

```bash
python3 modules/wp4-test/probe.py get
python3 modules/wp4-test/probe.py put --request-id 11111111111111111111111111111111
python3 modules/wp4-test/probe.py receipt --request-id 11111111111111111111111111111111
python3 modules/wp4-test/probe.py get
```

For a **fresh** installation/file, expect missing → stored → completed receipt →
found with `WP4 test` and its SHA-256. The fixed ID above is for this one test only;
record a new ID before a different write. If the file already exists, use the
reported current digest with `--expected-sha <digest>` and a new persisted ID.

Repeat the exact same `put` with the same ID/body: historical receipt, not another
write. Change the text under that ID: refuse/unconfirmed, never overwrite.
Revoke the rights: get/new put must no longer succeed; old receipt remains history.

`unconfirmed` means the helper cannot prove whether a write happened (including
denied or lost transport replies). Never treat it as success or repeat with a
new ID. Inspect the same receipt first. No test script automatically repairs keys,
adopts applications, reconnects business resources or retries an uncertain write.

## Build and automated verification

From the checkout root with development dependencies available:

```bash
PYTHONPATH=. python3 modules/wp4-test/build_test_package.py --output dist/wp4-test-1.0.0.zip
python3 -m pytest backend/tests/test_wp4_test_extension.py backend/tests/test_application_authority_status.py -q
```

The builder normalizes source line endings, fixes archive metadata, generates a
wheel RECORD and computes the actual wheel digest. It validates the final ZIP
using Core's normal package validator before writing it. Generated ZIPs are not
shipped in Core release packages; upload this extension separately.

Automated POSIX test uses this **exact built ZIP**, real native reviews/grants,
the signed SDK/platform transport and separate private-file worker. It checks
pre-grant refusal, explicit access, same-ID receipts, conflict and revocation.
It does not replace human VM/Hub acceptance, prove sandboxing, or close WP4/M20.

References:

- [Beta acceptance](../../docs/EXTENSION_PLATFORM_V2_BETA_ACCEPTANCE.md)
- [Local key administration](../../docs/EXTENSION_PLATFORM_V2_REVIEW_KEYS.md)
- [Authority Apply](../../docs/EXTENSION_PLATFORM_V2_AUTHORITY_APPLY.md)
- [Private files](../../docs/EXTENSION_PLATFORM_V2_PRIVATE_FILES.md)
