# 3mm 0.3.8

- The full installer selects a Raspberry Pi Zero W ARMv6 Hub archive on 32-bit
  Raspberry Pi OS Trixie (Python 3.13). It uses the distribution's Node.js/npm,
  `build-essential` and `python3-dev`; it does not build esbuild on the Pi.
  The immutable ARMv6 archive carries matching Rollup WASM and an ARMv6 esbuild.
  Keep an existing Node installation on its separate profile or use fresh media.
- **Recover application** can prepare the exact stopped package for review after
  an interrupted ordinary activation. If an earlier recovery left such a package
  stuck in Disabled, open **Recover application** again and explicitly review
  external effects. Review and approve access before the separate activation
  action. Recovery does not undo migrations or outside effects, grant access,
  start code, or discard data or configuration.
- An upgrade after restore preserves the encryption key in the restored Core
  configuration. It verifies the existing installation identity before stopping
  services and does not replace the key with a stale legacy copy.
- CAP21 provides a starter and common tooling for local authoring, review,
  compiled UI, generated clients and isolated migration checks. See the
  [starter guide](../modules/application-starter/README.md).
- CAP10 adds bounded anonymous forms and opt-in temporary guest drafts on the
  separate Public Web surface. The reference packages are source examples, not
  installed applications. No public ingress or guest listener is enabled by
  upgrading. See the [Public Web contract](PUBLIC_WEB_EXTENSION_PLAN.md).

Before upgrading, keep a tested backup. On older Core versions, the ordinary
release manifest is unchanged; ARMv6 Hub uses its separate catalog. Core,
Platform Runtime, application hosts, Agent, SDK and language packs keep
independent versions and update policies.
