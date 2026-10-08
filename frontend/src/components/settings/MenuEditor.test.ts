import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/utils/i18n', () => ({
  useI18n: () => ({ t: (_key: string, fallback: string) => fallback }),
}))

import MenuEditor from './MenuEditor.vue'

const items = [
  { label: { en: 'Reports', bg: 'Отчети' }, path: '/reports', audience: 'authenticated' },
  { label: { en: 'Settings' }, path: '/settings', audience: 'admin' },
]
const routeOptions = [
  { path: '/reports', label: 'Reports', adminOnly: false, requiresAuth: true },
  { path: '/settings', label: 'Settings', adminOnly: true, requiresAuth: true },
  { path: '/public', label: 'Public page', adminOnly: false, requiresAuth: false },
]

function editor() {
  return mount(MenuEditor, {
    props: { menu: { items }, menuLanguage: 'bg', availableLanguages: ['en', 'bg'], routeOptions, settingsStore: {} },
    global: { stubs: { VueDraggable: { name: 'VueDraggable', props: ['modelValue'], template: '<div><slot /></div>' } } },
  })
}

afterEach(() => vi.unstubAllGlobals())

describe('Theme-aware menu controls', () => {
  it('keeps localized edits and names the native controls', async () => {
    const wrapper = editor()
    expect(wrapper.find('label[for="menu-item-label-0"]').text()).toContain('BG')
    expect(wrapper.find('#menu-item-label-0').classes()).toContain('ui-control')
    await wrapper.find('#menu-item-label-0').setValue('Нови отчети')
    expect(wrapper.emitted('update-items')?.[0]?.[0]).toEqual([
      { ...items[0], label: { en: 'Reports', bg: 'Нови отчети' } }, items[1],
    ])
    expect(items[0].label.bg).toBe('Отчети')
  })

  it('preserves admin route defaults and prevents a public option for protected routes', async () => {
    const wrapper = editor()
    expect(wrapper.find('#menu-item-audience-0 option[value="public"]').attributes()).toHaveProperty('disabled')
    await wrapper.find('#menu-item-path-0').setValue('/settings')
    expect(wrapper.emitted('update-items')?.[0]?.[0]).toEqual([
      { ...items[0], path: '/settings', audience: 'admin' }, items[1],
    ])
  })

  it('retains custom paths, selected language and audience for new items', async () => {
    const wrapper = editor()
    await wrapper.find('#new-item-label').setValue('Външен екран')
    await wrapper.find('#new-item-path').setValue('__custom__')
    await wrapper.find('input[aria-label="Custom path"]').setValue('/dynamic/example')
    await wrapper.find('#new-item-audience').setValue('public')
    await wrapper.find('.menu-editor-add button').trigger('click')
    expect(wrapper.emitted('update-items')?.[0]?.[0]).toEqual([
      ...items, { label: { bg: 'Външен екран' }, path: '/dynamic/example', audience: 'public' },
    ])
  })

  it('keeps reorder events and the removal confirmation', async () => {
    const wrapper = editor()
    const reordered = [...items].reverse()
    wrapper.findComponent({ name: 'VueDraggable' }).vm.$emit('update:model-value', reordered)
    expect(wrapper.emitted('update-items')?.[0]?.[0]).toEqual(reordered)
    expect(wrapper.emitted('drag-end')).toHaveLength(1)
    vi.stubGlobal('confirm', vi.fn(() => false))
    await wrapper.find('.menu-item-danger').trigger('click')
    expect(window.confirm).toHaveBeenCalled()
    expect(wrapper.emitted('update-items')).toHaveLength(1)
  })
})
