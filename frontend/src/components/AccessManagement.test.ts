import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
const http = vi.hoisted(() => ({get: vi.fn(), put: vi.fn(), post: vi.fn()}))
vi.mock('@/utils/dynamic-http', () => ({default: http}))
vi.mock('@/utils/i18n', async () => {
  const {ref} = await import('vue')
  return {useI18n: () => ({currentLanguage: ref('en'), t: (_: string, fallback: string) => fallback})}
})
import Panel from './AccessManagement.vue'
beforeEach(() => {
  vi.resetAllMocks()
  http.get.mockImplementation((url: string) => Promise.resolve({data: url === '/api/access' ? {
    roles: [{id: 1, name: 'Operator'}], groups: [{id: 2, name: 'Staff'}], dashboards: [],
    user_roles: [], user_groups: [], group_roles: [], application_grants: [], dashboard_grants: [],
  } : []}))
  http.put.mockResolvedValue({}); http.post.mockResolvedValue({})
})
it('creates a named role and assigns membership through protected APIs', async () => {
  const wrapper = mount(Panel, {props: {users: [{id: 3, username: 'A'}]}})
  await flushPromises()
  await wrapper.get('input.input').setValue('Team')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(http.post).toHaveBeenCalledWith('/api/roles', {name: 'Team'})
  await wrapper.get('.access-columns section select').setValue(3)
  await wrapper.get('.check input').setValue(true)
  await flushPromises()
  expect(http.put).toHaveBeenCalledWith('/api/access/bindings', {kind: 'user-role', subject_id: 3, target_id: 1, enabled: true})
  expect(wrapper.emitted('changed')).toHaveLength(2)
  wrapper.unmount()
})
it('failed writes keep server state and require refresh', async () => {
  const wrapper = mount(Panel, {props: {users: [{id: 3, username: 'A'}]}})
  await flushPromises()
  await wrapper.get('.access-columns section select').setValue(3)
  http.put.mockRejectedValue(new Error('offline'))
  await wrapper.get('.check input').setValue(true)
  await flushPromises()
  expect(wrapper.get('fieldset').element.disabled).toBe(true)
  expect(wrapper.get('.check input').element.checked).toBe(false)
  expect(wrapper.find('[role=alert]').exists()).toBe(true)
  expect(wrapper.emitted('changed')).toBeUndefined()
  wrapper.unmount()
})
