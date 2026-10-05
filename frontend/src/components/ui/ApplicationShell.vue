<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import Menu from '../Menu.vue'
import ThemeToggle from '../ThemeToggle.vue'
import UiButton from './UiButton.vue'
import UiDialog from './UiDialog.vue'
import { useSettingsStore } from '@/stores/settings'
import { useUiLabels } from '@/utils/ui-labels'
import type { UiDesign, UiShellMode } from '@/utils/ui-design'

const props = withDefaults(defineProps<{ design: UiDesign; mode: UiShellMode; active?: boolean }>(), { active: true })
const settings = useSettingsStore()
const label = useUiLabels()
const route = useRoute()
const drawer = ref(false)
const application = computed(() => props.mode === 'application')
watch(() => route.fullPath, () => { drawer.value = false })
watch(() => props.mode, () => { drawer.value = false })
onBeforeUnmount(() => { drawer.value = false })
</script>

<template>
  <div :class="active ? ['ui-v2', 'ui-shell', `ui-shell--${application ? design.layout.navigation : mode}`] : 'ui-legacy-shell'"
    :data-button="active ? design.components.button : undefined" :data-card="active ? design.components.card : undefined">
    <a v-if="active" href="#ui-main" class="ui-skip">{{ label('skip') }}</a>
    <header v-if="!active" class="app-header"><Menu /></header>
    <Menu v-if="active" v-slot="{ navigation }">
      <aside v-if="application && design.layout.navigation === 'sidebar'" class="ui-sidebar">
        <RouterLink to="/" class="ui-brand">
          <img v-if="settings.brandingLogo" :src="settings.brandingLogo" alt="" />
          <span>{{ settings.headerSettings.siteName }}</span>
        </RouterLink>
        <nav :aria-label="label('navigation')" class="ui-navigation">
          <RouterLink v-for="item in navigation.items" :key="item.path" :to="item.path" class="ui-nav-item">
            <span class="ui-nav-mark" aria-hidden="true"></span>{{ navigation.label(item) }}
          </RouterLink>
        </nav>
        <RouterLink v-if="navigation.isAdmin" :to="{ name: 'UiPreview', query: { recovery: '1' } }" class="ui-recovery-link">
          {{ label('recovery') }}
        </RouterLink>
      </aside>
      <header v-if="mode !== 'display'" class="ui-toolbar">
        <UiButton v-if="application" class="ui-menu-toggle" :aria-label="label('openMenu')"
          aria-controls="ui-mobile-navigation" :aria-expanded="drawer" @click="drawer = true">☰</UiButton>
        <RouterLink v-if="!application || design.layout.navigation === 'top'" to="/" class="ui-brand ui-brand--top">
          <img v-if="settings.brandingLogo" :src="settings.brandingLogo" alt="" />
          <span>{{ settings.headerSettings.siteName }}</span>
        </RouterLink>
        <RouterLink v-if="application && design.layout.navigation === 'sidebar'" to="/" class="ui-brand ui-brand--mobile">
          <span>{{ settings.headerSettings.siteName }}</span>
        </RouterLink>
        <nav v-if="application && design.layout.navigation === 'top'" :aria-label="label('navigation')" class="ui-top-navigation">
          <RouterLink v-for="item in navigation.items" :key="item.path" :to="item.path" class="ui-nav-item">
            {{ navigation.label(item) }}
          </RouterLink>
        </nav>
        <nav v-if="!application && mode !== 'kiosk'" :aria-label="label('navigation')" class="ui-top-navigation ui-public-navigation">
          <RouterLink v-for="item in navigation.items" :key="item.path" :to="item.path" class="ui-nav-item">{{ navigation.label(item) }}</RouterLink>
        </nav>
        <div class="ui-toolbar-controls">
          <select v-if="navigation.showLanguageSwitcher" class="ui-control ui-language"
            :aria-label="label('language')" :value="navigation.selectedLanguage" @change="navigation.changeLanguage">
            <option v-for="language in navigation.languages" :key="language" :value="language">{{ language.toUpperCase() }}</option>
          </select>
          <ThemeToggle :persist-preference="!settings.previewDesign" />
          <RouterLink v-if="navigation.isAdmin && application && design.layout.navigation === 'top'"
            :to="{ name: 'UiPreview', query: { recovery: '1' } }" class="ui-button ui-button--quiet"
            :aria-label="label('recovery')" :title="label('recovery')">↺</RouterLink>
          <UiButton variant="quiet" :aria-label="label('search')" @click="navigation.openCommandPalette">
            <span aria-hidden="true">⌘</span><span class="ui-shortcut">Ctrl+K</span>
          </UiButton>
          <UiButton v-if="navigation.loggedIn" variant="quiet" @click="navigation.logout">{{ navigation.t('menu.logout', 'Logout') }}</UiButton>
          <template v-else-if="mode !== 'kiosk'">
            <RouterLink class="ui-button ui-button--quiet" to="/user/login">{{ navigation.t('menu.login', 'Login') }}</RouterLink>
            <RouterLink class="ui-button ui-button--quiet" to="/user/register">{{ navigation.t('menu.register', 'Register') }}</RouterLink>
          </template>
        </div>
      </header>
      <UiDialog v-if="application" v-model:open="drawer" class="ui-mobile-drawer" :title="label('navigation')" :close-label="label('closeMenu')">
        <nav id="ui-mobile-navigation" :aria-label="label('navigation')" class="ui-navigation">
          <RouterLink v-for="item in navigation.items" :key="item.path" :to="item.path" class="ui-nav-item" @click="drawer = false">
            {{ navigation.label(item) }}
          </RouterLink>
          <RouterLink v-if="navigation.isAdmin" :to="{ name: 'UiPreview', query: { recovery: '1' } }"
            class="ui-recovery-link" @click="drawer = false">{{ label('recovery') }}</RouterLink>
        </nav>
      </UiDialog>
    </Menu>
    <!-- Stable content parent: changing preview/shell must not remount the page. -->
    <main id="ui-main" :tabindex="active ? -1 : undefined" :class="{ 'ui-main': active }"><slot /></main>
  </div>
</template>

<style scoped>
.ui-shell { min-height: 100dvh; display: grid; grid-template-rows: auto 1fr; }
.app-header { padding: 0; background: var(--ui-header-bg, #4CAF50); color: var(--ui-header-text, #fff); }
.app-header :deep(.navbar) { width: min(100% - 2rem, 1200px); min-height: 64px; margin: 0 auto; padding: .5rem 0; }
.app-header :deep(.navbar-brand) { font-size: 1.1rem; font-weight: 700; letter-spacing: -.02em; }
.app-header :deep(.nav-link) { border-radius: 8px; padding: .55rem .75rem; font-size: .9rem; }
.ui-shell--sidebar { grid-template-columns: var(--ui-sidebar-width) minmax(0, 1fr); }
.ui-sidebar { grid-column: 1; grid-row: 1 / 3; display: flex; flex-direction: column; min-width: 0; background: var(--ui-surface); border-right: 1px solid var(--ui-border); padding: 16px 12px; }
.ui-brand { display: flex; align-items: center; gap: 10px; padding: 10px 12px; color: var(--ui-header-text); background: var(--ui-header-bg); border-radius: var(--ui-radius-sm); text-decoration: none; font-size: 1.08em; font-weight: 650; overflow-wrap: anywhere; margin: 0; }
.ui-brand img { width: 30px; max-height: 36px; object-fit: contain; }
.ui-navigation { display: grid; gap: 4px; margin-top: 20px; }
.ui-nav-item { display: flex; align-items: center; gap: 10px; min-height: 40px; padding: 9px 12px; margin: 0; color: var(--ui-text-secondary); border-radius: var(--ui-radius-sm); text-decoration: none; overflow-wrap: anywhere; line-height: 1.35; }
.ui-nav-item:hover { background: var(--ui-surface-alt); text-decoration: none; }
.ui-nav-item.router-link-active { color: var(--ui-accent); background: var(--ui-surface-alt); font-weight: 600; }
.ui-nav-mark { width: 6px; height: 6px; border-radius: 50%; background: currentColor; flex: 0 0 6px; }
.ui-recovery-link { display: block; padding: 12px; margin: auto 0 0; color: var(--ui-text-muted); text-decoration: none; font-size: .85em; }
.ui-toolbar { grid-column: -2 / -1; display: flex; align-items: center; gap: 12px; flex-wrap: wrap; padding: 12px 24px; min-width: 0; min-height: 64px; border-bottom: 1px solid var(--ui-border); background: var(--ui-surface); text-align: left; }
.ui-toolbar-controls { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-left: auto; }
.ui-shell .ui-language { width: auto; min-width: 64px; }
.ui-toolbar :deep(.theme-toggle) { color: var(--ui-text); border-color: var(--ui-border); min-height: var(--ui-control-height); font-size: 16px; padding: 7px 10px; transform: none; }
.ui-toolbar :deep(.theme-toggle:hover) { background: var(--ui-surface-alt); transform: none; }
.ui-main { grid-column: -2 / -1; min-width: 0; width: 100%; max-width: var(--ui-content-width); padding: 28px; margin: 0 auto; }
.ui-top-navigation { display: flex; flex-wrap: wrap; gap: 4px; }
.ui-shell .ui-menu-toggle { display: none; }
.ui-shell .ui-brand--mobile { display: none; }
.ui-shell :deep(.ui-mobile-drawer) { margin: 0 auto 0 0; width: min(320px, 90vw); height: 100dvh; max-height: 100dvh; border-radius: 0; border-width: 0 1px 0 0; }
.ui-shell--display .ui-main { max-width: none; padding: 0; }
.ui-skip { position: fixed; left: 16px; top: -100px; z-index: 1100; padding: 12px; background: var(--ui-surface); border: 2px solid var(--ui-focus); border-radius: var(--ui-radius-sm); }
.ui-skip:focus { top: 12px; }
@media (max-width: 991px) {
  .app-header :deep(.navbar-collapse) { padding: .75rem 0 .5rem; }
  .ui-shell--sidebar { grid-template-columns: minmax(0, 1fr); }
  .ui-sidebar, .ui-shell--top .ui-top-navigation { display: none; }
  .ui-shell .ui-menu-toggle { display: inline-flex; }
  .ui-shell .ui-brand--mobile { display: flex; flex: 1; min-width: 0; }
  .ui-toolbar { padding: 10px 16px; gap: 8px; }
  .ui-toolbar-controls { gap: 4px; }
  .ui-main { padding: 20px 16px; }
  .ui-brand--top { max-width: 100%; }
  .ui-public-navigation { width: 100%; }
}
@media (max-width: 480px) {
  .ui-shortcut { display: none; }
  .ui-brand--top { flex: 1; min-width: 0; }
  .ui-toolbar-controls { flex-basis: 100%; justify-content: flex-end; margin-left: 0; }
}
</style>
