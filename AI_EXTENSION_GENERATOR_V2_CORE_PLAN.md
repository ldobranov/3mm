# 3mm — AI Extension Generator v2 + Core Integration Plan

## Purpose

This document defines the target architecture and migration plan for the 3mm AI Extension Generator so it works as a first-class client of **Extension Platform v2**.

The goal is not to build an AI system that knows the internal source tree of 3mm Core.

The goal is to build an AI system that can create valid, secure and maintainable 3mm extensions using the same public contracts available to human developers.

---

# Core principle

The AI Extension Generator must generate against:

```text
Manifest v2
Extension SDK
Capability Catalog
Runtime contracts
Package format
Validation rules
Dependency metadata
```

It must not generate against:

```text
Core implementation details
private backend modules
private database sessions
private frontend stores
arbitrary host filesystem paths
systemctl/subprocess workarounds
```

This makes the generator resilient to internal Core refactors and prevents every new generated extension from creating pressure for extension-specific Core changes.

---

# Target architecture

```text
User
 │
 │ natural-language request
 ▼
AI Extension Generator
 │
 ├── Requirement Analyzer
 ├── Extension Spec Builder
 ├── Capability Resolver
 ├── Dependency Resolver
 ├── Architecture Planner
 ├── Code Generator
 ├── UI Generator
 ├── Test Generator
 └── Repair Loop
 │
 ▼
Extension Toolchain
 │
 ├── Manifest v2 Validator
 ├── SDK Type/Contract Validator
 ├── Security Validator
 ├── Tests
 └── Packager
 │
 ▼
.cxp package
 │
 ├── Local install
 ├── Private Registry
 └── Marketplace submission
```

Core provides the stable contracts.

The AI Generator consumes them.

---

# 1. Generator input model

The generator should not start by writing code.

It should first convert the user request into an **Extension Specification**.

Example user request:

```text
When GPIO 17 becomes active, send an HTTP webhook.
Provide settings for URL and debounce time.
Keep a history of the last 100 events.
```

Generated intermediate specification:

```json
{
  "name": "GPIO Webhook",
  "target": ["node"],

  "features": [
    "GPIO trigger",
    "HTTP webhook",
    "settings UI",
    "event history"
  ],

  "required_capabilities": [
    "gpio.read",
    "network.http",
    "storage.read",
    "storage.write"
  ],

  "backend_required": true,
  "frontend_required": true,

  "storage": {
    "event_history": true,
    "settings": true
  }
}
```

This specification becomes the basis for all later decisions.

---

# 2. Requirement Analyzer

## Responsibility

Extract from natural language:

- functional requirements;
- target device role;
- UI needs;
- storage needs;
- external integration needs;
- hardware requirements;
- background-processing needs;
- security-sensitive operations;
- commercial intent;
- publishing intent.

## Required output

A structured, versioned object.

The generator must avoid hidden assumptions.

If the user request is ambiguous, the generator should choose safe defaults where possible and mark uncertainty in the specification.

---

# 3. Capability Resolver

## Responsibility

Map requested functionality to the published 3mm Capability Catalog.

Example:

```text
Read GPIO
→ gpio.read

Write GPIO
→ gpio.write

HTTP request
→ network.http

Persistent extension data
→ storage.read + storage.write

Publish internal event
→ events.publish
```

## Resolution states

Every requested operation must end in one of four states:

```text
AVAILABLE_CAPABILITY
AVAILABLE_DEPENDENCY
UNSUPPORTED
CORE_CAPABILITY_CANDIDATE
```

## Important rule

The generator must never convert:

```text
UNSUPPORTED
```

into:

```text
use subprocess
import Core internals
write directly to /etc
access raw database
```

---

# 4. Core Capability Proposal

When functionality is missing, the generator may produce an architectural proposal instead of unsafe code.

Example:

```text
Requested functionality:
Read serial port from a USB adapter.

Current platform:
No serial capability available.

Proposed general-purpose capability:
serial.read
serial.write

Potential reuse:
- vending controllers
- Arduino integrations
- industrial equipment
- Modbus adapters

Recommendation:
evaluate as a generic Core capability rather than adding Vending-specific Core logic.
```

The generator must not automatically modify Core.

Core changes remain explicit architectural decisions.

---

# 5. Dependency Resolver integration

The generator should use registry/dependency metadata during planning.

Example:

```text
User needs Modbus TCP
```

If registry metadata contains:

```text
io.vendor.modbus >= 3.0
```

the generator may declare it as a dependency instead of reimplementing Modbus internally.

Generated manifest:

```json
{
  "dependencies": {
    "io.vendor.modbus": ">=3.0 <4.0"
  }
}
```

This encourages reuse and reduces generated code.

---

# 6. Manifest Generator

The generator must create Manifest v2 from the Extension Specification.

Example:

```json
{
  "schema_version": 2,
  "id": "dev.generated.gpio-webhook",
  "name": "GPIO Webhook",
  "version": "0.1.0",

  "platform": {
    "api": "2"
  },

  "runtime": {
    "type": "sandboxed"
  },

  "targets": ["node"],

  "capabilities": [
    "gpio.read",
    "network.http",
    "storage.read",
    "storage.write"
  ],

  "dependencies": {},

  "license": {
    "entitlement_required": false
  }
}
```

The manifest must be validated before code generation continues.

---

# 7. Project scaffold

The generator should use a stable extension scaffold.

Example:

```text
my-extension/
├── manifest.json
├── backend/
│   ├── main.py
│   └── ...
├── frontend/
│   ├── ...
│   └── ...
├── migrations/
├── assets/
└── tests/
```

The generator should not invent a new directory convention for each extension.

Scaffolding should be versioned with the Extension SDK.

---

# 8. Backend generation

Generated backend code must use only the public Extension SDK.

Example conceptual code:

```python
async def on_start(ctx):
    config = await ctx.storage.get("config")

    await ctx.gpio.subscribe(
        pin=config["pin"],
        callback=handle_trigger,
    )
```

Forbidden patterns for native v2 generation:

```python
from backend.db.base import get_db
from backend.services import ...
import internal_core_module
subprocess.run(["systemctl", ...])
open("/etc/...")
```

If the generator needs functionality not available in the SDK, it must stop or propose a capability.

---

# 9. Frontend generation

Generated frontend code should use a documented 3mm Frontend Extension SDK.

The SDK should expose only stable concepts, for example:

```text
extension settings
extension API calls
notifications
theme tokens
localization
navigation registration
safe events
```

Third-party generated UI must not rely on:

```text
private Vue stores
Core auth token access
internal router internals
undocumented components
```

For sandboxed UI, generated code must target the sandbox bridge.

---

# 10. Settings model

The generator should prefer declarative settings schemas where possible.

Example:

```json
{
  "settings_schema": {
    "pin": {
      "type": "integer",
      "title": "GPIO pin",
      "required": true
    },

    "webhook_url": {
      "type": "string",
      "format": "uri",
      "required": true
    },

    "debounce_ms": {
      "type": "integer",
      "default": 100
    }
  }
}
```

A declarative settings system reduces generated UI code and improves consistency.

---

# 11. Storage and data model

Generated extensions should use extension-scoped storage.

The generator must classify data as:

```text
configuration
persistent domain data
cache
logs/events
temporary data
```

It should choose the smallest suitable storage mechanism.

Direct Core database access is forbidden for native v2 output.

---

# 12. Migrations

If generated persistent schema changes between extension versions, the generator must create explicit migrations.

Example:

```text
001_initial
002_add_webhook_headers
003_add_retry_policy
```

Migrations must:

- be versioned;
- be deterministic;
- pass lifecycle preflight;
- support transactional execution where possible;
- not modify Core-owned schema.

---

# 13. Permissions generation

Permissions are derived from capabilities.

The AI must not request excessive permissions "just in case".

Example:

Bad:

```text
gpio.read
gpio.write
network.http
filesystem.full
system.manage
```

for an extension that only reads GPIO.

Good:

```text
gpio.read
network.http
storage.read
storage.write
```

The validator should compare actual SDK calls with declared permissions when possible.

---

# 14. Security validation

Before packaging, generated code must go through automated checks.

At minimum:

```text
Manifest validation
Capability validation
Forbidden import scan
Forbidden filesystem access scan
Forbidden process execution scan
Dependency validation
Frontend sandbox validation
Secrets scan
Package structure validation
```

AI-generated code must not receive a weaker security path.

---

# 15. Test generation

The generator should create tests alongside implementation.

Test classes:

```text
unit tests
capability contract tests
configuration tests
migration tests
lifecycle tests
permission tests
failure-path tests
```

Example for GPIO webhook:

```text
GPIO event triggers one webhook
debounce prevents duplicate trigger
failed HTTP request does not crash extension
invalid URL is rejected
event history is capped
```

---

# 16. Extension test harness

Core should provide a developer/AI test harness with mocked capabilities.

Example:

```python
ctx = FakeExtensionContext()

ctx.gpio.emit(17, 1)

assert ctx.http.requests == [...]
```

This allows extensions to be tested without physical Raspberry Pi hardware for most logic.

Hardware-specific integration tests can remain separate.

---

# 17. Repair loop

The AI Generator should use a controlled repair loop.

```text
generate
↓
validate
↓
test
↓
failure?
 ├── no → package
 └── yes
      ↓
 classify error
      ↓
 repair extension
      ↓
 validate again
```

The repair loop must never "fix" an error by bypassing platform boundaries.

Example:

```text
Capability denied
```

must not become:

```text
use os.open("/dev/gpio...")
```

---

# 18. Packaging

After successful validation and tests:

```text
3mm extension pack
```

creates:

```text
dist/
└── gpio-webhook-0.1.0.cxp
```

The same packager is used for:

```text
human-written extension
AI-generated extension
CI pipeline
Marketplace submission
```

---

# 19. Local AI-generated extensions

For personal/local creation:

```text
Prompt
↓
Generate
↓
Validate
↓
Tests
↓
Development package/source
↓
Install locally
```

Possible trust state:

```text
DEVELOPMENT
```

Unsigned local development may be allowed with a clear warning.

---

# 20. Marketplace publishing

AI-generated code must not be published automatically merely because generation succeeded.

Publishing pipeline:

```text
AI generated
↓
normal validation
↓
normal tests
↓
publisher identity
↓
package signing
↓
security scan
↓
review
↓
publish
```

The marketplace must not treat AI-authored code differently from human-authored code.

---

# 21. Private Registry publishing

For businesses or deployments:

```text
AI Generator
↓
.cxp
↓
private Registry
↓
specific 3mm installations
```

This allows users to benefit from AI generation without making extensions public.

---

# 22. Commercial extension generation

The generator may configure generic entitlement requirements.

Example:

```json
{
  "license": {
    "entitlement_required": true
  }
}
```

But pricing, subscriptions and payment processing remain Marketplace concerns.

The generated extension should not contain special marketplace billing logic unless it is itself an application that explicitly needs external payment functionality.

---

# 23. Generator knowledge sources

The generator should use versioned platform information.

Recommended machine-readable inputs:

```text
manifest-schema.json
capabilities.json
sdk-api.json / SDK type definitions
runtime-contract.json
package-schema.json
registry dependency metadata
UI component/contract catalog
```

Documentation can supplement these sources but should not be the only source of truth.

---

# 24. Version pinning

Every generation session should pin the target platform contract.

Example:

```text
Manifest schema: 2
Extension API: 2
SDK: 2.3
Target Core: >=0.4
```

This makes generated output reproducible and avoids silently changing code because Core advanced.

---

# 25. Generator templates

Use small maintained templates for:

```text
backend-only extension
frontend-only extension
full-stack extension
node extension
server extension
server+node extension
event-driven extension
hardware integration extension
```

Templates should contain structure and SDK wiring, not business-specific implementation.

---

# 26. AI Generator UX flow

Recommended user-facing flow:

```text
Describe extension
      ↓
AI analyzes
      ↓
Review generated plan
      ↓
Capabilities / permissions
      ↓
Generate
      ↓
Validation + tests
      ↓
Preview
      ↓
Install / Save package / Publish
```

A concise plan preview should show:

```text
Name
Target
Features
Dependencies
Capabilities
Permissions
Runtime
Data storage
External connections
```

---

# 27. Example generation

User:

```text
Create an extension for a museum.
When GPIO 17 is pressed, send UDP "20,1".
After 200 ms send "20,0".
Show the last 20 triggers.
```

Specification:

```text
Target:
node

Capabilities:
gpio.read
network.udp
storage.read
storage.write

Backend:
yes

Frontend:
yes

Runtime:
sandboxed
```

If `network.udp` exists, generation continues.

If it does not exist:

```text
Missing capability:
network.udp

Classification:
CORE_CAPABILITY_CANDIDATE

Reason:
Generic UDP send functionality can be reused by museum controls,
industrial devices and network integrations.
```

The AI does **not** generate a raw socket escape route unless raw socket access is an explicitly supported capability.

---

# 28. Existing AI Generator migration

The current generator should migrate incrementally.

## Stage 1 — Manifest v2 output

Keep current code generation where necessary, but generate the new manifest and validate against Domain v2.

## Stage 2 — `.cxp` packaging

Generated extensions use the standard distribution format.

## Stage 3 — Capability-aware planning

Add Extension Specification and Capability Resolver.

## Stage 4 — SDK-native generation

Stop generating Core-internal imports.

New extensions use Extension Platform API v2.

## Stage 5 — sandbox-native generation

Default third-party/generated extensions to sandboxed runtime.

## Stage 6 — publishing integration

Support private registry and Marketplace submission packages.

---

# 29. Legacy generated extensions

Previously generated extensions remain:

```text
legacy-trusted
```

They can continue running through the Legacy Adapter.

A future migration assistant may convert them to native v2.

Possible flow:

```text
Legacy extension
↓
analyze imports / routes / storage
↓
map to capabilities
↓
generate migration plan
↓
human review
↓
native v2 extension
```

---

# 30. Core changes required specifically to support the AI Generator

Most generator needs are already covered by the six Extension Platform v2 work packages.

The Core-side pieces that must be designed with AI use in mind are:

## A. Machine-readable Manifest schema

The generator needs authoritative schema validation.

## B. Machine-readable Capability Catalog

Each capability should expose metadata such as:

```json
{
  "id": "gpio.read",
  "api_version": "2",
  "targets": ["node", "server"],
  "runtime_support": ["trusted", "sandboxed"],
  "description": "Read GPIO inputs"
}
```

## C. Stable SDK type definitions

The AI should have explicit callable contracts.

## D. Test harness

Capabilities need mock implementations.

## E. Extension validator API/CLI

The generator should call the same validation logic used by human tooling.

## F. Package builder

One deterministic package implementation.

## G. Dependency metadata access

The generator needs registry metadata to prefer dependencies over code duplication.

## H. Compatibility preflight

Before generation completes, confirm the result can run on the selected target.

---

# 31. What does NOT belong in Core for the AI Generator

Do not add:

```text
AI prompts
model-specific code
OpenAI/Anthropic provider logic
prompt templates
generation history
token billing
chat UI
AI-specific extension loader
AI-specific security bypass
```

Those belong in the AI Extension Generator extension/service.

Core provides generic platform contracts only.

---

# 32. AI Generator as an extension

Long-term, the preferred architecture is:

```text
3mm Core
   │
   ├── Extension Platform API
   │
   └── AI Extension Generator extension
           │
           ├── AI provider
           ├── generation pipeline
           ├── project workspace
           └── package output
```

The generator itself should use Core-provided generic services where appropriate.

However, it may need elevated/trusted permissions during development/build operations. Those permissions should still be explicit and bounded.

---

# 33. Security boundary for generated projects

Generation workspace and extension runtime are different concerns.

The generator may need a controlled build workspace:

```text
generation workspace
    ↓
build/test tools
    ↓
.cxp artifact
```

The generated extension itself must still run under its declared runtime and permissions.

A trusted generator must not imply a trusted generated extension.

---

# 34. Suggested generator modules

Conceptual internal structure:

```text
ai_generator/
├── requirements/
│   └── analyzer
├── spec/
│   ├── model
│   └── validator
├── capabilities/
│   └── resolver
├── dependencies/
│   └── resolver
├── planning/
│   └── architect
├── generation/
│   ├── backend
│   ├── frontend
│   ├── manifest
│   ├── migrations
│   └── tests
├── validation/
│   └── pipeline
├── repair/
│   └── loop
├── packaging/
│   └── adapter
└── publishing/
    ├── local
    ├── registry
    └── marketplace
```

This is a generator-side design, not a Core package structure.

---

# 35. Recommended implementation sequence

## Phase 1 — Core contracts

Complete enough of:

```text
Extension Domain v2
Manifest v2
Capability catalog design
```

Then update the generator to produce structured specs and Manifest v2.

## Phase 2 — Distribution

Complete:

```text
.cxp
validator
package builder
local source
```

Then generated extensions become standard packages.

## Phase 3 — Platform API

Complete:

```text
SDK v2
capability broker
storage
events
core test harness
```

Then generator v2 stops depending on Core internals.

## Phase 4 — Isolation

Complete:

```text
sandbox runtime
permission enforcement
frontend isolation
```

Then generated extensions default to sandboxed mode.

## Phase 5 — Registry

Use the normal Registry Protocol and dependency metadata.

Generator gains:

```text
dependency discovery
private publishing
version awareness
```

## Phase 6 — Commercial foundation

Generator can mark commercial extensions as entitlement-required.

## Phase 7 — Marketplace workflow

Add:

```text
publisher submission
review state
package signing
release publishing
```

outside Core.

---

# 36. Definition of Done for AI Extension Generator v2

The generator is considered v2-ready when a user can request an extension in natural language and the system can:

```text
understand the requirement
↓
create a structured Extension Specification
↓
resolve available capabilities
↓
resolve reusable dependencies
↓
identify unsupported requirements safely
↓
generate Manifest v2
↓
generate SDK-native backend/frontend code
↓
generate tests
↓
validate permissions
↓
run the standard extension validator
↓
run tests
↓
repair normal implementation errors
↓
produce a valid .cxp
↓
install locally through Core
```

without needing to know or modify Core internals.

---

# 37. Marketplace-ready Definition of Done

The generator is marketplace-ready when the same generated `.cxp` can additionally:

```text
pass security scanning
↓
be associated with a publisher
↓
be signed
↓
be submitted for review
↓
be published to an Extension Registry
↓
receive a Marketplace listing
```

without changing the extension's basic runtime architecture.

---

# 38. Architectural acceptance test

For every generated extension requirement, ask:

```text
Can this be built entirely through published 3mm extension contracts?
```

If yes:

```text
generate extension
```

If no:

```text
Is the missing feature broadly reusable?
```

If yes:

```text
produce Core Capability Proposal
```

If no:

```text
redesign or mark unsupported
```

The forbidden path is:

```text
request
↓
generator cannot do it
↓
add one-off Core hook
```

This rule is central to keeping 3mm maintainable.

---

# Final objective

The AI Extension Generator should become a **software builder for the 3mm Extension Platform**, not a patch generator for 3mm Core.

That gives 3mm one coherent ecosystem:

```text
Human developer
        │
        ├───────────────┐
        │               │
AI Extension Generator │
        │               │
        └──────┬────────┘
               ↓
         Extension SDK
               ↓
         Manifest v2
               ↓
         Validation
               ↓
         .cxp package
               ↓
     Core / Registry / Marketplace
```

This keeps Core generic, makes generated extensions safer and more predictable, and allows the same extension to move from local experiment to private deployment or public Marketplace product without changing the platform model.
