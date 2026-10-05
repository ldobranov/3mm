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
import { useUiLabels } from '@/utils/ui-labels'
import '@/assets/styles.css';
import '@/assets/ui-platform.css';

// Initialize stores
const themeStore = useThemeStore()
const settingsStore = useSettingsStore()
const route = useRoute()
const label = useUiLabels()
const appearanceReady = ref(false)
const startupController = new AbortController()
let disposed = false
// V1 stays legacy; v2 opts into the Core-owned shell, except protected recovery.
const modernShell = computed(() => !settingsStore.appearanceRecovery &&
  (settingsStore.previewDesign !== null || settingsStore.installedDesign !== null))
const shellMode = computed(() => resolveUiShellMode(route.meta))

// Authentication status
const isAuthenticated = ref(!!localStorage.getItem('authToken'))

const loadDefaults = async (signal?: AbortSignal) => {
  try {
    const items = await readSettings(undefined, signal)
    if (signal?.aborted) return

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
          }, signal ? { signal } : undefined)
        } catch (e) {
          console.error('Failed to save user theme:', e)
        }
      }

      if (signal?.aborted) return
      if (userLanguageSetting) {
        localStorage.setItem('preferredLanguage', userLanguageSetting.value)
        await setLanguage(userLanguageSetting.value)
      } else {
        // Authenticated user without saved preferences - save current language as their preference
        const currentLanguage = localStorage.getItem('preferredLanguage') || defaultLanguage || 'en'
        localStorage.setItem('preferredLanguage', currentLanguage)
        await setLanguage(currentLanguage)
        if (signal?.aborted) return
        try {
          await http.post('/settings/create', {
            key: 'user_language',
            value: currentLanguage,
            description: 'User language preference'
          }, signal ? { signal } : undefined)
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
    if (signal?.aborted) return
    console.error('Failed to load defaults:', e)
    // Keep the already initialized browser mode/language when settings are unavailable.
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
  // Do not mount navigation/pages in the legacy layout before public appearance,
  // saved mode, header settings and verified theme resources have settled.
  const signal = startupController.signal
  let timeout: ReturnType<typeof setTimeout> | undefined
  try {
    await Promise.race([
      Promise.allSettled([
        settingsStore.loadThemeAppearance(signal),
        loadDefaults(signal).then(() => { if (!signal.aborted) return settingsStore.loadSettings(signal) }),
      ]),
      new Promise<void>(resolve => {
        timeout = setTimeout(() => { startupController.abort(); resolve() }, 8000)
      }),
    ])
  } finally {
    clearTimeout(timeout)
    if (!disposed) {
      settingsStore.updateCSSVariables()
      appearanceReady.value = true
    }
  }
  if (disposed) return
  window.addEventListener('settings-updated', refreshAppearance)
  document.addEventListener('visibilitychange', refreshVisibleAppearance)
  // Listen for settings updates
  window.addEventListener('settings-updated', refreshSettings)
  // Listen for language changes
  window.addEventListener('language-changed', refreshSettings)
  // Same-tab auth changes use the application event; other tabs use storage.
  window.addEventListener('menu-refresh', syncAuthState)
  window.addEventListener('storage', handleAuthStorageChange)

})

onUnmounted(() => {
  disposed = true
  startupController.abort()
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
    <div v-if="!appearanceReady" class="app-startup" role="status" aria-live="polite" aria-busy="true">
      {{ label('loading') }}…
    </div>
    <template v-else>
      <ApplicationShell :active="modernShell" :design="settingsStore.uiDesign" :mode="shellMode">
        <RouterView />
      </ApplicationShell>
      <CommandPalette />
    </template>
  </div>
</template>

<style scoped>
.app-root {
  min-height: 100vh;
  background-color: var(--body-bg, #ffffff);
}

.app-startup {
  min-height: 100dvh;
  display: grid;
  place-items: center;
  background: #f5f6f8;
  color: #555b65;
  font: 500 0.875rem system-ui, sans-serif;
}

:global(html.dark-mode) .app-startup {
  background: #181b20;
  color: #b8bdc7;
}

</style>
