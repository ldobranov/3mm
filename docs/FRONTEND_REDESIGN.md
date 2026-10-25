# Frontend visual redesign guide

Read only for visual frontend work. General scope, Git and check policy remain
in root AGENTS.MD and docs/DEVELOPMENT_CHECKS.md.

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

Build after relevant frontend source changes and inspect the affected screen
in light/dark themes and relevant viewport sizes before the next major screen.
If dependencies are unavailable, report that instead of changing deployment.
