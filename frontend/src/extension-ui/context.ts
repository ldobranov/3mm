import { computed, inject, type InjectionKey, type Ref } from 'vue'

// Symbol.for keeps this boundary identical in the separately emitted UI module.
// The host provides presentation only, never stores, credentials or actions.
export interface ExtensionUiAppearance {
  readonly button: 'solid' | 'outline'
  readonly card: 'bordered' | 'raised'
}
export const extensionUiKey = Symbol.for('3mm.extension-ui.v1') as InjectionKey<Readonly<Ref<ExtensionUiAppearance>>>
const fallback = Object.freeze({ button: 'solid', card: 'bordered' } as const)

export function useExtensionUiAppearance() {
  const appearance = inject(extensionUiKey, undefined)
  return computed(() => appearance?.value ?? fallback)
}
