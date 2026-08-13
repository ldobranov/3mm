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

    <div v-if="menus.length > 0">
      <div class="form-group">
        <label for="active-menu" class="form-label">{{ t('settings.activeMenu', 'Active Menu') }}</label>
        <select id="active-menu" :value="activeMenuId" @input="handleMenuChange" class="select">
          <option v-for="menu in menus" :key="menu.id" :value="menu.id">
            {{ menu.name }}
          </option>
        </select>
      </div>

      <MenuEditor
        v-if="activeMenu && menuProp"
        :menu="menuProp"
        :menu-language="menuLanguage"
        :available-languages="availableLanguages"
        @add-item="addMenuItem"
        @edit-item="editMenuItem"
        @remove-item="removeMenuItem"
        @update-items="updateMenuItems"
        @drag-end="onDragEnd"
        :get-menu-item-label="getMenuItemLabel"
        :settings-store="settingsStore"
      />

      <div class="menu-actions">
        <button @click="saveMenu" class="button button-primary" :disabled="savingMenu">
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
import { defineComponent, computed } from 'vue'
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
    'set-active-menu',
    'add-menu-item',
    'edit-menu-item',
    'remove-menu-item',
    'save-menu',
    'drag-end'
  ],
  setup(props, { emit }) {
    const { t } = useI18n()

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
      setActiveMenu()
    }

    const setActiveMenu = () => {
      emit('set-active-menu')
    }

    const handleMenuLanguageChange = (value: string) => {
      emit('update:menuLanguage', value)
    }

    const onMenuLanguageChange = () => {
      emit('menu-language-change')
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

    const updateMenuItems = (items: any[]) => {
      emit('update:currentMenuItems', items)
    }

    const onDragEnd = () => {
      emit('drag-end')
    }

    const getMenuItemLabel = (item: any, languageCode: string): string => {
      // Helper function to normalize menu item labels to objects
      const normalizeMenuItemLabel = (item: any) => {
        if (typeof item.label === 'string') {
          item.label = { en: item.label }
        } else if (!item.label || typeof item.label !== 'object') {
          item.label = { en: 'Menu Item' }
        }
        return item
      }

      // Ensure label is normalized
      normalizeMenuItemLabel(item)

      if (typeof item.label === 'object' && item.label) {
        return item.label[languageCode] || item.label['en'] || Object.values(item.label)[0] || 'Menu Item'
      }
      return 'Menu Item'
    }

    return {
      t,
      activeMenu,
      menuProp,
      handleMenuChange,
      handleMenuLanguageChange,
      setActiveMenu,
      onMenuLanguageChange,
      updateMenuItems,
      addMenuItem,
      editMenuItem,
      removeMenuItem,
      saveMenu,
      onDragEnd,
      getMenuItemLabel
    }
  }
})
</script>

<style scoped>
.menu-meta-row {
  display: grid;
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.menu-help {
  margin-top: 0;
}

.menu-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 1rem;
}

.menu-empty-state {
  display: flex;
  align-items: flex-start;
  gap: 0.85rem;
  padding: 1rem;
  border: 1px dashed var(--card-border, #e3e3e3);
  border-radius: var(--border-radius-sm, 4px);
  color: var(--text-secondary, #666666);
  background: var(--panel-bg, #f8f9fa);
}

.menu-empty-state i {
  font-size: 1.25rem;
  color: var(--text-muted, #6b7280);
}

.menu-empty-state strong {
  display: block;
  color: var(--text-primary, #222222);
}

.menu-empty-state p {
  margin: 0.3rem 0 0;
}

:root[data-theme="dark"] .menu-empty-state,
.dark .menu-empty-state {
  border-color: var(--card-border, #4b5563);
  background: var(--panel-bg, #374151);
}
</style>
