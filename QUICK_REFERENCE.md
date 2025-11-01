# Theme System - Quick Reference Card

## 🎨 For Users

### Toggle Theme
**Option 1: Settings Page**
- Go to Settings
- Click "Light Mode" or "Dark Mode"
- Done! ✅

**Option 2: Command Palette**
- Press `Ctrl+K`
- Type "Toggle Dark Mode"
- Press Enter
- Done! ✅

### Theme Persistence
Your choice is automatically saved and will be restored when you return.

---

## 👨‍💻 For Developers

### Quick Start
```typescript
// Import the store
import { useThemeStore } from '@/stores/theme'

// Use in component
const themeStore = useThemeStore()

// Toggle theme
themeStore.toggleTheme()

// Set specific theme
themeStore.setTheme('dark')
themeStore.setTheme('light')

// Check current theme
if (themeStore.isDark()) {
  // Dark mode is active
}
```

### Use CSS Variables
```vue
<style scoped>
.my-component {
  background: var(--color-background);
  color: var(--color-text);
  border: 1px solid var(--color-border);
}
</style>
```

### Available Variables
```css
/* Backgrounds */
--color-background
--color-background-soft
--color-background-mute
--color-card-bg

/* Text */
--color-text
--color-heading
--color-link
--color-link-hover

/* UI */
--color-border
--color-border-hover
--color-input-bg
--color-input-border
--color-button-bg
--color-button-text
--color-button-hover

/* Effects */
--color-shadow
--color-overlay
```

---

## 🎯 Common Tasks

### Add Dark Mode to New Component
```vue
<template>
  <div class="my-card">
    <h2>Title</h2>
    <p>Content</p>
  </div>
</template>

<style scoped>
.my-card {
  background: var(--color-card-bg);
  color: var(--color-text);
  border: 1px solid var(--color-border);
  padding: 1rem;
  border-radius: 8px;
}

.my-card h2 {
  color: var(--color-heading);
}
</style>
```

### Create Themed Button
```vue
<button class="btn-primary">Click me</button>

<style scoped>
.btn-primary {
  background: var(--color-button-bg);
  color: var(--color-button-text);
  border: none;
  padding: 0.5rem 1rem;
  border-radius: 4px;
  cursor: pointer;
}

.btn-primary:hover {
  background: var(--color-button-hover);
}
</style>
```

### Create Themed Form
```vue
<input type="text" class="form-input" placeholder="Enter text" />

<style scoped>
.form-input {
  background: var(--color-input-bg);
  color: var(--color-text);
  border: 1px solid var(--color-input-border);
  padding: 0.5rem;
  border-radius: 4px;
}

.form-input:focus {
  outline: none;
  border-color: var(--color-link);
}
</style>
```

---

## 🎨 Color Reference

### Light Mode
```
Background:  #ffffff (white)
Text:        #2c3e50 (dark gray)
Card:        #ffffff (white)
Input:       #ffffff (white)
Border:      #d1d5db (light gray)
Link:        #34d399 (green)
Button:      #4CAF50 (green)
```

### Dark Mode
```
Background:  #181818 (very dark)
Text:        #f3f4f6 (light gray)
Card:        #1f2937 (dark gray)
Input:       #374151 (darker gray)
Border:      #4b5563 (medium gray)
Link:        #34d399 (emerald)
Button:      #10b981 (emerald)
```

---

## ⚡ Performance

- ✅ Instant theme switching (< 100ms)
- ✅ No page reload needed
- ✅ Minimal JavaScript overhead
- ✅ Efficient localStorage usage
- ✅ Smooth CSS transitions

---

## 🐛 Troubleshooting

| Problem | Solution |
|---------|----------|
| Theme not applying | Use CSS variables instead of hardcoded colors |
| Text not readable | Check text uses `--color-text` or `--color-heading` |
| Theme not persisting | Enable browser localStorage |
| Toggles out of sync | Ensure both use `useThemeStore()` |

---

## 📚 Documentation

- **THEME_USAGE_GUIDE.md** - Full developer guide
- **THEME_SYNC_FIX.md** - Architecture details
- **THEME_CHANGES_SUMMARY.txt** - Complete overview
- **IMPLEMENTATION_COMPLETE.md** - Status report

---

## ✅ Checklist for New Components

- [ ] Use CSS variables for colors
- [ ] Test in both light and dark modes
- [ ] Check text contrast
- [ ] Verify readability
- [ ] Test on mobile
- [ ] No hardcoded colors

---

## 🚀 Best Practices

1. **Always use CSS variables** for colors
2. **Test both themes** when adding features
3. **Check contrast ratios** for accessibility
4. **Avoid `!important`** flags
5. **Use semantic variable names**
6. **Add smooth transitions**
7. **Document custom colors**

---

## 📞 Need Help?

1. Check THEME_USAGE_GUIDE.md for examples
2. Review component source code
3. Check browser console for errors
4. Verify CSS variables are defined

---

**Status: ✅ Ready to Use**

Theme system is fully implemented and working across the entire application.
