import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import MenuEditor from './MenuEditor.vue'

vi.mock('@/utils/i18n', () => ({ useI18n: () => ({ t: (_: string, fallback: string) => fallback }) }))
const items: { label: Record<string, string>; path: string; audience: 'authenticated' | 'admin' }[] = [
  { label: { en: 'Reports', bg: 'Отчети' }, path: '/reports', audience: 'authenticated' },
  { label: { en: 'Settings' }, path: '/settings', audience: 'admin' },
]
const routeOptions = [
  { path: '/reports', label: 'Reports', adminOnly: false, requiresAuth: true },
  { path: '/settings', label: 'Settings', adminOnly: true, requiresAuth: true },
  { path: '/public', label: 'Public page', adminOnly: false, requiresAuth: false },
]
const editor = () => mount(MenuEditor, { props: { menu: { id: 1, items }, menuLanguage: 'bg', routeOptions } })

describe('shared collection-based menu editor', () => {
  it('edits one translation without mutating the saved item or losing the other language', async () => {
    const wrapper = editor()
    await wrapper.get('#menu-item-label-0').setValue('Нови отчети')
    expect(wrapper.emitted('update-items')?.[0]?.[0]).toEqual([{ ...items[0], label: { en: 'Reports', bg: 'Нови отчети' } }, items[1]])
    expect(items[0].label.bg).toBe('Отчети')
    wrapper.unmount()
  })
  it('retains route audience defaults and disables public access for protected pages', async () => {
    const wrapper = editor()
    expect(wrapper.get('#menu-item-audience-0 option[value=public]').attributes('disabled')).toBeDefined()
    await wrapper.get('#menu-item-path-0').setValue('/settings')
    expect(wrapper.emitted('update-items')?.[0]?.[0]).toEqual([{ ...items[0], path: '/settings', audience: 'admin' }, items[1]])
    wrapper.unmount()
  })
  it('adds a draft link with a custom path and the selected translation', async () => {
    const wrapper = editor()
    await wrapper.get('[data-collection-add]').trigger('click')
    await wrapper.get('#menu-item-label-2').setValue('Нов екран')
    await wrapper.get('#menu-item-custom-2').setValue('/dynamic/example')
    await wrapper.get('#menu-item-audience-2').setValue('public')
    const result = wrapper.emitted('update-items')!.at(-1)![0] as object[]
    expect(result.at(-1)).toEqual({ path: '/dynamic/example', label: { bg: 'Нов екран' }, audience: 'public' })
    expect(result.every(item => !('key' in item))).toBe(true)
    wrapper.unmount()
  })
  it('keeps stable keys for duplicate routes through field edits, reorder and draft removal', async () => {
    const wrapper = editor()
    await wrapper.get('.menu-item-duplicate').trigger('click')
    const keys = wrapper.findAll('[data-item-key]').map(row => row.attributes('data-item-key'))
    expect(new Set(keys).size).toBe(3)
    await wrapper.get('#menu-item-label-1').setValue('Копие')
    expect(wrapper.findAll('[data-item-key]').map(row => row.attributes('data-item-key'))).toEqual(keys)
    const first = wrapper.findAll('[data-item-key]')[0]!
    await first.get('button[aria-label^="Move down"]').trigger('click')
    expect(wrapper.findAll('[data-item-key]').map(row => row.attributes('data-item-key'))).toEqual([keys[1], keys[0], keys[2]])
    await wrapper.findAll('[data-item-key]')[0]!.get('button[aria-label^="Remove"]').trigger('click')
    expect(wrapper.findAll('[data-item-key]')).toHaveLength(2)
    expect(items).toHaveLength(2)
    wrapper.unmount()
  })
  it('locks edits and collection actions without emitting mutations', async () => {
    const wrapper = editor(); await wrapper.setProps({ disabled: true })
    expect(wrapper.get('[data-collection-add]').element).toHaveProperty('disabled', true)
    await wrapper.get('[data-collection-add]').trigger('click')
    await wrapper.get('#menu-item-label-0').setValue('Blocked')
    expect(wrapper.emitted('update-items')).toBeUndefined()
    wrapper.unmount()
  })
})
