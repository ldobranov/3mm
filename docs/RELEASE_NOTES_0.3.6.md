# 3mm 0.3.6

- Shows uploaded Agent modules and hardware providers in Extensions, with their
  device installations, enabled state and reported operation status. Missing
  package metadata no longer hides a recorded installation.
- Keeps applications first. Agent inventory is compact and collapsed initially;
  identifiers, command details and removal controls are available on expansion.
- Adds separately confirmed full module removal from a selected device. The
  Agent stops the module and removes its versions, saved module state and data.
  Other modules, application data, host I²C configuration and command receipts
  are not erased. An uncertain response is resolved through the original request,
  not by automatically repeating removal.
- Keeps uploaded-package deletion separate and blocked while device installations
  still reference the module. Confirmed removal requires an updated Agent.
- Fixes restore permissions for mutable application-host journals and instance
  pointers, and loads the current environment for restore and rollback activation.
  Preflight checks run before stopping services; immutable release and health
  verification boundaries remain in place.
- Fixes the restore completion check to require the current device API rather
  than the retired `/access` endpoint.
- Bundles Bulgarian language pack 1.0.5 for the inventory and removal interface.
  An already selected language package is not automatically replaced.

Recovery still requires current application access approval where invalidated;
restore does not automatically grant execution rights. This release does not
claim to fix the separately deferred LCD execution-permit HTTP 409 issue or
change Crypto Monitor's application version.
