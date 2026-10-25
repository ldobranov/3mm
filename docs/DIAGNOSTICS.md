# Redacted diagnostics

The Milestone 11 diagnostics bundle is an administrator-only JSON download for
troubleshooting one Standalone device. It is generated in memory and is not
persisted by Core.

Included information is deliberately narrow:

- installed version, release metadata and shared protocol version;
- operating system, architecture, Python version, CPU count, load and memory;
- total, used and free storage;
- SQLite integrity and migration revision;
- loopback Agent health and a one-way device fingerprint;
- latest non-secret backup operation state.

The generator does not read environment values, NetworkManager profiles,
application logs, database rows, uploaded files, extension payloads or backup
contents. Password, passphrase, secret, token, API-key, credential,
authorization, cookie and private-key fields are recursively replaced with
`[REDACTED]`. Common inline bearer, assignment and URL-userinfo forms are also
redacted before deterministic JSON serialization.

The API is restricted to administrators:

- `GET /api/v1/diagnostics/preview` returns the checks and expected size;
- `GET /api/v1/diagnostics/bundle` downloads the redacted JSON document.

The Settings page uses the authenticated API client, so diagnostic data is not
placed in a public URL or browser navigation history.


## Operation workspace and development (P5, 2026-10-24)

Settings → Support diagnostics now includes component observations, Core service
state, a temporary recording session and a shared operation timeline. Core's
running version and live Runtime/Agent/public responses are distinct from passive
installed pins. Connector/application-host/session process health stays **not
observed** until independently checked; a listener or installed artifact is not
provider readiness. A busy/unavailable observer is explicit. Refresh is manual.
The screen supports current themes, mobile layout and the Bulgarian language
extension; English remains the recovery base.

Detailed recording is off at process startup. Diagnostic/development profiles
use the same safe limits: default 600 s, maximum 1800 s, one 1 MiB process buffer,
10 events/s and 2048 bytes/event. Stop retains an exportable snapshot until its
TTL; expiry is enforced at capture/status/export and restart starts inactive.
No persistent spool is created. Choose an operation, application instance or trace
scope through the current admin API. The GUI exposes operation/instance selection
and a trace filter. A development profile is a label and scope, never extra rights.

All current signed SDK actions can record their SDK/Core transport hop. The
application HTTP/callback relay records admission, dispatch and response stages.
Only fixed operation/stage/result/reason labels, version, generated trace/span IDs,
optional validated instance ID, timestamp and duration enter records. Bodies,
secrets, paths, SQL, terminal/PTY data and arbitrary exception/log strings are
excluded. The support bundle remains separate from detailed records.

The timeline combines current Core records with **one explicitly imported producer
NDJSON export**. It labels imported records as snapshots, shows producer drop
counters, missing producers and truncation, and can save the merged JSON snapshot.
Core does not silently enable recording in other processes. Runtime/Agent/session
traces absent from the selected exports remain missing. Imported metadata is an
observation, not authenticated authority or live state. Producer wall clocks can
differ; a shared trace ID correlates one transport hop, not a whole business
transaction. Current-format imports require the current scope/instance fields.

All endpoints below require a current admin login and use no-store responses:

| Endpoint | Purpose |
| --- | --- |
| `GET /api/v1/diagnostics/workspace` | Fixed component pins/versions, bounded local observations and Core services |
| `POST /api/v1/diagnostics/session` | Explicit TTL/profile/operation/instance/trace scope |
| `GET` / `DELETE /api/v1/diagnostics/session` | Inspect / stop the Core recording |
| `GET /api/v1/diagnostics/session/records` | Bounded Core NDJSON download |
| `GET /api/v1/diagnostics/timeline` | Current bounded Core timeline |
| `POST /api/v1/diagnostics/timeline/merge` | Validate one NDJSON export and return a combined snapshot |

The observer has one non-queued slot, including metadata reads, and fixed loopback/
Unix probes with absolute deadlines (Runtime 0.4 s, Agent/public 0.3 s each).
No auth DB transaction spans those probes. Merge has one non-queued slot, a 4 MiB
input cap and five-second upload deadline; decoding runs outside the Core event
loop. The response displays at most 500 records. Imports are not retained in Core.
Malformed labels, extra fields, duplicate JSON keys, non-finite values and foreign
formats are refused. Collector failure cannot replace an operation's result.

For an independently started SDK recorder, use the normal client credentials;
diagnostics neither supply nor change them:

```python
from three_mm_application_sdk import SDK_VERSION, ApplicationPlatformClient
from three_mm_protocol.diagnostics import DiagnosticSession

records = DiagnosticSession("sdk", SDK_VERSION)
records.start(300, profile="development", operation="installation.identity.get",
              instance_id=instance_id)
client = ApplicationPlatformClient(socket_path, instance_id, secret, diagnostics=records)
# Perform the already authorized operation, then export explicitly.
with records.export() as chunks, open("sdk-records.ndjson", "xb") as output:
    for chunk in chunks:
        output.write(chunk)
```

## Offline and independent development commands

The installed local path works with Core stopped. From the current deployment
folder, using its Python environment (or the Node protocol environment):

```bash
python -m three_mm_protocol.diagnostic_snapshot --output /tmp/device-observations.json
python -m three_mm_protocol.diagnostic_snapshot --records sdk-records.ndjson --output /tmp/with-sdk-records.json
```

It reads only fixed component metadata and the explicit bounded export, imports
neither backend nor SQLAlchemy, and never contacts Core, starts services, reads
logs or changes networking. An absent Core is listed as missing. Installed pins
are passive observations with unknown process health. Output uses exclusive create
and cannot overwrite an existing report. `python -m tools.debug_snapshot` is the
source-tree alias.

The development CLI uses existing validation/upload/activation APIs. Select an
**explicit owned isolated Core URL**; the command does not start a lab server.
Tokens are prompted hidden and never saved, placed in URLs or retried. HTTPS uses
normal certificate verification; HTTP is restricted to loopback, redirects/proxies
are disabled, and a mutation timeout is unconfirmed. Current native review, UI
trust, grants, lifecycle and data rules remain mandatory.

```bash
python modules/public-web-reference/build_reference_package.py --output .runtime/public-a.zip
python -m tools.extension_dev validate .runtime/public-a.zip
# Run affected checks with tools/dev_lab.py before local activation.
python -m tools.extension_dev --url http://127.0.0.1:18887 upload .runtime/public-a.zip
python -m tools.extension_dev --url http://127.0.0.1:18887 activate <exact-archive-sha256>
python -m tools.extension_dev --url http://127.0.0.1:18887 trace-start --operation application.invoke --ttl 300
python -m tools.extension_dev --url http://127.0.0.1:18887 trace-export --output .runtime/core-records.ndjson
python -m tools.extension_dev --url http://127.0.0.1:18887 trace-stop
python -m tools.extension_dev --url http://127.0.0.1:18887 rollback <previous-archive-sha256>
```

Port 18887 is an example for a separately started disposable Core. Activation and
rollback each explicitly select exact uploaded bytes. Rollback requests the old
package through the same lifecycle rules; it is not permission to reset data,
downgrade a schema or replay effects. Keep each package's own data and outcome
receipts. Source builds, local tests and compatible component/package iteration
require no Core release or global development mode.

Local P5 acceptance runs two existing neutral packages (application-reference and
public-web-reference) with real native hosts, signed HTTP/Runtime calls, a fixed
Core/Runtime process, A→B→A and failed-candidate recovery. The compatibility package
fixtures are explicitly prepared in the disposable lab; they do not replace native
review acceptance. A separate current scoped SDK read succeeds then remains denied
after revocation while diagnostics is active. Read-only restored-host readiness is
observed before explicit outcome review. See WORKING_STATE.md for exact source,
artifacts and targeted evidence; installed/ARM/ARMv6/full-CI acceptance remains P6.
