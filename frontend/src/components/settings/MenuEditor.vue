<template>
  <div class="menu-editor">
    <div class="menu-editor-title">
      <div>
        <strong>{{ t('settings.menuItems', 'Menu Items') }}</strong>
        <p class="menu-editor-subtitle">
          {{ t('settings.menuLanguageHelp', 'Configure complete menu structure for the selected language') }}
        </p>
      </div>
      <span class="menu-editor-count">
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
              <label class="form-label menu-item-field-label">
                {{ t('settings.label', 'Label') }} ({{ menuLanguage.toUpperCase() }})
              </label>
              <input
                type="text"
                class="input menu-item-label"
                :value="getMenuItemLabel(item, menuLanguage)"
                @input="updateMenuItemLabel(index, $event)"
                :placeholder="`${t('settings.label', 'Label')} ${t('settings.in', 'in')} ${menuLanguage.toUpperCase()}`"
              />
            </div>

            <div class="menu-editor-field">
              <label class="form-label menu-item-field-label">
                {{ t('settings.path', 'Path') }}
              </label>
              <input
                type="text"
                class="input menu-item-path-input"
                :value="item.path"
                :placeholder="t('settings.path', 'Path')"
                @input="updateMenuItemPath(index, $event)"
              />
            </div>
          </div>
        </div>

        <div class="menu-item-actions">
          <button
            class="button button-outline button-sm menu-item-action"
            type="button"
            @click="duplicateMenuItem(index)"
          >
            {{ t('common.duplicate', 'Duplicate') }}
          </button>
          <button
            class="button button-outline button-sm menu-item-action menu-item-danger"
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
          <label class="form-label">{{ t('settings.label', 'Label') }} ({{ menuLanguage.toUpperCase() }})</label>
          <input
            type="text"
            class="input menu-editor-input"
            :placeholder="`${t('settings.label', 'Label')} ${t('settings.in', 'in')} ${menuLanguage.toUpperCase()}`"
            v-model="newItem.label"
          />
        </div>

        <div class="menu-editor-field">
          <label class="form-label">{{ t('settings.path', 'Path') }}</label>
          <input
            type="text"
            class="input menu-editor-input"
            :placeholder="t('settings.path', 'Path')"
            v-model="newItem.path"
          />
        </div>
      </div>

      <button
        class="button button-primary"
        type="button"
        @click="addMenuItem"
      >
        {{ t('settings.add', 'Add') }}
      </button>
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref } from 'vue'
import type { PropType } from 'vue'
import { useI18n } from '@/utils/i18n'
import { VueDraggable } from 'vue-draggable-plus'

interface MenuItem {
  label: Record<string, string>
  path: string
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
    getMenuItemLabel: {
      type: Function,
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
    const newItem = ref({ label: '', path: '' })

    const normalizeMenuItemLabel = (item: MenuItem) => {
      if (typeof item.label === 'string') {
        item.label = { en: item.label }
      } else if (!item.label || typeof item.label !== 'object') {
        item.label = { en: 'Menu Item' }
      }
      return item
    }

    const updateMenuItemLabel = (index: number, event: Event) => {
      const target = event.target as HTMLInputElement
      const items = [...props.menu.items]
      const item = items[index]
      normalizeMenuItemLabel(item)
      item.label[props.menuLanguage] = target.value
      emit('update-items', items)
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

    const handleItemsReorder = (items: MenuItem[]) => {
      emit('update-items', items)
      emit('drag-end')
    }

    const addMenuItem = () => {
      if (!newItem.value.label || !newItem.value.path) return

      const labelObj: Record<string, string> = {}
      labelObj[props.menuLanguage] = newItem.value.label

      const items = [...props.menu.items, {
        label: labelObj,
        path: newItem.value.path
      }]

      emit('update-items', items)
      newItem.value = { label: '', path: '' }
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
      updateMenuItemLabel,
      updateMenuItemPath,
      handleItemsReorder,
      addMenuItem,
      duplicateMenuItem,
      removeMenuItem
    }
  }
})
</script>

<style scoped>
.menu-editor {
  display: grid;
  gap: 1rem;
}

.menu-editor-title {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  padding-bottom: 0.85rem;
  border-bottom: 1px solid var(--color-border);
}

.menu-editor-title strong {
  font-size: 0.95rem;
  font-weight: 650;
  letter-spacing: -0.01em;
}

.menu-editor-subtitle {
  margin: 0.35rem 0 0;
  font-size: 0.88rem;
  color: var(--text-secondary);
}

.menu-editor-count {
  min-width: 2.2rem;
  padding: 0.3rem 0.6rem;
  border: 1px solid var(--color-border);
  border-radius: 999px;
  text-align: center;
  font-size: 0.82rem;
  font-weight: 650;
  color: var(--text-secondary);
  background: var(--panel-bg);
}

.menu-item {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: start;
  gap: 0.75rem;
  padding: 0.9rem;
  margin-bottom: 0.65rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  background-color: var(--card-bg);
  box-shadow: 0 1px 0 rgba(15, 23, 42, 0.03);
}

.drag-handle {
  cursor: move;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  margin-top: 1.65rem;
  font-size: 1rem;
  color: var(--text-muted);
  border-radius: 999px;
  background: var(--panel-bg);
}

.menu-item-content {
  min-width: 0;
}

.menu-item-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr);
  gap: 0.75rem;
}

.menu-editor-field {
  display: grid;
  gap: 0.35rem;
}

.menu-item-field-label {
  font-size: 0.75rem;
  color: var(--text-secondary);
}

.menu-item-label,
.menu-item-path-input,
.menu-editor-input {
  width: 100%;
}

.menu-item-actions {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  justify-content: flex-start;
}

.menu-item-action {
  min-width: 6.5rem;
}

.menu-item-danger {
  border-color: var(--button-danger-bg);
  color: var(--button-danger-bg);
}

.menu-items-empty {
  padding: 1rem;
  border: 1px dashed var(--color-border);
  border-radius: var(--border-radius-sm);
  background: var(--panel-bg);
  color: var(--text-secondary);
}

.menu-items-empty p {
  margin: 0;
}

.menu-editor-add {
  padding-top: 1rem;
  border-top: 1px solid var(--color-border);
  display: grid;
  gap: 0.75rem;
}

.menu-editor-add h4 {
  margin: 0;
  font-size: 0.95rem;
}

.menu-editor-add-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr);
  gap: 0.75rem;
}

:root[data-theme="dark"] .menu-item,
.dark .menu-item,
:root[data-theme="dark"] .menu-editor-title,
.dark .menu-editor-title,
:root[data-theme="dark"] .menu-editor-add,
.dark .menu-editor-add,
:root[data-theme="dark"] .menu-items-empty,
.dark .menu-items-empty,
:root[data-theme="dark"] .menu-editor-count,
.dark .menu-editor-count {
  border-color: var(--color-border);
}

@media (max-width: 900px) {
  .menu-item {
    grid-template-columns: 1fr;
  }

  .drag-handle {
    margin-top: 0;
  }

  .menu-item-grid,
  .menu-editor-add-grid {
    grid-template-columns: 1fr;
  }

  .menu-item-actions {
    flex-direction: row;
    justify-content: flex-start;
  }
}
</style>
