<script setup lang="ts">
import { RouterView, useRoute } from 'vue-router'
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'
import CommandPalette from './components/CommandPalette.vue'
import { useThemeStore } from '@/stores/theme'
import { useSettingsStore } from '@/stores/settings'
import { useI18n } from '@/utils/i18n'
import http from '@/utils/dynamic-http'
import { readSettings } from '@/utils/settings-api'
import ApplicationShell from './components/ui/ApplicationShell.vue'
import { resolveUiShellMode } from '@/utils/ui-design'
import '@/assets/styles.css';
import '@/assets/ui-platform.css';

// Initialize stores
const themeStore = useThemeStore()
const settingsStore = useSettingsStore()
const route = useRoute()
// V1 stays legacy; v2 opts into the Core-owned shell, except protected recovery.
const modernShell = computed(() => !settingsStore.appearanceRecovery &&
  (settingsStore.previewDesign !== null || settingsStore.installedDesign !== null))
const shellMode = computed(() => resolveUiShellMode(route.meta))

// Authentication status
const isAuthenticated = ref(!!localStorage.getItem('authToken'))

const loadDefaults = async () => {
  try {
    const items = await readSettings()

    const userThemeSetting = items.find((s: any) => s.key === 'user_theme')
    const userLanguageSetting = items.find((s: any) => s.key === 'user_language')
    const defaultTheme = items.find((s: any) => s.key === 'default_theme')?.value
    const defaultLanguage = items.find((s: any) => s.key === 'default_language')?.value

    const isAuthenticated = !!localStorage.getItem('authToken')
    const { setLanguage } = useI18n()

    // For authenticated users: use their saved preferences
    if (isAuthenticated) {
      if (userThemeSetting) {
        themeStore.setTheme(userThemeSetting.value as 'light' | 'dark')
        localStorage.setItem('theme', userThemeSetting.value)
      } else {
        // Authenticated user without saved preferences - save current theme as their preference
        const currentTheme = localStorage.getItem('theme') || defaultTheme || 'light'
        themeStore.setTheme(currentTheme as 'light' | 'dark')
        try {
          await http.post('/settings/create', {
            key: 'user_theme',
            value: currentTheme,
            description: 'User theme preference'
          })
        } catch (e) {
          console.error('Failed to save user theme:', e)
        }
      }

      if (userLanguageSetting) {
        localStorage.setItem('preferredLanguage', userLanguageSetting.value)
        await setLanguage(userLanguageSetting.value)
      } else {
        // Authenticated user without saved preferences - save current language as their preference
        const currentLanguage = localStorage.getItem('preferredLanguage') || defaultLanguage || 'en'
        localStorage.setItem('preferredLanguage', currentLanguage)
        await setLanguage(currentLanguage)
        try {
          await http.post('/settings/create', {
            key: 'user_language',
            value: currentLanguage,
            description: 'User language preference'
          })
        } catch (e) {
          console.error('Failed to save user language:', e)
        }
      }
    }
    // For non-authenticated users (new/incognito): use application defaults
    else {
      // Always use application defaults for new users
      if (defaultTheme) {
        themeStore.setTheme(defaultTheme as 'light' | 'dark')
        localStorage.setItem('theme', defaultTheme)
      } else {
        // Fallback if no default theme is set
        themeStore.setTheme('light')
        localStorage.setItem('theme', 'light')
      }

      if (defaultLanguage) {
        localStorage.setItem('preferredLanguage', defaultLanguage)
        await setLanguage(defaultLanguage)
      } else {
        // Fallback if no default language is set
        localStorage.setItem('preferredLanguage', 'en')
        await setLanguage('en')
      }
    }
  } catch (e) {
    console.error('Failed to load defaults:', e)
    // Fallback to safe defaults
    const { setLanguage } = useI18n()
    themeStore.setTheme('light')
    localStorage.setItem('theme', 'light')
    localStorage.setItem('preferredLanguage', 'en')
    await setLanguage('en')
  }
}

// Header content and visual precedence have one owner, the settings store.
const refreshSettings = () => { void settingsStore.loadSettings() }

const syncAuthState = () => {
  const currentAuth = !!localStorage.getItem('authToken')
  if (currentAuth !== isAuthenticated.value) {
    isAuthenticated.value = currentAuth
  }
}

const handleAuthStorageChange = (event: StorageEvent) => {
  if (event.key === 'authToken') {
    syncAuthState()
  }
}

const refreshAppearance = () => { void settingsStore.loadThemeAppearance() }
const refreshVisibleAppearance = () => {
  if (document.visibilityState === 'visible') refreshAppearance()
}

// Watch for authentication changes
watch(isAuthenticated, async (newVal, oldVal) => {
  if (newVal && !oldVal) {
    // User just logged in, reload defaults to save preferences
    await loadDefaults()
  }
})

onMounted(async () => {
  // Independently load public appearance even when legacy settings/auth fail.
  void settingsStore.loadSettings()
  refreshAppearance()
  window.addEventListener('settings-updated', refreshAppearance)
  document.addEventListener('visibilitychange', refreshVisibleAppearance)
  // Listen for settings updates
  window.addEventListener('settings-updated', refreshSettings)
  // Listen for language changes
  window.addEventListener('language-changed', refreshSettings)
  // Same-tab auth changes use the application event; other tabs use storage.
  window.addEventListener('menu-refresh', syncAuthState)
  window.addEventListener('storage', handleAuthStorageChange)

  // Load default theme and language for new users
  await loadDefaults()

})

onUnmounted(() => {
  window.removeEventListener('settings-updated', refreshAppearance)
  document.removeEventListener('visibilitychange', refreshVisibleAppearance)
  window.removeEventListener('settings-updated', refreshSettings)
  window.removeEventListener('language-changed', refreshSettings)
  window.removeEventListener('menu-refresh', syncAuthState)
  window.removeEventListener('storage', handleAuthStorageChange)
})
</script>

<template>
  <div class="app-root">
    <ApplicationShell :active="modernShell" :design="settingsStore.uiDesign" :mode="shellMode">
      <RouterView />
    </ApplicationShell>
    <CommandPalette />
  </div>
</template>

<style scoped>
.app-root {
  min-height: 100vh;
  background-color: var(--body-bg, #ffffff);
  transition: background-color 0.3s ease;
}

</style>
