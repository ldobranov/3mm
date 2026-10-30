import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import MenuConfigurationSection from './MenuConfigurationSection.vue'

vi.mock('@/utils/i18n', () => ({ useI18n: () => ({ t: (_: string, fallback: string) => fallback }) }))
const saved = [{ path: '/report', label: { en: 'Reports' }, audience: 'authenticated' as const }]
const menus = () => mount(MenuConfigurationSection, {
  props: { menuLanguage: 'en', availableLanguages: ['en', 'bg'], menus: [{ id: 1, name: 'Main', is_active: true, items: saved }],
    activeMenuId: 1, currentMenuItems: saved, routeOptions: [{ path: '/report', label: 'Reports', requiresAuth: true, adminOnly: false }] },
  global: { stubs: { MenuEditor: true, UiDialog: { props: ['open'], template: '<section v-if="open" role="dialog"><slot /><slot name="actions" /></section>' } } },
})
describe('menu contents and management workspace', () => {
  it('requires explicit dialog confirmation to delete a menu', async () => {
    const wrapper = menus()
    await wrapper.get('.menu-delete').trigger('click')
    expect(wrapper.emitted('delete-menu')).toBeUndefined()
    expect(wrapper.get('[role=dialog]').text()).toContain('Main')
    await wrapper.get('[role=dialog] form').trigger('submit')
    expect(wrapper.emitted('delete-menu')).toEqual([[1]])
    wrapper.unmount()
  })
  it('creates and renames with shared dialog fields, without browser prompts', async () => {
    const wrapper = menus()
    await wrapper.get('[data-action=create-menu]').trigger('click')
    await wrapper.get('[role=dialog] input').setValue('Footer')
    await wrapper.get('[role=dialog] form').trigger('submit')
    expect(wrapper.emitted('create-menu')).toEqual([['Footer']])
    await wrapper.get('[data-action=rename-menu]').trigger('click')
    await wrapper.get('[role=dialog] input').setValue('New name')
    await wrapper.get('[role=dialog] form').trigger('submit')
    expect(wrapper.emitted('rename-menu')).toEqual([[{ id: 1, name: 'New name' }]])
    wrapper.unmount()
  })
  it('saves only a valid changed draft, including an intentionally empty menu', async () => {
    const wrapper = menus()
    await wrapper.get('.menu-content-form').trigger('submit')
    expect(wrapper.emitted('save-menu')).toBeUndefined()
    await wrapper.setProps({ currentMenuItems: [{ ...saved[0]!, path: '', label: { en: '' } }] })
    await wrapper.get('.menu-content-form').trigger('submit')
    expect(wrapper.emitted('save-menu')).toBeUndefined()
    await wrapper.setProps({ currentMenuItems: [] })
    await wrapper.get('.menu-content-form').trigger('submit')
    expect(wrapper.emitted('save-menu')).toHaveLength(1)
    expect(saved).toHaveLength(1)
    wrapper.unmount()
  })
  it('fences CRUD after uncertainty and exposes read-only recovery', async () => {
    const wrapper = menus(); await wrapper.setProps({ state: 'unconfirmed' })
    await wrapper.get('[data-action=create-menu]').trigger('click')
    expect(wrapper.find('[role=dialog]').exists()).toBe(false)
    await wrapper.get('[data-action=reload-menus]').trigger('click')
    expect(wrapper.emitted('reload')).toHaveLength(1)
    expect(wrapper.emitted('create-menu')).toBeUndefined()
    wrapper.unmount()
  })
})
