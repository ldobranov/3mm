# Public Web Physical Acceptance

Status: required before Milestone 19 can be closed.

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

Record:

- exact Core commit/release;
- device model and OS;
- package SHA-256;
- every HTTP status above;
- public process memory after first request;
- idle shutdown result;
- disable/re-enable result;
- application-service failure isolation result;
- confirmation that Admin Web/Core stayed healthy.

Milestone 19 is not complete until this physical record passes.
