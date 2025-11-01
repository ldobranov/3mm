# Theme Synchronization & Global Application Fix

## Problem Statement
1. Theme toggle in Ctrl+K (Command Palette) and Settings page were not synced
2. Dark mode was only being applied to the command palette popup, not the entire app
3. Font colors were too dark on dark backgrounds (poor contrast)

## Solution Implemented

### 1. Centralized Theme Store (`/frontend/src/stores/theme.ts`)
- Single source of truth for theme state
- Automatically persists to localStorage
- Detects system preference on first load
- Provides reactive methods: `toggleTheme()`, `setTheme()`, `isDark()`

### 2. Global CSS Variables System
**Files Updated:**
- `/frontend/src/assets/base.css` - Extended with comprehensive theme variables
- `/frontend/src/assets/main.css` - Added Bootstrap component overrides for dark mode
- `/frontend/src/assets/styles.css` - Global dark mode support

**Key Variables:**
```css
--color-background       /* Main background */
--color-text            /* Main text color */
--color-heading         /* Heading text color */
--color-card-bg         /* Card/panel background */
--color-input-bg        /* Input field background */
--color-input-border    /* Input field border */
--color-button-bg       /* Button background */
--color-button-text     /* Button text */
--color-link            /* Link color */
--color-shadow          /* Shadow color */
--color-overlay         /* Modal overlay color */
```

### 3. Settings Page Theme Toggle
**File Updated:** `/frontend/src/views/Settings.vue`

Added a new "Theme Settings" section with:
- Radio button group for Light/Dark mode selection
- Instant theme switching via `themeStore.setTheme()`
- Synced with the centralized theme store

### 4. Command Palette Integration
**File Updated:** `/frontend/src/components/CommandPalette.vue`

- Updated to use `useThemeStore()` instead of local state
- Calls `themeStore.toggleTheme()` for theme switching
- Automatically synced with Settings page

### 5. Pages View Dark Mode Support
**File Updated:** `/frontend/src/views/Pages.vue`

- Replaced all hardcoded colors with CSS variables
- Fixed modal backgrounds and text colors
- Proper contrast for all text elements
- Dark mode support for cards, forms, and modals

### 6. Main App Initialization
**File Updated:** `/frontend/src/App.vue`

- Initializes theme store on app load
- Ensures theme is applied before rendering

## How It Works

### Theme Application Flow
```
User clicks theme toggle (Settings or Ctrl+K)
    ↓
themeStore.setTheme('dark' | 'light')
    ↓
Theme store updates reactive state
    ↓
Theme store applies .dark-mode class to <html> and <body>
    ↓
CSS variables automatically update
    ↓
All components using CSS variables update instantly
```

### Synchronization
Both toggles (Settings page and Ctrl+K) use the same `useThemeStore()`:
- Changes in one location instantly reflect in the other
- Theme preference persists across sessions
- No manual sync needed

## CSS Architecture

### Light Mode (Default)
```css
:root {
  --color-background: #ffffff;
  --color-text: #2c3e50;
  --color-card-bg: #ffffff;
  --color-input-bg: #ffffff;
  --color-input-border: #d1d5db;
  /* ... more variables */
}
```

### Dark Mode
```css
.dark-mode {
  --color-background: #181818;
  --color-text: #f3f4f6;
  --color-card-bg: #1f2937;
  --color-input-bg: #374151;
  --color-input-border: #4b5563;
  /* ... more variables */
}
```

## Bootstrap Component Overrides

Dark mode styles for all Bootstrap components:
- `.btn-primary`, `.btn-secondary`, `.btn-outline-*`
- `.form-control`, `.form-select`, `.form-label`
- `.card`, `.card-header`, `.card-body`
- `.badge`, `.alert`, `.alert-*`
- `.navbar-toggler`, `.navbar-toggler-icon`

## Files Modified

1. **Theme Store**
   - `/frontend/src/stores/theme.ts` (NEW)

2. **CSS Files**
   - `/frontend/src/assets/base.css`
   - `/frontend/src/assets/main.css`
   - `/frontend/src/assets/styles.css`

3. **Vue Components**
   - `/frontend/src/App.vue`
   - `/frontend/src/views/Settings.vue`
   - `/frontend/src/views/Pages.vue`
   - `/frontend/src/components/CommandPalette.vue`
   - `/frontend/src/components/Menu.vue`
   - `/frontend/src/components/ThemeToggle.vue` (NEW)

## Testing Checklist

- [ ] Click theme toggle in Settings page → entire app changes theme
- [ ] Click theme toggle in Ctrl+K → entire app changes theme
- [ ] Both toggles show the same selected theme
- [ ] Theme persists after page refresh
- [ ] All pages support dark mode:
  - [ ] Home
  - [ ] Dashboard
  - [ ] Pages
  - [ ] Settings
  - [ ] Users
  - [ ] Security
  - [ ] Profile
- [ ] Text contrast is good in both themes
- [ ] Modals and popups respect theme
- [ ] Forms and inputs are readable in both themes
- [ ] Buttons have proper contrast

## Browser Support

- Modern browsers with CSS custom properties support
- Fallback to light mode for older browsers
- System preference detection via `prefers-color-scheme`

## Performance

- Theme changes are instant (CSS variables)
- No page reload required
- Minimal JavaScript overhead
- Efficient localStorage usage
- Smooth transitions between themes

## Future Enhancements

1. Add theme selection to user preferences (backend)
2. Add custom theme creation UI
3. Add theme preview before applying
4. Add keyboard shortcut for theme toggle (e.g., Ctrl+Shift+T)
5. Add theme scheduling (auto-switch at specific times)
