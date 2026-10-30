<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, useId } from 'vue'
import { UiButton, UiField } from '@/extension-ui/v1'
import { useUiLabels } from '@/utils/ui-labels'
import { defaultMenuLayout, MENU_REGIONS, resolveMenuRegions, type MenuLayout, type MenuLocation, type MenuRegion } from '@/utils/menu-layout'
import http from '@/utils/dynamic-http'

const props = defineProps<{ modelValue?: MenuLayout; navigation: 'sidebar' | 'top' }>()
const emit = defineEmits<{ 'update:modelValue': [value: MenuLayout | undefined] }>()
const label = useUiLabels()
const id = useId()
const menus = ref<{ id: number; name: string; is_active: boolean }[]>([])
const loading = ref(true)
const unavailable = ref(false)
const limit = ref(false)
const controller = new AbortController()
let request = 0
const load = async () => {
  const current = ++request
  loading.value = true
  try {
    const response = await http.get('/menu/read', { signal: controller.signal })
    if (controller.signal.aborted || current !== request) return
    if (!Array.isArray(response.data.items)) throw new Error('unavailable')
    menus.value = response.data.items.filter((menu: Record<string, unknown>) =>
      Number.isInteger(menu?.id) && Number(menu.id) > 0 && typeof menu.name === 'string')
    unavailable.value = false
  } catch {
    if (!controller.signal.aborted && current === request) unavailable.value = true
  } finally { if (current === request) loading.value = false }
}
onMounted(() => { void load(); window.addEventListener('menu-refresh', load) })
onBeforeUnmount(() => { controller.abort(); window.removeEventListener('menu-refresh', load) })
const rows = computed(() => [
  ...menus.value,
  ...(props.modelValue?.placements ?? []).filter(item => !menus.value.some(menu => menu.id === item.menu_id))
    .map(item => ({ id: item.menu_id, name: `${label('missingMenu')} #${item.menu_id}`, is_active: false })),
])
const locations = computed(() => [
  { value: 'hidden', label: label('menuHidden') }, { value: 'primary', label: label('menuPrimary') },
  { value: 'header', label: label('menuHeader') }, { value: 'sidebar', label: label('menuSidebar') },
  { value: 'footer', label: label('menuFooter') },
])
const regionLabel = (region: MenuRegion) => label(({ header: 'menuHeader', sidebar: 'menuSidebar', footer: 'menuFooter' } as const)[region])
const layout = () => props.modelValue ? JSON.parse(JSON.stringify(props.modelValue)) as MenuLayout : defaultMenuLayout()
const publish = (value: MenuLayout) => {
  limit.value = false
  emit('update:modelValue', value.placements === undefined && !MENU_REGIONS.some(region => value.sticky[region]) ? undefined : value)
}
const locationFor = (menu: { id: number; is_active: boolean }) => props.modelValue?.placements === undefined
  ? menu.is_active ? 'primary' : 'hidden'
  : props.modelValue.placements.find(item => item.menu_id === menu.id)?.location ?? 'hidden'
const place = (menuId: number, location: string | boolean) => {
  if (loading.value || unavailable.value || typeof location !== 'string' || !locations.value.some(item => item.value === location)) return
  const value = layout()
  const active = menus.value.find(menu => menu.is_active)
  value.placements = (value.placements ?? (active ? [{ menu_id: active.id, location: 'primary' as const }] : []))
    .filter(item => item.menu_id !== menuId)
  if (location !== 'hidden') value.placements.push({ menu_id: menuId, location: location as MenuLocation })
  if (value.placements.length > 16) { limit.value = true; return }
  publish(value)
}
const stick = (region: MenuRegion, enabled: string | boolean) => {
  const value = layout(); value.sticky[region] = enabled === true; publish(value)
}
const automatic = () => { const value = layout(); delete value.placements; publish(value) }
const preview = computed(() => resolveMenuRegions(menus.value, props.modelValue, props.navigation === 'sidebar' ? 'sidebar' : 'header'))
</script>

<template>
  <section class="theme-menu-settings ui-stack" :aria-label="label('menuPlacementTitle')">
    <h3>{{ label('menuPlacementTitle') }}</h3>
    <p class="ui-help">{{ label('menuPlacementHelp') }}</p>
    <p v-if="loading" role="status">{{ label('loading') }}…</p>
    <div v-else-if="unavailable" role="alert" class="ui-stack">
      <p>{{ label('menuReadFailed') }}</p><UiButton data-action="reload-menus" @click="load">{{ label('reloadMenus') }}</UiButton>
    </div>
    <template v-else>
      <p v-if="!rows.length" class="ui-help">{{ label('noConfiguredMenus') }}</p>
      <UiField v-for="menu in rows" :key="menu.id" :id="`${id}-menu-${menu.id}`" type="select" :data-menu-id="menu.id"
        :label="menu.name" :model-value="locationFor(menu)" :options="locations" @update:model-value="place(menu.id, $event)" />
      <UiButton data-action="automatic-menus" :disabled="modelValue?.placements === undefined" @click="automatic">{{ label('automaticMenus') }}</UiButton>
    </template>
    <p v-if="limit" role="alert">{{ label('menuPlacementLimit') }}</p>
    <fieldset class="sticky-options ui-stack">
      <legend>{{ label('stickyMenus') }}</legend>
      <p class="ui-help">{{ label('stickyMenusHelp') }}</p>
      <UiField v-for="region in MENU_REGIONS" :key="region" :id="`${id}-sticky-${region}`" type="checkbox" :data-sticky="region"
        :label="regionLabel(region)" :model-value="modelValue?.sticky[region] ?? false" @update:model-value="stick(region, $event)" />
    </fieldset>
    <div v-if="!unavailable && !loading" class="menu-layout-preview" :aria-label="label('menuLayoutPreview')">
      <div v-for="region in MENU_REGIONS" :key="region" :class="`menu-preview-${region}`" :data-preview-region="region">
        <strong>{{ regionLabel(region) }}<span v-if="modelValue?.sticky[region]"> · {{ label('sticky') }}</span></strong>
        <span v-for="menu in preview[region]" :key="menu.id">{{ menu.name }}</span>
        <span v-if="!preview[region].length" class="ui-help">{{ label('menuHidden') }}</span>
      </div>
      <div class="menu-preview-page">{{ label('menuPageContent') }}</div>
    </div>
    <p class="ui-help">{{ label('menuPlacementDraft') }}</p>
  </section>
</template>

<style scoped>
.theme-menu-settings { border-block: 1px solid var(--ui-border); padding-block: calc(var(--ui-space) * 4); }
.theme-menu-settings h3, .sticky-options legend { font-size: 1em; font-weight: 650; margin: 0; }
.sticky-options { border: 0; padding: 0; margin: 0; min-width: 0; }
.menu-layout-preview { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 2fr); gap: 4px; padding: 8px; background: var(--ui-canvas); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-sm); }
.menu-layout-preview > div { display: grid; align-content: start; gap: 6px; padding: 10px; background: var(--ui-surface); border-radius: var(--ui-radius-sm); overflow-wrap: anywhere; font-size: .85em; }
.menu-preview-header, .menu-preview-footer { grid-column: 1 / -1; }
.menu-preview-header { grid-row: 1; }.menu-preview-sidebar { grid-row: 2; }.menu-preview-page { grid-row: 2; }.menu-preview-footer { grid-row: 3; }
</style>
