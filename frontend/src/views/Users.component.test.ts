import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const http = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn()
}))
const settingsStore = vi.hoisted(() => ({
  styleSettings: {
    cardBg: '#fff',
    textPrimary: '#111',
    cardBorder: '#ddd'
  }
}))

vi.mock('@/utils/dynamic-http', () => ({ default: http }))
vi.mock('@/stores/settings', () => ({ useSettingsStore: () => settingsStore }))
vi.mock('@/utils/i18n', async () => {
  const { ref } = await import('vue')
  return {
    useI18n: () => ({
      currentLanguage: ref('en'),
      t: (_key: string, fallback: string) => fallback
    })
  }
})

import Users from './Users.vue'

const admin = {
  id: 1,
  username: 'admin',
  email: 'admin@example.com',
  role: 'admin',
  created_at: '2026-08-27T19:00:00'
}

const mountView = async () => {
  const wrapper = mount(Users, {
    global: {
      stubs: { teleport: true }
    }
  })
  await flushPromises()
  return wrapper
}

describe('Users management page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    localStorage.setItem('user_id', '1')
    http.get.mockResolvedValue({ data: { items: [admin], total: 1 } })
    http.post.mockResolvedValue({ data: {} })
    http.put.mockResolvedValue({ data: {} })
    http.delete.mockResolvedValue({ data: {} })
  })

  it('loads and displays users from the protected API', async () => {
    const wrapper = await mountView()

    expect(http.get).toHaveBeenCalledWith('/api/user/read')
    expect(wrapper.text()).toContain('admin@example.com')
    expect(wrapper.text()).not.toContain('Failed to fetch users')
  })

  it('uses the API prefix when creating and updating users', async () => {
    const wrapper = await mountView()

    await wrapper.find('.view-header button').trigger('click')
    const createForm = wrapper.find('form')
    const createInputs = createForm.findAll('input')
    await createInputs[0].setValue('operator')
    await createInputs[1].setValue('operator@example.com')
    await createInputs[2].setValue('test-password')
    await createForm.find('select').setValue('admin')
    await createForm.trigger('submit')
    await flushPromises()

    expect(http.post).toHaveBeenCalledWith('/api/user/create', {
      username: 'operator',
      email: 'operator@example.com',
      password: 'test-password',
      role: 'admin'
    })

    await wrapper.find('.user-actions button').trigger('click')
    await wrapper.findAll('form input')[2].setValue('new-admin-password')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(http.put).toHaveBeenCalledWith('/api/user/update', {
      id: 1,
      username: 'admin',
      email: 'admin@example.com',
      role: 'admin',
      password: 'new-admin-password'
    })
  })

  it('uses the protected delete endpoint', async () => {
    http.get.mockResolvedValue({
      data: {
        items: [admin, { ...admin, id: 2, username: 'operator', email: 'operator@example.com' }],
        total: 2
      }
    })
    const wrapper = await mountView()
    const deleteButtons = wrapper.findAll('.user-actions .button-danger')

    await deleteButtons[1].trigger('click')
    await wrapper.find('.modal-surface .button-danger').trigger('click')
    await flushPromises()

    expect(http.delete).toHaveBeenCalledWith('/api/user/delete/2')
  })
})
