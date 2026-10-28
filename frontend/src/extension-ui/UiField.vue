<script setup lang="ts">
import { computed } from 'vue'
const props = withDefaults(defineProps<{
  id: string; label: string; modelValue?: string | number | boolean | null
  type?: 'text' | 'email' | 'number' | 'date' | 'datetime-local' | 'checkbox' | 'textarea' | 'select'
  description?: string; error?: string; required?: boolean; disabled?: boolean; readonly?: boolean
  placeholder?: string; autofocus?: boolean
  maxlength?: number; step?: string | number; min?: number; max?: number
  options?: ReadonlyArray<{ value: string; label: string; disabled?: boolean }>
}>(), { type: 'text', modelValue: '', required: false, disabled: false, readonly: false, autofocus: false, maxlength: 1024 })
const emit = defineEmits<{ 'update:modelValue': [value: string | boolean] }>()
const describedBy = computed(() => [props.description && `${props.id}-help`, props.error && `${props.id}-error`].filter(Boolean).join(' ') || undefined)
const textValue = computed(() => typeof props.modelValue === 'boolean' ? '' : props.modelValue ?? '')
function input(event: Event) {
  const target = event.target as HTMLInputElement
  emit('update:modelValue', props.type === 'checkbox' ? target.checked : target.value)
}
</script>

<template>
  <div class="ui-field" :class="{ 'ui-field--checkbox': type === 'checkbox' }">
    <label :for="id">{{ label }}<span v-if="required" aria-hidden="true"> *</span></label>
    <textarea v-if="type === 'textarea'" :id="id" class="ui-control" :value="textValue"
      :placeholder="placeholder" :autofocus="autofocus"
      :required="required" :disabled="disabled" :readonly="readonly" :maxlength="maxlength"
      :aria-invalid="Boolean(error) || undefined" :aria-describedby="describedBy" @input="input" />
    <select v-else-if="type === 'select'" :id="id" class="ui-control" :value="textValue"
      :autofocus="autofocus"
      :required="required" :disabled="disabled || readonly" :aria-invalid="Boolean(error) || undefined"
      :aria-describedby="describedBy" @change="input">
      <option v-for="option in options" :key="option.value" :value="option.value" :disabled="option.disabled">{{ option.label }}</option>
    </select>
    <input v-else :id="id" class="ui-control" :type="type" :value="type === 'checkbox' ? undefined : textValue"
      :placeholder="placeholder" :autofocus="autofocus"
      :checked="type === 'checkbox' && modelValue === true" :required="required" :disabled="disabled || (type === 'checkbox' && readonly)"
      :readonly="readonly" :maxlength="maxlength" :step="step" :min="min" :max="max"
      :aria-invalid="Boolean(error) || undefined" :aria-describedby="describedBy" @input="input" />
    <small v-if="description" :id="`${id}-help`" class="ui-help">{{ description }}</small>
    <small v-if="error" :id="`${id}-error`" class="ui-field-error">{{ error }}</small>
  </div>
</template>
