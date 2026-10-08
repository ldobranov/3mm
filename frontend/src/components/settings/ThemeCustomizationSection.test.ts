import { mount } from '@vue/test-utils'
import { reactive } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import ThemeCustomizationSection from './ThemeCustomizationSection.vue'

function editor(saving = false) {
  const settings = reactive({
    bodyBg: '#ffffff', contentBg: '#ffffff', buttonPrimaryBg: '#007bff',
    buttonSecondaryBg: '#6c757d', buttonDangerBg: '#dc3545', cardBg: '#ffffff',
    cardBorder: '#e3e3e3', panelBg: '#ffffff', textPrimary: '#222222',
    textSecondary: '#666666', textMuted: '#999999',
    borderRadiusSm: 4, borderRadiusMd: 8, borderRadiusLg: 12,
  })
  const settingsStore = { updateCSSVariables: vi.fn() }
  const wrapper = mount(ThemeCustomizationSection, {
    props: { themeType: 'light', sectionTitle: 'Light colours', settings, settingsStore, saving,
      t: (_key: string, fallback: string) => fallback },
  })
  return { wrapper, settings, settingsStore }
}

describe('Built-in theme controls', () => {
  it('retains live colour/radius bindings and the explicit save event', async () => {
    const { wrapper, settings, settingsStore } = editor()
    await wrapper.find('input[type="text"][aria-label="Body Background Color"]').setValue('#eeeeee')
    await wrapper.find('#light-borderRadiusSm').setValue('6')
    expect(settings.bodyBg).toBe('#eeeeee')
    expect(settings.borderRadiusSm).toBe(6)
    expect(settingsStore.updateCSSVariables).toHaveBeenCalled()
    expect(wrapper.emitted('save')).toBeUndefined()
    await wrapper.find('button[type="submit"]').trigger('click')
    expect(wrapper.emitted('save')).toHaveLength(1)
    expect(wrapper.find('input[type="color"]').attributes('aria-label')).toBe('Body Background Color')
  })

  it('keeps save disabled while saving and demo buttons non-submitting', () => {
    const { wrapper } = editor(true)
    expect(wrapper.find('button[type="submit"]').attributes()).toHaveProperty('disabled')
    expect(wrapper.findAll('.preview-buttons button').every(button => button.attributes('type') === 'button')).toBe(true)
  })
})
