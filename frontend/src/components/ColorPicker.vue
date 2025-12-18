<template>
  <div class="form-field">
    <label class="form-label">{{ label }}</label>
    <div class="color-input-group">
      <input
        type="color"
        :value="modelValue"
        @input="handleColorChange"
        class="color-picker"
      />
      <input
        type="text"
        :value="modelValue"
        @input="handleTextChange"
        :placeholder="placeholder"
        class="color-text-input"
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
/* Uses .color-input-group and .color-* classes from styles.css */
</style>