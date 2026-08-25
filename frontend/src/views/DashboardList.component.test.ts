import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const http = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  delete: vi.fn()
}))

vi.mock('@/utils/dynamic-http', () => ({ default: http }))
vi.mock('@/stores/settings', () => ({
  useSettingsStore: () => ({
    styleSettings: {
      cardBg: '#fff',
      textPrimary: '#111',
      cardBorder: '#ddd'
    }
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

const displays = [
  { id: 1, title: 'Workshop', slug: 'workshop', is_public: false, user_id: 7, owner_username: 'admin' },
  { id: 2, title: 'Shared status', slug: 'shared', is_public: true, user_id: 8, owner_username: 'operator' }
]

const mountView = async () => {
  const wrapper = mount(DashboardList, {
    global: {
      plugins: [createPinia()],
      stubs: {
        RouterLink: { template: '<a><slot /></a>' },
        Teleport: true
      }
    }
  })
  await flushPromises()
  return wrapper
}

describe('Dashboard management workflow', () => {
  beforeEach(() => {
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
    expect(wrapper.findAll('.dashboard-card .button-danger')).toHaveLength(1)
  })

  it('creates a dashboard from the modal and refreshes the list', async () => {
    const wrapper = await mountView()

    await wrapper.find('.view-header .button-primary').trigger('click')
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

    await wrapper.find('.dashboard-card .button-danger').trigger('click')
    expect(wrapper.text()).toContain('"Workshop"')
    await wrapper.find('.modal-surface .button-danger').trigger('click')
    await flushPromises()

    expect(http.delete).toHaveBeenCalledWith('/api/displays/1')
    expect(http.get).toHaveBeenCalledTimes(2)
  })
})
