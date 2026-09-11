import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn() }))
vi.mock('@/utils/dynamic-http', () => ({ default: http }))
vi.mock('@/utils/i18n', async () => {
  const { ref } = await import('vue')
  return { useI18n: () => ({ currentLanguage: ref('bg'), t: (_: string, fallback: string) => fallback }) }
})
import Panel from './UserApplicationPermissions.vue'
const base = '/api/v1/application-extensions'
const permission = { permission_id: 'records', label: { en: 'Records', translations: { bg: 'Записи' } }, description: { en: 'Manage records', translations: {} } }
const snapshot = (grants: unknown[] = []) => ({ data: { permissions: [permission], grants } })
async function open() {
  const wrapper = mount(Panel, { props: { userId: 2, isAdmin: false } })
  await flushPromises()
  await wrapper.get('select').setValue('org.example.app')
  await flushPromises()
  return wrapper
}
describe('User application permissions', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    http.get.mockImplementation((url: string) => Promise.resolve(url === base
      ? { data: [{ module_id: 'org.example.app', active_version: '1.0.0', enabled: true, status: 'active' }, { module_id: 'disabled', enabled: false, status: 'disabled' }] }
      : snapshot([{ user_id: 3, permission_id: 'records' }])))
    http.post.mockResolvedValue({})
    http.delete.mockResolvedValue({})
  })
  it('uses active declarations, localized labels and only the selected user grants', async () => {
    const wrapper = await open()
    expect(wrapper.text()).toContain('Записи')
    expect(wrapper.text()).not.toContain('disabled')
    expect(wrapper.get('input').element.checked).toBe(false)
    expect(http.post).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('grants and revokes through protected endpoints and reloads server state', async () => {
    const wrapper = await open()
    http.get.mockResolvedValue(snapshot([{ user_id: 2, permission_id: 'records' }]))
    await wrapper.get('input').setValue(true)
    await flushPromises()
    expect(http.post).toHaveBeenCalledWith(`${base}/org.example.app/permissions/grants`, { user_id: 2, permission_id: 'records' })
    expect(wrapper.get('input').element.checked).toBe(true)
    http.get.mockResolvedValue(snapshot())
    await wrapper.get('input').setValue(false)
    await flushPromises()
    expect(http.delete).toHaveBeenCalledWith(`${base}/org.example.app/permissions/grants/2/records`)
    expect(wrapper.get('input').element.checked).toBe(false)
    wrapper.unmount()
  })
  it('does not pretend a failed write succeeded and requires refresh', async () => {
    const wrapper = await open()
    http.post.mockRejectedValue(new Error('Unavailable'))
    await wrapper.get('input').setValue(true)
    await flushPromises()
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
    expect(wrapper.get('input').element.checked).toBe(false)
    expect(wrapper.get('input').element.disabled).toBe(true)
    wrapper.unmount()
  })
  it('distinguishes an empty list from a failed load', async () => {
    http.get.mockResolvedValue({ data: [] })
    const wrapper = mount(Panel, { props: { userId: 2, isAdmin: true } })
    await flushPromises()
    expect(wrapper.text()).toContain('No active applications')
    expect(wrapper.text()).toContain('Global administrators')
    wrapper.unmount()
    http.get.mockRejectedValue(new Error('Forbidden'))
    const failed = mount(Panel, { props: { userId: 2, isAdmin: false } })
    await flushPromises()
    expect(failed.text()).not.toContain('No active applications')
    expect(failed.find('[role="alert"]').exists()).toBe(true)
    failed.unmount()
  })
})
