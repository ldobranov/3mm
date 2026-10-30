<script setup lang="ts">
import { computed, onBeforeUnmount, provide, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import Menu from '../Menu.vue'
import ThemeToggle from '../ThemeToggle.vue'
import UiButton from './UiButton.vue'
import UiDialog from './UiDialog.vue'
import MenuGroups from './MenuGroups.vue'
import { useSettingsStore } from '@/stores/settings'
import { useUiLabels } from '@/utils/ui-labels'
import type { UiDesign, UiShellMode } from '@/utils/ui-design'
import { extensionUiKey } from '@/extension-ui/context'

const props = withDefaults(defineProps<{ design: UiDesign; mode: UiShellMode; active?: boolean }>(), { active: true })
provide(extensionUiKey, computed(() => Object.freeze({
  button: props.design.components.button,
  card: props.design.components.card,
})))
const settings = useSettingsStore()
const label = useUiLabels()
const route = useRoute()
const drawer = ref(false)
const application = computed(() => props.mode === 'application')
const sticky = computed(() => settings.menuLayout?.sticky)
watch(() => route.fullPath, () => { drawer.value = false })
watch(() => props.mode, () => { drawer.value = false })
onBeforeUnmount(() => { drawer.value = false })
</script>

<template>
  <div :class="active ? ['ui-v2', 'ui-shell', `ui-shell--${application ? design.layout.navigation : mode}`] : 'ui-legacy-shell'"
    :data-button="active ? design.components.button : undefined" :data-card="active ? design.components.card : undefined">
    <a v-if="active" href="#ui-main" class="ui-skip">{{ label('skip') }}</a>
    <Menu :custom="active" :primary-location="application && design.layout.navigation === 'sidebar' ? 'sidebar' : 'header'">
      <template #default="{ navigation }">
      <aside v-if="application && (design.layout.navigation === 'sidebar' || navigation.regions.sidebar.length)" class="ui-sidebar">
        <div class="ui-sidebar-content" :class="{ 'ui-sidebar-content--sticky': sticky?.sidebar }">
        <RouterLink to="/" class="ui-brand">
          <img v-if="settings.brandingLogo" :src="settings.brandingLogo" alt="" />
          <span>{{ settings.headerSettings.siteName }}</span>
        </RouterLink>
        <MenuGroups :groups="navigation.regions.sidebar" :item-label="navigation.label" />
        </div>
      </aside>
      <header v-if="mode !== 'display'" class="ui-toolbar" :class="{ 'ui-toolbar--sticky': sticky?.header }">
        <UiButton v-if="application && (navigation.regions.sidebar.length || navigation.regions.header.length)" class="ui-menu-toggle" :aria-label="label('openMenu')"
          aria-controls="ui-mobile-navigation" :aria-expanded="drawer" @click="drawer = true">☰</UiButton>
        <RouterLink v-if="!application || design.layout.navigation === 'top'" to="/" class="ui-brand ui-brand--top">
          <img v-if="settings.brandingLogo" :src="settings.brandingLogo" alt="" />
          <span>{{ settings.headerSettings.siteName }}</span>
        </RouterLink>
        <RouterLink v-if="application && design.layout.navigation === 'sidebar'" to="/" class="ui-brand ui-brand--mobile">
          <span>{{ settings.headerSettings.siteName }}</span>
        </RouterLink>
        <MenuGroups v-if="application" class="ui-header-menus" horizontal :groups="navigation.regions.header" :item-label="navigation.label" />
        <MenuGroups v-if="!application && mode !== 'kiosk'" class="ui-public-navigation" horizontal
          :groups="[...navigation.regions.header, ...navigation.regions.sidebar]" :item-label="navigation.label" />
        <div class="ui-toolbar-controls">
          <select v-if="navigation.showLanguageSwitcher" class="ui-control ui-language"
            :aria-label="label('language')" :value="navigation.selectedLanguage" @change="navigation.changeLanguage">
            <option v-for="language in navigation.languages" :key="language" :value="language">{{ language.toUpperCase() }}</option>
          </select>
          <ThemeToggle :persist-preference="!settings.previewDesign" />
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
        <MenuGroups id="ui-mobile-navigation" :groups="[...navigation.regions.header, ...navigation.regions.sidebar]"
          :item-label="navigation.label" @navigate="drawer = false" />
      </UiDialog>
      </template>
      <template #content>
        <!-- Stable content parent across layout, placement, preview and recovery. -->
        <main id="ui-main" :tabindex="active ? -1 : undefined" :class="{ 'ui-main': active }"><slot /></main>
      </template>
      <template #footer="{ navigation }">
        <footer v-if="active && mode !== 'kiosk' && mode !== 'display' && navigation.regions.footer.length"
          class="ui-footer" :class="{ 'ui-footer--sticky': sticky?.footer }">
          <MenuGroups horizontal :groups="navigation.regions.footer" :item-label="navigation.label" />
        </footer>
      </template>
    </Menu>
  </div>
</template>

<style scoped>
.ui-shell { min-height: 100dvh; display: grid; grid-template-rows: auto 1fr auto; }
.ui-legacy-shell :deep(.navbar) { width: min(100% - 2rem, 1200px); min-height: 64px; margin: 0 auto; padding: .5rem 0; }
.ui-legacy-shell :deep(.navbar-brand) { font-size: 1.1rem; font-weight: 700; letter-spacing: -.02em; }
.ui-legacy-shell :deep(.nav-link) { border-radius: 8px; padding: .55rem .75rem; font-size: .9rem; }
.ui-shell:has(> .ui-sidebar) { grid-template-columns: var(--ui-sidebar-width) minmax(0, 1fr); }
.ui-sidebar { grid-column: 1; grid-row: 1 / -1; min-width: 0; background: var(--ui-surface); border-right: 1px solid var(--ui-border); }
.ui-sidebar-content { padding: 16px 12px; display: grid; gap: 20px; }
.ui-sidebar-content--sticky { position: sticky; top: 0; max-height: 100dvh; overflow-y: auto; overscroll-behavior: contain; }
.ui-brand { display: flex; align-items: center; gap: 10px; padding: 10px 12px; color: var(--ui-header-text); background: var(--ui-header-bg); border-radius: var(--ui-radius-sm); text-decoration: none; font-size: 1.08em; font-weight: 650; overflow-wrap: anywhere; margin: 0; }
.ui-brand img { width: 30px; max-height: 36px; object-fit: contain; }
.ui-toolbar { grid-column: -2 / -1; display: flex; align-items: center; gap: 12px; flex-wrap: wrap; padding: 12px 24px; min-width: 0; min-height: 64px; border-bottom: 1px solid var(--ui-border); background: var(--ui-surface); text-align: left; }
.ui-toolbar--sticky { position: sticky; top: 0; z-index: 20; max-height: 45dvh; overflow-y: auto; }
.ui-footer { grid-column: -2 / -1; grid-row: 3; min-width: 0; padding: 12px 24px; border-top: 1px solid var(--ui-border); background: var(--ui-surface); }
.ui-footer--sticky { position: sticky; bottom: 0; z-index: 20; max-height: 30dvh; overflow-y: auto; }
.ui-toolbar-controls { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-left: auto; }
.ui-shell .ui-language { width: auto; min-width: 64px; }
.ui-toolbar :deep(.theme-toggle) { color: var(--ui-text); border-color: var(--ui-border); min-height: var(--ui-control-height); font-size: 16px; padding: 7px 10px; transform: none; }
.ui-toolbar :deep(.theme-toggle:hover) { background: var(--ui-surface-alt); transform: none; }
.ui-main { grid-column: -2 / -1; grid-row: 2; min-width: 0; width: 100%; max-width: var(--ui-content-width); padding: 28px; margin: 0 auto; }
.ui-shell .ui-menu-toggle { display: none; }
.ui-shell .ui-brand--mobile { display: none; }
.ui-shell :deep(.ui-mobile-drawer) { margin: 0 auto 0 0; width: min(320px, 90vw); height: 100dvh; max-height: 100dvh; border-radius: 0; border-width: 0 1px 0 0; }
.ui-shell--display .ui-main { max-width: none; padding: 0; }
.ui-skip { position: fixed; left: 16px; top: -100px; z-index: 1100; padding: 12px; background: var(--ui-surface); border: 2px solid var(--ui-focus); border-radius: var(--ui-radius-sm); }
.ui-skip:focus { top: 12px; }
@media (max-width: 991px) {
  .ui-legacy-shell :deep(.navbar-collapse) { padding: .75rem 0 .5rem; }
  .ui-shell:has(> .ui-sidebar) { grid-template-columns: minmax(0, 1fr); }
  .ui-sidebar, .ui-header-menus { display: none; }
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
