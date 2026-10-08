import { createPinia } from 'pinia'
import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() }))
vi.mock('@/utils/dynamic-http', () => ({ default: http }))
vi.mock('vue-router', () => ({ useRoute: () => ({ params: { id: '2' } }) }))
vi.mock('@/stores/settings', () => ({ useSettingsStore: () => ({ uiDesign: { components: { card: 'raised', button: 'outline' } } }) }))
vi.mock('@/utils/i18n', () => ({ useI18n: () => ({ t: (_key: string, fallback: string) => fallback }) }))
import DisplayEditor from './DisplayEditor.vue'
import { useWidgetsStore } from '@/stores/widgets'

const board = { id: 2, title: 'Shared board', slug: 'shared', is_public: true, owner_username: 'owner' }
const initial = [1, 2].map(id => ({ id, display_id: 2, type: `extension:${id}`, config: { title: `Widget ${id}` }, x: 0, y: 0, width: 3, height: 2, z_index: 1 }))
const nativeMethods = ['showModal', 'close'].map(name => ({ name, descriptor: Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, name) }))
const mounted: Array<ReturnType<typeof mount>> = []
const canvas = defineComponent({ name: 'DisplayCanvas', props: ['widgets', 'editable'], emits: ['editWidget', 'deleteWidget', 'layoutChanged', 'addFromDrop'], template: '<div class="test-canvas" />' })
const inspector = defineComponent({ name: 'EditorPanel', props: ['modelValue', 'widget', 'saving', 'error'], emits: ['preview', 'save', 'cancel', 'update:modelValue'], template: '<div class="test-inspector">{{ error }}</div>' })
const palette = defineComponent({ name: 'WidgetPalette', emits: ['add'], template: '<div />' })

async function setup() {
  const pinia = createPinia()
  const wrapper = mount(DisplayEditor, { global: { plugins: [pinia], stubs: {
    DisplayCanvas: canvas, EditorPanel: inspector, WidgetPalette: palette,
    RouterLink: { props: ['to'], template: '<a :data-destination="JSON.stringify(to)"><slot /></a>' }
  } } })
  mounted.push(wrapper)
  await flushPromises()
  return { wrapper, store: useWidgetsStore(pinia) }
}

describe('Display editor workspace', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value: function(this: HTMLDialogElement) { this.open = true } })
    Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value: function(this: HTMLDialogElement) { this.open = false; this.dispatchEvent(new Event('close')) } })
    http.get.mockImplementation(async (url: string) => ({ data: url.endsWith('/widgets') ? { items: structuredClone(initial) } : board }))
    http.patch.mockImplementation(async (url: string, payload: object) => ({ data: url.startsWith('/api/widgets') ? { ...initial[0], ...payload } : { ...board, ...payload } }))
    http.post.mockResolvedValue({ data: {} })
    http.delete.mockResolvedValue({ data: {} })
  })
  afterEach(() => {
    mounted.splice(0).forEach(wrapper => wrapper.unmount())
    for (const { name, descriptor } of nativeMethods) {
      if (descriptor) Object.defineProperty(HTMLDialogElement.prototype, name, descriptor)
      else Reflect.deleteProperty(HTMLDialogElement.prototype, name)
    }
  })
  it('loads the same display/widget endpoints and retains owner-aware preview', async () => {
    const { wrapper } = await setup()
    expect(http.get.mock.calls.map(call => call[0])).toEqual(['/api/displays/2', '/api/displays/2/widgets'])
    expect(JSON.parse(wrapper.find('a').attributes('data-destination')!)).toEqual({ name: 'PublicDisplay', params: { username: 'owner', slug: 'shared' } })
    expect(wrapper.attributes('data-card')).toBe('raised')
    expect(wrapper.attributes('data-button')).toBe('outline')
    expect(wrapper.findAll('[style]')).toHaveLength(0)
    expect(wrapper.findAll('.editor-workspace > section')).toHaveLength(3)
    expect(wrapper.find('.widget-selection select').findAll('option')).toHaveLength(3)
  })
  it('previews locally and restores drafts before switching or cancelling', async () => {
    const { wrapper, store } = await setup()
    const panel = wrapper.findComponent(inspector)
    await wrapper.find('.widget-selection select').setValue('1')
    panel.vm.$emit('preview', { id: 1, config: { title: 'Unsaved' } })
    await flushPromises()
    expect(store.list(2)[0].config.title).toBe('Unsaved')
    await wrapper.find('.widget-selection select').setValue('2')
    expect(store.list(2)[0].config.title).toBe('Widget 1')
    panel.vm.$emit('preview', { id: 2, config: { title: 'Temporary' } })
    panel.vm.$emit('cancel', 2)
    panel.vm.$emit('update:modelValue', false)
    await flushPromises()
    expect(store.list(2)[1].config.title).toBe('Widget 2')
    expect(panel.props('modelValue')).toBe(false)
    expect(http.patch).not.toHaveBeenCalled()
  })
  it('does not replace the cancel snapshot when reselecting the same widget', async () => {
    const { wrapper, store } = await setup()
    const panel = wrapper.findComponent(inspector)
    wrapper.findComponent(canvas).vm.$emit('editWidget', 1)
    panel.vm.$emit('preview', { id: 1, config: { title: 'Draft' } })
    wrapper.findComponent(canvas).vm.$emit('editWidget', 1)
    panel.vm.$emit('cancel', 1)
    expect(store.list(2)[0].config.title).toBe('Widget 1')
  })
  it('closes only after save succeeds and keeps failed drafts available', async () => {
    const { wrapper } = await setup()
    await wrapper.find('.widget-selection select').setValue('1')
    const panel = wrapper.findComponent(inspector)
    http.patch.mockRejectedValueOnce(new Error('Save unavailable'))
    panel.vm.$emit('save', { id: 1, config: { title: 'Draft' } })
    await flushPromises()
    expect(panel.props('modelValue')).toBe(true)
    expect(panel.props('error')).toBe('Save unavailable')
    panel.vm.$emit('save', { id: 1, config: { title: 'Draft' } })
    await flushPromises()
    expect(http.patch).toHaveBeenLastCalledWith('/api/widgets/1', { config: { title: 'Draft' } })
    expect(panel.props('modelValue')).toBe(false)
  })
  it('preserves layout/drop/add payloads and closes a deleted selection', async () => {
    const { wrapper } = await setup()
    const c = wrapper.findComponent(canvas)
    const layout = [{ id: 1, x: 3, y: 2, width: 4, height: 2, z_index: 1 }]
    c.vm.$emit('layoutChanged', layout)
    c.vm.$emit('addFromDrop', { type: 'TEXT', x: 4, y: 2, width: 3, height: 2 })
    wrapper.findComponent(palette).vm.$emit('add', 'TEXT')
    await flushPromises()
    expect(http.post).toHaveBeenCalledWith('/api/widgets/bulk-layout', { widgets: layout })
    expect(http.post).toHaveBeenCalledWith('/api/displays/2/widgets', { type: 'TEXT', x: 4, y: 2, width: 3, height: 2, z_index: 1, config: {} })
    expect(http.post).toHaveBeenCalledWith('/api/displays/2/widgets', { type: 'TEXT', x: 0, y: 0, width: 3, height: 2, z_index: 1, config: {} })
    await wrapper.find('.widget-selection select').setValue('1')
    c.vm.$emit('deleteWidget', 1)
    await flushPromises()
    expect(http.delete).toHaveBeenCalledWith('/api/widgets/1')
    expect(wrapper.findComponent(inspector).props('modelValue')).toBe(false)
  })
  it('keeps native modal cancellation and the dashboard settings payload', async () => {
    const { wrapper } = await setup()
    await wrapper.find('.workspace-actions button').trigger('click')
    await wrapper.find('dialog').trigger('cancel')
    expect(wrapper.find('dialog').exists()).toBe(false)
    expect(http.patch).not.toHaveBeenCalled()
    await wrapper.find('.workspace-actions button').trigger('click')
    const form = wrapper.find('form')
    const inputs = form.findAll('input[type="text"]')
    await inputs[0].setValue('Renamed')
    await inputs[1].setValue('renamed')
    await form.find('input[type="checkbox"]').setValue(false)
    http.patch.mockRejectedValueOnce(new Error('Settings unavailable'))
    await form.trigger('submit')
    await flushPromises()
    expect(wrapper.find('dialog').text()).toContain('Settings unavailable')
    await form.trigger('submit')
    await flushPromises()
    expect(http.patch).toHaveBeenLastCalledWith('/api/displays/2', { title: 'Renamed', slug: 'renamed', is_public: false })
    expect(wrapper.find('dialog').exists()).toBe(false)
  })
  it('shows empty and load-failure states', async () => {
    http.get.mockImplementation(async (url: string) => ({ data: url.endsWith('/widgets') ? { items: [] } : board }))
    const { wrapper } = await setup()
    expect(wrapper.find('.canvas-empty[role="status"]').exists()).toBe(true)
    expect(wrapper.find('.widget-selection select').attributes('disabled')).toBeDefined()
    http.get.mockRejectedValueOnce(new Error('Offline'))
    const failure = await setup()
    expect(failure.wrapper.find('[role="alert"]').text()).toContain('Offline')
  })
  it('retains backdrop cancellation but protects a pending settings save', async () => {
    const { wrapper } = await setup()
    await wrapper.find('.workspace-actions button').trigger('click')
    const dialog = wrapper.find('dialog')
    vi.spyOn(dialog.element, 'getBoundingClientRect').mockReturnValue({ left: 10, top: 10, right: 100, bottom: 100 } as DOMRect)
    await dialog.trigger('click', { clientX: 20, clientY: 20 })
    expect(wrapper.find('dialog').exists()).toBe(true)
    await dialog.trigger('click', { clientX: 0, clientY: 0 })
    expect(wrapper.find('dialog').exists()).toBe(false)
    await wrapper.find('.workspace-actions button').trigger('click')
    let resolve!: (value: unknown) => void
    http.patch.mockReturnValueOnce(new Promise(r => { resolve = r }))
    await wrapper.find('form').trigger('submit')
    await wrapper.find('dialog').trigger('cancel')
    expect(wrapper.find('dialog').exists()).toBe(true)
    expect(wrapper.find('dialog button[type="submit"]').attributes('disabled')).toBeDefined()
    resolve({ data: board })
    await flushPromises()
    expect(wrapper.find('dialog').exists()).toBe(false)
  })
})
