# Production security and remote access

Status: guidance for Milestone 15 hardening, grounded in the current release
behavior. It documents what is implemented today, what must be configured by an
operator, and what is not yet a live acceptance claim.

This is deployment guidance, not a change to the runtime. It does not open any
port, generate any certificate or alter the installer.

## 1. Current network boundary (verified facts)

| Listener | Process | Reachability today |
| --- | --- | --- |
| `80` | `three_mm_web` (alias port) | LAN IP and `<hostname>.local` via mDNS |
| `8080` | `three_mm_web` | LAN compatibility listener |
| `8887` | `three_mm_core` API (uvicorn) | development/HTTP boundary |
| `8890` | local Agent | loopback only |
| `8895` | Setup AP captive portal | temporary local open network only |

The current transport is plain HTTP. It is a **trusted-LAN beta bootstrap**, not a
public-ingress security boundary. Several contracts already state this:

- Network recovery is local-link only and intentionally not Internet-routed.
- The Setup AP is open on purpose and exists only while setup mode is active.
- The public web listener is loopback-only and leaves DNS/TLS to an explicit
  deployment binding (Milestone 19).

Do not treat any of these listeners as production secrets transport. Credentials
and provider keys must never cross an untrusted network in plaintext.

## 2. Secure remote access (operator guidance)

**Verified facts (from the current code):**

- `three_mm_web` (ports 80/8080) serves the static SPA, its hashed assets,
  `/uploads/*` and the static `/runtime-config.json` file. It does **not** proxy
  the API.
- The shipped Core service binds `0.0.0.0:8887` (uvicorn `backend.main:app`),
  not loopback-only. The proxy can reach it at `127.0.0.1:8887`, but a firewall
  must block direct untrusted access. Its routes are **not** all under `/api`: alongside
  `/api/*` it also serves `/settings/*`, `/menu/*`, `/language/*`,
  `/frontend-config`, `/user/*`, `/sessions/*`, `/groups`, `/roles`,
  `/permissions/*`, `/display/*`, `/read`, `/api/translations/*`,
  `/api/images/*`, `/api/settings/*`, `/api/extensions/*`, `/api/marketplace/*`,
  `/api/ai/*`, `/api/displays/*`, `/api/public/*`, `/api/admin/*` and `/api/v1/*`.
- The frontend resolves its API base in this order: a `localStorage` override,
  then the static `/runtime-config.json` (`backend_url` or `backend_port`), then
  the Core `/frontend-config` route, then a `:8887` guess. The stored value is
  the `frontend_backend_url` setting returned by `/frontend-config`.
- `FRONTEND_URL` and `CORS_ORIGINS` alone do **not** change the API address.
  The shipped static file contains `{"backend_port":8887}`. This valid response
  wins before `/frontend-config` is requested: changing the stored Core setting
  alone cannot bootstrap a fresh browser through two HTTPS origins.

Because Core's surface is not confined to `/api`, the robust and verifiable
deployment is **two HTTPS origins** behind one reverse proxy:

| Public origin | Upstream | Serves |
| --- | --- | --- |
| `https://3mm.example.com` | `127.0.0.1:80` (Web) | SPA, assets, `/uploads`; proxy supplies `/runtime-config.json` |
| `https://api.3mm.example.com` | `127.0.0.1:8887` (Core) | Every API route |

Serve an explicit API URL from the Web proxy's exact `/runtime-config.json`
route, as shown below. This overrides the static HTTP response, **not files in
the immutable release**. Also allow the Web origin in Core's existing host
configuration:

```text
FRONTEND_URL = https://3mm.example.com
CORS_ORIGINS = ["https://3mm.example.com"]
```

### Caddy example

On the same host, the shipped Web service already occupies port 80. This example
disables Caddy's HTTP redirects and HTTP-01 challenge so it does not compete for
that listener. Certificate automation instead needs public DNS and direct TCP 443
access to Caddy for TLS-ALPN-01; if another TLS terminator intercepts that challenge,
use explicitly managed certificates or an operator-configured DNS challenge.
Users must open the HTTPS URL explicitly; this example provides no HTTP redirect.
See Caddy's [automatic HTTPS options](https://caddyserver.com/docs/caddyfile/options#auto-https)
and [ACME issuer options](https://caddyserver.com/docs/caddyfile/directives/tls#acme).

```caddyfile
{
    auto_https disable_redirects
    cert_issuer acme {
        disable_http_challenge
    }
}

3mm.example.com {
    encode gzip
    handle /runtime-config.json {
        header Content-Type application/json
        header Cache-Control "no-store"
        respond `{"backend_url":"https://api.3mm.example.com"}` 200
    }
    handle {
        reverse_proxy 127.0.0.1:80
    }
}

api.3mm.example.com {
    encode gzip
    reverse_proxy 127.0.0.1:8887
}
```

### nginx example

```nginx
server {
    listen 443 ssl;
    server_name 3mm.example.com;
    # ssl_certificate / ssl_certificate_key ...
    location = /runtime-config.json {
        default_type application/json;
        add_header Cache-Control "no-store" always;
        return 200 '{"backend_url":"https://api.3mm.example.com"}';
    }
    location / {
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_pass http://127.0.0.1:80;
    }
}

server {
    listen 443 ssl;
    server_name api.3mm.example.com;
    # ssl_certificate / ssl_certificate_key ...
    location / {
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_pass http://127.0.0.1:8887;
    }
}
```

A single-origin alternative is possible but fragile: it must route **all** Core
prefixes above to `127.0.0.1:8887` and only the SPA shell/assets/`/uploads` to
`127.0.0.1:80`, and it must keep the SPA history fallback working. The two-origin
form avoids enumerating Core's non-`/api` routes and is the recommended default.

Before deployment, validate the actual operator configuration (`caddy validate`
or `nginx -t`) and check listener ownership. These examples have not been accepted
against a live public certificate/DNS environment; do not stop the Web service or
edit an immutable release merely to free port 80.

Verify `/runtime-config.json` returns the explicit HTTPS API URL, then open a
fresh browser profile: API requests must use that origin, never public `:8887`.
A previous Connection override (`mm_backend_url_override`, including an empty
same-origin value) takes precedence. Clear that override through the Connection
settings before testing discovery; do not erase login/theme storage wholesale.
The saved Core `backend_url` may also be set through Settings or
`POST /frontend-config`, but it is only a fallback, not a substitute for this
proxy bootstrap. Local regression tests cover both paths and override priority;
they do not prove public DNS, certificate renewal or live ingress acceptance.

Recommended order, smallest exposure first:

1. **Keep the development HTTP boundary private.** Port `8887` (Core API) and the
   `8080` compatibility listener must not be forwarded to the Internet. The
   compatibility listener exists for LAN clients only.
2. **Terminate TLS at one reverse proxy** (Caddy, nginx or Traefik) that binds the
   two explicit public hostnames above. The proxy must preserve the original
   `Host`; the proxy bootstrap must supply the **HTTPS API origin** as
   `backend_url` and Core must allow the **HTTPS Web origin** in `FRONTEND_URL`/`CORS_ORIGINS`,
   otherwise browsers encounter CORS failures rather than a secure session.
3. **Do not expose the Agent loopback port, the Core API port or the Setup AP** to
   the Internet. The Agent is intentionally loopback-only; exposing it would
   defeat device isolation.
4. **Use a local firewall/UFW** that defaults to deny and allows only:
   - the reverse proxy port on the intended interface,
   - the LAN Web port when trusted-LAN access is required,
   - nothing for `8887`, `8890`, `8895`.
5. **Keep mDNS local.** mDNS (`<hostname>.local`) is not routed and is not a
   substitute for a DNS record or a certificate. Certificate issuance for a
   public name requires real DNS, not `.local`.
6. **TLS is not self-asserted by 3mm.** A reverse proxy/TLS is infrastructure, not
   an application feature. Cloudflare or another proxy is an acceptable operator
   choice, but it does not replace item 3 and item 4 above.

Ports 80/8080 HTTP may remain for trusted-LAN bootstrap; they must not be the
only path once a device is reachable from an untrusted network.

## 3. Production administrator bootstrap

Current behavior:

- A brand-new empty database receives the initial login `admin@example.com` with
  password `admin`. An update never recreates the account or resets an existing
  password.
- The password must be changed from **Profile** immediately after first login.

Required operator sequence before any production use:

1. Sign in and change the initial password **before** exposing the device.
2. Create a named administrator, verify its login, then retire the Beta placeholder
   `admin@example.com`. Never remove the only administrator or your recovery path.
3. Create named operator accounts with the least role (`operator`/`user`) needed;
   do not share a single administrator account for daily use.
4. Keep at least one local administrator account that is not tied to a cloud or
   single sign-on path, so offline recovery stays available.

## 4. Credential-rotation policy

Rotate at a documented interval and immediately after any suspected exposure,
device reuse, backup loss or personnel change:

| Credential | Rotation rule |
| --- | --- |
| Administrator / operator passwords | Change on first login; rotate per policy; explicitly revoke existing sessions through Users after changing a password |
| Wi-Fi / network profile | Re-enter through Setup/network recovery; do not copy plaintext passwords into application state/logs; OS-managed protected NetworkManager profiles are a separate boundary |
| Application secret references | Use the existing create/rotate/revoke secret flow (`APPLICATION_SECRET_CREATED/ROTATED/REVOKED`); rotation increments the version and advances the authority epoch |
| Provider/device credentials | Use the device credential pairing/revoke flow; never embed provider keys in manifests, logs or diagnostics |
| Backup encryption key | Rotate only under the shared mutation lock (`deployment/backup_key_rotation.py`); existing archives become unreadable, so re-export or acknowledge first, and test restore after each rotation |
| Application review keys | Use the existing local authority-admin rotate/recover commands; old sealed evidence becomes invalid and does not restore grants automatically |
| Release-signing keys | Distribution/rotation policy is still pending; the helper alone does not establish installer trust |

Do not write plaintext passwords or keys into shell command arguments, Git,
logs or application rows. Use existing hashed/encrypted credential stores and
opaque references rather than inventing a second secret path. Public frontend
origin settings are not credentials and may be stored as ordinary configuration.

### Manual operational controls added in beta.47

- `GET /api/audit-logs/retention-plan?retention_days=90` is an administrator-only
  dry run. `POST /api/audit-logs/retention` requires the exact confirmation
  `AUDIT RETENTION`, 30–3650 days and a batch of 1–10000. It removes only old
  non-evidential human audit records and records the purge in the same transaction.
  Device events, application authority, execution/outbox and backup journals are
  not purged. No update installs an automatic retention job.
- `GET /api/v1/diagnostics/alerts` is administrator-only and read-only. It reports
  backup/storage/diagnostic warnings; it sends no messages and changes no state.
- `deployment/backup_key_rotation.py` defaults to dry run. An explicit root-local
  `--apply` holds `/run/lock/3mm-release-mutation.lock`; a busy lock refuses rotation
  without changing the key. Existing `.3mmbak` archives block it unless the operator
  acknowledges orphaning them. Password-protected recovery exports must be verified
  before such a deliberate rotation. Do not rotate a production key merely to test
  the release. The helper does not re-encrypt or delete archives.

## 5. Not implemented / not claimed here

- No certificate is generated or renewed by this document.
- No public-ingress acceptance has been performed on a live Internet-exposed host.
- No secret is rotated by this document.

This slice adds manual bounded audit retention, read-only operational alert
summaries and guarded backup-key rotation. Existing redacted diagnostics and
restore mechanisms remain in place. These are foundations, not completion of
Milestone 15. Still open:

- Release signing is an opt-in Ed25519 helper only. The publisher, catalog and
  installer do not use it yet; these releases must not be described as signed.
  Trusted private repositories and signing-key distribution/rotation remain open.
- Fleet rollout rings and coordinated Hub/Node maintenance.
- Live TLS/Internet-ingress and supported cross-host restore acceptance.
- End-to-end credential rotation/recovery acceptance and operational alert
  delivery/monitoring policy. The read-only alert endpoint sends no notifications.
