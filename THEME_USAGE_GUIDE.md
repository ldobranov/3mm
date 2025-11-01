# Theme System Usage Guide

## Quick Start

### For Users
1. **Toggle Theme via Settings Page:**
   - Go to Settings
   - Click "Light Mode" or "Dark Mode" button
   - Theme applies instantly across the entire app

2. **Toggle Theme via Command Palette:**
   - Press `Ctrl+K`
   - Search for "Toggle Dark Mode"
   - Select and press Enter
   - Theme applies instantly

3. **Theme Persistence:**
   - Your theme choice is automatically saved
   - Theme will be restored when you return to the app

### For Developers

#### Using the Theme Store

```typescript
import { useThemeStore } from '@/stores/theme'

export default {
  setup() {
    const themeStore = useThemeStore()
    
    // Get current theme
    const isDark = themeStore.isDark()  // boolean
    const theme = themeStore.theme      // 'light' | 'dark'
    
    // Change theme
    themeStore.toggleTheme()            // Toggle between light/dark
    themeStore.setTheme('dark')         // Set specific theme
    themeStore.setTheme('light')
    
    return { isDark, theme }
  }
}
```

#### Using CSS Variables in Components

```vue
<template>
  <div class="my-component">
    <h1>Hello World</h1>
    <p>This text will automatically adapt to the theme</p>
  </div>
</template>

<style scoped>
.my-component {
  background-color: var(--color-background);
  color: var(--color-text);
  padding: 1rem;
  border: 1px solid var(--color-border);
}

.my-component h1 {
  color: var(--color-heading);
}
</style>
```

#### Available CSS Variables

**Background Colors:**
- `--color-background` - Main background
- `--color-background-soft` - Slightly different background
- `--color-background-mute` - Muted background
- `--color-card-bg` - Card/panel background

**Text Colors:**
- `--color-text` - Main text
- `--color-heading` - Heading text
- `--color-link` - Link text
- `--color-link-hover` - Link hover state

**UI Elements:**
- `--color-border` - Border color
- `--color-border-hover` - Border hover state
- `--color-input-bg` - Input field background
- `--color-input-border` - Input field border
- `--color-button-bg` - Button background
- `--color-button-text` - Button text
- `--color-button-hover` - Button hover state

**Effects:**
- `--color-shadow` - Box shadow color
- `--color-overlay` - Modal overlay color

#### Adding Dark Mode to New Components

**Option 1: Use CSS Variables (Recommended)**
```vue
<style scoped>
.my-card {
  background: var(--color-card-bg);
  color: var(--color-text);
  border: 1px solid var(--color-border);
}
</style>
```

**Option 2: Use Dark Mode Class**
```vue
<style scoped>
.my-card {
  background: white;
  color: #333;
}

.dark-mode .my-card {
  background: #1f2937;
  color: #f3f4f6;
}
</style>
```

**Option 3: Conditional Styling**
```vue
<template>
  <div :class="{ 'dark-theme': isDark }">
    <!-- content -->
  </div>
</template>

<script setup>
import { useThemeStore } from '@/stores/theme'
import { computed } from 'vue'

const themeStore = useThemeStore()
const isDark = computed(() => themeStore.isDark())
</script>

<style scoped>
.dark-theme {
  background: #1f2937;
  color: #f3f4f6;
}
</style>
```

## Theme Colors Reference

### Light Mode
| Element | Color | Hex |
|---------|-------|-----|
| Background | White | #ffffff |
| Text | Dark Gray | #2c3e50 |
| Heading | Dark Gray | #2c3e50 |
| Card | White | #ffffff |
| Input | White | #ffffff |
| Border | Light Gray | #d1d5db |
| Link | Green | #34d399 |
| Button | Green | #4CAF50 |

### Dark Mode
| Element | Color | Hex |
|---------|-------|-----|
| Background | Very Dark Gray | #181818 |
| Text | Light Gray | #f3f4f6 |
| Heading | White | #ffffff |
| Card | Dark Gray | #1f2937 |
| Input | Darker Gray | #374151 |
| Border | Medium Gray | #4b5563 |
| Link | Emerald | #34d399 |
| Button | Emerald | #10b981 |

## Common Patterns

### Responsive to Theme Changes
```vue
<template>
  <div class="container">
    <div class="card">
      <h2>{{ title }}</h2>
      <p>{{ content }}</p>
    </div>
  </div>
</template>

<style scoped>
.container {
  background: var(--color-background);
  color: var(--color-text);
  transition: background-color 0.3s, color 0.3s;
}

.card {
  background: var(--color-card-bg);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 1rem;
}

.card h2 {
  color: var(--color-heading);
}
</style>
```

### Form Elements
```vue
<template>
  <form>
    <div class="form-group">
      <label>Name</label>
      <input type="text" class="form-input" />
    </div>
  </form>
</template>

<style scoped>
.form-group {
  margin-bottom: 1rem;
}

.form-group label {
  color: var(--color-text);
  display: block;
  margin-bottom: 0.5rem;
}

.form-input {
  background: var(--color-input-bg);
  color: var(--color-text);
  border: 1px solid var(--color-input-border);
  padding: 0.5rem;
  border-radius: 4px;
  width: 100%;
}

.form-input:focus {
  outline: none;
  border-color: var(--color-link);
  box-shadow: 0 0 0 3px rgba(52, 211, 153, 0.1);
}
</style>
```

### Buttons
```vue
<template>
  <button class="btn btn-primary">Click me</button>
</template>

<style scoped>
.btn {
  padding: 0.5rem 1rem;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.3s;
}

.btn-primary {
  background: var(--color-button-bg);
  color: var(--color-button-text);
}

.btn-primary:hover {
  background: var(--color-button-hover);
}
</style>
```

## Troubleshooting

### Theme not applying to new component
1. Check that component uses CSS variables
2. Verify CSS variables are defined in base.css
3. Check for hardcoded colors that override variables
4. Ensure component is not using `!important` flags

### Text not readable in dark mode
1. Check text color is using `--color-text` or `--color-heading`
2. Verify contrast ratio (should be at least 4.5:1)
3. Check for hardcoded colors in component styles

### Theme not persisting
1. Check browser localStorage is enabled
2. Verify theme store is initialized in main.ts
3. Check browser console for errors

### Sync issues between toggles
1. Ensure both components use `useThemeStore()`
2. Check that theme store is properly exported
3. Verify Pinia is initialized before components mount

## Best Practices

1. **Always use CSS variables** for colors instead of hardcoding
2. **Test both themes** when adding new components
3. **Use semantic variable names** (e.g., `--color-text` not `--color-dark-gray`)
4. **Add transitions** for smooth theme switching
5. **Check contrast ratios** for accessibility
6. **Avoid `!important`** flags that override theme variables
7. **Use computed properties** for reactive theme-based logic
8. **Document custom colors** if you add new variables

## Performance Tips

- CSS variables are applied instantly (no re-render needed)
- Theme changes don't require page reload
- localStorage is efficient for persistence
- Transitions make theme changes feel smooth
- No JavaScript overhead for theme application

## Accessibility

- Light mode: Dark text on light background (WCAG AA compliant)
- Dark mode: Light text on dark background (WCAG AA compliant)
- Both modes support color-blind users
- High contrast ratios for readability
- Respects system `prefers-color-scheme` preference
