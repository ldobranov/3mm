<template>
  <fieldset class="form-section theme-selector">
    <legend class="form-label">{{ label || t('settings.applicationTheme', 'Application Theme') }}</legend>
    <div class="theme-options">
      <label class="theme-option">
        <input
          type="radio"
          name="theme"
          value="light"
          :checked="modelValue === 'light'"
          @change="handleChange"
        />
        <i class="bi bi-sun-fill" aria-hidden="true"></i>
        {{ t('settings.lightMode', 'Light Mode') }}
      </label>
      <label class="theme-option">
        <input
          type="radio"
          name="theme"
          value="dark"
          :checked="modelValue === 'dark'"
          @change="handleChange"
        />
        <i class="bi bi-moon-fill" aria-hidden="true"></i>
        {{ t('settings.darkMode', 'Dark Mode') }}
      </label>
    </div>
    <small class="help-text">
      {{ t('settings.chooseTheme', 'Choose your preferred application theme') }}
    </small>
  </fieldset>
</template>

<script lang="ts">
import { defineComponent } from 'vue'
import { useI18n } from '@/utils/i18n'

export default defineComponent({
  name: 'ThemeSelector',
  props: {
    label: { type: String, default: '' },
    modelValue: {
      type: String,
      required: true
    }
  },
  emits: ['update:modelValue', 'change'],
  setup(props, { emit }) {
    const { t } = useI18n()

    const handleChange = (e: Event) => {
      const target = e.target as HTMLInputElement
      emit('update:modelValue', target.value)
      emit('change')
    }

    return {
      t,
      handleChange
    }
  }
})
</script>

<style scoped>
.theme-selector { border: 0; padding: 0; min-width: 0; }
.theme-selector legend { font-size: inherit; }
.theme-options {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.theme-option {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  border: 1px solid var(--color-border);
  border-radius: var(--border-radius-sm);
  cursor: pointer;
  transition: background-color 0.3s ease;
}

.theme-option:hover {
  background-color: var(--color-background-soft);
}

.theme-option input[type="radio"] {
  margin: 0;
}
</style>
