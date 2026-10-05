import { ref, watch } from 'vue'
import { defineStore } from 'pinia'
import { useSettingsStore } from '@/stores/settings'

export const useThemeStore = defineStore('theme', () => {
  // Initialize from localStorage or system preference
  const getInitialTheme = (): 'light' | 'dark' => {
    const stored = localStorage.getItem('theme')
    if (stored === 'light' || stored === 'dark') {
      return stored
    }

    // Check system preference
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      return 'dark'
    }

    return 'light'
  }

  // Apply theme to document
  const applyTheme = (newTheme: 'light' | 'dark') => {
    if (newTheme === 'dark') {
      document.documentElement.classList.add('dark-mode')
      document.body.classList.add('dark-mode')
    } else {
      document.documentElement.classList.remove('dark-mode')
      document.body.classList.remove('dark-mode')
    }
  }

  const initialTheme = getInitialTheme()
  const theme = ref<'light' | 'dark'>(initialTheme)

  // Apply initial theme without setting localStorage
  applyTheme(initialTheme)

  // Watch for theme changes
  watch(theme, (newTheme) => {
    applyTheme(newTheme)

    // Update CSS variables when theme changes (defensive check)
    try {
      const settingsStore = useSettingsStore()
      // Temporary design preview must not become the next browser preference.
      if (!settingsStore.previewDesign) localStorage.setItem('theme', newTheme)
      if (settingsStore && typeof settingsStore.updateCSSVariables === 'function') {
        settingsStore.updateCSSVariables()
      }
    } catch (error) {
      localStorage.setItem('theme', newTheme)
      console.warn('Settings store not ready for CSS variables update:', error)
    }
  })

  // Toggle between light and dark
  const toggleTheme = () => {
    theme.value = theme.value === 'light' ? 'dark' : 'light'
  }

  // Set specific theme
  const setTheme = (newTheme: 'light' | 'dark') => {
    theme.value = newTheme
  }

  // Check if dark mode is active
  const isDark = () => theme.value === 'dark'

  return {
    theme,
    toggleTheme,
    setTheme,
    isDark
  }
})
