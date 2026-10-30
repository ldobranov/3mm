import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import ThemeMenuSettings from './ThemeMenuSettings.vue'
import { defaultMenuLayout, type MenuLayout } from '@/utils/menu-layout'

const api = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/utils/dynamic-http', () => ({ default: api }))
vi.mock('@/utils/i18n', () => ({ useI18n: () => ({ t: (_: string, fallback: string) => fallback, currentLanguage: ref('en') }) }))
afterEach(() => vi.clearAllMocks())

describe('menu position editor', () => {
  it('keeps missing saved IDs visible and permits explicit cleanup without choosing a replacement', async () => {
    api.get.mockResolvedValue({ data: { items: [{ id: 1, name: 'Main', is_active: true }] } })
    const value: MenuLayout = { ...defaultMenuLayout(), placements: [{ menu_id: 99, location: 'footer' }] }
    const wrapper = mount(ThemeMenuSettings, { props: { modelValue: value, navigation: 'sidebar' } })
    await flushPromises()
    expect(wrapper.get('[data-menu-id="99"]').text()).toContain('Deleted or unavailable')
    expect(wrapper.get('[data-preview-region="footer"]').text()).not.toContain('Main')
    await wrapper.get('[data-menu-id="99"] select').setValue('hidden')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([{ ...defaultMenuLayout(), placements: [] }])
    expect(value.placements).toEqual([{ menu_id: 99, location: 'footer' }])
    wrapper.unmount()
  })
  it('preserves placements on read failure and retries only an explicit read', async () => {
    api.get.mockRejectedValueOnce(new Error('offline'))
    const value: MenuLayout = { ...defaultMenuLayout(), placements: [{ menu_id: 2, location: 'header' }] }
    const wrapper = mount(ThemeMenuSettings, { props: { modelValue: value, navigation: 'top' } })
    await flushPromises()
    expect(wrapper.find('[data-menu-id]').exists()).toBe(false)
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    api.get.mockResolvedValue({ data: { items: [{ id: 2, name: 'Admin', is_active: false }] } })
    await wrapper.get('[data-action="reload-menus"]').trigger('click'); await flushPromises()
    expect(wrapper.get('[data-menu-id="2"] select').element).toHaveProperty('value', 'header')
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    wrapper.unmount()
  })
  it('changes stickiness without freezing the automatically active menu', async () => {
    api.get.mockResolvedValue({ data: { items: [{ id: 1, name: 'Main', is_active: true }] } })
    const wrapper = mount(ThemeMenuSettings, { props: { navigation: 'sidebar' } })
    await flushPromises()
    await wrapper.get('[data-sticky="sidebar"] input').setValue(true)
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([{ sticky: { header: false, sidebar: true, footer: false } }])
    wrapper.unmount()
  })
})
