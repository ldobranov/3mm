<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { UiButton, UiCollectionEditor, UiField } from '@/extension-ui/v1'
import { useI18n } from '@/utils/i18n'
import { useUiLabels } from '@/utils/ui-labels'
import { localizedNavigationLabel, navigationLabelForEditing, updateLocalizedNavigationLabel, type NavigationItem } from '@/utils/menu-navigation'

type Item = NavigationItem & { audience?: 'public' | 'authenticated' | 'admin' }
interface RouteOption { path: string; label: string; adminOnly: boolean; requiresAuth: boolean }
const props = defineProps<{ menu: { id?: number; items: Item[] }; menuLanguage: string; routeOptions: RouteOption[]; disabled?: boolean }>()
const emit = defineEmits<{ 'update-items': [value: Item[]] }>()
const { t } = useI18n()
const label = useUiLabels()
let sequence = 0
let menuId: number | undefined
const rows = ref<{ key: string; item: Item }[]>([])
watch(() => [props.menu.id, props.menu.items] as const, ([id, items]) => {
  const previous = id === menuId ? rows.value : []
  rows.value = items.map(item => ({ key: previous.find(row => row.item === item)?.key ?? String(++sequence), item }))
  menuId = id
}, { immediate: true })
const known = (path: string) => props.routeOptions.some(route => route.path === path)
const route = (path: string) => props.routeOptions.find(option => option.path === path)
const publicRoute = (path: string) => !route(path)?.requiresAuth && !route(path)?.adminOnly
const audience = (path: string): Item['audience'] => route(path)?.adminOnly ? 'admin' : route(path)?.requiresAuth ? 'authenticated' : 'public'
const routeChoices = computed(() => [
  ...props.routeOptions.map(option => ({ value: option.path, label: `${option.label}${option.adminOnly ? ' · Admin' : ''} — ${option.path}` })),
  { value: '__custom__', label: t('settings.customPath', 'Custom path') },
])
const audiences = (path: string) => [
  { value: 'public', label: t('settings.menuAudiencePublic', 'Everyone'), disabled: !publicRoute(path) },
  { value: 'authenticated', label: t('settings.menuAudienceAuthenticated', 'Signed-in users') },
  { value: 'admin', label: t('settings.menuAudienceAdmin', 'Administrators') },
]
const itemName = (row: typeof rows.value[number]) => localizedNavigationLabel(row.item.label, props.menuLanguage) || label('menuLink')
const publish = (value: typeof rows.value) => {
  if (props.disabled) return
  rows.value = value; emit('update-items', value.map(row => row.item))
}
const change = (key: string, field: 'label' | 'path' | 'route' | 'audience', value: string | boolean) => {
  if (props.disabled || typeof value !== 'string') return
  publish(rows.value.map(row => {
    if (row.key !== key) return row
    const item = field === 'label' ? updateLocalizedNavigationLabel(row.item, props.menuLanguage, value)
      : field === 'route' ? { ...row.item, path: value === '__custom__' ? '' : value, audience: value === '__custom__' ? 'authenticated' as const : audience(value) }
      : { ...row.item, [field]: value } as Item
    return { ...row, item }
  }))
}
const add = () => publish([...rows.value, { key: String(++sequence), item: { path: '', label: { [props.menuLanguage]: '' }, audience: 'authenticated' } }])
const duplicate = (key: string) => {
  const index = rows.value.findIndex(row => row.key === key)
  if (index < 0) return
  const value = [...rows.value]
  value.splice(index + 1, 0, { key: String(++sequence), item: JSON.parse(JSON.stringify(value[index]!.item)) })
  publish(value)
}
</script>

<template>
  <UiCollectionEditor class="menu-editor" :title="t('settings.menuItems', 'Menu Items')" :model-value="rows" :item-key="row => row.key"
    :item-label="itemName" :disabled="disabled" :add-label="t('settings.addMenuItem', 'Add Menu Item')" :remove-label="label('remove')"
    :move-up-label="label('moveUp')" :move-down-label="label('moveDown')" :empty-label="label('noMenuLinks')" @add="add" @update:model-value="publish">
    <template #default="{ item: row, index, disabled: locked }">
      <div class="menu-item-grid">
        <UiField :id="`menu-item-label-${index}`" :label="`${t('settings.label', 'Label')} (${menuLanguage.toUpperCase()})`"
          :model-value="navigationLabelForEditing(row.item.label, menuLanguage)"
          :description="!navigationLabelForEditing(row.item.label, menuLanguage) ? `${label('textFallback')}: ${itemName(row)}` : undefined"
          :disabled="locked" @update:model-value="change(row.key, 'label', $event)" />
        <UiField :id="`menu-item-path-${index}`" type="select" :label="t('settings.path', 'Path')" :model-value="known(row.item.path) ? row.item.path : '__custom__'"
          :options="routeChoices" :disabled="locked" @update:model-value="change(row.key, 'route', $event)" />
        <UiField v-if="!known(row.item.path)" :id="`menu-item-custom-${index}`" :label="t('settings.customPath', 'Custom path')" required
          :model-value="row.item.path" placeholder="/custom-path" :disabled="locked" @update:model-value="change(row.key, 'path', $event)" />
        <UiField :id="`menu-item-audience-${index}`" type="select" :label="t('settings.menuAudience', 'Visible to')"
          :model-value="row.item.audience || audience(row.item.path)" :options="audiences(row.item.path)" :disabled="locked"
          :description="!publicRoute(row.item.path) ? t('settings.menuPublicRouteRequired', 'This route requires sign-in and cannot be exposed publicly.') : undefined"
          @update:model-value="change(row.key, 'audience', $event)" />
      </div>
      <UiButton :disabled="locked" class="menu-item-duplicate" @click="duplicate(row.key)">{{ t('common.duplicate', 'Duplicate') }}</UiButton>
    </template>
  </UiCollectionEditor>
</template>

<style scoped>
.menu-item-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: calc(var(--ui-space) * 3); }
.menu-item-duplicate { justify-self: start; }
@media (max-width: 700px) { .menu-item-grid { grid-template-columns: minmax(0, 1fr); } }
</style>
