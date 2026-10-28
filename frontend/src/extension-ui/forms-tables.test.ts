import { afterEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import { UiField, UiForm, UiState, UiSurface, UiTable, UiButton } from './v1'
import { extensionUiKey, type ExtensionUiAppearance } from './context'

const mounted: Array<{ unmount: () => void }> = []
afterEach(() => mounted.splice(0).forEach(wrapper => wrapper.unmount()))

describe('public form and table consumers', () => {
  it('keeps a local draft across host appearance and language changes, without submitting it', async () => {
    const appearance = ref<ExtensionUiAppearance>({ button: 'solid', card: 'bordered' })
    const draft = ref(''), title = ref('Name')
    const consumer = defineComponent({ setup() {
      return () => h(UiSurface, null, () => h(UiForm, null, () => [
        h(UiField, { id: 'draft', label: title.value, modelValue: draft.value,
          'onUpdate:modelValue': (value: string | boolean) => { draft.value = String(value) } }),
        h(UiButton, { type: 'submit' }, () => 'Save'),
      ]))
    } })
    const wrapper = mount(consumer, { global: { provide: { [extensionUiKey as symbol]: appearance } } }); mounted.push(wrapper)
    const input = wrapper.get('input')
    await input.setValue('Unsaved draft')
    // The host changes presentation; the component does not own a theme or locale store.
    appearance.value = { button: 'outline', card: 'raised' }
    title.value = 'Име'
    await wrapper.vm.$nextTick()
    expect(wrapper.get('input').element).toBe(input.element)
    expect(wrapper.get('label').text()).toBe('Име')
    expect(wrapper.findComponent(UiSurface).attributes()).toMatchObject({ 'data-button': 'outline', 'data-card': 'raised' })
    expect((input.element as HTMLInputElement).value).toBe('Unsaved draft')
    expect(wrapper.findComponent(UiForm).emitted('submit')).toBeUndefined()
  })

  it('uses labelled native validation and prevents submission while busy', async () => {
    const wrapper = mount(UiForm, { slots: { default: () => [
      h(UiField, { id: 'name', label: 'Name', required: true }), h(UiButton, { type: 'submit' }, () => 'Save'),
    ] } }); mounted.push(wrapper)
    expect(wrapper.get('label').attributes('for')).toBe(wrapper.get('input').attributes('id'))
    await wrapper.trigger('submit')
    expect(wrapper.emitted('submit')).toBeUndefined()
    await wrapper.get('input').setValue('Name'); await wrapper.trigger('submit')
    expect(wrapper.emitted('submit')).toHaveLength(1)
    await wrapper.setProps({ busy: true }); await wrapper.trigger('submit')
    expect(wrapper.get('fieldset').attributes('disabled')).toBeDefined()
    expect(wrapper.attributes('aria-busy')).toBe('true')
    expect(wrapper.emitted('submit')).toHaveLength(1)
  })

  it('connects validation and help text, escapes untrusted content and preserves a numeric draft', async () => {
    const wrapper = mount(UiField, { props: { id: 'amount', label: 'Amount', type: 'number', modelValue: '',
      description: 'Whole units', error: '<img src=x onerror=alert(1)>' } }); mounted.push(wrapper)
    expect(wrapper.get('input').attributes()).toMatchObject({ 'aria-invalid': 'true', 'aria-describedby': 'amount-help amount-error' })
    expect(wrapper.get('#amount-help').text()).toBe('Whole units')
    expect(wrapper.find('img').exists()).toBe(false)
    await wrapper.get('input').setValue('12')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['12'])
    await wrapper.get('input').setValue('')
    expect(wrapper.emitted('update:modelValue')?.[1]).toEqual(['']) // No premature conversion to zero.
    await wrapper.setProps({ error: undefined })
    expect(wrapper.get('input').attributes('aria-invalid')).toBeUndefined()
    expect(wrapper.get('input').attributes('aria-describedby')).toBe('amount-help')
  })

  it.each(['checkbox', 'select', 'textarea'] as const)('supports a controlled %s field without application actions', async type => {
    const wrapper = mount(UiField, { props: { id: 'field', label: 'Field', type,
      options: [{ value: 'a', label: 'First' }, { value: 'b', label: 'Second' }] } }); mounted.push(wrapper)
    const control = wrapper.get(type === 'checkbox' ? 'input' : type)
    await control.setValue(type === 'checkbox' ? true : type === 'select' ? 'b' : 'Draft')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([type === 'checkbox' ? true : type === 'select' ? 'b' : 'Draft'])
    await wrapper.setProps({ readonly: true })
    expect(control.attributes(type === 'textarea' ? 'readonly' : 'disabled')).toBeDefined()
  })

  it('retains row identity on reordering and emits only explicit pagination intents', async () => {
    const rows = [{ id: 'a', value: '<script>private()</script>' }, { id: 'b', value: 'Second' }]
    const wrapper = mount(UiTable, { props: { rows, columns: [{ key: 'value', label: 'Value' }],
      rowKey: (row: object) => String(Reflect.get(row, 'id')), caption: 'Records', emptyLabel: 'No records',
      hasNext: true, nextLabel: 'Следваща страница', paginationLabel: 'Страници' } }); mounted.push(wrapper)
    const first = wrapper.findAll('tbody tr')[0]!.element
    expect(wrapper.get('caption').text()).toBe('Records')
    expect(wrapper.get('th').attributes('scope')).toBe('col')
    expect(wrapper.get('[role=region]').attributes('tabindex')).toBe('0')
    expect(wrapper.find('script').exists()).toBe(false)
    await wrapper.setProps({ rows: [...rows].reverse(), hasPrevious: true })
    expect(wrapper.findAll('tbody tr')[1]!.element).toBe(first)
    expect(wrapper.emitted('next')).toBeUndefined()
    await wrapper.findAll('nav button')[1]!.trigger('click')
    expect(wrapper.emitted('next')).toHaveLength(1)
    await wrapper.setProps({ busy: true })
    await wrapper.findAll('nav button')[1]!.trigger('click')
    expect(wrapper.emitted('next')).toHaveLength(1)
    expect(wrapper.emitted('previous')).toBeUndefined()
  })

  it.each(['loading', 'error', 'empty'] as const)('announces %s without automatically retrying an action', kind => {
    const wrapper = mount(UiState, { props: { kind, message: 'Състояние' } }); mounted.push(wrapper)
    expect(wrapper.attributes('role')).toBe(kind === 'error' ? 'alert' : 'status')
    expect(wrapper.attributes('aria-busy')).toBe(kind === 'loading' ? 'true' : undefined)
    expect(wrapper.text()).toBe('Състояние')
    expect(wrapper.emitted()).toEqual({})
  })
})
