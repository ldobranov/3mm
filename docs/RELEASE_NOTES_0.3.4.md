# 3mm 0.3.4

- Adds reviewed character-display support and Raspberry Pi I²C setup, with
  explicit approval and a separate restart step.
- Fixes reinstalling a prepared application with missing device selections.
  Save the device, review and approve access, then activate explicitly.
- Reduces HTTP 409 conflicts from review-key contention. A command with an
  unconfirmed execution outcome is still not safe to replay automatically.
- Adds bounded recent HTTP failure diagnostics and correlated application-host
  failure categories without exposing request contents or raw errors.

Crypto Monitor remains a separate application package. Existing application
grants still apply only to the approved package and configuration. Native
application-host diagnostic detail requires an updated application host.
