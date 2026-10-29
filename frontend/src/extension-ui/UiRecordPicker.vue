<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ComboboxAnchor, ComboboxContent, ComboboxInput, ComboboxItem, ComboboxItemIndicator, ComboboxRoot, ComboboxTrigger } from 'reka-ui'
import UiButton from '../components/ui/UiButton.vue'

type Option = { id: string; label: string; description?: string; disabled?: boolean }
const props = withDefaults(defineProps<{
  id: string; label: string; options: ReadonlyArray<Option>; modelValue: string | ReadonlyArray<string> | null
  selectedOptions?: ReadonlyArray<Option>; multiple?: boolean; filterMode?: 'local' | 'external'
  disabled?: boolean; busy?: boolean; description?: string; error?: string; placeholder?: string
  emptyLabel?: string; loadingLabel?: string; selectedLabel?: string; removeLabel?: string
  toggleLabel?: string; unavailableLabel?: string
}>(), {
  selectedOptions: () => [], multiple: false, filterMode: 'local', disabled: false, busy: false,
  emptyLabel: 'No matching records', loadingLabel: 'Loading records…', selectedLabel: 'Selected records',
  removeLabel: 'Remove', toggleLabel: 'Show records', unavailableLabel: 'Unavailable record',
})
const emit = defineEmits<{ 'update:modelValue': [value: string | string[] | null] }>()
const search = defineModel<string>('search', { default: '' })
const open = ref(false)
const locked = computed(() => props.disabled || props.busy)
const selected = computed(() => Array.isArray(props.modelValue) ? [...props.modelValue] : typeof props.modelValue === 'string' ? [props.modelValue] : [])
const labels = computed(() => new Map([...props.selectedOptions, ...props.options].map(option => [option.id, option.label])))
const choices = computed(() => props.filterMode === 'external' ? props.options : props.options.filter(option =>
  `${option.label} ${option.description ?? ''}`.toLocaleLowerCase().includes(search.value.trim().toLocaleLowerCase())))
const describedBy = computed(() => [props.description && `${props.id}-help`, props.error && `${props.id}-error`, props.busy && `${props.id}-loading`].filter(Boolean).join(' ') || undefined)
watch(locked, value => { if (value) open.value = false })

function update(value: unknown) {
  if (locked.value) return
  const values = value == null ? [] : typeof value === 'string' ? [value] : value
  if (!Array.isArray(values) || !values.every(id => typeof id === 'string')) return
  const ids = [...new Set(values as string[])]
  const added = ids.filter(id => !selected.value.includes(id))
  if (added.some(id => !props.options.some(option => option.id === id && !option.disabled))) return
  if (props.multiple) emit('update:modelValue', ids)
  else {
    emit('update:modelValue', added.at(-1) ?? ids[0] ?? null)
    open.value = false
  }
}
function remove(id: string) {
  if (!locked.value) emit('update:modelValue', props.multiple ? selected.value.filter(value => value !== id) : null)
}
function preventFormSubmit(event: KeyboardEvent) {
  if (!event.isComposing) event.preventDefault()
}
</script>

<template>
  <div class="ui-field ui-record-picker" :aria-busy="busy || undefined">
    <label :for="id">{{ label }}</label>
    <!-- No portal: popup, focus and CSS tokens remain inside the owning UiSurface/dialog. -->
    <ComboboxRoot :model-value="multiple ? selected : selected[0] ?? null" :multiple="multiple" :open="open" :disabled="locked" ignore-filter
      :reset-search-term-on-blur="false" :reset-search-term-on-select="false" open-on-focus open-on-click
      @update:model-value="update" @update:open="open = !locked && $event">
      <ComboboxAnchor class="ui-picker-anchor">
        <ComboboxInput :id="id" v-model="search" class="ui-control" :disabled="locked" :maxlength="256"
          :placeholder="placeholder" :aria-invalid="Boolean(error) || undefined" :aria-describedby="describedBy" @keydown.enter="preventFormSubmit" />
        <ComboboxTrigger class="ui-button ui-button--quiet" :disabled="locked" :aria-label="toggleLabel"><span aria-hidden="true">⌄</span></ComboboxTrigger>
      </ComboboxAnchor>
      <ComboboxContent class="ui-picker-content" position="inline" :aria-label="label">
        <p v-if="!choices.length" class="ui-picker-empty" role="status">{{ emptyLabel }}</p>
        <ComboboxItem v-for="option in choices" :key="option.id" :value="option.id" :disabled="option.disabled" class="ui-picker-option">
          <span class="ui-picker-option-copy"><span>{{ option.label }}</span><small v-if="option.description" class="ui-help">{{ option.description }}</small></span>
          <ComboboxItemIndicator aria-hidden="true">✓</ComboboxItemIndicator>
        </ComboboxItem>
      </ComboboxContent>
    </ComboboxRoot>
    <small v-if="description" :id="`${id}-help`" class="ui-help">{{ description }}</small>
    <small v-if="error" :id="`${id}-error`" class="ui-field-error">{{ error }}</small>
    <small v-if="busy" :id="`${id}-loading`" class="ui-help" role="status">{{ loadingLabel }}</small>
    <ul v-if="selected.length" class="ui-picker-selection" :aria-label="selectedLabel">
      <li v-for="key in selected" :key="key" class="ui-picker-chip">
        <span>{{ labels.get(key) ?? unavailableLabel }}</span>
        <UiButton variant="quiet" :disabled="locked" :aria-label="`${removeLabel}: ${labels.get(key) ?? unavailableLabel}`" @click="remove(key)"><span aria-hidden="true">×</span></UiButton>
      </li>
    </ul>
  </div>
</template>
