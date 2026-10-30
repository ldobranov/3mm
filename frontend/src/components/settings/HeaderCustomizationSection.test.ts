import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import HeaderCustomizationSection from './HeaderCustomizationSection.vue'
import ImageEditorModal from '@/components/ImageEditorModal.vue'

vi.mock('@/utils/i18n', () => ({ useI18n: () => ({ t: (_: string, fallback: string) => fallback }) }))
const header = () => mount(HeaderCustomizationSection, {
  props: { headerLanguage: 'bg', availableLanguages: ['en', 'bg'], currentSiteName: '', currentHeaderMessage: '',
    siteNameFallback: 'English name', headerMessageFallback: 'English message', dirty: true,
    headerSettings: { siteName: 'Saved', headerMessage: 'Saved message', logoUrl: '/saved.png', backgroundColor: '#ffffff', textColor: '#000000' } },
  global: { stubs: { ImageEditorModal: true } },
})

describe('shared branding workspace', () => {
  it('shows fallback text and a draft logo without mutating the supplied settings', async () => {
    const wrapper = header(), original = wrapper.props('headerSettings')
    expect(wrapper.get('.preview-card').text()).toContain('English name')
    wrapper.findComponent(ImageEditorModal).vm.$emit('update:modelValue', '/new.png')
    expect(wrapper.emitted('logo-upload')).toEqual([['/new.png']])
    expect(original.logoUrl).toBe('/saved.png')
    expect(wrapper.find('input[type=color]').exists()).toBe(false)
    wrapper.unmount()
  })
  it('emits explicit save/discard intents and keeps preview navigation separate', async () => {
    const wrapper = header()
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('save-header-settings')).toHaveLength(1)
    await wrapper.get('.ui-editor-actions button').trigger('click')
    expect(wrapper.emitted('discard')).toHaveLength(1)
    await wrapper.get('[data-action=theme-settings]').trigger('click')
    expect(wrapper.emitted('open-theme')).toHaveLength(1)
    expect(wrapper.emitted('logo-remove')).toBeUndefined()
    wrapper.unmount()
  })
  it('locks uncertain saves and logo changes but permits explicit saved-value recovery', async () => {
    const wrapper = header(); await wrapper.setProps({ state: 'unconfirmed' })
    await wrapper.get('form').trigger('submit')
    wrapper.findComponent(ImageEditorModal).vm.$emit('update:modelValue', '/blocked.png')
    expect(wrapper.emitted('save-header-settings')).toBeUndefined()
    expect(wrapper.emitted('logo-upload')).toBeUndefined()
    await wrapper.get('[data-action=reload-header]').trigger('click')
    expect(wrapper.emitted('reload')).toHaveLength(1)
    wrapper.unmount()
  })
})
