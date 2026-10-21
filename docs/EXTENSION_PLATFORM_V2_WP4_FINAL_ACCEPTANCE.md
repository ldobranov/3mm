# M20 / WP4 — final functional acceptance record

Reconciled and accepted: **2026-10-21**. Status: **functionally completed by owner
acceptance** in the supported reviewed-native scope and with the limits below.
The owner explicitly confirmed: "Да, приемам и затваряме WP4". This record
preserves completed tests rather than creating another implementation phase.
It does not close M20 as a whole, WP5 or M21.

## Criteria and evidence

The criteria remain those in the [Core plan's WP4 section](../EXTENSION_PLATFORM_V2_CORE_PLAN.md#wp4--public-platform-api-sdk-and-authorization).
No criterion is removed by this reconciliation. Missing features must be reported
and refused, never implicitly supported by a declaration or compatibility path.

| Required outcome | Evidence and limit | Assessment |
| --- | --- | --- |
| Public SDK/API contracts, exact-resource admin review/approve/apply/revoke | Existing signed command, connector, event, publication, private-file, prepared relational, checkpoint, public identity/status and exact peer-read adapters; local negative/race/compatibility suites and earlier accepted file/SQL trials | Delivered within documented profiles |
| Separate package/native trust, service resources and human access | Exact package and target-compiled build reviews; real Hub operator/kiosk/service revocation and separate reapproval; no admin-role substitution for application permission | Functional boundaries exercised |
| Public frontend host, not private Core stores/tokens | Neutral reference uses `@3mm/application-ui/v1` and public Python SDK through the actual installed service/Agent path | Exercised on Hub and Standalone |
| Same neutral reference on Standalone/local Agent and Hub/mock Node | Same application ZIP and version; distinct target builds, local Raspberry mock and isolated ARMv6 mock Node; actual completed commands and fresh safe-state reads | Both layouts exercised; not all negatives repeated on each |
| Unauthorized/undeclared resources fail and compatibility remains | Local signed integration/refusal tests, human/kiosk/resource revocation on Hub, bounded SQL ATTACH/refused file access and post-recovery stale-right denial; full release suites below | Covered by the combined evidence, not a claim that every case ran live |
| Explicit local recovery and final integration | Actual disposable Standalone portable restore, fixed backup resumption, injected installer rollback-v2 and SDK stale-authority denial; corrections shipped in beta.55 | Accepted bounded scenarios preserved |

The [closeout history](EXTENSION_PLATFORM_V2_WP4_CLOSEOUT.md) retains targeted
suite evidence. Earlier file/SQL acceptance remains in the
[beta acceptance report](EXTENSION_PLATFORM_V2_BETA_ACCEPTANCE.md). No overlapping
test runs or skipped cases are added together as new passing coverage.

## Neutral reference and real layouts

Both layouts used `org.3mm.application-reference` **1.1.0**, ZIP SHA-256
`1cafba392068fa843588220890f0535bbc5f9c7465d6b5d3d239013134646b75`,
and `org.3mm.digital-output` **1.1.0**, capability `gpio.digital.control`, contract
**1.0**. The provider ZIP SHA-256 is
`e7ab19b266db360fc76b87204080c3ac863d13ad8c2a8c3657525e697da6991a`.
Each Core compiled and reviewed its own exact UI build; matching source ZIPs do
not mean build hashes or grants can be copied between installations.

### Hub plus isolated mock Node — owner-accepted functional stage

- VM Hub Agent `dev_ad7e90a045214c4088ed6ed7df50bec2`; app installation **7**.
  Target build `9858c6d8642452c756ccb2a20713de7a762dd30d077a3999bb0b0d61f6016b94`.
- Isolated mock Node `dev_1d54a2398b9346aeb557523d09192d49` on physical ARMv6
  hardware, separate state/identity and no access to real GPIO. This is not a
  physical-output acceptance test. The primary physical Agent was not replaced.
- Ordinary-user request `c38b8a1cd1477145b8a521af8d44826a` produced command
  `cmd_b11db9dc6e3e4a0c8237106f72920de4`, succeeded/executed, one delivery.
- Kiosk request `dabfe91687207c702dfc045f7788296b` produced command
  `cmd_f6552babb9da4609ac46fc77275dddd3`, succeeded/executed, one delivery.
- Separate kiosk revocation gave HTTP **200 before / 401 after** and **401** on
  revoked-session renewal, with unchanged command IDs/count and service grant.
  The original browser tab was lost; the explicit temporary-terminal check
  established this negative case, not a claimed observation of the lost tab.
- Service revocation refused request `efdd70a73ec306c994f4f88037f4b940`;
  lookup was `not_found` and command count remained **5**. Human permission was
  still present. After explicit service-right restoration, request
  `80b257c4d33fc05918c6b017b912bb25` produced only command
  `cmd_cf96c941258c46679390caf25dd91cd7`, succeeded/executed, one delivery;
  command count became **6**. Fresh mock output was **false** after the pulses.
- Core restart preserved command history. A later disable/enable boundary made
  the old-generation lookup `invalidated` without deleting execution history.
  A later Queue click has no preserved new request ID or seventh command proof;
  it is **not** counted as another execution. The owner explicitly accepted this
  stage and limitation after the temporary mock session expired.

### Standalone plus local mock Agent — successful command slice

- Raspberry `rasp-3mm`, beta.54, local Standalone Agent
  `dev_1dde24681b12499289727ea03d7c17af`; app installation **6**.
- Target build `8d6b2994585db00917e6f31c766ff2f452954259b2798f6c439c0fb26aa05828`;
  native review `0b386bf1adc93926601ce4774759f7c5`. Owner reported the separate
  active review/Approve/Apply and effective rights.
- Following the ordinary-user browser instructions, the owner supplied command
  `cmd_a84365ee48174a9cb0b92371d0fcf4e1`, `succeeded`, `claimed: true`,
  `execution_state: executed`, no error, 50 ms pulse and safe value false.
  A fresh local mock-state read confirmed output false.
- The original application request ID and delivery count were not supplied.
  No Standalone replay/kiosk/revocation/restart result is invented from the Hub
  results. Do not send another pulse just to recover missing metadata.

## Disposable Standalone recovery — accepted bounded scenarios

Target: WSL **3mm-WP4-Test**, beta.54, Agent
`dev_74e0a560294448b1ba7ccd8f71e502d4`. Never substitute the owner Ubuntu Hub.
Fixture `org.3mm.wp4-test` **1.0.0**, installation **1**, ZIP
`6cd6368d8f6402bb486ebcb5288c7369c0d30884beedeed9ad6db782fe175ca5`.

1. Portable backup `bkp_20261019T193441Z_700a6254.3mmrecovery` captured
   `WP4 recovery BEFORE`, SHA-256
   `b2592ab0ab736867aca2f515b983f04d817e9dfaac5ee7ba1ec8c1cdb1d3f91a`,
   completed request `3626b4f82de14a89998b5feed30e9152`.
2. A subsequent confirmed write, request `f0e5254dd47f43e080ee9e7b28b22002`,
   changed it to `WP4 recovery AFTER`, SHA-256
   `34b6c9449c662779d92ec63091281ad5a32ba77d86c11f1ba44c6040c288c340`.
3. Actual product **Restore from file** restored BEFORE bytes, service readiness
   and original Core/device identity, with fresh authority generation/app epoch.
   Old rights and reads were blocked. AFTER's restored receipt was absent and
   was not replayed. Old-key historical BEFORE receipt verification was denied,
   not silently re-signed.
4. The original missing-key helper refused without creating a key. Its corrected,
   explicitly selected missing-key workflow provisioned a new review key and
   native review, but did **not** restore resource permissions. A separate fresh
   owner Review/Approve/Apply produced grant revision **3** and SDK readback of
   the exact BEFORE text/digest.
5. The corrected full backup worker trial returned `backup-resume`, `passed: true`,
   exit **0**; the exact previously active app resumed. Owner SDK readback again
   confirmed BEFORE bytes. This tested the root worker, not beta.54's UI helper.
6. The first injected rollback restored base services but missed the app restart;
   that trial **failed**. The corrected **rollback-v2** returned `passed: true`,
   expected installer exit **1** after deliberately injected post-health failure.
   The installer automatically restored beta.54 and the exact app, with preserved
   identity/bytes and fresh authority generation, without a post-trial manual start.
7. Owner status/get after rollback confirmed active service but ineffective old
   rights, `review_key_unavailable`, and signed SDK read **blocked**. No automatic
   key recovery, reapproval or business-operation replay was performed.

Original failure logs and corrected results remain protected at
`/var/lib/3mm/wp4-closeout-tests` on that test distro. These are immutable-installer
and portable-file tests, not Hub restore, a new-version SQL migration or injected
failure through the published signed UI-update delivery chain.

Two initial BEFORE receipt reads returned HTTP 404 before the same-ID lookup
succeeded. Their cause remains unestablished; retain the observation rather than
calling it normal propagation or claiming that beta.55 fixed it. No duplicate put
was reported for that observation.

## Corrections published and integrated in beta.55

Verified on 2026-10-21 against GitHub repository metadata, not inferred merely
from local `VERSION` or a tag:

- Commit **`2e634e22f7498f798867a6de4e23ace6024ac8a4`**, tag **v0.3.0-beta.55**.
- [Exact-tag CI](https://github.com/ldobranov/3mm/actions/runs/39547773192):
  Python tests and frontend checks **success**.
- [Immutable release workflow](https://github.com/ldobranov/3mm/actions/runs/39547773376):
  **success**; [release](https://github.com/ldobranov/3mm/releases/tag/v0.3.0-beta.55)
  is published, non-draft, with full x86_64/ARM and ARMv6 Node assets/manifests.
- The tag contains exact backup app-unit resumption, empty-host service
  enumeration and ERR-trap/rollback app-resumption fixes. The beta.54 test
  candidates are not substituted for published release archives.
- Owner reported the Raspberry update successful, and supplied beta.55 VERSION,
  all four active base services and Core ready on the Ubuntu VM Hub. The earlier
  failed VM update is retained as a failed attempt; subsequent readiness is not
  proof that every possible update/rollback path passed.

Local consolidated release evidence, already recorded in the
[beta.55 notes](RELEASE_NOTES_0.3.0-beta.55.md): **4,770 passed / 604 skipped** in
the default Python suite; deployment/SDK **416 passed / 1 skipped**; frontend
**492 tests**, type-check and build pass. Hosted-job success is verified above;
these local test counts are not relabeled as hosted counts or new runs today.
Privileged/opt-in skips remain skips; targeted Root evidence does not cover all.

## Decision, boundaries and follow-up

The owner accepted the recorded functional evidence and explicit limits on
**2026-10-21**. **M20/WP4 is functionally completed.** No WP4 closeout decision
remains pending. No new implementation task or mandatory repeat of an accepted
scenario was identified by this reconciliation. This is not a claim of exhaustive
live coverage for every family/layout or an approval to reduce an agreed criterion.

- Styles of the neutral test app were explicitly excluded by the owner from
  functional acceptance. The observed missing scoped CSS remains a separate
  presentation defect; visual completion is not claimed.
- Unsupported scoped identity proof, peer mutation/receiver/unfiltered listing,
  jobs/public HTTP execution, arbitrary capability registration and SQL/peer
  combinations remain reported/refused. Compatibility is not a scoped fallback.
- General SQL/account/lifecycle workflows beyond the accepted prepared-profile
  scenarios, Hub portable restore and unassisted beta.55 clean-install acceptance
  are not established by these tests. Keep their original contracts/limitations;
  do not infer them from a healthy upgrade or the beta.54 first-install workaround.
- WP5 hostile-native-code, browser isolation and resource quotas are not proved
  by public SDK helpers or this functional acceptance record.
- M21 local Terminal, Node/Fleet/Cloud sessions and the unpublished Terminal
  disconnect/cleanup repair are separate. Its 113 targeted local passes are not
  additional WP4 release coverage and do not postpone non-session WP4 acceptance.

No runtime code, service, grant, release version or installed system was changed
to compile this record. No commit/push/publication or whole-M20 closure is implied.
