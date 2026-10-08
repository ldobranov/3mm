<template>
  <div class="menu-editor">
    <div class="menu-editor-title">
      <div>
        <strong>{{ t('settings.menuItems', 'Menu Items') }}</strong>
        <p class="menu-editor-subtitle">
          {{ t('settings.menuLanguageHelp', 'Configure complete menu structure for the selected language') }}
        </p>
      </div>
      <span class="menu-editor-count ui-badge">
        {{ menu.items.length }}
      </span>
    </div>

    <VueDraggable
      v-if="menu.items.length > 0"
      :model-value="menu.items"
      handle=".drag-handle"
      :animation="200"
      @update:model-value="handleItemsReorder"
    >
      <div
        v-for="(item, index) in menu.items"
        :key="`${item.path}-${index}`"
        class="menu-item"
      >
        <div class="drag-handle" aria-label="Drag handle">
          <i class="bi bi-grip-vertical"></i>
        </div>

        <div class="menu-item-content">
          <div class="menu-item-grid">
            <div class="menu-editor-field">
              <label class="form-label menu-item-field-label" :for="`menu-item-label-${index}`">
                {{ t('settings.label', 'Label') }} ({{ menuLanguage.toUpperCase() }})
              </label>
              <input
                type="text"
                class="input ui-control menu-item-label"
                :id="`menu-item-label-${index}`"
                :value="navigationLabelForEditing(item.label, menuLanguage)"
                @input="updateMenuItemLabel(index, $event)"
                :placeholder="`${t('settings.label', 'Label')} ${t('settings.in', 'in')} ${menuLanguage.toUpperCase()}`"
              />
              <small
                v-if="!navigationLabelForEditing(item.label, menuLanguage) && fallbackLabel(item)"
                class="help-text"
              >
                {{ t('settings.menuLabelFallback', 'Fallback in the header:') }} {{ fallbackLabel(item) }}
              </small>
            </div>

            <div class="menu-editor-field">
              <label class="form-label menu-item-field-label" :for="`menu-item-path-${index}`">
                {{ t('settings.path', 'Path') }}
              </label>
              <select
                class="select ui-control menu-item-path-input"
                :id="`menu-item-path-${index}`"
                :value="isKnownRoute(item.path) ? item.path : '__custom__'"
                @change="updateMenuItemRoute(index, $event)"
              >
                <option v-for="route in routeOptions" :key="route.path" :value="route.path">
                  {{ route.label }}{{ route.adminOnly ? ' · Admin' : '' }} — {{ route.path }}
                </option>
                <option value="__custom__">{{ t('settings.customPath', 'Custom path') }}</option>
              </select>
              <input
                v-if="!isKnownRoute(item.path)"
                type="text"
                class="input ui-control menu-item-path-input"
                :aria-label="t('settings.customPath', 'Custom path')"
                :value="item.path"
                :placeholder="t('settings.customPathPlaceholder', '/custom-path')"
                @input="updateMenuItemPath(index, $event)"
              />
            </div>

            <div class="menu-editor-field">
              <label class="form-label menu-item-field-label" :for="`menu-item-audience-${index}`">
                {{ t('settings.menuAudience', 'Visible to') }}
              </label>
              <select
                class="select ui-control menu-item-access-input"
                :id="`menu-item-audience-${index}`"
                :value="item.audience || defaultAudienceForPath(item.path)"
                @change="updateMenuItemAudience(index, $event)"
              >
                <option value="public" :disabled="!isPublicRoute(item.path)">
                  {{ t('settings.menuAudiencePublic', 'Everyone') }}
                </option>
                <option value="authenticated">{{ t('settings.menuAudienceAuthenticated', 'Signed-in users') }}</option>
                <option value="admin">{{ t('settings.menuAudienceAdmin', 'Administrators') }}</option>
              </select>
              <small v-if="!isPublicRoute(item.path)" class="help-text">
                {{ t('settings.menuPublicRouteRequired', 'This route requires sign-in and cannot be exposed publicly.') }}
              </small>
            </div>
          </div>
        </div>

        <div class="menu-item-actions">
          <button
            class="ui-button menu-item-action"
            type="button"
            @click="duplicateMenuItem(index)"
          >
            {{ t('common.duplicate', 'Duplicate') }}
          </button>
          <button
            class="ui-button ui-button--danger menu-item-action menu-item-danger"
            type="button"
            @click="removeMenuItem(index)"
          >
            {{ t('settings.remove', 'Remove') }}
          </button>
        </div>
      </div>
    </VueDraggable>

    <div v-else class="menu-items-empty">
      <p>{{ t('settings.noMenusAvailable', 'No menus available') }}</p>
    </div>

    <div class="menu-editor-add">
      <h4>{{ t('settings.addMenuItem', 'Add Menu Item') }}</h4>

      <div class="menu-editor-add-grid">
        <div class="menu-editor-field">
          <label class="form-label" for="new-item-label">{{ t('settings.label', 'Label') }} ({{ menuLanguage.toUpperCase() }})</label>
          <input
            type="text"
            class="input ui-control menu-editor-input"
            id="new-item-label"
            :placeholder="`${t('settings.label', 'Label')} ${t('settings.in', 'in')} ${menuLanguage.toUpperCase()}`"
            v-model="newItem.label"
          />
        </div>

        <div class="menu-editor-field">
          <label class="form-label" for="new-item-path">{{ t('settings.path', 'Path') }}</label>
          <select id="new-item-path" v-model="newItem.path" class="select ui-control menu-editor-input" @change="handleNewRouteChange">
            <option disabled value="">{{ t('settings.chooseRoute', 'Choose a route') }}</option>
            <option v-for="route in routeOptions" :key="route.path" :value="route.path">
              {{ route.label }}{{ route.adminOnly ? ' · Admin' : '' }} — {{ route.path }}
            </option>
            <option value="__custom__">{{ t('settings.customPath', 'Custom path') }}</option>
          </select>
          <input
            v-if="newItem.path === '__custom__'"
            v-model.trim="newItemCustomPath"
            type="text"
            class="input ui-control menu-editor-input"
            :aria-label="t('settings.customPath', 'Custom path')"
            :placeholder="t('settings.customPathPlaceholder', '/custom-path')"
          />
        </div>

        <div class="menu-editor-field">
          <label class="form-label" for="new-item-audience">{{ t('settings.menuAudience', 'Visible to') }}</label>
          <select id="new-item-audience" v-model="newItem.audience" class="select ui-control menu-editor-input">
            <option value="public" :disabled="!isPublicRoute(resolvedNewItemPath)">{{ t('settings.menuAudiencePublic', 'Everyone') }}</option>
            <option value="authenticated">{{ t('settings.menuAudienceAuthenticated', 'Signed-in users') }}</option>
            <option value="admin">{{ t('settings.menuAudienceAdmin', 'Administrators') }}</option>
          </select>
        </div>
      </div>

      <button
        class="ui-button ui-button--primary"
        type="button"
        @click="addMenuItem"
      >
        {{ t('settings.add', 'Add') }}
      </button>
    </div>
  </div>
</template>

<script lang="ts">
import { computed, defineComponent, ref } from 'vue'
import type { PropType } from 'vue'
import { useI18n } from '@/utils/i18n'
import {
  localizedNavigationLabel,
  navigationLabelForEditing,
  updateLocalizedNavigationLabel
} from '@/utils/menu-navigation'
import { VueDraggable } from 'vue-draggable-plus'

interface MenuItem {
  label: Record<string, string>
  path: string
  audience?: 'public' | 'authenticated' | 'admin'
}

interface MenuRouteOption {
  path: string
  label: string
  adminOnly: boolean
  requiresAuth: boolean
}

export default defineComponent({
  name: 'MenuEditor',
  components: {
    VueDraggable
  },
  props: {
    menu: {
      type: Object,
      required: true
    },
    menuLanguage: {
      type: String,
      required: true
    },
    availableLanguages: {
      type: Array as PropType<string[]>,
      required: true
    },
    routeOptions: {
      type: Array as PropType<MenuRouteOption[]>,
      required: true
    },
    settingsStore: {
      type: Object,
      required: true
    }
  },
  emits: ['add-item', 'edit-item', 'remove-item', 'update-items', 'drag-end'],
  setup(props, { emit }) {
    const { t } = useI18n()
    const newItem = ref<{ label: string; path: string; audience: MenuItem['audience'] }>({
      label: '',
      path: '',
      audience: 'authenticated'
    })
    const newItemCustomPath = ref('')

    const isKnownRoute = (path: string) => props.routeOptions.some(route => route.path === path)

    const resolvedNewItemPath = computed(() => newItem.value.path === '__custom__'
      ? newItemCustomPath.value.trim()
      : newItem.value.path)

    const routeForPath = (path: string) => props.routeOptions.find(route => route.path === path)

    const isPublicRoute = (path: string) => {
      const route = routeForPath(path)
      return route ? !route.requiresAuth : Boolean(path)
    }

    const defaultAudienceForPath = (path: string): MenuItem['audience'] => {
      const route = routeForPath(path)
      if (route?.adminOnly) return 'admin'
      if (route?.requiresAuth) return 'authenticated'
      return 'public'
    }

    const updateMenuItemLabel = (index: number, event: Event) => {
      const target = event.target as HTMLInputElement
      const items = [...props.menu.items]
      items[index] = updateLocalizedNavigationLabel(items[index], props.menuLanguage, target.value)
      emit('update-items', items)
    }

    const fallbackLabel = (item: MenuItem) => {
      const label = localizedNavigationLabel(item.label, props.menuLanguage)
      return label === navigationLabelForEditing(item.label, props.menuLanguage) ? '' : label
    }

    const updateMenuItemPath = (index: number, event: Event) => {
      const target = event.target as HTMLInputElement
      const items = [...props.menu.items]
      items[index] = {
        ...items[index],
        path: target.value
      }
      emit('update-items', items)
    }

    const updateMenuItemRoute = (index: number, event: Event) => {
      const target = event.target as HTMLSelectElement
      const items = [...props.menu.items]
      items[index] = {
        ...items[index],
        path: target.value === '__custom__' ? '' : target.value,
        audience: defaultAudienceForPath(target.value === '__custom__' ? '' : target.value)
      }
      emit('update-items', items)
    }

    const updateMenuItemAudience = (index: number, event: Event) => {
      const target = event.target as HTMLSelectElement
      const items = [...props.menu.items]
      items[index] = { ...items[index], audience: target.value as MenuItem['audience'] }
      emit('update-items', items)
    }

    const handleNewRouteChange = () => {
      if (newItem.value.path === '__custom__') return
      const route = props.routeOptions.find(item => item.path === newItem.value.path)
      if (route && !newItem.value.label.trim()) newItem.value.label = route.label
      newItem.value.audience = defaultAudienceForPath(newItem.value.path)
    }

    const handleItemsReorder = (items: MenuItem[]) => {
      emit('update-items', items)
      emit('drag-end')
    }

    const addMenuItem = () => {
      const path = newItem.value.path === '__custom__'
        ? newItemCustomPath.value.trim()
        : newItem.value.path
      if (!newItem.value.label || !path) return

      const labelObj: Record<string, string> = {}
      labelObj[props.menuLanguage] = newItem.value.label

      const items = [...props.menu.items, {
        label: labelObj,
        path,
        audience: newItem.value.audience || defaultAudienceForPath(path)
      }]

      emit('update-items', items)
      newItem.value = { label: '', path: '', audience: 'authenticated' }
      newItemCustomPath.value = ''
    }

    const duplicateMenuItem = (index: number) => {
      const item = props.menu.items[index]
      const items = [...props.menu.items]
      items.splice(index + 1, 0, {
        ...item,
        label: { ...item.label }
      })
      emit('update-items', items)
    }

    const removeMenuItem = (index: number) => {
      if (confirm('Remove this menu item?')) {
        const items = props.menu.items.filter((item: MenuItem, i: number) => i !== index)
        emit('update-items', items)
      }
    }

    return {
      t,
      newItem,
      newItemCustomPath,
      resolvedNewItemPath,
      isKnownRoute,
      isPublicRoute,
      defaultAudienceForPath,
      fallbackLabel,
      navigationLabelForEditing,
      updateMenuItemLabel,
      updateMenuItemPath,
      updateMenuItemRoute,
      updateMenuItemAudience,
      handleNewRouteChange,
      handleItemsReorder,
      addMenuItem,
      duplicateMenuItem,
      removeMenuItem
    }
  }
})
</script>

<style scoped>
.menu-editor { display: grid; gap: calc(var(--ui-space) * 4); min-width: 0; }
.menu-editor-title { display: flex; align-items: flex-start; justify-content: space-between; gap: calc(var(--ui-space) * 4); padding-bottom: calc(var(--ui-space) * 3); border-bottom: 1px solid var(--ui-border); }
.menu-editor-title strong, .menu-editor-add h4 { font-size: 1rem; font-weight: 650; }
.menu-editor-subtitle { margin-top: var(--ui-space); font-size: .9em; color: var(--ui-text-secondary); }
.menu-item { display: grid; grid-template-columns: auto minmax(0, 1fr); align-items: start; gap: calc(var(--ui-space) * 3); padding: calc(var(--ui-space) * 4); margin-bottom: calc(var(--ui-space) * 3); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-sm); background: var(--ui-surface); }
.drag-handle { cursor: move; display: inline-flex; align-items: center; justify-content: center; width: 2rem; height: 2rem; margin-top: 1.65rem; color: var(--ui-text-muted); border-radius: var(--ui-radius-sm); background: var(--ui-surface-alt); }
.menu-item-content, .menu-editor-field { min-width: 0; }
.menu-item-grid, .menu-editor-add-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: calc(var(--ui-space) * 3); }
.menu-editor-field { display: grid; align-content: start; gap: calc(var(--ui-space) * 2); }
.menu-item-field-label { color: var(--ui-text-secondary); font-size: .9em; }
.menu-item-actions { grid-column: 2; display: flex; flex-wrap: wrap; gap: calc(var(--ui-space) * 2); }
.menu-items-empty { padding: calc(var(--ui-space) * 4); border: 1px dashed var(--ui-border); border-radius: var(--ui-radius-sm); background: var(--ui-surface-alt); color: var(--ui-text-secondary); }
.menu-editor-add { padding-top: calc(var(--ui-space) * 4); border-top: 1px solid var(--ui-border); display: grid; gap: calc(var(--ui-space) * 3); }
.menu-editor-add h4 { margin: 0; }
.menu-editor-add > .ui-button { justify-self: start; }
@media (max-width: 900px) {
  .menu-item { grid-template-columns: minmax(0, 1fr); }
  .drag-handle { margin-top: 0; }
  .menu-item-grid, .menu-editor-add-grid { grid-template-columns: minmax(0, 1fr); }
  .menu-item-actions { grid-column: 1; }
}
</style>
