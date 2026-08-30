# Module Manifest v2

Every new 3mm module package is an immutable ZIP archive with `manifest.json`
at its root. The strict shared schema is implemented by
`three_mm_protocol.ModuleManifestV2` and rejects unknown fields.

Required declarations include stable identity and semantic version, target
runtimes, protocol/runtime/architecture compatibility, capabilities,
permissions, dependencies, configuration, health check, and generic
registrations.

Core validates archive size, expanded size, file count, paths, symbolic links,
permissions, compatibility, and SHA-256 integrity before accepting or sending a
package. A published `(module_id, version)` is immutable.

Agent stages outside the active release, validates again, and runs the declared
health check. Only a healthy release becomes active. A failed update leaves the
prior version active. Disable removes runtime registrations but retains the
release and module data.

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
