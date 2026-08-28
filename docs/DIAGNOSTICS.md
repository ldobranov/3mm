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
