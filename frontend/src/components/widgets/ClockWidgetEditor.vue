<script setup lang="ts">
import { computed } from 'vue';
import { useSettingsStore } from '@/stores/settings';

const settingsStore = useSettingsStore();
const styleSettings = computed(() => settingsStore.styleSettings);

const props = defineProps<{ modelValue: any }>();
const emit = defineEmits<{ (e: 'update:modelValue', v: any): void }>();

const timezone = computed({
  get: () => props.modelValue?.timezone || 'UTC',
  set: (val) => emit('update:modelValue', { ...props.modelValue, timezone: val })
});

const format = computed({
  get: () => props.modelValue?.format || 'HH:mm:ss',
  set: (val) => emit('update:modelValue', { ...props.modelValue, format: val })
});
</script>

<template>
  <div class="widget-editor">
    <div class="form-group">
      <label class="form-label">Timezone</label>
      <input
        type="text"
        class="input"
        v-model="timezone"
        placeholder="UTC or e.g. Europe/Sofia"
      />
    </div>
    <div class="form-group">
      <label class="form-label">Format</label>
      <input
        type="text"
        class="input"
        v-model="format"
        placeholder="HH:mm:ss"
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
</style>
