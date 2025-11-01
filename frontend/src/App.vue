<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'
import { ref, onMounted, onUnmounted, computed } from 'vue'
import Menu from './components/Menu.vue'
import CommandPalette from './components/CommandPalette.vue'
import { useThemeStore } from '@/stores/theme'
import { useSettingsStore } from '@/stores/settings'
import '@/assets/styles.css';

// Initialize stores
const themeStore = useThemeStore()
const settingsStore = useSettingsStore()

// Use reactive settings from store
const siteName = computed(() => settingsStore.headerSettings.siteName)
const headerMessage = computed(() => settingsStore.headerSettings.headerMessage)
const logoUrl = computed(() => settingsStore.headerSettings.logoUrl)
const headerBgColor = computed(() => settingsStore.headerSettings.backgroundColor)
const headerTextColor = computed(() => settingsStore.headerSettings.textColor)
const showDefaultLogo = computed(() => !logoUrl.value)

const fetchHeaderSettings = async () => {
  try {
    await settingsStore.loadSettings()
  } catch (e) {
    console.error('Failed to fetch header settings:', e)
  }
}

onMounted(() => {
  fetchHeaderSettings()
  // Listen for settings updates
  window.addEventListener('settings-updated', fetchHeaderSettings)
})

onUnmounted(() => {
  window.removeEventListener('settings-updated', fetchHeaderSettings)
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
