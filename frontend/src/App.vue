<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'
import Menu from './components/Menu.vue'
import CommandPalette from './components/CommandPalette.vue'
import { useThemeStore } from '@/stores/theme'
import { useSettingsStore } from '@/stores/settings'
import { useI18n } from '@/utils/i18n'
import http from '@/utils/dynamic-http'
import { readSettings } from '@/utils/settings-api'
import '@/assets/styles.css';

// Initialize stores
const themeStore = useThemeStore()
const settingsStore = useSettingsStore()
const { currentLanguage } = useI18n()

// Local reactive refs for header settings
const siteName = ref('Mega Monitor')
const headerMessage = ref('Welcome to Mega Monitor')
const logoUrl = ref('')
const headerBgColor = ref('#4CAF50')
const headerTextColor = ref('#ffffff')
const showDefaultLogo = computed(() => !logoUrl.value)

// Authentication status
const isAuthenticated = ref(!!localStorage.getItem('authToken'))
const authInterval = ref<ReturnType<typeof setInterval> | null>(null)

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

const fetchHeaderSettings = async () => {
  try {
    // Fetch header settings for current language (merged global + language-specific)
    const items = await readSettings(currentLanguage.value)

    // Update local refs with merged settings
    const siteNameSetting = items.find((s: any) => s.key === 'site_name')
    const headerMessageSetting = items.find((s: any) => s.key === 'header_message')
    const logoSetting = items.find((s: any) => s.key === 'logo_url')
    const bgColorSetting = items.find((s: any) => s.key === 'header_bg_color')
    const textColorSetting = items.find((s: any) => s.key === 'header_text_color')

    siteName.value = siteNameSetting?.value || 'Mega Monitor'
    headerMessage.value = headerMessageSetting?.value || 'Welcome to Mega Monitor'
    logoUrl.value = logoSetting?.value || ''
    headerBgColor.value = bgColorSetting?.value || '#4CAF50'
    headerTextColor.value = textColorSetting?.value || '#ffffff'
  } catch (e) {
    console.error('Failed to fetch header settings:', e)
    // Set defaults
    siteName.value = 'Mega Monitor'
    headerMessage.value = 'Welcome to Mega Monitor'
    logoUrl.value = ''
    headerBgColor.value = '#4CAF50'
    headerTextColor.value = '#ffffff'
  }
}

// Poll for auth token changes (since localStorage changes don't trigger watchers)
const checkAuth = () => {
  const currentAuth = !!localStorage.getItem('authToken')
  if (currentAuth !== isAuthenticated.value) {
    isAuthenticated.value = currentAuth
  }
}

// Watch for authentication changes
watch(isAuthenticated, async (newVal, oldVal) => {
  console.log('auth watcher triggered: newVal', newVal, 'oldVal', oldVal)
  if (newVal && !oldVal) {
    console.log('user logged in, calling loadDefaults')
    // User just logged in, reload defaults to save preferences
    await loadDefaults()
  }
})

onMounted(async () => {
  fetchHeaderSettings()
  // Listen for settings updates
  window.addEventListener('settings-updated', fetchHeaderSettings)
  // Listen for language changes
  window.addEventListener('language-changed', fetchHeaderSettings)

  // Load default theme and language for new users
  await loadDefaults()

  // Start polling for auth changes
  authInterval.value = setInterval(checkAuth, 1000)
})

onUnmounted(() => {
  window.removeEventListener('settings-updated', fetchHeaderSettings)
  window.removeEventListener('language-changed', fetchHeaderSettings)
  if (authInterval.value) {
    clearInterval(authInterval.value)
  }
})
</script>

<template>
  <div id="app" :style="{ backgroundColor: settingsStore.styleSettings.bodyBg }">
    <header class="app-header" :style="{ backgroundColor: headerBgColor, color: headerTextColor }">
      <Menu />
    </header>

    <RouterView />
    <CommandPalette />
  </div>
</template>

<style scoped>
#app {
  min-height: 100vh;
  background-color: var(--body-bg, #ffffff);
  transition: background-color 0.3s ease;
}

header {
  padding: 0;
}

.app-header :deep(.navbar) {
  width: min(100% - 2rem, 1200px);
  min-height: 64px;
  margin: 0 auto;
  padding: 0.5rem 0;
}

.app-header :deep(.navbar-brand) {
  font-size: 1.1rem;
  font-weight: 700;
  letter-spacing: -0.02em;
}

.app-header :deep(.nav-link) {
  border-radius: 8px;
  padding: 0.55rem 0.75rem;
  font-size: 0.9rem;
}

@media (max-width: 991px) {
  .app-header :deep(.navbar-collapse) {
    padding: 0.75rem 0 0.5rem;
  }
}
</style>
