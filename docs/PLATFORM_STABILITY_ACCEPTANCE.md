# Platform stability: Update Contract v2 + Frontend Bootstrap v1

Status: implemented on `main` and prepared for `v0.3.0-beta.42`; no bridge branch,
live deploy or reset performed for this correction. Published `v0.3.0-beta.41`
remains immutable. This work preserves Public Web, theme controls, authentication,
dynamic routes and the separate Node update workflow. No database migration or
SDK version change is required.

## Frontend contract

- `RuntimeConfig` owns backend URL selection: an explicit saved override
  (including empty same-origin), runtime config, portable frontend config, then
  the existing host/port fallback. URL changes invalidate the transport/catalog.
- `ExtensionCatalog` owns public enabled-extension discovery. Router, i18n and
  extension relationships reuse it rather than performing separate discoveries.
- Both caches share an in-flight promise; successful empty results are cached.
  TTLs are five minutes (runtime) and ten minutes (catalog). Failed fetches retain
  verified data and suppress further attempts for thirty seconds, including
  explicit refresh attempts. Each bootstrap fetch has a five-second deadline.
- No interceptor performs discovery or URL probes. Public API decisions use
  cached metadata synchronously, without concrete extension-name heuristics.
  Authorization remains enforced by the backend, not by this cache.
- Network retries are restricted to one GET/HEAD retry; uncertain mutation
  requests are never replayed automatically. Private authenticated 401 can
  refresh once; 403 or anonymous/public 401 do not trigger session logout.
- Enable/disable refreshes update the shared catalog; selecting an older enabled
  extension version overrides a higher bundled version. A verified empty list
  means no enabled extensions, not a reason to enable bundled ones.

With valid runtime config, the automated concurrent startup check (router,
i18n, relationships and thirty catalog consumers) requires exactly:

```text
1 × /runtime-config.json
1 × /api/extensions/public
```

Other application endpoints are separate; those totals are not a promise that
the entire application starts using only two HTTP requests. Failure cooldown,
malformed responses, stalled requests, URL-change races, Unicode payloads,
authentication and mutation replay have regression tests.

## Update safety tests

Tests verify target-contract parsing, required regular files, official identity
and dependency checks, root-private snapshots, preflight before mutations,
installer exit-code diagnostics, deterministic full release packaging and Node
profile regressions. An isolated real bash transport executes a fake target
installer introducing a new user/unit and exercises simulated health-failure
rollback. It never invokes real systemd or touches `/opt`, `/etc` or live data.

The existing immutable installer's rollback and separate Public Web identity
remain authoritative. The fake deployment test does **not** prove real systemd,
database migrations, power-loss recovery or hardware acceptance.

## beta.42 release-preparation evidence

On 2026-10-07, the complete isolated WSL/Linux Python 3.14 suite passed 1,462
tests with one opt-in HTTPS acceptance test skipped. All 39 separate deployment
tests and all 205 frontend tests passed; TypeScript checking, the production
frontend build and exact staged-source full-profile packaging also passed.
Temporary sockets used the Linux filesystem rather than the Windows checkout.
GitHub repeats the canonical Python 3.13 gates and builds full-profile plus
ARMv6 Node assets twice before publication. These checks do not close the live
acceptance gates below.

## Physical gate after publication (not executed yet)

1. Preserve a backup and record installed version, device identity, enabled
   extensions and working Public Web behavior on both WSL and Raspberry.
2. After publication, manually install official `v0.3.0-beta.42` using
   `install.sh --tag v0.3.0-beta.42` (default full profile). An older updater
   cannot use the new worker before this bootstrap. Check Core/Web/Agent,
   update helper, Public Web socket/service, private/public route separation and
   existing themes. No destructive clean install on a device with needed data.
3. In a fresh browser tab, record network requests for fifteen seconds; verify
   no runtime-config/catalog request storm. Repeat after idle, reconnect and a
   temporary backend outage. Measure idle Core CPU on the actual device.
4. Test one subsequent official release through `/system/updates`; its own
   installer must supply any new primitive. Inspect persisted terminal status
   and both helper/apply journals, identity and persistent data.
5. On a disposable test host, inject a deliberately failing target unit and
   verify the previous release, database, environment and healthy services are
   restored. A failed update status alone is not rollback proof.
6. Verify clean installation on disposable media, plus a paired Zero's existing
   Node update path. Confirm credentials, pairing and GPIO setup are preserved.

Do not close these physical gates solely from unit tests or successful release
publication. Tags remain immutable; deployment requires separate authorization.
