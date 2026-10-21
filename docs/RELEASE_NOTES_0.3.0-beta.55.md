# 3mm 0.3.0-beta.55 — prepared release notes

Status: local preparation only. No commit, tag, GitHub Release or installed update
is implied. Publish only from the reviewed exact `main` commit after the existing
Python 3.13/Node 22 and reproducible full/Node artifact workflow succeeds.

## Included

- Scoped M21 local browser sessions with real M20 service-resource approval and
  independent current human permission. No administrator bypass, token exposure,
  automatic reconnect or replay of uncertain input.
- Reviewed local/self-provider declarations and per-session systemd dynamic-user
  workers. Private Core/home/Windows paths and network access are unavailable;
  scratch space, memory, processes, descriptors and lifetime are bounded.
- Independent output, input, resize, disconnect and human/service revocation
  cleanup through one SDK/browser contract. Core owns isolation/transport, not a
  concrete Terminal implementation. Old unrestricted prototypes remain unmounted.
- Exact backup application-unit resumption and update/rollback quiescence fixes;
  service resumption failures are no longer hidden by a healthy Core service.

## Local checks

| Check | Result |
| --- | --- |
| Full Linux Python 3.12.3 suite | 4,770 passed; 604 explicitly skipped |
| Full deployment / Application SDK | 416 passed; one opt-in systemd skip |
| Core frontend, Node 22.23.3 | 492 tests / 56 files; type-check and build pass |
| Separate Terminal 1.0.2 | 38 frontend tests; 38 Python tests; type-check and M20 ZIP validation pass |
| Separate disposable Root/session profile | Real PTY, output/resize, denial and cleanup; idle human/service revocation |

The 604 default-suite skips include 595 Root-helper cases, additional privileged
and opt-in HTTPS/systemd cases, and two non-POSIX-only refusals. They are not
counted as passing. The targeted Root/profile proof does not cover every skip.
Warnings remain visible. Earlier interrupted/failed runs are not completed proof;
overlapping regressions/repetitions are not additional distinct release coverage.

Before metadata preparation, both working checkouts were byte-compared with the
owner's successful Linux test copies, including the two corrected test fixtures.
The forthcoming exact-tag workflow and installed-VM trial are still required.
The post-metadata package/release-contract regression also passes 101 cases;
this overlaps the complete suites and is not additional unique coverage.

Prepared separate artifact: `3mm-terminal-1.0.2.zip`, 111,173 bytes, SHA-256
`fdbd7d347c7884893a582ab911f340114a8622abab2a61f40e20099b272a7962`.
Its final source ZIP validates and compiles through Core's actual UI compiler.
Local compiled output is not an installed native/UI trust record; build/review
again through the target Core before approving access.

The Terminal follow-up fixes 16 KiB input framing and component-level PTY resize
synchronization/cleanup. It opens with the same reviewed options and uses the
separate resize control afterward; no permission or worker limit is broadened.
Version 1.0.2 uses canonical LF source endings. The earlier unpublished 1.0.1
candidate remains unchanged. Core's Python CI budget is 90 minutes, not a relaxed
test assertion; the prior local main suite alone exceeded the old 60-minute job.

## Trial after publication and update

Use **Core beta.55 + the separately built Terminal 1.0.2 package** on a recoverable
test VM first. Core does not bundle or install Terminal. Manifest v2's coarse
`>=0.3.0` floor cannot pin individual Betas; beta.54 and older lack this profile.

The feature remains OFF by default. Follow
[the local trial procedure](M21_LOCAL_TERMINAL_TEST.md) for the explicit flag,
socket, exact local Agent device, native/compiled-UI trust, resource review/apply
and separate human permission. Current Terminal routing requires a test admin
with `terminal_use`, not merely an administrator login.

This is a restricted temporary workspace, NOT a root/raspberry maintenance shell.
Node/Fleet/Cloud transport, cross-application provider trust and attach/detach are
not enabled. This release does not close M20/WP4 or M21, nor prove broad malicious-
code/browser isolation. No database migration, Device Protocol 1.0 or SDK 1.3 bump
is introduced. The full runtime adds `websockets==17.2`; minimal Node stays separate.

Keep a verified backup. Built-in backup/restore is Standalone-only; use an
independent VM snapshot/export for a Hub. An update does not create reviews,
approve rights, clear recovery fences, start Terminal or deploy physical effects.
