# 3mm 0.3.5

This release includes the changes from the unpublished 0.3.4 tag.

- Adds reviewed character-display support and Raspberry Pi I²C setup, with
  explicit approval and a separate restart step.
- Lets administrators save a required device selection on a stopped, prepared
  application before approving access and activating it.
- Reduces HTTP 409 conflicts from review-key contention while preserving current
  authority checks. Unconfirmed commands are not automatically replayed.
- Adds bounded recent HTTP failure diagnostics and correlated application-host
  failure categories without exposing request contents or raw errors.
- Rejects revoked required device sources through the normal authority error path.
- Bundles Bulgarian language pack 1.0.3 for the hardware setup and HTTP diagnostics
  panels. It does not automatically replace an existing language selection.

Crypto Monitor remains a separate application package. Grants remain bound to
the approved package and configuration. Native application-host diagnostic
detail requires an updated application host.
