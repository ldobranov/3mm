<template>
  <SettingsSection :title="sectionTitle">
    <form @submit.prevent>
      <!-- Dynamic Color Sections -->
      <div
        v-for="config in colorConfigs"
        :key="config.category"
        class="form-section"
      >
        <h4>{{ config.title }}</h4>
        <div
          v-for="item in config.items"
          :key="item.key"
          class="form-field"
        >
          <ColorPicker
            :label="item.label"
            :model-value="settings[item.key]"
            :placeholder="item.placeholder"
            @update:model-value="settings[item.key] = $event"
          />
        </div>
      </div>

      <!-- Border Radius Section -->
      <div class="form-section">
        <h4>{{ t('settings.borderRadius', 'Border Radius') }}</h4>
        <div
          v-for="radius in borderRadiusConfigs"
          :key="radius.key"
          class="form-field"
        >
          <label :for="`${themeType}-${radius.key}`" class="form-label">
            {{ radius.label }}
          </label>
          <div class="range-input-group">
            <input
              :id="`${themeType}-${radius.key}`"
              type="range"
              :min="radius.min"
              :max="radius.max"
              step="1"
              class="input"
              :value="settings[radius.key]"
              @input="settings[radius.key] = parseInt(($event.target as HTMLInputElement).value)"
            />
            <span class="range-value">{{ settings[radius.key] }}px</span>
          </div>
        </div>
      </div>

      <!-- Preview -->
      <div class="form-field">
        <label class="form-label">{{ t('settings.preview', 'Preview') }}</label>
        <div class="preview-card">
          <h5>{{ t('settings.sampleCard', 'Sample Card') }}</h5>
          <p class="preview-text">
            {{ t('settings.previewText', 'This is how your styled components will look.') }}
          </p>
          <div class="preview-buttons">
            <button class="preview-button-primary">
              {{ t('settings.primaryButton', 'Primary Button') }}
            </button>
            <button class="preview-button-secondary">
              {{ t('settings.secondaryButton', 'Secondary Button') }}
            </button>
            <button class="preview-button-danger">
              {{ t('settings.dangerButton', 'Danger Button') }}
            </button>
          </div>
        </div>
      </div>

      <button
        type="submit"
        class="button button-primary"
        :disabled="saving"
        @click="handleSave"
      >
        {{ saving ? t('settings.saving', 'Saving...') : `${t('settings.saveThemeSettings', 'Save Theme Settings')} ${themeType.charAt(0).toUpperCase() + themeType.slice(1)}` }}
      </button>
    </form>
  </SettingsSection>
</template>

<script lang="ts">
import { defineComponent, computed, watch } from 'vue'
import type { PropType } from 'vue'
import SettingsSection from '@/components/SettingsSection.vue'
import ColorPicker from '@/components/ColorPicker.vue'

export default defineComponent({
  name: 'ThemeCustomizationSection',
  components: {
    SettingsSection,
    ColorPicker
  },
  props: {
    themeType: {
      type: String,
      required: true
    },
    settings: {
      type: Object,
      required: true
    },
    saving: {
      type: Boolean,
      default: false
    },
    t: {
      type: Function,
      required: true
    },
    settingsStore: {
      type: Object,
      required: true
    },
    sectionTitle: {
      type: String,
      required: true
    }
  },
  emits: ['save'],
  setup(props, { emit }) {
    // Watch for settings changes to update CSS variables for live preview
    watch(() => props.settings, () => {
      props.settingsStore.updateCSSVariables()
    }, { deep: true })

    const colorConfigs = computed(() => [
      // Background Colors
      {
        category: 'background',
        title: props.t('settings.backgroundColors', 'Background Colors'),
        items: [
          {
            key: 'bodyBg',
            label: props.t('settings.bodyBackgroundColor', 'Body Background Color'),
            placeholder: props.themeType === 'light' ? '#ffffff' : '#1f2937'
          },
          {
            key: 'contentBg',
            label: props.t('settings.contentBackgroundColor', 'Content Background Color'),
            placeholder: props.themeType === 'light' ? '#ffffff' : '#1f2937'
          }
        ]
      },
      // Button Colors
      {
        category: 'buttons',
        title: props.t('settings.buttonColors', 'Button Colors'),
        items: [
          {
            key: 'buttonPrimaryBg',
            label: props.t('settings.primaryButtonColor', 'Primary Button Color'),
            placeholder: props.themeType === 'light' ? '#007bff' : '#3b82f6'
          },
          {
            key: 'buttonSecondaryBg',
            label: props.t('settings.secondaryButtonColor', 'Secondary Button Color'),
            placeholder: props.themeType === 'light' ? '#6c757d' : '#6b7280'
          },
          {
            key: 'buttonDangerBg',
            label: props.t('settings.dangerButtonColor', 'Danger Button Color'),
            placeholder: props.themeType === 'light' ? '#dc3545' : '#ef4444'
          }
        ]
      },
      // Card & Component Colors
      {
        category: 'components',
        title: props.t('settings.cardComponentColors', 'Card & Component Colors'),
        items: [
          {
            key: 'cardBg',
            label: props.t('settings.cardBackgroundColor', 'Card Background Color'),
            placeholder: props.themeType === 'light' ? '#ffffff' : '#374151'
          },
          {
            key: 'cardBorder',
            label: props.t('settings.cardBorderColor', 'Card Border Color'),
            placeholder: props.themeType === 'light' ? '#e3e3e3' : '#4b5563'
          },
          {
            key: 'panelBg',
            label: props.t('settings.panelBackgroundColor', 'Panel Background Color'),
            placeholder: props.themeType === 'light' ? '#ffffff' : '#374151'
          }
        ]
      },
      // Text Colors
      {
        category: 'text',
        title: props.t('settings.textColors', 'Text Colors'),
        items: [
          {
            key: 'textPrimary',
            label: props.t('settings.primaryTextColor', 'Primary Text Color'),
            placeholder: props.themeType === 'light' ? '#222222' : '#e5e7eb'
          },
          {
            key: 'textSecondary',
            label: props.t('settings.secondaryTextColor', 'Secondary Text Color'),
            placeholder: props.themeType === 'light' ? '#666666' : '#9ca3af'
          },
          {
            key: 'textMuted',
            label: props.t('settings.mutedTextColor', 'Muted Text Color'),
            placeholder: props.themeType === 'light' ? '#999999' : '#6b7280'
          }
        ]
      }
    ])

    const borderRadiusConfigs = computed(() => [
      { key: 'borderRadiusSm', label: props.t('settings.borderRadiusSmall', 'Border Radius (Small)'), min: 0, max: 20 },
      { key: 'borderRadiusMd', label: props.t('settings.borderRadiusMedium', 'Border Radius (Medium)'), min: 0, max: 30 },
      { key: 'borderRadiusLg', label: props.t('settings.borderRadiusLarge', 'Border Radius (Large)'), min: 0, max: 50 }
    ])

    const handleSave = () => {
      emit('save')
    }

    return {
      colorConfigs,
      borderRadiusConfigs,
      handleSave
    }
  }
})
</script>

<style scoped>
.preview-text {
  margin: 0 0 1rem 0;
  opacity: 0.8;
  color: var(--text-secondary, #666666);
}
</style>