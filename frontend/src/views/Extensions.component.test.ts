import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const http = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn()
}))
const compiledUi = vi.hoisted(() => ({ getCatalog: vi.fn() }))
const runtimeRoutes = vi.hoisted(() => ({ reload: vi.fn() }))
const settingsStore = vi.hoisted(() => ({
  styleSettings: {
    cardBg: '#fff',
    textPrimary: '#111',
    cardBorder: '#ddd'
  },
  loadSettings: vi.fn(),
  updateCSSVariables: vi.fn()
}))

vi.mock('@/utils/dynamic-http', () => ({ default: http }))
vi.mock('@/utils/compiled-ui', () => ({ getCompiledUiCatalog: compiledUi.getCatalog }))
vi.mock('@/utils/runtime-extensions', () => ({ reloadRuntimeExtensionRoutes: runtimeRoutes.reload }))
vi.mock('@/stores/settings', () => ({ useSettingsStore: () => settingsStore }))
vi.mock('@/stores/theme', () => ({ useThemeStore: () => ({ theme: 'light' }) }))
vi.mock('vue-router', () => ({ useRouter: () => ({}) }))
vi.mock('@/utils/i18n', async () => {
  const { ref } = await import('vue')
  const currentLanguage = ref('en')
  return {
    useI18n: () => ({
      currentLanguage,
      t: (_key: string, fallback: string, params?: Record<string, string>) => {
        let result = fallback
        for (const [key, value] of Object.entries(params || {})) {
          result = result.replace(`{${key}}`, value)
        }
        return result
      }
    }),
    i18n: { loadExtensionTranslationsForExtension: vi.fn() }
  }
})

import Extensions from './Extensions.vue'

const runtimeExtension = {
  id: 'runtime:org.3mm.clock',
  source: 'runtime',
  name: 'Clock',
  type: 'widget',
  version: '1.2.0',
  description: 'A clock widget',
  status: 'active',
  is_enabled: true,
  created_at: '',
  can_manage: true,
  available_versions: ['1.1.0', '1.2.0'],
  package_sha256: 'a'.repeat(64),
  is_installed: true
}

const mountView = async () => {
  const wrapper = mount(Extensions, {
    global: {
      stubs: {
        RouterLink: { template: '<a><slot /></a>' }
      }
    }
  })
  await flushPromises()
  return wrapper
}

describe('Extensions management workflow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    localStorage.setItem('role', 'admin')
    http.get.mockResolvedValue({ data: [runtimeExtension] })
    http.patch.mockResolvedValue({ data: {} })
    http.delete.mockResolvedValue({ data: {} })
    compiledUi.getCatalog.mockResolvedValue([{
      module_id: 'org.3mm.indicator',
      version: '1.0.0',
      name: 'Indicator',
      source_sha256: 'b'.repeat(64)
    }])
    runtimeRoutes.reload.mockResolvedValue(undefined)
    settingsStore.loadSettings.mockResolvedValue(undefined)
  })

  it('shows both runtime and compiled extensions in one catalog', async () => {
    const wrapper = await mountView()

    expect(wrapper.text()).toContain('Clock')
    expect(wrapper.text()).toContain('Runtime')
    expect(wrapper.text()).toContain('Indicator')
    expect(wrapper.text()).toContain('Compiled UI')
  })

  it('disables a runtime extension and refreshes dynamic routes', async () => {
    const wrapper = await mountView()
    const toggle = wrapper.find('.extension-card .toggle-switch input')

    await toggle.setValue(false)
    await flushPromises()

    expect(http.patch).toHaveBeenCalledWith(
      '/api/v1/runtime-extensions/definitions/org.3mm.clock',
      { enabled: false }
    )
    expect(runtimeRoutes.reload).toHaveBeenCalledOnce()
    expect(wrapper.find('.extension-card .status-badge').text()).toBe('inactive')
  })

  it('uninstalls runtime code while preserving data by default', async () => {
    const wrapper = await mountView()
    const uninstall = wrapper.findAll('.extension-card button')
      .find(button => button.text() === 'Uninstall')
    expect(uninstall).toBeDefined()

    await uninstall!.trigger('click')
    expect(wrapper.text()).toContain('Data will be preserved')

    await wrapper.find('.modal-footer .button-danger').trigger('click')
    await flushPromises()

    expect(http.delete).toHaveBeenCalledWith(
      '/api/v1/runtime-extensions/definitions/org.3mm.clock',
      { params: { delete_data: false } }
    )
    expect(runtimeRoutes.reload).toHaveBeenCalledOnce()
  })
})
