<script setup lang="ts">
import { computed, ref, useId } from 'vue'
import { UiButton, UiDialog, UiEditorForm, UiField } from '@/extension-ui/v1'
import SettingsSection from '@/components/SettingsSection.vue'
import MenuEditor from './MenuEditor.vue'
import { localizedNavigationLabel, type NavigationItem } from '@/utils/menu-navigation'
import { useI18n } from '@/utils/i18n'
import { useUiLabels } from '@/utils/ui-labels'

type Item = NavigationItem & { audience?: 'public' | 'authenticated' | 'admin' }
interface Menu { id: number; name: string; items: Item[]; is_active: boolean }
interface RouteOption { path: string; label: string; adminOnly: boolean; requiresAuth: boolean }
const props = withDefaults(defineProps<{
  menuLanguage: string; availableLanguages: string[]; menus: Menu[]; activeMenuId: number | null
  currentMenuItems: Item[]; routeOptions: RouteOption[]; savingMenu?: boolean; creatingMenu?: boolean; managingMenu?: boolean
  disabled?: boolean; unavailable?: boolean; state?: 'idle' | 'unconfirmed'; error?: string
}>(), { savingMenu: false, creatingMenu: false, managingMenu: false, disabled: false, unavailable: false, state: 'idle', error: '' })
const emit = defineEmits<{
  'update:menuLanguage': [value: string]; 'update:activeMenuId': [value: number]; 'update:currentMenuItems': [value: Item[]]
  'create-menu': [name: string]; 'rename-menu': [value: { id: number; name: string }]; 'delete-menu': [id: number]
  'activate-menu': [id: number]; 'save-menu': []; discard: []; reload: []; 'open-theme': []
}>()
const { t } = useI18n()
const label = useUiLabels()
const id = useId()
const activeMenu = computed(() => props.menus.find(menu => menu.id === props.activeMenuId))
const menu = computed(() => activeMenu.value ? { ...activeMenu.value, items: props.currentMenuItems } : null)
const busy = computed(() => props.savingMenu || props.creatingMenu || props.managingMenu)
const locked = computed(() => busy.value || props.disabled || props.unavailable || props.state !== 'idle')
const dirty = computed(() => JSON.stringify(props.currentMenuItems) !== JSON.stringify(activeMenu.value?.items ?? []))
const valid = computed(() => props.currentMenuItems.every(item => typeof item.path === 'string' && item.path.startsWith('/') &&
  (typeof item.label === 'string' ? Boolean(item.label.trim()) : Object.values(item.label || {}).some(value => typeof value === 'string' && Boolean(value.trim())))))
const menuChoices = computed(() => props.menus.map(menu => ({ value: String(menu.id), label: menu.name })))
const languages = computed(() => props.availableLanguages.map(value => ({ value, label: value.toUpperCase() })))
const action = ref<'create' | 'rename' | 'delete' | null>(null)
const actionName = ref('')
const target = ref<{ id: number; name: string } | null>(null)
const actionTitle = computed(() => action.value === 'create' ? t('settings.createMenu', 'Create menu')
  : action.value === 'rename' ? t('common.rename', 'Rename') : t('common.delete', 'Delete'))
const openAction = (kind: typeof action.value) => {
  if (locked.value) return
  action.value = kind; target.value = activeMenu.value ? { id: activeMenu.value.id, name: activeMenu.value.name } : null
  actionName.value = kind === 'rename' ? target.value?.name ?? '' : ''
}
const confirmAction = () => {
  if (locked.value || !action.value) return
  const kind = action.value, name = actionName.value.trim(), selected = target.value
  if (kind !== 'delete' && !name) return
  action.value = null
  if (kind === 'create') emit('create-menu', name)
  else if (selected && kind === 'rename') emit('rename-menu', { id: selected.id, name })
  else if (selected) emit('delete-menu', selected.id)
}
</script>

<template>
  <SettingsSection :title="t('settings.menuConfiguration', 'Menu Configuration')">
    <div class="ui-stack">
      <p class="ui-help">{{ t('uiPlatform.menuEditorPlacementHelp', 'Edit menu contents here. Set their positions and sticky zones in Theme settings; the active menu is only the automatic default.') }}</p>
      <div class="ui-row">
        <UiButton data-action="create-menu" :disabled="locked" @click="openAction('create')">{{ t('settings.createMenu', 'Create menu') }}</UiButton>
        <UiButton data-action="theme-settings" @click="emit('open-theme')">{{ label('openThemeSettings') }}</UiButton>
      </div>
      <div class="menu-selectors">
        <UiField id="active-menu" type="select" :label="t('settings.menuToEdit', 'Menu to edit')"
          :model-value="activeMenuId === null ? '' : String(activeMenuId)" :options="menuChoices" :disabled="locked || !menus.length"
          @update:model-value="typeof $event === 'string' && emit('update:activeMenuId', Number($event))" />
        <UiField id="menu-language" type="select" :label="t('settings.menuLanguage', 'Menu Language')" :model-value="menuLanguage"
          :options="languages" :disabled="locked" @update:model-value="typeof $event === 'string' && emit('update:menuLanguage', $event)" />
      </div>
      <div v-if="activeMenu" class="ui-row">
        <span class="ui-badge">{{ activeMenu.is_active ? label('automaticMenu') : label('customMenu') }}</span>
        <UiButton v-if="!activeMenu.is_active" data-action="activate-menu" :disabled="locked" @click="emit('activate-menu', activeMenu.id)">{{ t('settings.setActiveMenu', 'Set as active') }}</UiButton>
        <UiButton data-action="rename-menu" :disabled="locked" @click="openAction('rename')">{{ t('common.rename', 'Rename') }}</UiButton>
        <UiButton class="menu-delete" variant="danger" :disabled="locked" @click="openAction('delete')">{{ t('common.delete', 'Delete') }}</UiButton>
      </div>
      <UiEditorForm v-if="menu" class="menu-content-form" :title="activeMenu?.name ?? ''" :description="label('menuContentHelp')"
        :dirty="dirty" :valid="valid" :busy="busy" :disabled="disabled || unavailable" :state="state" :error="error"
        :save-label="t('settings.saveMenu', 'Save Menu')" :cancel-label="label('discardDraft')" :dirty-label="label('menuDraftHelp')"
        :saved-label="label('cleanDraft')" :unconfirmed-label="label('settingsUnconfirmed')" @save="emit('save-menu')" @cancel="emit('discard')">
        <template #default="{ disabled: blocked }">
          <MenuEditor :menu="menu" :menu-language="menuLanguage" :route-options="routeOptions" :disabled="blocked"
            @update-items="emit('update:currentMenuItems', $event)" />
          <p v-if="!valid" role="alert">{{ label('invalidMenuDraft') }}</p>
        </template>
        <template #recovery><UiButton :disabled="busy" data-action="reload-menus" @click="emit('reload')">{{ label('reloadSaved') }}</UiButton></template>
      </UiEditorForm>
      <div v-else class="menu-empty-state ui-section">
        <p>{{ t('settings.emptyHeaderMenuHelp', 'The header has no navigation links. Create a menu to choose links, or leave it empty. Settings remain available at /settings and through Ctrl+K.') }}</p>
      </div>
      <div v-if="(!menu && (error || state !== 'idle')) || (unavailable && state === 'idle')" class="ui-stack" role="alert">
        <p>{{ state === 'unconfirmed' ? label('settingsUnconfirmed') : error }}</p>
        <UiButton :disabled="busy" data-action="reload-menus" @click="emit('reload')">{{ label('reloadSaved') }}</UiButton>
      </div>
      <details v-if="currentMenuItems.length" class="menu-draft-preview">
        <summary>{{ label('menuPreview') }}</summary>
        <p class="ui-help">{{ label('menuPreviewHelp') }}</p>
        <ol><li v-for="(item, index) in currentMenuItems" :key="index"><strong>{{ localizedNavigationLabel(item.label, menuLanguage) }}</strong> <code>{{ item.path }}</code></li></ol>
      </details>
    </div>
    <UiDialog :open="action !== null" :title="actionTitle" :close-label="label('close')" @update:open="!$event && (action = null)">
      <form :id="`${id}-action`" @submit.prevent="confirmAction">
        <p v-if="action === 'delete'">{{ label('deleteMenuWarning') }} <strong>{{ target?.name }}</strong></p>
        <UiField v-else :id="`${id}-name`" :label="t('settings.newMenuName', 'Menu name')" v-model="actionName" required :maxlength="120" autofocus />
      </form>
      <template #actions>
        <UiButton @click="action = null">{{ label('cancel') }}</UiButton>
        <UiButton data-action="confirm-menu-action" :variant="action === 'delete' ? 'danger' : 'primary'" type="submit" :form="`${id}-action`"
          :disabled="locked || (action !== 'delete' && !actionName.trim())">{{ actionTitle }}</UiButton>
      </template>
    </UiDialog>
  </SettingsSection>
</template>

<style scoped>
.menu-selectors { display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 1fr); gap: calc(var(--ui-space) * 4); }
.menu-draft-preview { padding: 16px; border: 1px solid var(--ui-border); border-radius: var(--ui-radius-sm); }
.menu-draft-preview summary { cursor: pointer; font-weight: 650; }
.menu-draft-preview li { display: flex; flex-wrap: wrap; gap: 12px; padding-block: 8px; overflow-wrap: anywhere; }
.menu-draft-preview code { color: var(--ui-text-muted); }
@media (max-width: 600px) { .menu-selectors { grid-template-columns: minmax(0, 1fr); } }
</style>
