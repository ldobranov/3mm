# 3mm project instructions

You are working on the 3mm project.

## Project scope

3mm is a full-stack project covering the Core backend, frontend, shared
protocol, Agent, provisioning, runtime extensions and Raspberry Pi deployment.

Work on the part of the system required by the user's current request. Backend,
API, database, authentication, routing and deployment changes are allowed when
the requested feature or fix requires them. Keep those changes scoped,
compatible where practical, migrated, tested and recoverable.

## Frontend redesign direction

When working on the frontend visual redesign, the goal is to transform the
existing Bootstrap-like admin interface into a clean, modern
control/management application.

The desired visual direction is:

- professional desktop application feel
- neutral graphite / white surfaces
- restrained use of color
- one accent color
- clean typography
- compact controls
- clear visual hierarchy
- excellent dark mode
- responsive mobile layout
- avoid generic Bootstrap admin-panel appearance

The main desktop layout should become:

- left application sidebar
- main content area
- compact top controls where appropriate

The Display Editor should ultimately become a workspace-style interface:
- widgets/palette on the left
- canvas in the center
- properties/editor panel on the right

Do not implement the whole redesign in one step.

## Project architecture rules

CRITICAL:

- Change backend behavior only when required by the current task.
- Preserve existing API compatibility unless the user explicitly approves a breaking change.
- Database model changes require an Alembic migration and migration tests.
- Authentication and authorization changes require explicit task scope and security tests.
- Routing changes must preserve authentication, role filtering and dynamic registrations.
- Do not hardcode extension or module names into Core.
- Navigation must remain data-driven.
- Extension routes and module registrations must continue to work dynamically.
- Preserve existing i18n behavior.
- Preserve light/dark theme support.
- Preserve user authentication and role filtering.
- Preserve Command Palette behavior.
- Preserve dynamically loaded extensions.

The Core must never know concrete modules/extensions by name.

## Frontend stack

The frontend is:

- Vue 3
- TypeScript
- Vite
- Pinia
- Vue Router
- Bootstrap is currently installed
- Bootstrap Icons are used
- existing CSS custom properties are used for theming

Do not introduce another frontend framework without explicit approval.

Do not add Tailwind, Vuetify, Quasar, PrimeVue or another component framework.

Prefer native Vue + CSS.

## CSS strategy

We currently have a mixture of:

- Bootstrap classes
- global custom CSS
- scoped component CSS
- inline styles

The redesign should gradually consolidate this.

Prefer:

1. global design tokens / CSS variables
2. reusable component classes
3. scoped styles only for component-specific layout

Avoid adding more inline styles.

Do not rewrite the entire CSS system at once.

Existing theme variables and settings must remain compatible unless explicitly changed.

## Safety rules

Before editing a file:

1. Read the entire relevant file.
2. Read components or stores it directly depends on when necessary.
3. Explain briefly what you intend to change.
4. Modify the minimum number of files required.

Never make unrelated cleanup changes while doing visual work.

Never delete functionality just because it looks unused without checking router/import/API usage.

Do not create branches.
Do not modify Git history.

Do not commit or push unless the user explicitly requests it. When requested,
review the exact scope, exclude local/generated artifacts, run proportionate
checks, then commit and push intentionally.

## Working style

Work incrementally.

For each step:

1. inspect the existing implementation
2. explain the proposed visual change
3. edit only the required files
4. run the frontend build
5. report errors if any
6. for visual redesign work, do not continue to the next major screen until the current one has been visually reviewed

When possible use:

npm run build-only

If dependencies are missing, report that rather than changing deployment architecture.

## First redesign phases

Phase 1:
- App.vue
- Menu.vue
- global styles

Goal:
Create the new application shell and navigation.

Phase 2:
- DashboardList.vue

Goal:
Modern project/dashboard cards and clearer information hierarchy.

Phase 3:
- DisplayEditor.vue
- WidgetPalette.vue
- EditorPanel.vue
- DisplayCanvas.vue only if required

Goal:
Create a true workspace/editor layout.

Phase 4:
- Settings.vue and settings components

Goal:
Make Settings easier to navigate and visually consistent.

## Important: Raspberry deployment

The Raspberry Pi deployment is an immutable release layout:

/opt/3mm/current -> /opt/3mm/releases/<release-id>

The Raspberry deployment normally receives a prebuilt frontend/dist.

Do not redesign the deployment process as part of unrelated frontend visual
work. Deployment changes are allowed when explicitly requested or required by
the active milestone, and must preserve immutable releases, health checks and
rollback.

For normal development, edit and build in the local Git checkout.

## Visual review

Codex should use browser automation when useful to inspect the running application after visual changes.

Do not judge visual success only from code.

Check:
- spacing
- alignment
- responsive layout
- light mode
- dark mode
- navigation states
- long labels
- forms
- modals

Take screenshots or describe visible issues before proceeding.
