<template>
  <div class="form-section">
    <label class="form-label">{{ label }} ({{ modelValue.toUpperCase() }})</label>
    <select
      :value="modelValue"
      class="select"
      @change="handleChange"
    >
      <option
        v-for="lang in availableLanguages"
        :key="lang"
        :value="lang"
      >
        {{ lang.toUpperCase() }}
      </option>
    </select>
  </div>
</template>

<script lang="ts">
import { defineComponent } from 'vue'
import type { PropType } from 'vue'

export default defineComponent({
  name: 'LanguageSelector',
  props: {
    modelValue: {
      type: String,
      required: true
    },
    availableLanguages: {
      type: Array as PropType<string[]>,
      required: true
    },
    label: {
      type: String,
      required: true
    }
  },
  emits: ['update:modelValue', 'change'],
  setup(props, { emit }) {
    const handleChange = (e: Event) => {
      const target = e.target as HTMLSelectElement
      emit('update:modelValue', target.value)
      emit('change')
    }

    return {
      handleChange
    }
  }
})
</script>

<style scoped>
/* Uses existing .form-section, .form-label, and .select classes from styles.css */
</style>