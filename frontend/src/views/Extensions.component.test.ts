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
    http.post.mockResolvedValue({ data: {} })
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

  it('shows and activates a staged application extension', async () => {
    const packageSha = 'c'.repeat(64)
    http.get.mockImplementation((url: string) => {
      if (url === '/api/v1/runtime-extensions/catalog') {
        return Promise.resolve({ data: [runtimeExtension] })
      }
      if (url === '/api/v1/modules/packages') {
        return Promise.resolve({
          data: [{
            module_id: 'org.example.application',
            version: '0.1.0',
            sha256: packageSha,
            manifest: {
              name: 'Example Application',
              description: 'Example local-first workflow application.',
              entrypoints: {
                core: 'application-extension.json',
                ui: 'compiled-ui.json'
              }
            }
          }]
        })
      }
      if (url === '/api/v1/application-extensions') {
        return Promise.resolve({ data: [] })
      }
      return Promise.resolve({ data: [] })
    })
    const wrapper = await mountView()

    const card = wrapper.findAll('.extension-card')
      .find(item => item.text().includes('Example Application'))
    expect(card).toBeDefined()
    expect(card!.text()).toContain('Application')
    expect(card!.text()).toContain('staged')
    expect(card!.text()).toContain('Delete package')

    const activate = card!.findAll('button')
      .find(button => button.text() === 'Install and activate')
    expect(activate).toBeDefined()
    await activate!.trigger('click')
    await flushPromises()

    expect(http.post).toHaveBeenCalledWith(
      `/api/v1/application-extensions/packages/${packageSha}/activate`
    )
    expect(compiledUi.getCatalog).toHaveBeenCalled()
  })

  it('asks for a declared device binding before application activation', async () => {
    const packageSha = '9'.repeat(64)
    const deviceId = `dev_${'1'.repeat(32)}`
    http.get.mockImplementation((url: string) => {
      if (url === '/api/v1/modules/packages') {
        return Promise.resolve({
          data: [{
            module_id: 'org.example.reader-app',
            version: '0.2.0',
            sha256: packageSha,
            manifest: {
              name: 'Reader Application',
              entrypoints: { core: 'application-extension.json' }
            }
          }]
        })
      }
      if (url === `/api/v1/application-extensions/packages/${packageSha}/configuration`) {
        return Promise.resolve({
          data: {
            fields: [{
              key: 'READER_DEVICE_ID',
              kind: 'device',
              label: 'Reader device',
              required: true,
              value: null
            }],
            devices: [{ device_id: deviceId, display_name: 'Front reader', role: 'node' }]
          }
        })
      }
      return Promise.resolve({ data: [] })
    })
    const wrapper = await mountView()
    const card = wrapper.findAll('.extension-card')
      .find(item => item.text().includes('Reader Application'))!

    await card.findAll('button')
      .find(button => button.text() === 'Install and activate')!
      .trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('Reader device')
    await wrapper.get('#application-config-READER_DEVICE_ID').setValue(deviceId)
    await wrapper.get('.modal-footer .version-btn').trigger('click')
    await flushPromises()

    expect(http.post).toHaveBeenCalledWith(
      `/api/v1/application-extensions/packages/${packageSha}/activate`,
      { configuration: { READER_DEVICE_ID: deviceId } }
    )
  })

  it('uninstalls an application while keeping its uploaded package visible', async () => {
    const packageSha = 'd'.repeat(64)
    http.get.mockImplementation((url: string) => {
      if (url === '/api/v1/runtime-extensions/catalog') {
        return Promise.resolve({ data: [] })
      }
      if (url === '/api/v1/modules/packages') {
        return Promise.resolve({
          data: [{
            module_id: 'org.example.application',
            version: '0.1.0',
            sha256: packageSha,
            manifest: {
              name: 'Example Application',
              entrypoints: {
                core: 'application-extension.json',
                ui: 'compiled-ui.json'
              }
            }
          }]
        })
      }
      if (url === '/api/v1/application-extensions') {
        return Promise.resolve({
          data: [{
            module_id: 'org.example.application',
            active_version: '0.1.0',
            status: 'active',
            enabled: true
          }]
        })
      }
      return Promise.resolve({ data: [] })
    })
    const wrapper = await mountView()
    const card = wrapper.findAll('.extension-card')
      .find(item => item.text().includes('Example Application'))
    const uninstall = card!.findAll('button')
      .find(button => button.text() === 'Uninstall')

    await uninstall!.trigger('click')
    expect(wrapper.text()).toContain('application data and uploaded package will be preserved')
    await wrapper.find('.modal-footer .button-danger').trigger('click')
    await flushPromises()

    expect(http.delete).toHaveBeenCalledWith(
      '/api/v1/application-extensions/org.example.application'
    )
    expect(compiledUi.getCatalog).toHaveBeenCalled()
  })

  it('deletes only the selected staged application package', async () => {
    http.get.mockImplementation((url: string) => {
      if (url === '/api/v1/modules/packages') {
        return Promise.resolve({
          data: [{
            module_id: 'org.example.application',
            version: '0.1.0',
            sha256: 'e'.repeat(64),
            manifest: {
              name: 'Example Application',
              entrypoints: {
                core: 'application-extension.json',
                ui: 'compiled-ui.json'
              }
            }
          }]
        })
      }
      return Promise.resolve({ data: [] })
    })
    const wrapper = await mountView()
    const card = wrapper.findAll('.extension-card')
      .find(item => item.text().includes('Example Application'))
    const remove = card!.findAll('button')
      .find(button => button.text() === 'Delete package')

    await remove!.trigger('click')
    await wrapper.find('.modal-footer .button-danger').trigger('click')
    await flushPromises()

    expect(http.delete).toHaveBeenCalledWith(
      '/api/v1/modules/compiled-ui/packages/org.example.application/0.1.0'
    )
  })

  it('keeps permanent application data erasure as a separate action', async () => {
    http.get.mockImplementation((url: string) => {
      if (url === '/api/v1/modules/packages') {
        return Promise.resolve({
          data: [{
            module_id: 'org.example.application',
            version: '0.1.0',
            sha256: 'f'.repeat(64),
            manifest: {
              name: 'Example Application',
              entrypoints: {
                core: 'application-extension.json',
                ui: 'compiled-ui.json'
              }
            }
          }]
        })
      }
      return Promise.resolve({ data: [] })
    })
    const wrapper = await mountView()
    const card = wrapper.findAll('.extension-card')
      .find(item => item.text().includes('Example Application'))
    const erase = card!.findAll('button')
      .find(button => button.text() === 'Erase data')

    await erase!.trigger('click')
    expect(wrapper.text()).toContain('This cannot be undone')
    await wrapper.find('.modal-footer .button-danger').trigger('click')
    await flushPromises()

    expect(http.delete).toHaveBeenCalledWith(
      '/api/v1/application-extensions/org.example.application/data'
    )
  })

  it('renders the uploaded extension name in the success message', async () => {
    http.post.mockResolvedValue({
      data: { module_id: 'org.example.application' }
    })
    const wrapper = await mountView()
    const input = wrapper.get('#extension-file')
    const file = new File(['package'], 'application.zip', { type: 'application/zip' })
    Object.defineProperty(input.element, 'files', { value: [file] })
    await input.trigger('change')
    await wrapper.get('.upload-form').trigger('submit')
    await flushPromises()

    expect(wrapper.find('.success-message').text()).toBe(
      'Extension "org.example.application" uploaded successfully!'
    )
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
