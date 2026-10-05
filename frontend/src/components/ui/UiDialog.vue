<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, useId, watch } from 'vue'
import UiButton from './UiButton.vue'

const props = defineProps<{ open: boolean; title: string; closeLabel: string }>()
const emit = defineEmits<{ 'update:open': [open: boolean] }>()
const element = ref<HTMLDialogElement>()
const titleId = useId()
let returnFocus: HTMLElement | null = null
const restoreFocus = () => {
  if (returnFocus?.isConnected) returnFocus.focus()
  returnFocus = null
}
const closed = () => { emit('update:open', false); restoreFocus() }
const containTab = (event: KeyboardEvent) => {
  if (event.key !== 'Tab' || !element.value?.open) return
  const controls = Array.from(element.value.querySelectorAll<HTMLElement>(
    'button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex="0"]',
  )).filter(control => control.getClientRects().length > 0)
  const first = controls[0], last = controls[controls.length - 1]
  if (!first || !last) { event.preventDefault(); element.value.focus(); return }
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
}
watch(() => props.open, async open => {
  await nextTick()
  const dialog = element.value
  if (!dialog) return
  if (open && !dialog.open) {
    returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    dialog.showModal() // Native focus containment, inert background and Escape.
  } else if (!open && dialog.open) dialog.close()
}, { immediate: true })
onBeforeUnmount(() => { if (element.value?.open) element.value.close(); restoreFocus() })
</script>

<template>
  <dialog ref="element" class="ui-dialog" tabindex="-1" :aria-labelledby="titleId" @close="closed" @keydown="containTab"
    @cancel.prevent="emit('update:open', false)">
    <div class="ui-dialog-heading">
      <h2 :id="titleId">{{ title }}</h2>
      <UiButton variant="quiet" :aria-label="closeLabel" @click="emit('update:open', false)">×</UiButton>
    </div>
    <slot />
    <div v-if="$slots.actions" class="ui-dialog-actions"><slot name="actions" /></div>
  </dialog>
</template>
