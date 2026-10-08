import { afterEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, ref } from 'vue'
import { mount } from '@vue/test-utils'
import * as publicUi from './v1'
import ApplicationShell from '../components/ui/ApplicationShell.vue'
import { builtinUiDesign } from '../utils/ui-design'

vi.mock('@/stores/settings', () => ({ useSettingsStore: () => ({ headerSettings: { siteName: 'Reference' } }) }))
vi.mock('@/utils/ui-labels', () => ({ useUiLabels: () => (key: string) => key }))
vi.mock('vue-router', () => ({ useRoute: () => ({ fullPath: '/' }) }))
vi.mock('../components/Menu.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../components/ThemeToggle.vue', () => ({ default: { template: '<button />' } }))

afterEach(() => vi.restoreAllMocks())

describe('public extension UI v1', () => {
  it('exports only versioned presentation primitives, not Core services', () => {
    expect(Object.keys(publicUi).sort()).toEqual(['UI_CONTRACT_VERSION', 'UiButton', 'UiDialog', 'UiSurface'])
    expect(publicUi.UI_CONTRACT_VERSION).toBe(1)
  })

  it('opts in without a shell provider using safe default component variants', () => {
    const wrapper = mount(publicUi.UiSurface, { slots: { default: () => h(publicUi.UiButton, null, () => 'Action') } })
    expect(wrapper.classes()).toContain('ui-v2')
    expect(wrapper.attributes()).toMatchObject({ 'data-button': 'solid', 'data-card': 'bordered' })
    expect(wrapper.find('button').attributes('type')).toBe('button')
    wrapper.unmount()
  })

  it('receives host theme switches in legacy and modern shell without remounting the draft', async () => {
    const mounted = vi.fn()
    const reference = defineComponent({ mounted, setup() {
      const draft = ref('Draft')
      return () => h(publicUi.UiSurface, null, () => h('input', {
        value: draft.value, onInput: (event: Event) => { draft.value = (event.target as HTMLInputElement).value },
      }))
    } })
    const design = builtinUiDesign()
    const wrapper = mount(ApplicationShell, { props: { active: false, design, mode: 'display' }, slots: { default: () => h(reference) }, global: { stubs: { RouterLink: true } } })
    const input = wrapper.find('input')
    await input.setValue('Unsaved draft')
    expect(wrapper.findComponent(publicUi.UiSurface).attributes('data-button')).toBe('solid')
    const alternate = structuredClone(design)
    alternate.components = { button: 'outline', card: 'raised' }
    await wrapper.setProps({ design: alternate, active: true })
    expect(wrapper.findComponent(publicUi.UiSurface).attributes()).toMatchObject({ 'data-button': 'outline', 'data-card': 'raised' })
    expect(wrapper.find('input').element).toBe(input.element)
    expect((input.element as HTMLInputElement).value).toBe('Unsaved draft')
    expect(mounted).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('keeps public button loading and event semantics identical to the Core primitive', async () => {
    const click = vi.fn()
    const wrapper = mount(publicUi.UiButton, { props: { variant: 'primary' }, attrs: { onClick: click }, slots: { default: 'Local action' } })
    await wrapper.trigger('click')
    await wrapper.setProps({ loading: true })
    await wrapper.trigger('click')
    expect(click).toHaveBeenCalledTimes(1)
    expect(wrapper.attributes('aria-busy')).toBe('true')
    wrapper.unmount()
  })
})
