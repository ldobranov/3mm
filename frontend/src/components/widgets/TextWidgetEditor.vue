<script setup lang="ts">
import { computed } from 'vue';
import { useSettingsStore } from '@/stores/settings';

const settingsStore = useSettingsStore();
const styleSettings = computed(() => settingsStore.styleSettings);

const props = defineProps<{ modelValue: any }>();
const emit = defineEmits<{ (e: 'update:modelValue', v: any): void }>();

const cfg = computed({
  get: () => props.modelValue || {},
  set: (v) => emit('update:modelValue', { ...(v || {}) }),
});
</script>

<template>
  <div class="widget-editor">
    <div class="form-group">
      <label class="form-label">Content</label>
      <textarea
        class="input textarea"
        rows="6"
        v-model="cfg.content"
        placeholder="Your text"
      />
    </div>
    <div class="form-row">
      <div class="form-group">
        <label class="form-label">Font Size</label>
        <input
          type="number"
          class="input"
          v-model.number="cfg.fontSize"
          min="8"
          max="72"
        />
      </div>
      <div class="form-group">
        <label class="form-label">Color</label>
        <input
          type="color"
          class="input color-input"
          v-model="cfg.color"
        />
      </div>
    </div>
    <div class="form-group">
      <label class="form-label">Align</label>
      <select
        class="input select"
        v-model="cfg.align"
      >
        <option value="left">Left</option>
        <option value="center">Center</option>
        <option value="right">Right</option>
        <option value="justify">Justify</option>
      </select>
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

.form-row {
  display: flex;
  gap: 0.75rem;
}

.form-row .form-group {
  flex: 1;
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

.textarea {
  resize: vertical;
  min-height: 6rem;
}

.color-input {
  cursor: pointer;
  height: 2.5rem;
}

.select {
  cursor: pointer;
}
</style>
