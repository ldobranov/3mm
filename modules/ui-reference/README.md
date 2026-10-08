# UI Contract Reference 1.0.0

Neutral **UI-only application page**, not an Application SDK service or hardware
module. It demonstrates [the public `@3mm/ui/v1` contract](../../docs/EXTENSION_UI_V1.md)
without a reader binding, backend wheel, credentials or API operations.

The same reviewed Vue source uses shared Surface/Button/Dialog, native form,
validation, status badges and table classes. Its only CSS is scoped layout.
The EN/BG language selector is local demonstration content, not a second Core
language setting. Confirm changes only the in-memory demo result.

Build from the repository root:

```powershell
python modules/ui-reference/build_package.py --output .runtime/ui-reference-1.0.0.zip
```

On a Core build that ships **V7 / `@3mm/ui/v1`**, upload this ZIP through the
existing **Extensions** installer, then open `/ui-reference` as administrator.
No separate uploader, manual Core route or Agent install is needed. The ZIP uses
the existing `compiled_ui_version: 1`; entrypoint `requires_role: admin` uses the
existing frontend route guard. There are no protected backend operations here.

The reference is not auto-installed or made a required dependency of Core.
Generated ZIPs and browser fixtures are local artifacts, not release payloads.
Older Core releases without the public UI module are not supported by this new
example; legacy Vue-only extension source remains compatible.

Review under two installed v2 themes, light/dark, mobile and built-in fallback.
Entering a draft, switching appearance and cancelling a native dialog must not
send requests or discard the draft. A Core live lifecycle check is distinct from
the isolated local proof recorded in the [V7 report](../../docs/THEME_PLATFORM_V2_V7_REPORT.md).
