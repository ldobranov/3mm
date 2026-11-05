# Public Web Runtime & Extension Contract

Status: **GET/HEAD baseline completed on 2026-10-07**. Physical Raspberry acceptance passed on runtime commit `996760f6`. The bounded CAP10 form profile below is a separate local change.
Milestone: 19
Base: `401372c6` / `0.3.0-beta.40`

## Goal

Let 3mm safely host public web applications as separately installed
Application Extensions without teaching Core about a website, shop, blog,
product catalog, SEO provider, search engine or frontend framework.

A completed milestone must make a later public application able to own its
public pages, machine-readable resources and redirects without adding
application-specific routes or handlers to Core.

## Boundary

Core owns only the public web mechanism:

- a versioned public HTTP contract;
- public route registration and conflict detection;
- dispatch to an active supervised application service;
- request normalization, response validation and resource limits;
- public-surface lifecycle, isolation and recovery;
- generic host/surface ownership needed to keep administration recoverable.

Extensions own all public content and domain meaning. A future shop may produce
product pages, metadata or XML resources, but Core must not contain shop, SEO,
Google, product, category or sitemap behavior.

The existing administrative SPA remains Core-owned. Public web serving must not
give an extension control of Core authentication, settings, recovery or API
namespaces.

## Baseline

The current `three_mm_web` service is a static SPA server. A missing
extensionless path falls back to `frontend/dist/index.html`; a missing resource
such as an XML file does not. Application Extension v1 already exposes public
JSON operations through the Core API, but an extension cannot own an ordinary
HTTP GET path, return HTML/XML/text with a real status code, or issue a redirect.

Therefore a public website can be approximated as a client-side SPA today, but
a complete public web application cannot be implemented as an isolated
extension without additional generic platform support.

## Design rules

1. Public web is an optional platform surface, not the normal Core UI.
2. Application services remain outside the Core process.
3. An extension never registers a FastAPI router or opens an unmanaged listener.
4. Routes are declarative, bounded and validated before activation.
5. A public page uses an isolated `public` query operation. Anonymous POST is
   available only for the explicitly reviewed, bounded form profile below.
6. The public gateway forwards only a small normalized request model. Core
   sessions, administrator cookies, Authorization and raw internal headers are
   not forwarded.
7. Responses use a closed versioned model. Extensions cannot control transport
   headers such as `Connection`, `Content-Length`, `Set-Cookie` or CORS.
8. Route conflicts fail closed. There is no last-installed-wins behavior.
9. Disable, rollback and uninstall update route ownership transactionally.
10. A failed public extension cannot make the administrative/recovery surface
    unavailable.
11. No bot-specific rendering or crawler detection belongs in Core.
12. The first reference package is neutral and must not introduce a concrete
    product or SEO branch.

## Contract v1

`ApplicationPublicHttpRouteV1` declares:

- stable route ID;
- a bounded path template;
- GET/HEAD methods only;
- one public query operation;
- explicitly allowed response content types;
- a per-route response-size ceiling.

Path parameters occupy a complete segment, for example
`/items/{slug}`. Catch-all parameters, encoded templates, dot segments,
trailing-slash aliases and ambiguous duplicate parameters are rejected. Unicode
literal segments remain possible; runtime URL decoding and canonicalization are
owned by the gateway.

`ApplicationPublicHttpRequestV1` carries only:

- method;
- normalized path;
- path parameters;
- bounded query values;
- an allowlisted subset of request headers.

The first header allowlist is intentionally small: `Accept`,
`Accept-Language`, `If-None-Match` and `If-Modified-Since`.

`ApplicationPublicHttpResponseV1` supports a bounded set of normal page,
redirect, client-error and service-error statuses. Text bodies cover HTML, plain text, CSS, JavaScript, JSON, manifests and
XML/feed formats. Bounded base64 bodies cover common web images, fonts and PDF
documents without widening the application service's general transport limit.
A route can opt into at most 512 KiB of decoded body data; the default is
256 KiB. Response headers are allowlisted to generic caching/content metadata. Redirect location is a dedicated field rather than an
arbitrary header.

The GET/HEAD handler's declared operation schemas must match the v1 public HTTP request
and response schemas exactly. This keeps package review deterministic and avoids
a new Core branch for every public application.

### CAP10 — bounded anonymous form

An application can declare one literal public route with `form_operation_id`.
GET/HEAD renders the form; POST on that exact path calls the dedicated anonymous
command. A command declares a closed object of 1–8 required, bounded single-line
strings. It cannot be invoked through the administrative application API. The
form profile declares no platform effects or external providers; the reference
uses only its own SQLite database. Native code still requires review and this is
not a sandbox. An exact active package and a current sealed application approval
are checked at admission and again before the result is confirmed.

POST is disabled by default. An explicitly configured listener accepts only its
exact `Host` and `Origin`, UTF-8 URL-encoded form fields and a single bounded
`Content-Length` (4 KiB maximum; 3 seconds to read the body). There is no cookie,
authorization, source-IP or forwarded-header field in the application payload.
The prototype permits four concurrent submissions, 12 per socket peer and 120
total per 60-second window. This is an abuse bound, not authentication or
edge protection; all clients behind one proxy share that peer's budget. TLS,
external ingress, trusted proxy identity, guest/customer sessions and payments
are not configured by this change.

The form carries `_request_id`, a random 32-character lowercase hex string. It
is not a credential. The reference stores the key and choice in one SQLite
transaction: same key and value confirms the original record, different value
is refused. At 1,024 records it refuses new records without removing old keys.
A lost result or access revoked after admission may leave a committed record;
no layer automatically repeats the submission. The reference build and local
acceptance procedure are in the [form README](../modules/public-form-reference/README.md).

### CAP10 — temporary guest draft

`guest_session: true` opts the bounded form profile into a temporary guest
context. The declaration must explicitly list `methods: ["GET"]`, an ASCII
literal path and an HTML page; POST still uses `form_operation_id`. There is no
guest context on HEAD, other routes, Core's application API or authenticated
operations. The application reads `context.public_guest` on the current SDK
1.3 host: `guest_id` and `expires_at` only. The actor stays anonymous and has no
Core, user or platform permissions.

Enable it only on a dedicated form origin with `--form-origin` and
`--guest-forms`. Core issues a signed 15-minute cookie after a successful
reviewed GET. It is bound to the exact origin, route, package, installation and
authority epoch, and stops working after a Core restart. GET does not extend
its expiry. Only Public Web sets the cookie; the native application never
receives the raw credential. HTTPS uses a host-only `__Host-` cookie with
`Secure`, `HttpOnly` and `SameSite=Strict`; use a separate hostname from admin
and other mutually untrusted sites, since cookies do not isolate by port.
[HTTP cookie prefix rules](https://httpwg.org/http-extensions/draft-ietf-httpbis-rfc6265bis.html#name-the-__host--prefix).
Plain HTTP is restricted to a loopback test listener and uses a path-scoped lab cookie.

The app includes the verified guest ID as a hidden `_guest_id` field. POST
still needs the exact Origin and must present both the valid cookie and the
matching form field. The field is not a credential, is not passed in the app
payload, and must not be used in URLs. This prevents an old tab submitting a
draft into a different guest session. Expired, missing or tampered proof is
refused before dispatch. No cookies are issued on approval failure or on POST.

The [guest draft example](../modules/public-guest-reference/README.md) stores
only a preset choice in app-owned SQLite, scoped by guest ID. Reusing a request
ID for that guest cannot add a second record. Expired drafts cannot be resumed;
their rows are pruned on a subsequent valid write. This is not a customer
account, login, permanent draft, reverse-proxy setup or data-erasure service.
Guest mode requires coordinated Core, Runtime, Public Web and application-host
builds and stays off in the standard service configuration.

### CAP12 — signed callback verifier (local contract only)

The initial profile verifies machine-to-machine POST bytes. Its standalone
loopback lab does not register a route in the installed Public Web service,
enable an existing form endpoint, or dispatch to an application. The reference
profile is not an adapter for a vendor's own signature format.

- An endpoint has a locally configured audience (32 lowercase hex characters)
  and its own independently generated 32-byte secret. Only trusted endpoint
  configuration selects these values. Neither value is inferred from Host,
  query parameters, a browser session, or a caller-selected key.
- The sender supplies a stable event ID (1–128 characters, starting with an
  ASCII letter or digit; the rest may also contain `_.:-`), a canonical
  positive Unix timestamp in seconds (1–11 ASCII digits, no leading zero),
  and a signature `v1=<64 lowercase hex digits>`. The verifier allows up to
  300 seconds of age and 30 seconds of future skew. The body is 1–65536 bytes.
- The MAC is HMAC-SHA256. Sign the ASCII fields
  `3mm.webhook.v1`, `POST`, audience, timestamp and event ID, each followed by
  a single LF, then append the raw body with no decoding, reserialization or
  additional LF. The proof contains the body digest, not the body or secret.
  An independent signing vector lives in the protocol tests.

The lab listens only on IPv4 loopback and accepts only its literal POST path:
`/webhook` in standalone mode or the reviewed package's path below. It needs
the exact loopback Host, one Content-Length, and
`application/octet-stream`. Supply exactly one of each signed header:
`X-3mm-Webhook-Id`, `X-3mm-Webhook-Timestamp`, and
`X-3mm-Webhook-Signature`. No browser credentials, transfer/content encoding,
or query string. The listener uses one worker with an absolute read deadline
and rejects an oversized declared body before reading it.

The dedicated SQLite inbox uses a versioned lab schema, not a Core migration.
It commits the body and one receipt per event ID before `202`. A freshly signed
retry with the same body returns the original receipt, even after the raw body
is removed; a different body for that ID returns `409`. Verification always
precedes lookup. `202` means originally accepted, not processed by an application
or guaranteed to remain deliverable. Storage/commit failures cannot return `202`.
Use only synthetic bodies in a private disposable directory; stop the lab before
changing the key. Other audiences and unrelated databases are not overwritten.

From the repository root, run the real loopback/SQLite test (including a
process restart) without a live device or external service:

```sh
python -m pytest -q tools/tests/test_webhook_lab.py three_mm_protocol/tests/test_public_webhooks.py
```

To run just the lab manually, provide an existing private state directory, a
32-hex audience and a file containing exactly 32 random bytes:

```sh
python -m tools.webhook_lab --state-dir "$CAP12_STATE_DIR" --audience "$CAP12_AUDIENCE" --key-file "$CAP12_KEY_FILE"
```

The URL printed by the lab has an ephemeral port. Do not proxy or expose it.
The CLI remains synthetic and has no Core configuration.

An SDK 1.3 manifest-v2 package may opt in through `application-extension.json`:

```json
{
  "public_webhook": {
    "contract_version": 1,
    "webhook_id": "receive",
    "path": "/webhooks/demo",
    "signature_profile": "hmac_sha256_v1",
    "handler_operation_id": "receive_event"
  }
}
```

This is a bounded, resource-free profile: one literal path under `/webhooks/`,
no browser routes or declared platform effects, and a separate redacted, idempotent
internal command. Use `webhook_delivery_input_schema()` and
`webhook_delivery_result_schema()` from `three_mm_protocol.public_webhooks`.
The generic invocation gateway refuses this command. A declaration can be
reviewed, but does not register a route in the installed service.

The reviewed integration lab creates a `ReviewedWebhookAdmission` for that
declaration with an explicit audience, installation ID, instance ID and
package SHA-256 in a disposable Core database. After signature verification, it rechecks the
current sealed grant and active installation under Core's authority fence,
holds that fence through the short local inbox commit, and releases it before
HTTP output. Both new submissions and duplicate receipt lookups refuse after
disable, revocation or package change. A new grant does not reopen an old
binding. The version-2 lab inbox records the binding fingerprint and cannot
be reopened in standalone mode or with a replacement grant. Keep earlier
version-1 lab files untouched and use a fresh private directory and new
audience for a new trial; no Core database migration or reset.

Receiving an event and delivering it are separate decisions. A current admin
session reviews the exact declaration/binding via `review_delivery`; then
`decide_delivery` requires explicit confirmation, that fingerprint, the
expected decision revision, and a request ID. The decision and its audit
receipt use the existing sealed Core journal. `hold_delivery` checks both that
separate approval and the current package authority before a future delivery
can be admitted. Delivery revocation leaves the inbox and its receipts intact;
historical approval receipts do not grant access. A different audience,
artifact, grant revision or review key does not inherit approval.

`tools.webhook_delivery_lab.deliver_one` explicitly selects one durable receipt
and the reviewed test host. Under the delivery gate it verifies the stored body
digest and commits a unique attempt as `unconfirmed` before any socket I/O.
The Core fence is released before contacting the private Unix socket; revocation
prevents new claims but cannot recall an already admitted attempt. The host
receives the exact bytes in Base64, the event ID, and the receipt ID as the
idempotency key. The bounded signed RPC pins the instance and package; no user
identity, ingress signing key or credentials are forwarded.

Only a valid signed response for that attempt may confirm `delivered` or
`rejected`. A failed connection before sending records `not_dispatched`;
partial send, a lost or invalid response, or a failed outcome commit leaves
`unconfirmed`. A second call reads the recorded attempt without sending, even
when no execution was confirmed.

The version-4 lab retains at most 128 raw bodies and admits a new delivery claim
only within one hour of admission, measured by the host clock. A terminal
attempt drops its body in the same transaction. An expired receipt without an
attempt cannot be claimed, and a previously claimed attempt keeps its recorded
status; expiry does not cancel an admitted invocation. Signed admission,
approved claims, or explicit local `prune_expired()` maintenance remove elapsed
bodies. There is no idle background sweep. SQLite can reuse the freed space;
this does not guarantee file shrinkage or erasure from journals, backups or the
underlying medium.

The inbox keeps the event ID, digest, receipt and attempt metadata for its
lifetime, capped at 4096 receipts. At either limit it refuses new events with
`503` without evicting prior IDs; a newly signed request must not silently
reintroduce a previously accepted event. A matching version-2/3 inbox upgrades
atomically, preserving receipts and attempt outcomes. Older bodies with no
recorded expiry get one hour from upgrade unless already terminal.

`tools.webhook_delivery_lab.consume_pending` is the explicit local consumer
cycle. It takes no event ID from the caller and processes at most four
eligible receipts serially, earliest expiry first and insertion order for
ties. It skips expired bodies and every prior attempt. It rechecks the sealed
approval and exact host before each claim, and commits the claim before
sending. An absent socket blocks a new claim; if it disappears after claiming,
the original result is still recorded without automatic retry. Revocation
stops the next claim even if the admitted call is still finishing.

The cycle reports `drained`, `limit_reached`, `blocked`, or `paused` and the
receipt/attempt/status metadata of work it performed. An unconfirmed or
not-dispatched attempt pauses the cycle. An explicitly started later cycle
can handle other pending receipts, but cannot replay that attempt. The caller
owns scheduling and runs one cycle at a time; the lab installs no timer or
daemon. No bodies, signing keys or exception details are reported.

Local acceptance (POSIX, no installed Core or external service):

```sh
python -m pytest -q tools/tests/test_webhook_lab.py three_mm_protocol/tests/test_public_webhooks.py backend/tests/test_application_webhook_admission.py
```

This closes the loopback candidate, not the full public rollout. Before
enabling deployed ingress, verify explicit route ownership on the isolated
Public Web listener, operator key provisioning/rotation, supervised consumer
start/stop and quotas, and restart/revocation on the actual service boundary.
This candidate adds no Core tables, admin endpoint, public route or installed
worker, and does not add vendor-specific verification or challenge adapters.

## Route ownership

Core reconstructs the public route registry from active application packages.
Within one package duplicate public paths are already invalid. Cross-package
conflicts are checked before a candidate becomes live. The public listener is a
separate surface from the administrative SPA, so public paths never shadow Core
API, settings or recovery routes even when the same path text exists on both
surfaces.

Root ownership is therefore meaningful only on the public surface. External
public-domain/TLS ingress must target that surface explicitly; it is never
inferred from an untrusted Host header.

## Runtime shape

The target request flow is:

```text
public listener/surface
        |
Core public gateway
        |
validated route registry
        |
active Application Extension installation
        |
supervised application service
        |
ApplicationPublicHttpResponseV1
```

The gateway validates the request before dispatch and the response before
writing bytes to the network. Timeouts, malformed responses, unavailable
services and oversized bodies fail closed.

The public runtime must not require Vue SSR. An extension may return complete
server-rendered HTML, static-style HTML, or HTML that hydrates its own reviewed
browser assets. Core only transports the validated response.

## Lifecycle

- install/stage: routes are not live;
- activation: candidate routes are checked before ownership switches;
- disable: public routes stop resolving while extension data remains;
- rollback: the previous healthy package regains its declared routes;
- uninstall: route ownership disappears with the runtime;
- restore: public ownership is reconstructed only from validated active state.

No public route is persisted as an unrelated hardcoded Core router.

## Stages

### P0 — baseline and threat boundary

Status: complete as design review.

- inspect current static web server, application gateway and route contracts;
- confirm the missing generic HTTP response/route ownership capability;
- keep SEO and shop semantics outside the milestone.

### P1 — versioned public HTTP contract

Status: complete on branch. The base contract landed in `d9054264`; bounded
asset/cache response support was finalized in `966cff74`, with subsequent full
CI green.

- add request, response and public route v1 contracts;
- bind routes only to isolated public query operations;
- enforce bounded paths, text/binary content types, statuses, headers and response sizes;
- support cache validation through ETag/Last-Modified and no-body 304 responses;
- preserve existing Application Extension v1 packages unchanged;
- add protocol contract tests.

### P2 — Core route registry and public gateway

Status: complete on branch. Registry/dispatch landed in `1e9e6653`; route
specificity was finalized in `f3969562`. Full CI passed.

- build active-package public route registry and deterministic conflict checks;
- dispatch GET/HEAD to supervised application operations;
- validate request and response models at the gateway;
- enforce timeouts, response sizes and safe headers;
- return explicit 404/405/503 behavior without SPA fallback ambiguity.

### P3 — isolated public surface and ownership

Status: complete on branch. Runtime isolation landed in `1b9da531`, deployment
wiring in `2d8582fa`, and the dedicated `3mm-public` OS identity/security
boundary in `9fc0d31d`. Full CI passed. The boundary uses a separate
socket-activated public HTTP process and a local Core Unix-socket gateway.
Public failure is not allowed to fail Core startup.

- separate public ownership from the administrative SPA/recovery surface;
- use loopback socket activation so installations without public traffic keep no
  resident public-web process;
- make root ownership explicit on that surface;
- ensure extension failure cannot block local administration;
- run the public process as a dedicated OS identity and keep it away from Core
  state, privileged helper sockets, credentials and the shared service environment;
- leave trusted public origin/host and TLS ingress to an explicit deployment
  binding without trusting arbitrary Host headers for canonical identity.

TLS/custom-domain/cloud ingress automation is not required to prove v1 unless a
generic platform gap is found during acceptance.

### P4 — lifecycle and recovery

Status: complete on branch at `36e681a2`; full CI passed. Route ownership is
reconstructed from active installation/package state rather than a second
persistent route table.

- activation/disable/rollback/uninstall route ownership tests;
- restart and restore reconstruction;
- bounded diagnostics with no request credentials or private content leakage;
- failure tests for malformed, slow and unavailable application services.

### P5 — neutral reference application

Status: complete on branch at `2ae1c3b3`; full Python and frontend CI passed.
The reference is a real deterministic Application Extension package with no UI,
connector, hardware, secret or SEO dependency.

The reference application provides:

- `/` -> HTML;
- `/items/{slug}` -> HTML;
- `/feed.xml` -> XML;
- `/info.txt` -> plain text;
- `/old-item` -> permanent redirect;
- `/gone` -> 410;
- unknown path -> 404.

The reference proves public HTTP behavior only. It must not require a concrete
extension name in Core.

### P6 — Raspberry acceptance

Status: **complete on 2026-10-07**. See
[PUBLIC_WEB_PHYSICAL_ACCEPTANCE.md](PUBLIC_WEB_PHYSICAL_ACCEPTANCE.md).

The accepted physical runtime is commit `996760f6` /
`996760f669fd-20261007065735` on a Raspberry Pi 3B+ with Debian 13. Direct
GET/HEAD behavior, redirects, 404/410, disable/re-enable, fail-closed application
failure, Admin/Core independence, socket activation, idle shutdown, resource
impact and OS/file-access isolation all passed.

## Acceptance criteria

Milestone 19 is complete only when:

- an installed application can publish real HTML, XML, JSON and text responses
  through declared public routes;
- GET and HEAD work without rebuilding the Core frontend;
- redirects and explicit 404/410 responses work through the generic contract;
- overlapping routes between extensions and ambiguous same-extension routes
  fail before they become live; the separate public surface cannot shadow the
  administrative/API surface;
- public request credentials and administrator session data never reach the
  application handler;
- forbidden response headers, malformed responses and oversized bodies fail
  closed;
- disabling, rollback, uninstall, Core restart and restore leave no stale route
  ownership;
- a public extension crash or timeout leaves administration/recovery usable;
- the neutral reference passes deterministic laptop tests and physical
  Raspberry acceptance;
- a later website/shop can implement its homepage, friendly item/category URLs,
  HTML metadata, structured data, XML/text discovery resources and redirects
  without adding a concrete Core route or business model.

Milestone 19 is complete at the generic platform boundary above. If a later
website/shop proves that it needs a shop-, SEO- or provider-specific Core
endpoint, that is not part of this accepted contract and must be reviewed as a
new generic platform requirement rather than added ad hoc.

## Explicitly out of scope

- shop/catalog/order/payment models;
- SEO rules or search-engine integrations;
- Google/Bing-specific APIs;
- automatic sitemap generation;
- analytics/tag-manager script injection;
- arbitrary extension response headers;
- arbitrary HTTP methods in v1;
- arbitrary server-side executable templates inside Core;
- extension-to-extension service discovery unless a separate generic need is
  proven;
- custom-domain DNS/TLS automation before the generic public surface is proven.
