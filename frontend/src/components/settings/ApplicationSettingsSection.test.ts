import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import http from '@/utils/dynamic-http'
import ApplicationSettingsSection from './ApplicationSettingsSection.vue'

vi.mock('@/utils/i18n', () => ({ useI18n: () => ({ t: (_key: string, fallback: string) => fallback }) }))
vi.mock('@/utils/dynamic-http', () => ({ default: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }))

afterEach(() => { localStorage.clear(); vi.resetAllMocks() })

describe('Core application defaults after product extraction', () => {
  it('retains admin language/theme and session controls without provider requests', async () => {
    localStorage.setItem('authToken', 'test-token'); localStorage.setItem('role', 'admin')
    vi.mocked(http.get).mockImplementation(async (url) => ({ data: url === '/settings/read'
      ? { items: [{ key: 'default_theme', value: 'dark' }, { key: 'default_language', value: 'bg' }] }
      : { duration_hours: 48, minimum_hours: 1, maximum_hours: 720 } }))
    vi.mocked(http.put).mockResolvedValue({ data: { duration_hours: 24 } })
    vi.mocked(http.post).mockResolvedValue({ data: {} })
    const wrapper = mount(ApplicationSettingsSection, { props: { availableLanguages: ['en', 'bg'] }, global: { stubs: {
      ThemeSelector: { props: ['modelValue'], template: '<button class="theme" @click="$emit(\'update:modelValue\', \'light\')">{{ modelValue }}</button>' },
      LanguageSelector: { props: ['modelValue'], template: '<button class="language" @click="$emit(\'update:modelValue\', \'en\')">{{ modelValue }}</button>' },
    } } })
    await flushPromises()
    expect(vi.mocked(http.get).mock.calls.map(call => call[0])).toEqual(['/settings/read', '/api/admin/session-settings'])
    expect(wrapper.find('.theme').text()).toBe('dark')
    expect(wrapper.find('.language').text()).toBe('bg')
    await wrapper.find('.theme').trigger('click'); await wrapper.find('.language').trigger('click')
    expect(http.post).toHaveBeenCalledWith('/settings/create', expect.objectContaining({ key: 'default_language', value: 'en' }))
    await wrapper.find('#session-duration-hours').setValue(24)
    await wrapper.find('.settings-actions button').trigger('click'); await flushPromises()
    expect(http.put).toHaveBeenCalledWith('/api/admin/session-settings', { duration_hours: 24 })
    expect(wrapper.text()).toContain('Session duration saved')
    expect(wrapper.find('input[type="password"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it.each(['registered', 'guest'])('keeps platform controls restricted for %s', async (role) => {
    if (role !== 'guest') { localStorage.setItem('authToken', 'test-token'); localStorage.setItem('role', role) }
    vi.mocked(http.get).mockResolvedValue({ data: { items: [] } })
    const wrapper = mount(ApplicationSettingsSection, { props: { availableLanguages: ['en'] } })
    await flushPromises()
    expect(wrapper.find('#session-duration-hours').exists()).toBe(false)
    expect(http.get).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain(role === 'guest' ? 'Please log in' : 'header selectors')
    wrapper.unmount()
  })
})
