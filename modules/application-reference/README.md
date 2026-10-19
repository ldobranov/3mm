# Neutral application reference

This is a separately built Manifest v2 application package, not a bundled Core
module. Its service imports the public Python SDK and its Vue screens import
only Vue and `@3mm/application-ui/v1`. Same-origin UI and reviewed native code
are **not sandboxed**.

## Profiles

- The default **1.0.1 compatibility workflow** is unchanged. It includes its
  existing application database, connector and background-work examples; it is
  not evidence of scoped WP4 acceptance.
- **1.1.0 scoped capability acceptance** uses one exact command binding, one
  kiosk/operator submission operation and an operator lookup. It declares no
  connector, job, event subscription or scoped relational database. Its no-op
  migration only satisfies the existing host's compatibility schema journal.
  The generic manifest still requires the platform's baseline data permissions;
  these are not applied resource grants.

## Build the scoped profile

Run from a checkout with the project's Python dependencies installed:

```bash
python3 modules/application-reference/build_reference_package.py \
  --output .runtime/application-reference-scoped-1.1.0.zip \
  --reader-device-id dev_33333333333333333333333333333333 \
  --scoped-command modules/application-reference/scoped-command.example.json
```

For this profile, the existing `--reader-device-id` argument supplies
`TARGET_DEVICE_ID`. The example ID and contract are **local test fixtures**,
not discovered devices or a recipe for physical GPIO. Make an explicit copy of
the specification for a separately verified mock target. Select its exact
capability ID, contract version, action, bounded argument schema and one valid
argument object. The builder refuses unknown fields, unversioned contracts and
invalid example arguments; it never guesses a provider contract. The example
`pulse` / `output.1` does not necessarily match a live provider's
`pulse_output` / `gpio.output.1` contract.

Building is inert: it creates no installation, trust, grant, command or device
effect. Upload/inspection, source/build review, runtime activation and resource
approval remain separate normal platform actions.

Scoped Python/Vue sources normalize CRLF to LF and use fixed ZIP creator metadata
before packaging, so Windows and Linux builds of the same scoped inputs have
identical bytes. The existing compatibility packaging is not changed. See the [post-update installation and
access runbook](ACCEPTANCE.md) for the required stopped adoption, exact target
build review, independent human/kiosk/SDK rights and one-request owner test.

## Authorized mock acceptance

1. Use a disposable environment or take a verified recoverable snapshot first.
   Record Standalone/Hub/Node roles, exact versions and target identities. Confirm
   an isolated mock provider; stop if GPIO is real or unknown. Do not change a
   working Agent's driver just to pass the test.
2. Inspect/upload the package and inspect its compiled build through the existing
   Extensions workflow. Review the exact wheel and source/build hashes. Record
   native-code trust and the separate same-origin UI risk acknowledgement using
   the existing local administrator flow. Do not write authority database rows.
3. Follow the existing lifecycle and stopped-first-adoption procedure. Review
   `command:acceptance` against the exact target/provider/action. Approve and
   Apply are separate. Starting/re-enabling may invalidate an older epoch;
   inspect current status and use a fresh resource review when required.
4. An ordinary operator needs the separate `probe_use` human permission. A kiosk
   needs an explicit enrollment for this application. Neither supplies the
   service's command grant; an operator must not use the administrator gateway.
5. In the delivered UI, paste the exact specification's `arguments` JSON and
   explicitly queue **one** mock request. Preserve the shown request ID. A queue
   response is not hardware execution. Use **Read existing outcome** with that
   ID to observe the existing queue record, not to issue another command.
6. If the response is unconfirmed, submission and editing are blocked. Lookup
   remains read-only; it does not re-enable submission. Save the original ID
   externally before closing/reloading the page: this example deliberately has
   no browser credential/state storage and is not a durable browser journal.
7. Verify human/kiosk revocation, stale UI build, undeclared/foreign bindings,
   changed arguments under the same ID, service grant revocation and disable
   refuse new work. Restart/health must not replay business work; re-enable is
   not reapproval. Record command count/outcomes before and after each step.

Do not automatically resend an uncertain request, create a replacement ID,
grant resources from the UI's human access, or infer execution from a queue row.

## Evidence and limits

`backend/tests/test_application_reference_scoped.py` installs the delivered ZIP
into a disposable catalog, runs its actual wheel in a separate host process and
uses HTTP actor/audience checks plus both signed Unix IPC boundaries. Local
native/firmware provider rows model two layouts; they do **not** prove live
Hub/Node transport, Agent execution, privilege isolation, boot or portable restore.
The integration uses the existing fake compiler fixture for build-trust metadata;
the real install-time compiler and rendered UI are checked separately.

`frontend/src/utils/application-reference-scoped.test.ts` tests the actual Vue
component with the public host contract, including uncertain-response lookup
without resend and request IDs usable on LAN HTTP origins. The WP4 closeout
checklist records acceptance separately from these local results.
