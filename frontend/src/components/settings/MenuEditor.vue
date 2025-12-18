<template>
  <div>
    <div style="margin-bottom: 1rem;">
      <strong>{{ t('settings.menuItems', 'Menu Items') }}</strong>
    </div>

    <VueDraggable
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
        <div class="drag-handle">☰</div>
        <div class="menu-item-content">
          <input
            type="text"
            class="input"
            style="margin-bottom: 0.25rem;"
            :value="getMenuItemLabel(item, menuLanguage)"
            @input="updateMenuItemLabel(index, $event)"
            :placeholder="`${t('settings.label', 'Label')} ${t('settings.in', 'in')} ${menuLanguage.toUpperCase()}`"
          />
          <div class="text-muted-theme">
            {{ t('settings.path', 'Path') }}: {{ item.path }}
          </div>
        </div>
        <div class="menu-item-actions">
          <button
            class="button button-outline button-sm"
            style="margin-right: 0.25rem; margin-bottom: 0.25rem;"
            @click="editMenuItem(index)"
          >
            {{ t('settings.edit', 'Edit') }}
          </button>
          <button
            class="button button-outline button-sm"
            :style="{ '--accent': 'var(--button-danger-bg)', borderColor: 'var(--button-danger-bg)', color: 'var(--button-danger-bg)' }"
            @click="removeMenuItem(index)"
          >
            {{ t('settings.remove', 'Remove') }}
          </button>
        </div>
      </div>
    </VueDraggable>

    <!-- Add New Item -->
    <div style="margin-top: 1rem; padding-top: 1rem; border-top: 1px solid var(--color-border);">
      <h4 style="margin-bottom: 0.5rem;">
        {{ t('settings.addMenuItem', 'Add Menu Item') }}
      </h4>
      <div style="margin-bottom: 0.5rem;">
        <label class="form-label">{{ t('settings.label', 'Label') }} ({{ menuLanguage.toUpperCase() }})</label>
      </div>
      <input
        type="text"
        class="input"
        style="margin-bottom: 0.5rem;"
        :placeholder="`${t('settings.label', 'Label')} ${t('settings.in', 'in')} ${menuLanguage.toUpperCase()}`"
        v-model="newItem.label"
      />
      <div style="margin-bottom: 0.5rem;">
        <label class="form-label">{{ t('settings.path', 'Path') }}</label>
      </div>
      <input
        type="text"
        class="input"
        style="margin-bottom: 0.5rem;"
        :placeholder="t('settings.path', 'Path')"
        v-model="newItem.path"
      />
      <button
        class="button button-primary"
        @click="addMenuItem"
      >
        {{ t('settings.add', 'Add') }}
      </button>
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, watch } from 'vue'
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

    const handleItemsReorder = (items: MenuItem[]) => {
      emit('update-items', items)
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

    const editMenuItem = (index: number) => {
      const item = props.menu.items[index]
      const newPath = prompt('Enter new path:', item.path)

      if (newPath !== null && newPath !== item.path) {
        const items = [...props.menu.items]
        items[index] = { ...item, path: newPath }
        emit('update-items', items)
      }
    }

    const removeMenuItem = (index: number) => {
      if (confirm('Remove this menu item?')) {
        const items = props.menu.items.filter((item: MenuItem, i: number) => i !== index)
        emit('update-items', items)
      }
    }

    const onDragEnd = () => {
      emit('drag-end')
    }

    return {
      t,
      newItem,
      updateMenuItemLabel,
      handleItemsReorder,
      addMenuItem,
      editMenuItem,
      removeMenuItem,
      onDragEnd
    }
  }
})
</script>

<style scoped>
.menu-item {
  display: flex;
  align-items: center;
  padding: 0.75rem;
  margin-bottom: 0.5rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  background-color: var(--card-bg);
}

.drag-handle {
  cursor: move;
  margin-right: 0.75rem;
  font-size: 1.2rem;
  color: var(--text-muted);
}

.menu-item-content {
  flex: 1;
}

.menu-item-actions {
  margin-left: 0.5rem;
}

</style>