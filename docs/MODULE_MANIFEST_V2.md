# Module Manifest v2

Every new 3mm module package is an immutable ZIP archive with `manifest.json`
at its root. The strict shared schema is implemented by
`three_mm_protocol.ModuleManifestV2` and rejects unknown fields.

Required declarations include stable identity and semantic version, target
runtimes, protocol/runtime/architecture compatibility, capabilities,
permissions, dependencies, configuration, health check, and generic
registrations. `module_id` remains the canonical extension identity; Extension
Platform v2 does not introduce a second `extension_id` namespace.

`compatibility.extension_api` is the public 3mm Extension Platform API contract.
It defaults to the current `1.0` contract so existing manifest-v2 packages remain
valid. Compatibility is major-version strict and minor-version additive: a host
supporting `1.1` may run a package requesting `1.0`, but not the reverse.

Packages may also declare stable publisher metadata as
`publisher: {"id": "...", "name": "..."}`. The field is optional at the local
package layer for backward compatibility and development packages. A future
Registry/publishing layer may require it without changing Core package identity.

Core validates archive size, expanded size, file count, paths, symbolic links,
permissions, compatibility, and SHA-256 integrity before accepting or sending a
package. A published `(module_id, version)` is immutable.

Agent stages outside the active release, validates again, and runs the declared
health check. Only a healthy release becomes active. A failed update leaves the
prior version active. Disable removes runtime registrations but retains the
release and module data.

The AI Extension Builder consumes the same shared `EXTENSION_API_VERSION`
constant when it emits manifest-v2 packages. AI-generated packages therefore do
not have a separate manifest or compatibility path.

AI projects pin a `module_id` when the project is first persisted. Renaming the
display name must not change that identity. Older projects without a stored ID
first preserve a valid `module_id` from their stored generated `manifest.json`;
only projects that never produced such a manifest fall back to the immutable
project slug. Build history rejects a compiled artifact whose `module_id` does
not match the project.

The initial deny-by-default permission policy recognizes `data.read`,
`data.write`, `events.consume`, `events.publish`, `network.outbound`,
`process.spawn`, `secrets.use`, `hardware.inventory`, and `hardware.gpio`.
Stronger OS-level isolation remains required before untrusted generated code is
supported.

An `application-extension v1` package declares
`entrypoints.core = application-extension.json`, a checksum-bound wheel below
`service/`, and optional `compiled-ui.json` routes. Its application descriptor,
manifest identity, consumed/provided event capabilities, exact permissions,
strict configuration keys, secret-reference fields, service artifact and UI
route entrypoints are validated together. Until the supervised Stage 2 runtime
exists, the package upload endpoint rejects this otherwise valid format so no
service or route can be partially activated.
