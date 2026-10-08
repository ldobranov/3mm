<template>
  <div class="form-field">
    <label class="form-label">{{ label }}</label>
    <div class="color-input-group">
      <input
        type="color"
        :value="modelValue"
        :aria-label="label"
        @input="handleColorChange"
        class="color-picker ui-control"
      />
      <input
        type="text"
        :value="modelValue"
        :aria-label="label"
        @input="handleTextChange"
        :placeholder="placeholder"
        class="color-text-input ui-control"
      />
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent } from 'vue'

export default defineComponent({
  name: 'ColorPicker',
  props: {
    label: {
      type: String,
      required: true
    },
    modelValue: {
      type: String,
      required: true
    },
    placeholder: {
      type: String,
      default: '#ffffff'
    }
  },
  emits: ['update:modelValue'],
  setup(props, { emit }) {
    const handleColorChange = (e: Event) => {
      const target = e.target as HTMLInputElement
      emit('update:modelValue', target.value)
    }

    const handleTextChange = (e: Event) => {
      const target = e.target as HTMLInputElement
      emit('update:modelValue', target.value)
    }

    return {
      handleColorChange,
      handleTextChange
    }
  }
})
</script>

<style scoped>
/* Shared control styling is opt-in through the Settings ui-v2 boundary. */
.ui-v2 .color-input-group { display: grid; grid-template-columns: 3rem minmax(0, 1fr); gap: calc(var(--ui-space) * 2); min-width: 0; }
.ui-v2 .color-picker { width: 3rem; padding: calc(var(--ui-space) * 1.5); cursor: pointer; }
.ui-v2 .color-text-input { width: 100%; min-width: 0; max-width: none; font-family: ui-monospace, monospace; }
</style>
