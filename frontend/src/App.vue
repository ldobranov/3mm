<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'
import Menu from './components/Menu.vue'
import CommandPalette from './components/CommandPalette.vue'
import { useThemeStore } from '@/stores/theme'
import { useSettingsStore } from '@/stores/settings'
import { useI18n } from '@/utils/i18n'
import http from '@/utils/dynamic-http'
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
const authInterval = ref<number | null>(null)

const loadDefaults = async () => {
  try {
    const response = await http.get('/settings/read')
    const items = response.data.items || []

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
    const response = await http.get(`/settings/read?language=${currentLanguage.value}`)
    const items = response.data.items || []

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
    <header :style="{ backgroundColor: headerBgColor, color: headerTextColor }">
      <img
        v-if="showDefaultLogo"
        alt="Vue logo"
        class="logo"
        src="@/assets/logo.svg"
        width="125"
        height="125"
      />
      <img
        v-else-if="logoUrl"
        :alt="siteName + ' logo'"
        class="logo"
        :src="logoUrl"
        style="max-width: 200px; max-height: 125px; width: auto; height: auto;"
      />

      <div class="wrapper">
        <div class="greetings">
          <h1 :style="{ color: headerTextColor }">{{ siteName }}</h1>
          <h3 :style="{ color: headerTextColor }">{{ headerMessage }}</h3>
        </div>

        <nav>
          <Menu />
        </nav>
      </div>
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
  line-height: 1.5;
  max-height: 100vh;
}

.logo {
  display: block;
  margin: 0 auto 2rem;
  object-fit: contain;
}

.greetings h1 {
  font-weight: 500;
  font-size: 2.6rem;
  position: relative;
  top: -10px;
  text-align: center;
}

.greetings h3 {
  font-size: 1.2rem;
  text-align: center;
}

nav {
  width: 100%;
  font-size: 12px;
  text-align: center;
  margin-top: 2rem;
}

nav a.router-link-exact-active {
  color: var(--color-text);
}

nav a.router-link-exact-active:hover {
  background-color: transparent;
}

nav a {
  display: inline-block;
  padding: 0 1rem;
  border-left: 1px solid var(--color-border);
}

nav a:first-of-type {
  border: 0;
}

@media (min-width: 1024px) {
  header {
    display: flex;
    place-items: center;
    padding-right: calc(var(--section-gap) / 2);
  }

  .logo {
    margin: 0 2rem 0 0;
  }

  header .wrapper {
    display: flex;
    place-items: flex-start;
    flex-wrap: wrap;
  }

  .greetings h1,
  .greetings h3 {
    text-align: left;
  }

  nav {
    text-align: left;
    margin-left: -1rem;
    font-size: 1rem;

    padding: 1rem 0;
    margin-top: 1rem;
  }
}
</style>
