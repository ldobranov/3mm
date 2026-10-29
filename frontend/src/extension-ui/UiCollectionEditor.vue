<script setup lang="ts" generic="Item extends object">
import { computed, nextTick, ref } from 'vue'
import UiButton from '../components/ui/UiButton.vue'
import UiState from './UiState.vue'

const props = withDefaults(defineProps<{
  title: string; modelValue: ReadonlyArray<Item>; itemKey: (item: Item) => string; itemLabel: (item: Item) => string
  disabled?: boolean; minItems?: number; maxItems?: number
  addLabel?: string; removeLabel?: string; moveUpLabel?: string; moveDownLabel?: string; emptyLabel?: string; invalidKeysLabel?: string
}>(), {
  disabled: false, minItems: 0, maxItems: Infinity, addLabel: 'Add item', removeLabel: 'Remove',
  moveUpLabel: 'Move up', moveDownLabel: 'Move down', emptyLabel: 'No items',
  invalidKeysLabel: 'Every item needs a unique, non-empty stable key.',
})
const emit = defineEmits<{ 'update:modelValue': [value: Item[]]; add: [] }>()
const root = ref<HTMLElement>()
const validKeys = computed(() => {
  const keys = props.modelValue.map(props.itemKey)
  return keys.every(key => typeof key === 'string' && key.length > 0) && new Set(keys).size === keys.length
})
const locked = computed(() => props.disabled || !validKeys.value)

async function move(key: string, step: number, event: Event) {
  if (locked.value) return
  const index = props.modelValue.findIndex(item => props.itemKey(item) === key), target = index + step
  if (index < 0 || target < 0 || target >= props.modelValue.length) return
  const control = event.currentTarget as HTMLElement
  const items = [...props.modelValue]
  const [item] = items.splice(index, 1)
  items.splice(target, 0, item!)
  emit('update:modelValue', items)
  await nextTick()
  if (control.isConnected && !control.matches(':disabled')) control.focus()
  else [...(root.value?.querySelectorAll<HTMLElement>('[data-item-key]') ?? [])]
    .find(element => element.dataset.itemKey === key)?.querySelector<HTMLButtonElement>('button:not(:disabled)')?.focus()
}
async function remove(key: string) {
  if (locked.value || props.modelValue.length <= props.minItems) return
  const index = props.modelValue.findIndex(item => props.itemKey(item) === key)
  if (index < 0) return
  const items = props.modelValue.filter(item => props.itemKey(item) !== key)
  const nextKey = items[Math.min(index, items.length - 1)]
  emit('update:modelValue', items)
  await nextTick()
  const row = nextKey && [...(root.value?.querySelectorAll<HTMLElement>('[data-item-key]') ?? [])].find(element => element.dataset.itemKey === props.itemKey(nextKey))
  ;(row ? row.querySelector<HTMLButtonElement>('button:not(:disabled)') : root.value?.querySelector<HTMLButtonElement>('[data-collection-add]'))?.focus()
}
</script>

<template>
  <section ref="root" class="ui-collection ui-stack" :aria-label="title">
    <div class="ui-collection-heading"><h2>{{ title }}</h2>
      <UiButton data-collection-add :disabled="locked || modelValue.length >= maxItems" @click="!locked && modelValue.length < maxItems && emit('add')">{{ addLabel }}</UiButton>
    </div>
    <UiState v-if="!validKeys" kind="error" :message="invalidKeysLabel" />
    <UiState v-else-if="!modelValue.length" kind="empty" :message="emptyLabel" />
    <ol v-else class="ui-collection-list ui-stack">
      <li v-for="(item, index) in modelValue" :key="itemKey(item)" :data-item-key="itemKey(item)" class="ui-section ui-stack">
        <div class="ui-collection-heading">
          <h3>{{ itemLabel(item) }}</h3>
          <div class="ui-row">
            <UiButton variant="quiet" :disabled="locked || index === 0" :aria-label="`${moveUpLabel}: ${itemLabel(item)}`" @click="move(itemKey(item), -1, $event)"><span aria-hidden="true">↑</span></UiButton>
            <UiButton variant="quiet" :disabled="locked || index === modelValue.length - 1" :aria-label="`${moveDownLabel}: ${itemLabel(item)}`" @click="move(itemKey(item), 1, $event)"><span aria-hidden="true">↓</span></UiButton>
            <UiButton variant="quiet" :disabled="locked || modelValue.length <= minItems" :aria-label="`${removeLabel}: ${itemLabel(item)}`" @click="remove(itemKey(item))">{{ removeLabel }}</UiButton>
          </div>
        </div>
        <slot :item="item" :index="index" :disabled="locked" />
      </li>
    </ol>
  </section>
</template>
