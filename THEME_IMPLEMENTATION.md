# Dark/Light Theme Implementation

## Overview
Implemented a comprehensive dark/light theme system for the entire application. The theme now works globally across all components, not just the command palette (Ctrl+K window).

## What Was Implemented

### 1. Theme Store (`/frontend/src/stores/theme.ts`)
- Centralized theme management using Pinia store
- Persists theme preference to localStorage
- Automatically applies theme on app initialization
- Supports system preference detection
- Provides `toggleTheme()`, `setTheme()`, and `isDark()` methods

### 2. CSS Variables System (`/frontend/src/assets/base.css`)
- Extended CSS custom properties for comprehensive theming
- Added variables for:
  - Background colors (main, soft, mute)
  - Text colors (heading, body)
  - Border colors
  - Card/panel backgrounds
  - Input field styling
  - Button colors
  - Link colors
  - Shadows and overlays
- Dark mode applied via `.dark-mode` class on `<html>` and `<body>`
- Respects system preference when no explicit choice is made

### 3. Global Styles (`/frontend/src/assets/styles.css`)
- Updated to use CSS variables for all colors
- Added smooth transitions for theme changes
- Dark mode support for:
  - Cards, panels, and widgets
  - Input fields, textareas, and selects
  - Buttons
  - Links
  - Tables
  - Modals and dialogs

### 4. Theme Toggle Button (`/frontend/src/components/ThemeToggle.vue`)
- Standalone component for toggling theme
- Shows sun icon in dark mode, moon icon in light mode
- Smooth animations and hover effects
- Accessible with proper ARIA labels
- Integrated into the main navigation menu

### 5. Updated Components
- **App.vue**: Initializes theme store on app load
- **Menu.vue**: Includes ThemeToggle button in navigation
- **CommandPalette.vue**: Uses centralized theme store instead of local state

## How to Use

### For Users
1. **Toggle via Button**: Click the sun/moon icon in the navigation menu
2. **Toggle via Command Palette**: Press `Ctrl+K` and select "Toggle Dark Mode"
3. **Automatic**: Theme preference is saved and persists across sessions

### For Developers

#### Using the Theme Store
```typescript
import { useThemeStore } from '@/stores/theme'

const themeStore = useThemeStore()

// Toggle theme
themeStore.toggleTheme()

// Set specific theme
themeStore.setTheme('dark')
themeStore.setTheme('light')

// Check current theme
const isDark = themeStore.isDark()
const currentTheme = themeStore.theme // 'light' or 'dark'
```

#### Using CSS Variables in Components
```css
.my-component {
  background-color: var(--color-card-bg);
  color: var(--color-text);
  border: 1px solid var(--color-border);
}

.my-button {
  background-color: var(--color-button-bg);
  color: var(--color-button-text);
}

.my-button:hover {
  background-color: var(--color-button-hover);
}
```

#### Adding Theme-Specific Styles
```css
/* Light mode (default) */
.my-element {
  background: white;
}

/* Dark mode */
.dark-mode .my-element {
  background: #1f2937;
}
```

## Available CSS Variables

### Colors
- `--color-background`: Main background color
- `--color-background-soft`: Slightly different background
- `--color-background-mute`: Muted background
- `--color-text`: Main text color
- `--color-heading`: Heading text color
- `--color-border`: Border color
- `--color-border-hover`: Border color on hover

### Component-Specific
- `--color-card-bg`: Card/panel background
- `--color-input-bg`: Input field background
- `--color-input-border`: Input field border
- `--color-button-bg`: Button background
- `--color-button-text`: Button text
- `--color-button-hover`: Button hover state
- `--color-link`: Link color
- `--color-link-hover`: Link hover color
- `--color-shadow`: Box shadow color
- `--color-overlay`: Modal overlay color

## Features

### ✅ Implemented
- Global theme switching
- Persistent theme preference (localStorage)
- System preference detection
- Smooth transitions between themes
- Theme toggle button in navigation
- Command palette integration
- Comprehensive CSS variable system
- Dark mode support for all UI elements

### 🎨 Theme Colors

#### Light Mode
- Background: White (#ffffff)
- Text: Dark gray (#2c3e50)
- Accents: Green (#4CAF50)

#### Dark Mode
- Background: Dark gray (#181818)
- Text: Light gray (#f3f4f6)
- Accents: Emerald (#10b981)

## Browser Support
- Modern browsers with CSS custom properties support
- Fallback to light mode for older browsers
- System preference detection via `prefers-color-scheme`

## Performance
- Theme changes are instant with CSS variables
- No page reload required
- Minimal JavaScript overhead
- Efficient localStorage usage

## Accessibility
- Proper color contrast in both themes
- ARIA labels on theme toggle button
- Keyboard accessible
- Respects user's system preferences
