import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import UiButton from './UiButton.vue'
import UiDialog from './UiDialog.vue'

const nativeMethods = ['showModal', 'close'].map(name => ({ name, descriptor: Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, name) }))
afterEach(() => {
  vi.restoreAllMocks(); document.body.innerHTML = ''
  for (const { name, descriptor } of nativeMethods) {
    if (descriptor) Object.defineProperty(HTMLDialogElement.prototype, name, descriptor)
    else Reflect.deleteProperty(HTMLDialogElement.prototype, name)
  }
})
describe('shared UI primitives', () => {
  it('preserves button action, type, attrs and loading/disabled semantics', async () => {
    const click = vi.fn()
    const button = mount(UiButton, { props: { variant: 'danger' }, attrs: { onClick: click, 'aria-label': 'Delete' }, slots: { default: 'Delete' } })
    expect(button.attributes('type')).toBe('button')
    expect(button.classes()).toContain('ui-button--danger')
    await button.trigger('click'); expect(click).toHaveBeenCalledTimes(1)
    await button.setProps({ loading: true, type: 'submit' })
    expect(button.attributes('disabled')).toBeDefined()
    expect(button.attributes('aria-busy')).toBe('true')
    expect(button.attributes('type')).toBe('submit')
    await button.trigger('click'); expect(click).toHaveBeenCalledTimes(1)
    button.unmount()
  })
  it('uses modal dialog, restores opener focus and emits Escape cancellation', async () => {
    // jsdom does not implement native dialog behavior; browser review verifies it.
    Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value: function(this: HTMLDialogElement) { this.open = true } })
    Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value: function(this: HTMLDialogElement) { this.open = false; this.dispatchEvent(new Event('close')) } })
    const opener = document.createElement('button'); document.body.append(opener); opener.focus()
    const dialog = mount(UiDialog, { attachTo: document.body, props: { open: false, title: 'Test title', closeLabel: 'Close' }, slots: { default: '<input autofocus />' } })
    await dialog.setProps({ open: true }); await nextTick()
    expect(dialog.find('dialog').element.open).toBe(true)
    expect(dialog.attributes('aria-labelledby')).toBe(dialog.find('h2').attributes('id'))
    const controls = [dialog.find('button').element, dialog.find('input').element]
    for (const control of controls) vi.spyOn(control, 'getClientRects').mockReturnValue({ length: 1 } as DOMRectList)
    controls[1]!.focus()
    await dialog.find('input').trigger('keydown', { key: 'Tab' })
    expect(document.activeElement).toBe(controls[0])
    await dialog.find('button').trigger('keydown', { key: 'Tab', shiftKey: true })
    expect(document.activeElement).toBe(controls[1])
    await dialog.trigger('cancel')
    expect(dialog.emitted('update:open')).toEqual([[false]])
    await dialog.setProps({ open: false }); await nextTick()
    expect(document.activeElement).toBe(opener)
    dialog.unmount()
  })
})
