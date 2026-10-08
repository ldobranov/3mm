import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
const fetchWidgets = vi.hoisted(() => vi.fn())
vi.mock('@/stores/widgets', () => ({ useWidgetsStore: () => ({ fetchAvailableExtensions: fetchWidgets }) }))
vi.mock('@/utils/i18n', () => ({ useI18n: () => ({ t: (_key: string, fallback: string) => fallback }) }))
import WidgetPalette from './WidgetPalette.vue'

describe('Dynamic widget palette', () => {
  beforeEach(() => { vi.clearAllMocks() })
  it('retains legacy and compiled type selection and drag payloads', async () => {
    fetchWidgets.mockResolvedValue([{ id: 7, name: 'Generic widget' }, { id: 'compiled', name: 'Other provider', widget_type: 'compiled:org.reference:1.0.0:widget' }])
    const wrapper = mount(WidgetPalette)
    await flushPromises()
    const buttons = wrapper.findAll('button')
    await buttons[0].trigger('click')
    await buttons[1].trigger('click')
    expect(wrapper.emitted('add')).toEqual([['extension:7'], ['compiled:org.reference:1.0.0:widget']])
    expect(buttons[0].attributes('type')).toBe('button')
    const dataTransfer = { effectAllowed: '', setData: vi.fn() }
    await wrapper.findAll('[draggable="true"]')[1].trigger('dragstart', { dataTransfer })
    expect(dataTransfer.setData).toHaveBeenCalledWith('text/plain', 'compiled:org.reference:1.0.0:widget')
    expect(dataTransfer.effectAllowed).toBe('copyMove')
    wrapper.unmount()
  })
  it('distinguishes loading, empty catalog and failure', async () => {
    let resolve!: (value: unknown[]) => void
    fetchWidgets.mockReturnValueOnce(new Promise(r => { resolve = r }))
    const wrapper = mount(WidgetPalette)
    expect(wrapper.find('[role="status"]').text()).toContain('Loading')
    resolve([])
    await flushPromises()
    expect(wrapper.find('[role="status"]').text()).toContain('No widget extensions')
    wrapper.unmount()
    fetchWidgets.mockRejectedValueOnce(new Error('Offline'))
    const failure = mount(WidgetPalette)
    await flushPromises()
    expect(failure.find('[role="alert"]').text()).toContain('Offline')
    failure.unmount()
  })
})
