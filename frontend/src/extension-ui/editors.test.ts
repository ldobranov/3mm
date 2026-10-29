import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import { UiCollectionEditor, UiEditorForm, UiField, UiRecordPicker, UiSurface } from './v1'
import EditingReference from '../../../modules/ui-reference/source/frontend/EditingReference.vue'

const mounted: Array<{ unmount: () => void }> = []
const scrollDescriptor = Object.getOwnPropertyDescriptor(Element.prototype, 'scrollIntoView')
beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
  Object.defineProperty(Element.prototype, 'scrollIntoView', { configurable: true, value: vi.fn() })
})
afterEach(() => {
  mounted.splice(0).forEach(wrapper => wrapper.unmount())
  if (scrollDescriptor) Object.defineProperty(Element.prototype, 'scrollIntoView', scrollDescriptor)
  else Reflect.deleteProperty(Element.prototype, 'scrollIntoView')
  vi.unstubAllGlobals()
})

describe('shared editor form', () => {
  it('checks native validity and emits only an explicit save or discard intent', async () => {
    const wrapper = mount(UiEditorForm, { props: { title: 'Settings', dirty: true },
      slots: { default: () => h(UiField, { id: 'editor-name', label: 'Name', required: true }) } }); mounted.push(wrapper)
    await wrapper.trigger('submit')
    expect(wrapper.emitted('save')).toBeUndefined()
    await wrapper.get('input').setValue('Draft'); await wrapper.trigger('submit')
    expect(wrapper.emitted('save')).toHaveLength(1)
    await wrapper.findAll('button')[0]!.trigger('click')
    expect(wrapper.emitted('cancel')).toHaveLength(1)
  })

  it.each(['busy', 'disabled', 'invalid', 'clean', 'unconfirmed', 'conflict'] as const)('does not save a %s editor', async reason => {
    const wrapper = mount(UiEditorForm, { props: { title: 'Settings', dirty: reason !== 'clean',
      valid: reason !== 'invalid', busy: reason === 'busy', disabled: reason === 'disabled',
      state: reason === 'unconfirmed' || reason === 'conflict' ? reason : 'idle' },
      slots: { default: '<input value="Draft" />' } }); mounted.push(wrapper)
    await wrapper.trigger('submit')
    expect(wrapper.emitted('save')).toBeUndefined()
    expect(wrapper.get('button[type=submit]').attributes('disabled')).toBeDefined()
    if (reason === 'unconfirmed' || reason === 'conflict') {
      await wrapper.findAll('button')[0]!.trigger('click')
      expect(wrapper.emitted('cancel')).toBeUndefined()
      expect(wrapper.get('[role=alert]').text()).not.toBe('')
    }
  })

  it('preserves the draft and never resubmits when labels or an unresolved state change', async () => {
    const wrapper = mount(UiEditorForm, { props: { title: 'Settings', dirty: true }, slots: { default: '<input />', recovery: '<button type="button">Read original outcome</button>' } }); mounted.push(wrapper)
    const input = wrapper.get('input'); await input.setValue('Keep this draft')
    await wrapper.setProps({ title: 'Настройки', state: 'unconfirmed', unconfirmedLabel: 'Провери първоначалния резултат.' })
    expect(wrapper.get('fieldset').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[role=alert]').text()).toBe('Провери първоначалния резултат.')
    expect(wrapper.findAll('button').find(button => button.text() === 'Read original outcome')!.attributes('disabled')).toBeUndefined()
    await wrapper.setProps({ state: 'idle' })
    expect(wrapper.get('input').element).toBe(input.element)
    expect(input.element).toHaveProperty('value', 'Keep this draft')
    expect(wrapper.emitted('save')).toBeUndefined()
    expect(wrapper.emitted('cancel')).toBeUndefined()
  })
})

const options = [{ id: 'a', label: 'Alpha' }, { id: 'b', label: 'Beta' }, { id: 'c', label: 'Unavailable', disabled: true }]
describe('record picker using the real Reka combobox', () => {
  it('filters local records, supports keyboard choice and keeps the popup in its surface', async () => {
    const wrapper = mount(UiSurface, { attachTo: document.body, slots: { default: () => h(UiRecordPicker, { id: 'records', label: 'Records', options, modelValue: null }) } }); mounted.push(wrapper)
    const picker = wrapper.findComponent(UiRecordPicker), input = picker.get('input')
    expect(picker.get('label').attributes('for')).toBe(input.attributes('id'))
    await input.setValue('Beta'); await flushPromises()
    expect(picker.findAll('[role=option]').map(option => option.text())).toEqual(['Beta'])
    expect(wrapper.element.contains(picker.get('[role=listbox]').element)).toBe(true)
    await input.trigger('keydown', { key: 'ArrowDown' }); await flushPromises()
    await input.trigger('keydown', { key: 'Enter' }); await flushPromises()
    expect(picker.emitted('update:modelValue')).toEqual([['b']])
    expect(picker.find('[role=listbox]').exists()).toBe(false)
  })

  it('supports multiple stable IDs and refuses disabled choices', async () => {
    const wrapper = mount(UiRecordPicker, { attachTo: document.body, props: { id: 'many', label: 'Records', options, multiple: true, modelValue: ['a'] } }); mounted.push(wrapper)
    await wrapper.get('input').trigger('focus'); await flushPromises()
    const rows = wrapper.findAll('[role=option]')
    await rows.find(row => row.text() === 'Unavailable')!.trigger('click')
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    await rows.find(row => row.text() === 'Beta')!.trigger('click')
    expect(wrapper.emitted('update:modelValue')).toEqual([[['a', 'b']]])
  })

  it('keeps selections across external result pages, uses supplied labels and removes only the chosen ID', async () => {
    const wrapper = mount(UiRecordPicker, { attachTo: document.body, props: { id: 'remote', label: 'Articles', options: [options[1]!], selectedOptions: [options[0]!], modelValue: ['a', 'missing'], multiple: true, filterMode: 'external', search: 'server query' } }); mounted.push(wrapper)
    await wrapper.get('input').trigger('focus'); await flushPromises()
    expect(wrapper.findAll('[role=option]').map(row => row.text())).toEqual(['Beta'])
    expect(wrapper.get('.ui-picker-selection').text()).toContain('Alpha')
    expect(wrapper.get('.ui-picker-selection').text()).toContain('Unavailable record')
    await wrapper.setProps({ options: [] })
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    expect(wrapper.emitted('update:search')).toBeUndefined()
    await wrapper.get('.ui-picker-selection button').trigger('click')
    expect(wrapper.emitted('update:modelValue')).toEqual([[['missing']]])
  })

  it.each(['disabled', 'busy'] as const)('closes and blocks all selection controls while %s', async flag => {
    const wrapper = mount(UiRecordPicker, { attachTo: document.body, props: { id: 'locked', label: 'Records', options, modelValue: 'a' } }); mounted.push(wrapper)
    await wrapper.get('input').trigger('focus'); await flushPromises()
    await wrapper.setProps({ [flag]: true }); await flushPromises()
    expect(wrapper.get('input').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[role=listbox]').exists()).toBe(false)
    await wrapper.get('.ui-picker-selection button').trigger('click')
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  })

  it('escapes record text, labels errors, and Enter in an empty search never submits a parent form', async () => {
    const submit = vi.fn()
    const wrapper = mount(defineComponent({ setup: () => () => h('form', { onSubmit: submit }, [h(UiRecordPicker, {
      id: 'escape', label: 'Search', modelValue: null, options: [{ id: 'x', label: '<img src=x onerror=alert(1)>' }], error: 'Unavailable', description: 'Choose one',
    })]) }), { attachTo: document.body }); mounted.push(wrapper)
    const input = wrapper.get('input')
    expect(input.attributes()).toMatchObject({ 'aria-invalid': 'true', 'aria-describedby': 'escape-help escape-error' })
    await input.setValue('No matches'); await flushPromises()
    const key = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true })
    input.element.dispatchEvent(key)
    expect(key.defaultPrevented).toBe(true)
    expect(submit).not.toHaveBeenCalled()
    expect(wrapper.find('img').exists()).toBe(false)
  })
})

const items = [{ id: 'a', label: 'First' }, { id: 'b', label: 'Second' }]
const itemKey = (item: object) => String(Reflect.get(item, 'id'))
const itemLabel = (item: object) => String(Reflect.get(item, 'label'))
describe('draft collection editor', () => {
  it('reorders immutable arrays using stable keys and retains the edited input instance', async () => {
    const draft = ref(items.map(item => ({ ...item })))
    const wrapper = mount(defineComponent({ setup: () => () => h(UiCollectionEditor, { title: 'Panels', modelValue: draft.value, itemKey, itemLabel,
      'onUpdate:modelValue': (value: object[]) => { draft.value = value as typeof items } }, { default: ({ item }: { item: typeof items[number] }) => h('input', {
        value: item.label, onInput: (event: Event) => { item.label = (event.target as HTMLInputElement).value },
      }) }) }), { attachTo: document.body }); mounted.push(wrapper)
    const first = wrapper.get('[data-item-key=a] input')
    await first.setValue('Unsaved panel title')
    await wrapper.get('[data-item-key=a] button[aria-label^="Move down:"]').trigger('click'); await flushPromises()
    expect(draft.value.map(item => item.id)).toEqual(['b', 'a'])
    expect(items.map(item => item.id)).toEqual(['a', 'b'])
    expect(wrapper.get('[data-item-key=a] input').element).toBe(first.element)
    expect(first.element).toHaveProperty('value', 'Unsaved panel title')
    expect(document.activeElement?.closest('[data-item-key]')?.getAttribute('data-item-key')).toBe('a')
  })

  it('emits add/remove draft intents and respects collection limits', async () => {
    const wrapper = mount(UiCollectionEditor, { props: { title: 'Panels', modelValue: items, itemKey, itemLabel, minItems: 1, maxItems: 2 } }); mounted.push(wrapper)
    expect(wrapper.get('[data-collection-add]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-item-key=b] button[aria-label="Remove: Second"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')).toEqual([[[items[0]]]])
    expect(items).toHaveLength(2)
    await wrapper.setProps({ modelValue: [items[0]!] })
    expect(wrapper.get('[data-item-key=a] button[aria-label="Remove: First"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-collection-add]').trigger('click')
    expect(wrapper.emitted('add')).toHaveLength(1)
  })

  it('refuses duplicate keys and never fixes or discards the supplied draft automatically', async () => {
    const duplicate = [items[0]!, items[0]!]
    const wrapper = mount(UiCollectionEditor, { props: { title: 'Panels', modelValue: duplicate, itemKey, itemLabel } }); mounted.push(wrapper)
    expect(wrapper.get('[role=alert]').text()).toContain('unique')
    expect(wrapper.find('[data-item-key]').exists()).toBe(false)
    expect(wrapper.get('[data-collection-add]').attributes('disabled')).toBeDefined()
    expect(wrapper.emitted()).toEqual({})
    expect(duplicate).toHaveLength(2)
  })

  it('disables draft actions without emitting updates on label, order or permission changes', async () => {
    const wrapper = mount(UiCollectionEditor, { props: { title: 'Panels', modelValue: items, itemKey, itemLabel } }); mounted.push(wrapper)
    await wrapper.setProps({ disabled: true, title: 'Панели', modelValue: [...items].reverse() })
    for (const button of wrapper.findAll('button')) {
      expect(button.attributes('disabled')).toBeDefined(); await button.trigger('click')
    }
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    expect(wrapper.emitted('add')).toBeUndefined()
  })
})

describe('neutral public-import editing consumer', () => {
  it('edits, reorders, saves and discards a draft while language changes preserve field identity', async () => {
    const wrapper = mount(EditingReference, { props: { locale: 'en' } }); mounted.push(wrapper)
    const inputs = wrapper.findAll('input').filter(input => input.attributes('role') !== 'combobox')
    const name = inputs[0]!
    await name.setValue('Edited panel')
    await wrapper.setProps({ locale: 'bg' })
    expect(wrapper.findAll('input').some(input => input.element === name.element)).toBe(true)
    expect(name.element).toHaveProperty('value', 'Edited panel')
    expect(wrapper.get('h2').text()).toContain('редактиране')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.findComponent(UiEditorForm).props('dirty')).toBe(false)
    await name.setValue('Discard this')
    await wrapper.findAll('button').find(button => button.text() === 'Отхвърли локалната чернова')!.trigger('click')
    expect(wrapper.findAll('input').some(input => (input.element as HTMLInputElement).value === 'Edited panel')).toBe(true)
    expect(wrapper.findComponent(UiEditorForm).props('dirty')).toBe(false)
  })
})
