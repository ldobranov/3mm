<script setup lang="ts">
import { ref, computed } from 'vue';
import { useI18n } from '@/utils/i18n';

const { t } = useI18n();

const props = defineProps<{ config: any; modelValue?: any }>();
const emit = defineEmits<{ (e: 'update:modelValue', v: any): void }>();

const title = computed({
  get: () => (props.config || props.modelValue)?.title || t('extensions.pagesextension.settings.title'),
  set: (val) => emit('update:modelValue', { ...(props.config || props.modelValue), title: val })
});

const defaultPublic = computed({
  get: () => (props.config || props.modelValue)?.defaultPublic ?? true,
  set: (val) => emit('update:modelValue', { ...(props.config || props.modelValue), defaultPublic: val })
});

const maxPages = computed({
  get: () => (props.config || props.modelValue)?.maxPages || 100,
  set: (val) => emit('update:modelValue', { ...(props.config || props.modelValue), maxPages: val })
});
</script>

<template>
  <div class="pages-editor">
    <div class="form-group">
      <label class="form-label">{{ t('extensions.pagesextension.settings.title') }}</label>
      <input
        type="text"
        class="input"
        v-model="title"
      />
    </div>

    <div class="form-group">
      <label class="checkbox-label">
        <input
          type="checkbox"
          v-model="defaultPublic"
        />
        {{ t('extensions.pagesextension.settings.defaultPublic') }}
      </label>
    </div>

    <div class="form-group">
      <label class="form-label">{{ t('extensions.pagesextension.settings.maxPages') }}</label>
      <input
        type="number"
        class="input"
        v-model.number="maxPages"
        min="1"
        max="1000"
      />
    </div>
  </div>
</template>

<style scoped>
.pages-editor {
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