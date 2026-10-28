import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const http = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  delete: vi.fn()
}))

vi.mock('@/utils/dynamic-http', () => ({ default: http }))
vi.mock('@/stores/settings', () => ({
  useSettingsStore: () => ({
    uiDesign: { components: { card: 'raised', button: 'outline' } }
  })
}))
vi.mock('@/utils/i18n', async () => {
  const { ref } = await import('vue')
  return {
    useI18n: () => ({
      currentLanguage: ref('en'),
      t: (_key: string, fallback: string) => fallback
    })
  }
})

import DashboardList from './DashboardList.vue'

const nativeMethods = ['showModal', 'close'].map(name => ({ name, descriptor: Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, name) }))
const mounted: Array<ReturnType<typeof mount>> = []

const displays = [
  { id: 1, title: 'Workshop', slug: 'workshop', is_public: false, user_id: 7, owner_username: 'admin' },
  { id: 2, title: 'Shared status', slug: 'shared', is_public: true, user_id: 8, owner_username: 'operator' }
]

const mountView = async () => {
  const wrapper = mount(DashboardList, {
    global: {
      plugins: [createPinia()],
      stubs: {
        RouterLink: { props: ['to'], template: '<a :data-destination="JSON.stringify(to)"><slot /></a>' },
        Teleport: true
      }
    }
  })
  mounted.push(wrapper)
  await flushPromises()
  return wrapper
}

describe('Dashboard management workflow', () => {
  afterEach(() => {
    mounted.splice(0).forEach(wrapper => wrapper.unmount())
    vi.restoreAllMocks()
    for (const { name, descriptor } of nativeMethods) {
      if (descriptor) Object.defineProperty(HTMLDialogElement.prototype, name, descriptor)
      else Reflect.deleteProperty(HTMLDialogElement.prototype, name)
    }
  })
  beforeEach(() => {
    // Native modal/focus behavior is also checked in the browser fixture.
    Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value: function(this: HTMLDialogElement) { this.open = true } })
    Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value: function(this: HTMLDialogElement) { this.open = false; this.dispatchEvent(new Event('close')) } })
    vi.clearAllMocks()
    localStorage.clear()
    localStorage.setItem('username', 'admin')
    localStorage.setItem('user_id', '7')
    http.get.mockResolvedValue({ data: { items: displays } })
    http.post.mockResolvedValue({
      data: { id: 3, title: 'New board', slug: 'new-board', is_public: true, user_id: 7 }
    })
    http.delete.mockResolvedValue({ data: {} })
  })

  it('distinguishes owned and shared dashboards', async () => {
    const wrapper = await mountView()

    expect(wrapper.text()).toContain('Workshop')
    expect(wrapper.text()).toContain('Shared status')
    expect(wrapper.text()).toContain('Shared with you')
    expect(wrapper.findAll('.dashboard-card .ui-button--danger')).toHaveLength(1)
    expect(wrapper.findAll('.dashboard-card')[1].text()).toContain('View')
    expect(wrapper.findAll('.dashboard-card')[1].text()).not.toContain('Delete')
  })

  it('creates a dashboard from the modal and refreshes the list', async () => {
    const wrapper = await mountView()

    await wrapper.find('.view-header .ui-button--primary').trigger('click')
    const form = wrapper.find('.modal-form')
    const textInputs = form.findAll('input[type="text"]')
    await textInputs[0].setValue('New board')
    await textInputs[1].setValue('new-board')
    await form.find('input[type="checkbox"]').setValue(true)
    await form.trigger('submit')
    await flushPromises()

    expect(http.post).toHaveBeenCalledWith('/api/displays', {
      title: 'New board',
      slug: 'new-board',
      is_public: true
    })
    expect(http.get).toHaveBeenCalledTimes(2)
    expect(wrapper.find('.modal-form').exists()).toBe(false)
  })

  it('deletes only the selected owned dashboard', async () => {
    const wrapper = await mountView()

    await wrapper.find('.dashboard-card .ui-button--danger').trigger('click')
    expect(wrapper.text()).toContain('"Workshop"')
    await wrapper.find('dialog .ui-button--danger').trigger('click')
    await flushPromises()

    expect(http.delete).toHaveBeenCalledWith('/api/displays/1')
    expect(http.get).toHaveBeenCalledTimes(2)
  })

  it('uses theme component variants without per-card or modal inline colors', async () => {
    const wrapper = await mountView()
    expect(wrapper.attributes('data-card')).toBe('raised')
    expect(wrapper.attributes('data-button')).toBe('outline')
    expect(wrapper.findAll('article.ui-section')).toHaveLength(2)
    expect(wrapper.findAll('[style]')).toHaveLength(0)
    await wrapper.find('.dashboard-create').trigger('click')
    expect(wrapper.findAll('[style]')).toHaveLength(0)
    expect(wrapper.find('dialog').attributes('aria-labelledby')).toBe(wrapper.find('dialog h2').attributes('id'))
    expect(wrapper.find('input[autofocus]').exists()).toBe(true)
    expect(wrapper.find('button[type="submit"]').attributes('form')).toBe(wrapper.find('form').attributes('id'))
  })

  it('preserves public preview and editor destinations including shared owners', async () => {
    const wrapper = await mountView()
    const destinations = wrapper.findAll('.dashboard-card a').map(link => JSON.parse(link.attributes('data-destination')!))
    expect(destinations).toEqual([
      { name: 'PublicDisplay', params: { username: 'admin', slug: 'workshop' } }, '/dashboard/1/edit',
      { name: 'PublicDisplay', params: { username: 'operator', slug: 'shared' } }, '/dashboard/2/edit',
    ])
  })

  it('supports native Escape cancellation without creating or deleting data', async () => {
    const wrapper = await mountView()
    await wrapper.find('.dashboard-create').trigger('click')
    await wrapper.find('dialog').trigger('cancel')
    expect(wrapper.find('dialog').exists()).toBe(false)
    await wrapper.find('.dashboard-card .ui-button--danger').trigger('click')
    expect(wrapper.find('dialog button[autofocus]').text()).toBe('Cancel')
    await wrapper.find('dialog').trigger('cancel')
    expect(wrapper.find('dialog').exists()).toBe(false)
    expect(http.post).not.toHaveBeenCalled()
    expect(http.delete).not.toHaveBeenCalled()
  })

  it('keeps the existing empty state and create entry', async () => {
    http.get.mockResolvedValue({ data: { items: [] } })
    const wrapper = await mountView()
    expect(wrapper.find('.dashboard-empty[role="status"]').text()).toContain('No dashboards available')
    expect(wrapper.find('.dashboard-create').exists()).toBe(true)
    expect(wrapper.find('.dashboard-grid').exists()).toBe(false)
  })

  it('preserves backdrop cancellation but not clicks inside the dialog', async () => {
    const wrapper = await mountView()
    await wrapper.find('.dashboard-create').trigger('click')
    const dialog = wrapper.find('dialog')
    vi.spyOn(dialog.element, 'getBoundingClientRect').mockReturnValue({ left: 10, top: 10, right: 100, bottom: 100 } as DOMRect)
    await dialog.trigger('click', { clientX: 20, clientY: 20 })
    expect(wrapper.find('dialog').exists()).toBe(true)
    await dialog.trigger('click', { clientX: 0, clientY: 0 })
    expect(wrapper.find('dialog').exists()).toBe(false)
    expect(http.post).not.toHaveBeenCalled()
    expect(http.delete).not.toHaveBeenCalled()
  })
})
