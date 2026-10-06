# Public Web Runtime & Extension Contract

Status: implementation started on 2026-10-06
Milestone: 19
Base: `401372c6` / `0.3.0-beta.40`

## Goal

Let CONERAX safely host public web applications as separately installed
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
5. A public HTTP handler is an isolated `public` query operation.
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
redirect, client-error and service-error statuses. Its body types are limited to
HTML, plain text, JSON and XML. Response headers are allowlisted to generic
caching/content metadata. Redirect location is a dedicated field rather than an
arbitrary header.

The handler's declared operation schemas must match the v1 public HTTP request
and response schemas exactly. This keeps package review deterministic and avoids
a new Core branch for every public application.

## Route ownership

Stage P2 will add a Core-owned registry over active application packages.
Within one package duplicate public paths are already invalid. Cross-package
conflicts, reserved Core paths and public-surface ownership are checked before a
candidate becomes live.

The reserved path set is derived from actual Core/admin/API surfaces during P2;
it is not duplicated prematurely in the protocol package.

No extension can claim administrative API or recovery paths. Root ownership is
possible only on the explicitly enabled public surface, never by silently
shadowing the administrative SPA.

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

Status: complete on branch; full CI passed for `d9054264`.

- add request, response and public route v1 contracts;
- bind routes only to isolated public query operations;
- enforce bounded paths, content types, statuses, headers and response sizes;
- preserve existing Application Extension v1 packages unchanged;
- add protocol contract tests.

### P2 — Core route registry and public gateway

Status: in progress.

- derive reserved Core paths from the running platform route inventory;
- build active-package public route registry and deterministic conflict checks;
- dispatch GET/HEAD to supervised application operations;
- validate request and response models at the gateway;
- enforce timeouts, response sizes and safe headers;
- return explicit 404/405/503 behavior without SPA fallback ambiguity.

### P3 — isolated public surface and ownership

- separate public ownership from the administrative SPA/recovery surface;
- add administrator-controlled public-surface enable/binding state;
- make root ownership explicit on that surface;
- ensure extension failure cannot block local administration;
- define trusted public origin/host handling without trusting arbitrary Host
  headers for canonical identity.

TLS/custom-domain/cloud ingress automation is not required to prove v1 unless a
generic platform gap is found during acceptance.

### P4 — lifecycle and recovery

- activation/disable/rollback/uninstall route ownership tests;
- restart and restore reconstruction;
- bounded diagnostics with no request credentials or private content leakage;
- failure tests for malformed, slow and unavailable application services.

### P5 — neutral reference application

Create a reference application with no shop or SEO semantics:

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

On a provisioned physical installation verify direct HTTP GET/HEAD behavior,
redirects, errors, extension disable/rollback/restart and simultaneous access to
the administrative recovery UI. Record resource impact and recovery behavior.

## Acceptance criteria

Milestone 19 is complete only when:

- an installed application can publish real HTML, XML, JSON and text responses
  through declared public routes;
- GET and HEAD work without rebuilding the Core frontend;
- redirects and explicit 404/410 responses work through the generic contract;
- duplicate or reserved routes fail before they become live;
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

If building that later extension requires a shop-, SEO- or provider-specific
Core endpoint, this milestone is incomplete.

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
