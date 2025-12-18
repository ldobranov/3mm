<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from '@/utils/i18n';

const { t } = useI18n();

type ClockConfig = {
  timezone?: string;
  format?: string;
  showCustomMessage?: boolean;
  customMessage?: string;
};

const props = defineProps<{ config: ClockConfig; modelValue?: ClockConfig }>();
const emit = defineEmits<{ (e: 'update:modelValue', v: ClockConfig): void }>();

const timezone = computed({
  get: () => (props.config || props.modelValue)?.timezone || 'UTC',
  set: (val) => emit('update:modelValue', { ...(props.config || props.modelValue), timezone: val })
});

const format = computed({
  get: () => (props.config || props.modelValue)?.format || 'HH:mm:ss',
  set: (val) => emit('update:modelValue', { ...(props.config || props.modelValue), format: val })
});

const showCustomMessage = computed({
  get: () => (props.config || props.modelValue)?.showCustomMessage || false,
  set: (val) => emit('update:modelValue', { ...(props.config || props.modelValue), showCustomMessage: val })
});

const customMessage = computed({
  get: () => (props.config || props.modelValue)?.customMessage || '',
  set: (val) => emit('update:modelValue', { ...(props.config || props.modelValue), customMessage: val })
});
</script>

<template>
  <div class="widget-editor">
    <div class="form-group">
      <label class="form-label">{{ t('extensions.multilingualclockwidget.settings.timezone') }}</label>
      <select class="input" v-model="timezone">
        <option value="UTC">UTC</option>
        <option value="America/New_York">Eastern Time</option>
        <option value="America/Chicago">Central Time</option>
        <option value="America/Denver">Mountain Time</option>
        <option value="America/Los_Angeles">Pacific Time</option>
        <option value="Europe/London">London</option>
        <option value="Europe/Paris">Paris</option>
        <option value="Europe/Sofia">Sofia</option>
        <option value="Asia/Tokyo">Tokyo</option>
      </select>
    </div>

    <div class="form-group">
      <label class="form-label">{{ t('extensions.multilingualclockwidget.settings.format') }}</label>
      <select class="input" v-model="format">
        <option value="HH:mm:ss">24-hour (HH:mm:ss)</option>
        <option value="hh:mm:ss A">12-hour (hh:mm:ss AM/PM)</option>
        <option value="HH:mm">24-hour (HH:mm)</option>
        <option value="hh:mm A">12-hour (hh:mm AM/PM)</option>
      </select>
    </div>

    <div class="form-group">
      <label class="checkbox-label">
        <input
          type="checkbox"
          v-model="showCustomMessage"
        />
        {{ t('extensions.multilingualclockwidget.settings.showCustomMessage') }}
      </label>
    </div>

    <div v-if="showCustomMessage" class="form-group">
      <label class="form-label">{{ t('extensions.multilingualclockwidget.settings.customMessage') }}</label>
      <input
        type="text"
        class="input"
        v-model="customMessage"
        :placeholder="t('extensions.multilingualclockwidget.settings.customMessage')"
      />
    </div>
  </div>
</template>

<style scoped>
.widget-editor {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.form-label {
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--text-primary);
}

.input {
  padding: 0.5rem;
  border: 1px solid var(--input-border);
  border-radius: var(--border-radius-sm);
  background-color: var(--input-bg);
  color: var(--text-primary);
  font-size: 0.875rem;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.input:focus {
  outline: none;
  border-color: var(--input-focus-border);
  box-shadow: 0 0 0 2px rgba(var(--button-primary-bg), 0.2);
}

.input::placeholder {
  color: var(--input-placeholder);
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--text-primary);
}

.checkbox-label input[type="checkbox"] {
  width: auto;
  margin: 0;
}
</style>