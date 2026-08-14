# Milestone 6 Report

Date: 2026-08-14

## Result

Milestone 6 is implementation-complete. 3mm can build a read-only AI context
from trusted device capabilities, validate a strict declarative automation,
show its exact device/action diff, and require explicit hash-bound approval
before deployment.

Approved local automations are delivered through the existing idempotent Agent
command queue. The Agent stores them atomically, restores them after restart,
and runs their capability event/action bindings without Core or an AI provider.
Simulation and dry-run do not mutate device state. Applied revisions, rollback
commands, original intent and actors are linked by an automation audit trail.

## AI usage and billing boundary

- Groq and OpenRouter are behind a provider-independent completion interface.
- Every paid job has a conservative estimate and requires an approved maximum.
- Prepaid credit is reserved before the provider call, settled against recorded
  token usage, and unused or failed-job credit is released.
- BYOK keys are accepted only as a temporary request header and are never
  written to the database, usage ledger or audit data.
- The usage ledger records estimates, reservations, releases, actual token
  counts and charged microcredits without provider secrets.
- Identical completed planning requests reuse the existing reviewed artifact
  and do not call the AI provider again.
- An unavailable provider or exhausted balance blocks only a new AI job. It has
  no dependency path to Agent startup or an already deployed automation.

The internal microcredit price table is deliberately isolated from provider
adapters. Production commerce, payment processing and a remotely managed price
catalog remain integration concerns rather than automation runtime concerns.

## User workflow

The administrator can describe behavior in natural language, choose prepaid or
BYOK mode, inspect an estimate, approve the maximum, and generate a proposal.
The same screen then supports readable review, explicit approval, simulation,
dry-run, apply and rollback. Invalid capability references cannot be applied.

The deployment view distinguishes the Core revision from the Agent result. It
shows queued, installed and failed delivery states, the configured enabled or
disabled state, and the last Agent error. Applied proposals are hidden from the
review queue by default and remain available through the completed-history
filter.

Enable and disable operations create immutable revisions and use the same
idempotent `automation.apply` command boundary. A disabled revision removes its
runtime subscription while retaining the declarative automation on disk.

## Automated verification

- Focused Core, Agent and shared-protocol tests pass for proposal validation,
  deployment status, revision-based enable/disable and restart restoration.
- The migration test builds a clean database to the new head, verifies Alembic
  consistency, repeats the upgrade, and downgrades to base.
- Tests cover prepaid reservation and settlement, insufficient balance, BYOK
  secret non-persistence, artifact reuse, simulation purity, audited rollback,
  local offline execution, disabled-subscription removal and restart restoration.
- Frontend TypeScript checking and the production Vite build pass.

## Raspberry acceptance result

The workflow was deployed to `rasp-3mm` as an immutable working release. Live
Groq and OpenRouter requests both produced proposals. The capability metadata
contract rejected unsupported trigger/action combinations and non-Boolean GPIO
values before deployment.

Mock GPIO module `1.0.4` was installed on the Agent. The accepted automation was
applied, persisted unchanged across Agent restart, disabled through revision 3,
and enabled again through revision 4. With the automation disabled, changing
`gpio.input.1` to `true` left `gpio.output.1` at `false`. After enabling and
restarting the Agent, the same input transition changed the output to `true`.
The behavior therefore runs locally without an AI provider in the execution
path.
