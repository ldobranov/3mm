# Public Web Physical Acceptance

Status: **PASSED on 2026-10-07. Milestone 19 physical acceptance is complete.**

This procedure validates the public-web runtime on a provisioned full
Standalone/Hub installation. It does not publish a release, expose a public
domain or change DNS/TLS. The public listener remains loopback-only.

## Preconditions

- the target release contains Milestone 19 P0-P5;
- Core, Web and Agent are healthy before the test;
- the neutral `org.3mm.public-web-reference` package is built from the exact
  accepted source and installed through the normal Extensions lifecycle;
- no manual files are copied into `/opt/3mm/current`.

Build the neutral package from the matching source checkout:

```bash
python modules/public-web-reference/build_reference_package.py \
  --output public-web-reference.zip
```

Upload and activate that ZIP through Extensions. It has no configuration,
network connector, hardware capability or secret.

## A. Service and isolation baseline

On the target:

```bash
systemctl is-active 3mm-core.service
systemctl is-active 3mm-web.service
systemctl is-active 3mm-agent.service
systemctl is-active 3mm-public-web.socket
systemctl is-enabled 3mm-public-web.socket
id 3mm-public
sudo ss -ltn 'sport = :8081'
```

Expected:

- Core/Web/Agent and the public socket are active;
- the public socket is enabled;
- `3mm-public` is a dedicated system identity;
- only `127.0.0.1:8081` listens for the public surface;
- ports 80/8080 remain the administrative SPA.

Before the first request, `3mm-public-web.service` may be inactive. That is
expected: the socket starts it on demand.

## B. Neutral public HTTP flow

Run:

```bash
curl -i http://127.0.0.1:8081/
curl -i http://127.0.0.1:8081/items/example
curl -I http://127.0.0.1:8081/items/example
curl -i http://127.0.0.1:8081/feed.xml
curl -i http://127.0.0.1:8081/info.txt
curl -sS -o /dev/null -D - http://127.0.0.1:8081/old-item
curl -i http://127.0.0.1:8081/gone
curl -i http://127.0.0.1:8081/missing
```

Expected:

- `/` and `/items/example`: 200 HTML;
- HEAD: 200 with the GET content length and no body;
- `/feed.xml`: 200 `application/xml`;
- `/info.txt`: 200 plain text;
- `/old-item`: 301 with `Location: /items/example`;
- `/gone`: 410;
- unknown path: 404.

No response may contain an administrator session, raw exception text or
application-service socket details.

## C. Admin independence

While the public reference is active:

```bash
curl -fsS http://127.0.0.1:8887/health
curl -I http://127.0.0.1:8080/
```

Both must remain healthy regardless of public-route success or failure.

Disable the public reference through Extensions and repeat:

```bash
curl -i http://127.0.0.1:8081/
curl -fsS http://127.0.0.1:8887/health
```

The public route must become 404 while Core remains healthy. Re-enable the
reference and confirm the route returns.

## D. Public application failure

List supervised application services and identify the reference instance:

```bash
systemctl list-units --type=service '3mm-application-extension@*' --all
```

Stop only the reference application service, then request the public page.
The public surface must fail closed (normally 503) while:

```bash
curl -fsS http://127.0.0.1:8887/health
curl -I http://127.0.0.1:8080/
```

continue to succeed. Start the reference service again and verify recovery.

## E. Socket activation and resource impact

After one successful request:

```bash
systemctl status 3mm-public-web.service --no-pager
systemctl show 3mm-public-web.service -p MemoryCurrent -p CPUUsageNSec
```

Wait more than 60 seconds without public traffic and check again:

```bash
systemctl is-active 3mm-public-web.service || true
systemctl is-active 3mm-public-web.socket
```

Expected: the process exits after its idle window while the lightweight socket
remains active and can start it again on the next request.

## F. Isolation checks

Verify the public identity is not the Core or application identity:

```bash
id 3mm
id 3mm-app
id 3mm-public
sudo -u 3mm-public test ! -r /etc/3mm/3mm.env
sudo -u 3mm-public test ! -r /var/lib/3mm/core/3mm.db
sudo -u 3mm-public test ! -w /run/3mm/update-helper.sock
```

The public service itself additionally runs with `PrivateNetwork=true`,
`PrivateDevices=true`, `ProtectSystem=strict` and inaccessible Core state
paths.

## Acceptance record

Physical acceptance passed on 2026-10-07.

### Accepted runtime

- branch: `milestone/public-web-foundation`;
- commit: `996760f669fd5448b5636e36812c058848cc5c16`;
- immutable release: `996760f669fd-20261007065735`;
- project version: `0.3.0-test.1`;
- release metadata: `includes_working_tree=false`;
- CI run 129 for the accepted runtime commit: passed;
- target: Raspberry Pi 3 Model B Plus Rev 1.4;
- OS: Debian GNU/Linux 13 (trixie).

### Reference package

- module: `org.3mm.public-web-reference`;
- version: `1.0.0`;
- instance: `b1481f1cd27e1ff0ca9b1bf5`;
- package SHA-256:
  `5007ae614b1061d944a6c4f5e3410671b613219e3a32acafca8753bc3a1b6439`;
- stored package existed and its independently recomputed SHA-256 matched;
- final lifecycle state: `enabled=1`, `status=active`.

### HTTP results

| Request | Result |
| --- | --- |
| `GET /` | 200, `text/html; charset=utf-8` |
| `GET /items/example` | 200, `text/html; charset=utf-8` |
| `HEAD /items/example` | 200, no body, `Content-Length: 139` matching GET |
| `GET /feed.xml` | 200, `application/xml` |
| `GET /info.txt` | 200, `text/plain; charset=utf-8` |
| `GET /old-item` | 301, `Location: /items/example` |
| `GET /gone` | 410 |
| `GET /missing` | 404 |

No tested public response exposed administrator-session data, raw Core
exceptions or application-service socket details.

### Lifecycle and failure isolation

- disabling the reference through Extensions changed `GET /` to 404 and
  stopped/disabled only its supervised service; Core remained healthy;
- re-enabling restored the supervised service and `GET /` returned 200;
- manually stopping only the reference service produced fail-closed 503 while
  Core returned `{"status":"ok"}` and Admin Web on port 8080 returned 200;
- after starting the reference service, an early request during its startup
  window still returned 503, then recovered to 200 about six seconds later
  without restarting Core or the public listener;
- repeated immutable deployment during P6 restored every database-authoritative
  `enabled + active` Application Extension service after Core activation.

### Socket activation, resources and isolation

After a successful request the public process had:

- RSS: 36,460 KiB (about 35.6 MiB);
- observed CPU usage: 1.823 seconds;
- `MemoryCurrent` was not reported by systemd on this host, so RSS was recorded
  directly from the process.

After 65 seconds without traffic:

- `3mm-public-web.service`: inactive;
- `3mm-public-web.socket`: active;
- the next request returned 200 and socket activation restarted the service.

The dedicated identities were distinct: `3mm`, `3mm-app`, and
`3mm-public`. The public service reported `PrivateNetwork=yes`,
`PrivateDevices=yes`, `ProtectSystem=strict`, and inaccessible paths
`/var/lib/3mm /etc/3mm`. As `3mm-public`, all three explicit isolation
checks passed:

- no read access to `/etc/3mm/3mm.env`;
- no read access to `/var/lib/3mm/core/3mm.db`;
- no write access to `/run/3mm/update-helper.sock`.

### P6 deployment defects closed during acceptance

Physical testing exposed three generic deployment/runtime gaps before the final
pass:

- `bafacbe6`: Core now owns a dedicated `/run/3mm-public-web` runtime
  directory and the isolated public process uses its bounded Core socket;
- `59e6cab8`: the installer writes the same socket path to persistent service
  configuration so it cannot override the systemd boundary with a stale path;
- `996760f6`: immutable full deployments and rollback reconcile supervised
  Application Extension services from authoritative `enabled + active`
  database state instead of leaving them stopped with Core.

These are generic platform/deployment fixes; none introduces website, shop, SEO,
provider or reference-application semantics into Core.

### Conclusion

**PASS.** Milestone 19 physical acceptance is complete for the local isolated
public-web runtime. This record does not claim public DNS, TLS, custom-domain or
Internet-ingress acceptance, which remain outside Milestone 19.
