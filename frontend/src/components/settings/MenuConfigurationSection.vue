<template>
  <SettingsSection :title="t('settings.menuConfiguration', 'Menu Configuration')">
    <div class="menu-meta-row">
      <LanguageSelector
        :model-value="menuLanguage"
        :available-languages="availableLanguages"
        @update:model-value="handleMenuLanguageChange"
        :label="t('settings.menuLanguage', 'Menu Language')"
      />

      <small class="help-text menu-help">
        {{ t('settings.menuLanguageHelp', 'Configure complete menu structure for the selected language') }}
      </small>
    </div>

    <form class="menu-create-row" @submit.prevent="createMenu">
      <div class="menu-create-field">
        <label for="new-menu-name" class="form-label">{{ t('settings.newMenuName', 'New menu name') }}</label>
        <input
          id="new-menu-name"
          v-model.trim="newMenuName"
          class="input ui-control"
          type="text"
          maxlength="120"
          :placeholder="t('settings.newMenuPlaceholder', 'For example: Main navigation')"
        />
      </div>
      <button class="ui-button" type="submit" :disabled="creatingMenu || !newMenuName">
        {{ creatingMenu ? t('settings.creating', 'Creating...') : t('settings.createMenu', 'Create menu') }}
      </button>
    </form>

    <div v-if="menus.length > 0">
      <div class="form-group">
        <label for="active-menu" class="form-label">{{ t('settings.menuToEdit', 'Menu to edit') }}</label>
        <select id="active-menu" :value="activeMenuId" @input="handleMenuChange" class="select ui-control">
          <option v-for="menu in menus" :key="menu.id" :value="menu.id">
            {{ menu.name }}
          </option>
        </select>
      </div>

      <div v-if="activeMenu" class="menu-management-row">
        <span class="menu-state ui-badge" :class="{ active: activeMenu.is_active }">
          {{ activeMenu.is_active ? t('settings.activeMenu', 'Active menu') : t('settings.inactiveMenu', 'Inactive menu') }}
        </span>
        <div class="menu-management-actions">
          <button
            v-if="!activeMenu.is_active"
            class="ui-button"
            type="button"
            :disabled="managingMenu"
            @click="activateMenu"
          >
            {{ t('settings.setActiveMenu', 'Set as active') }}
          </button>
          <button class="ui-button" type="button" :disabled="managingMenu" @click="renameMenu">
            {{ t('common.rename', 'Rename') }}
          </button>
          <button class="ui-button ui-button--danger menu-delete" type="button" :disabled="managingMenu" @click="deleteMenu">
            {{ t('common.delete', 'Delete') }}
          </button>
        </div>
      </div>

      <MenuEditor
        v-if="activeMenu && menuProp"
        :menu="menuProp"
        :menu-language="menuLanguage"
        :available-languages="availableLanguages"
        :route-options="routeOptions"
        @add-item="addMenuItem"
        @edit-item="editMenuItem"
        @remove-item="removeMenuItem"
        @update-items="updateMenuItems"
        @drag-end="onDragEnd"
        :settings-store="settingsStore"
      />

      <div class="menu-actions">
        <button @click="saveMenu" class="ui-button ui-button--primary" :disabled="savingMenu">
          {{ savingMenu ? t('settings.saving', 'Saving...') : t('settings.saveMenu', 'Save Menu') }}
        </button>
      </div>
    </div>
    <div v-else class="menu-empty-state">
      <i class="bi bi-list-nested" aria-hidden="true"></i>
      <div>
        <strong>{{ t('settings.noMenusAvailable', 'No custom menus configured') }}</strong>
        <p>{{ t('settings.noMenusHelp', 'The current navigation is generated dynamically from enabled modules. A custom menu must exist before its items can be edited here.') }}</p>
      </div>
    </div>
  </SettingsSection>
</template>

<script lang="ts">
import { defineComponent, computed, ref } from 'vue'
import type { PropType } from 'vue'
import { useI18n } from '@/utils/i18n'
import SettingsSection from '@/components/SettingsSection.vue'
import LanguageSelector from '@/components/LanguageSelector.vue'
import MenuEditor from '@/components/settings/MenuEditor.vue'

interface Menu {
  id: number
  name: string
  items: any[]
  is_active: boolean
}

interface MenuRouteOption {
  path: string
  label: string
  adminOnly: boolean
  requiresAuth: boolean
}

export default defineComponent({
  name: 'MenuConfigurationSection',
  components: {
    SettingsSection,
    LanguageSelector,
    MenuEditor
  },
  props: {
    menuLanguage: {
      type: String,
      required: true
    },
    availableLanguages: {
      type: Array as PropType<string[]>,
      required: true
    },
    menus: {
      type: Array as PropType<Menu[]>,
      required: true
    },
    routeOptions: {
      type: Array as PropType<MenuRouteOption[]>,
      required: true
    },
    activeMenuId: {
      type: Number as PropType<number | null>,
      default: null
    },
    currentMenuItems: {
      type: Array,
      required: true
    },
    savingMenu: {
      type: Boolean,
      default: false
    },
    creatingMenu: {
      type: Boolean,
      default: false
    },
    managingMenu: {
      type: Boolean,
      default: false
    },
    settingsStore: {
      type: Object,
      required: true
    },
  },
  emits: [
    'update:menuLanguage',
    'update:activeMenuId',
    'update:currentMenuItems',
    'menu-language-change',
    'activate-menu',
    'rename-menu',
    'delete-menu',
    'add-menu-item',
    'edit-menu-item',
    'remove-menu-item',
    'create-menu',
    'save-menu',
    'drag-end'
  ],
  setup(props, { emit }) {
    const { t } = useI18n()
    const newMenuName = ref('')

    const activeMenu = computed(() => {
      if (!props.activeMenuId) return null
      return props.menus.find(m => m.id === props.activeMenuId)
    })

    const menuProp = computed(() => {
      if (!activeMenu.value) return null
      return { ...activeMenu.value, items: props.currentMenuItems } as Record<string, any>
    })

    const handleMenuChange = (e: Event) => {
      const target = e.target as HTMLSelectElement
      const value = target.value ? parseInt(target.value) : null
      emit('update:activeMenuId', value)
    }

    const handleMenuLanguageChange = (value: string) => {
      emit('update:menuLanguage', value)
    }

    const addMenuItem = (newItem: any) => {
      emit('add-menu-item', newItem)
    }

    const editMenuItem = (index: number) => {
      emit('edit-menu-item', index)
    }

    const removeMenuItem = (index: number) => {
      emit('remove-menu-item', index)
    }

    const saveMenu = () => {
      emit('save-menu')
    }

    const createMenu = () => {
      const name = newMenuName.value.trim()
      if (!name) return
      emit('create-menu', name)
      newMenuName.value = ''
    }

    const activateMenu = () => {
      if (activeMenu.value) emit('activate-menu', activeMenu.value.id)
    }

    const renameMenu = () => {
      if (!activeMenu.value) return
      const name = prompt(t('settings.renameMenuPrompt', 'Enter a new menu name:'), activeMenu.value.name)?.trim()
      if (name && name !== activeMenu.value.name) emit('rename-menu', { id: activeMenu.value.id, name })
    }

    const deleteMenu = () => {
      if (!activeMenu.value) return
      if (confirm(t('settings.deleteMenuConfirm', `Delete menu "${activeMenu.value.name}"?`))) {
        emit('delete-menu', activeMenu.value.id)
      }
    }

    const updateMenuItems = (items: any[]) => {
      emit('update:currentMenuItems', items)
    }

    const onDragEnd = () => {
      emit('drag-end')
    }

    return {
      t,
      activeMenu,
      menuProp,
      handleMenuChange,
      handleMenuLanguageChange,
      updateMenuItems,
      addMenuItem,
      editMenuItem,
      removeMenuItem,
      newMenuName,
      createMenu,
      activateMenu,
      renameMenu,
      deleteMenu,
      saveMenu,
      onDragEnd
    }
  }
})
</script>

<style scoped>
.menu-meta-row { display: grid; gap: calc(var(--ui-space) * 3); margin-bottom: calc(var(--ui-space) * 4); }
.menu-help { margin: 0; }
.menu-create-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: end; gap: calc(var(--ui-space) * 3); margin-bottom: calc(var(--ui-space) * 4); padding: calc(var(--ui-space) * 4); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-sm); background: var(--ui-surface-alt); }
.menu-create-field, .form-group { display: grid; gap: calc(var(--ui-space) * 2); min-width: 0; }
.menu-actions { display: flex; justify-content: flex-end; margin-top: calc(var(--ui-space) * 4); }
.menu-management-row { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: calc(var(--ui-space) * 3); margin: calc(var(--ui-space) * 4) 0; }
.menu-management-actions { display: flex; flex-wrap: wrap; gap: calc(var(--ui-space) * 2); }
.menu-state.active { color: var(--ui-success); }
.menu-empty-state { display: flex; align-items: flex-start; gap: calc(var(--ui-space) * 3); padding: calc(var(--ui-space) * 4); border: 1px dashed var(--ui-border); border-radius: var(--ui-radius-sm); color: var(--ui-text-secondary); background: var(--ui-surface-alt); }
.menu-empty-state i { font-size: 1.25rem; color: var(--ui-text-muted); }
.menu-empty-state strong { display: block; color: var(--ui-text); }
.menu-empty-state p { margin-top: var(--ui-space); }
@media (max-width: 720px) {
  .menu-create-row { grid-template-columns: minmax(0, 1fr); }
  .menu-management-actions { width: 100%; }
  .menu-management-actions .ui-button { flex: 1; }
}
</style>
