import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const http = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn()
}))
const compiledUi = vi.hoisted(() => ({ getCatalog: vi.fn() }))
const runtimeRoutes = vi.hoisted(() => ({ reload: vi.fn() }))
const settingsStore = vi.hoisted(() => ({
  uiDesign: { components: { card: 'raised', button: 'outline' } },
  loadSettings: vi.fn(),
  loadThemeAppearance: vi.fn(),
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

const nativeMethods = ['showModal', 'close'].map(name => ({ name, descriptor: Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, name) }))
const mounted: Array<ReturnType<typeof mount>> = []

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

const themePackage = {
  module_id: 'org.example.theme',
  version: '1.0.0',
  sha256: '7'.repeat(64),
  name: { en: 'Example theme', translations: { bg: 'Примерна тема' } },
  enabled: false,
  is_installed: false,
  is_selected: false,
  status: 'staged',
}

const mountView = async () => {
  const wrapper = mount(Extensions, {
    global: {
      stubs: {
        RouterLink: { template: '<a><slot /></a>' }
      }
    }
  })
  mounted.push(wrapper)
  await flushPromises()
  return wrapper
}

describe('Extensions management workflow', () => {
  afterEach(() => {
    mounted.splice(0).forEach(wrapper => wrapper.unmount())
    vi.restoreAllMocks()
    for (const { name, descriptor } of nativeMethods) {
      if (descriptor) Object.defineProperty(HTMLDialogElement.prototype, name, descriptor)
      else Reflect.deleteProperty(HTMLDialogElement.prototype, name)
    }
  })
  beforeEach(() => {
    Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value: function(this: HTMLDialogElement) { this.open = true } })
    Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value: function(this: HTMLDialogElement) { this.open = false; this.dispatchEvent(new Event('close')) } })
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
    settingsStore.loadThemeAppearance.mockResolvedValue(undefined)
  })

  it('shows both runtime and compiled extensions in one catalog', async () => {
    const wrapper = await mountView()

    expect(wrapper.text()).toContain('Clock')
    expect(wrapper.text()).toContain('Runtime')
    expect(wrapper.text()).toContain('Indicator')
    expect(wrapper.text()).toContain('Compiled UI')
  })

  it.each([['admin', true, true], ['admin', false, false], ['user', true, false]])(
    'authority entry is scoped to an installed administrator-managed application (%s, %s)',
    async (role, installed, visible) => {
      localStorage.setItem('role', String(role))
      http.get.mockImplementation((url: string) => Promise.resolve({ data:
        url === '/api/v1/modules/packages' ? [{ module_id: 'org.example.reference', version: '1.0.0', sha256: '1'.repeat(64),
          manifest: { name: 'Reference application', entrypoints: { core: 'application-extension.json' } } }]
        : url === '/api/v1/application-extensions' && installed ? [{ module_id: 'org.example.reference', active_version: '1.0.0', status: 'disabled', enabled: false }]
        : url === '/api/v1/runtime-extensions/catalog' ? [runtimeExtension] : [],
      }))
      const wrapper = await mountView()
      expect(wrapper.find('.authority-manage-btn').exists()).toBe(visible)
      expect(http.get.mock.calls.some(([url]) => url.endsWith('/authority'))).toBe(false)
      expect(wrapper.findAll('.extension-card').filter(card => !card.text().includes('Reference application'))
        .every(card => !card.find('.authority-manage-btn').exists())).toBe(true)
      if (visible) {
        http.get.mockRejectedValueOnce({ response: { status: 409, data: { detail: { code: 'native_review_unavailable' } } } })
        await wrapper.get('.authority-manage-btn').trigger('click'); await flushPromises()
        expect(http.get).toHaveBeenLastCalledWith('/api/v1/application-extensions/org.example.reference/authority', { timeout: 12000 })
        expect(wrapper.get('dialog h2').text()).toBe('Application resource access')
      }
      expect(http.post).not.toHaveBeenCalled()
    },
  )

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
    expect(wrapper.get('dialog').attributes('aria-labelledby')).toBe(wrapper.get('dialog h2').attributes('id'))
    expect(wrapper.get('#application-config-READER_DEVICE_ID').attributes('autofocus')).toBeDefined()
    expect(wrapper.get('.ui-dialog-actions .version-btn').attributes('disabled')).toBeDefined()
    await wrapper.get('dialog').trigger('cancel')
    expect(wrapper.find('dialog').exists()).toBe(false)
    expect(http.post).not.toHaveBeenCalled()
    await card.findAll('button').find(button => button.text() === 'Install and activate')!.trigger('click')
    await flushPromises()
    await wrapper.get('#application-config-READER_DEVICE_ID').setValue(deviceId)
    await wrapper.get('.ui-dialog-actions .version-btn').trigger('click')
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
    await wrapper.find('.ui-dialog-actions .ui-button--danger').trigger('click')
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
    await wrapper.find('.ui-dialog-actions .ui-button--danger').trigger('click')
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
    await wrapper.find('.ui-dialog-actions .ui-button--danger').trigger('click')
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

    await wrapper.find('.ui-dialog-actions .ui-button--danger').trigger('click')
    await flushPromises()

    expect(http.delete).toHaveBeenCalledWith(
      '/api/v1/runtime-extensions/definitions/org.3mm.clock',
      { params: { delete_data: false } }
    )
    expect(runtimeRoutes.reload).toHaveBeenCalledOnce()
  })

  it('uses the single upload and enables only the exact theme version without selecting it', async () => {
    http.get.mockImplementation((url: string) => Promise.resolve({ data:
      url.endsWith('/themes/catalog') ? { items: [themePackage, { ...themePackage, version: '2.0.0', sha256: '8'.repeat(64) }] }
        : url.endsWith('/runtime-extensions/catalog') ? [runtimeExtension] : [],
    }))
    http.post.mockResolvedValue({ data: { module_id: themePackage.module_id } })
    const wrapper = await mountView()
    expect(wrapper.findAll('input[type=file]')).toHaveLength(1)
    const cards = wrapper.findAll('.extension-card').filter(card => card.text().includes('Example theme'))
    expect(cards).toHaveLength(2)
    expect(cards[0].text()).toContain('Theme')
    expect(cards[0].text()).toContain('Enabling does not change')
    const input = wrapper.get('#extension-file')
    Object.defineProperty(input.element, 'files', { value: [new File(['zip'], 'theme.zip')] })
    await input.trigger('change')
    await wrapper.get('.upload-form').trigger('submit')
    await flushPromises()
    expect(http.post).toHaveBeenCalledWith('/api/v1/modules/packages', expect.any(FormData))
    expect(http.post).toHaveBeenCalledTimes(1)
    const card = wrapper.findAll('.extension-card').find(card => card.text().includes('Example theme') && card.text().includes('1.0.0'))!
    expect(card.get('.toggle-switch input').attributes('disabled')).toBeUndefined()
    await card.get('.toggle-switch input').setValue(true)
    await flushPromises()
    expect(http.post).toHaveBeenLastCalledWith(`/api/v1/modules/themes/packages/${themePackage.sha256}/enable`)
    expect(http.post).toHaveBeenCalledTimes(2)
    expect(runtimeRoutes.reload).not.toHaveBeenCalled()
  })

  it('keeps disable/delete recovery for an unavailable selected theme and refreshes appearance', async () => {
    http.get.mockImplementation((url: string) => Promise.resolve({ data:
      url.endsWith('/themes/catalog') ? { items: [{ ...themePackage, enabled: true, is_installed: true, is_selected: true, status: 'unavailable' }] } : [],
    }))
    const wrapper = await mountView()
    const card = wrapper.findAll('.extension-card').find(card => card.text().includes('Example theme'))!
    expect(card.text()).toContain('Selected')
    expect(card.text()).toContain('Package missing or invalid')
    await card.get('.toggle-switch input').setValue(false)
    await flushPromises()
    expect(http.post).toHaveBeenCalledWith(`/api/v1/modules/themes/packages/${themePackage.sha256}/disable`)
    expect(settingsStore.loadThemeAppearance).toHaveBeenCalledOnce()
    await wrapper.findAll('.extension-card').find(card => card.text().includes('Example theme'))!.get('.delete-btn').trigger('click')
    expect(wrapper.get('.modal-body').text()).toContain('An active theme will return to built-in settings')
    expect(wrapper.find('.modal-body input[type=checkbox]').exists()).toBe(false)
    await wrapper.get('.ui-dialog-actions .ui-button--danger').trigger('click')
    await flushPromises()
    expect(http.delete).toHaveBeenCalledWith(`/api/v1/modules/themes/packages/${themePackage.sha256}`)
    expect(settingsStore.loadThemeAppearance).toHaveBeenCalledTimes(2)
    expect(runtimeRoutes.reload).not.toHaveBeenCalled()
  })

  it('does not request the private theme catalog for a non-administrator', async () => {
    localStorage.setItem('role', 'user')
    const wrapper = await mountView()
    expect(http.get.mock.calls.some(([url]) => url === '/api/v1/modules/themes/catalog')).toBe(false)
    expect(wrapper.find('#extension-file').exists()).toBe(false)
  })
  it('uses the common theme variants and keeps compiled controls read-only', async () => {
    const wrapper = await mountView()
    expect(wrapper.attributes('data-card')).toBe('raised')
    expect(wrapper.attributes('data-button')).toBe('outline')
    expect(wrapper.findAll('.extension-card.ui-section')).toHaveLength(2)
    expect(wrapper.findAll('[style]')).toHaveLength(0)
    const compiled = wrapper.findAll('.extension-card').find(card => card.text().includes('Indicator'))!
    expect(compiled.get('input[type=checkbox]').attributes('disabled')).toBeDefined()
    expect(compiled.get('input[type=checkbox]').attributes('aria-label')).toContain('Indicator')
    expect(compiled.find('.extension-actions').exists()).toBe(false)
    expect(http.post).not.toHaveBeenCalled()
  })

  it('cancels a destructive confirmation with Escape and leaves data unchanged', async () => {
    const wrapper = await mountView()
    await wrapper.get('.extension-card .delete-btn').trigger('click')
    expect(wrapper.get('dialog button[autofocus]').text()).toBe('Cancel')
    expect(wrapper.get('dialog').attributes('aria-labelledby')).toBe(wrapper.get('dialog h2').attributes('id'))
    expect(wrapper.get('dialog input[type=checkbox]').element).toHaveProperty('checked', false)
    await wrapper.get('dialog').trigger('cancel')
    expect(wrapper.find('dialog').exists()).toBe(false)
    expect(http.delete).not.toHaveBeenCalled()
  })

  it('keeps the removal target and dialog stable while its request is pending', async () => {
    let finish!: (result: { data: object }) => void
    http.delete.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const wrapper = await mountView()
    await wrapper.get('.extension-card .delete-btn').trigger('click')
    await wrapper.get('.ui-dialog-actions .ui-button--danger').trigger('click')
    await flushPromises()
    expect(wrapper.get('.ui-dialog-actions button[autofocus]').attributes('disabled')).toBeDefined()
    await wrapper.get('dialog').trigger('cancel')
    await wrapper.get('dialog .ui-button--quiet').trigger('click')
    expect(wrapper.find('dialog').exists()).toBe(true)
    expect(http.delete).toHaveBeenCalledOnce()
    finish({ data: {} })
    await flushPromises()
    expect(wrapper.find('dialog').exists()).toBe(false)
    expect(http.delete).toHaveBeenCalledWith(
      '/api/v1/runtime-extensions/definitions/org.3mm.clock', { params: { delete_data: false } },
    )
  })

  it('keeps a non-manageable package disabled without removing its catalog entry', async () => {
    localStorage.setItem('role', 'user')
    http.get.mockResolvedValue({ data: [{ ...runtimeExtension, can_manage: false }] })
    const wrapper = await mountView()
    const card = wrapper.get('.extension-card')
    expect(card.text()).toContain('Clock')
    expect(card.get('input[type=checkbox]').attributes('disabled')).toBeDefined()
    expect(card.get('.version-btn').attributes('disabled')).toBeDefined()
    expect(card.find('.delete-btn').exists()).toBe(false)
    expect(wrapper.find('.ai-builder-link').exists()).toBe(false)
  })

  it('shows removal errors inside the open dialog and allows a safe cancellation', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    http.delete.mockRejectedValueOnce({ response: { data: { detail: 'Removal rejected.' } } })
    const wrapper = await mountView()
    await wrapper.get('.extension-card .delete-btn').trigger('click')
    await wrapper.get('.ui-dialog-actions .ui-button--danger').trigger('click')
    await flushPromises()
    expect(wrapper.get('dialog [role=alert]').text()).toBe('Removal rejected.')
    expect(wrapper.get('dialog button[autofocus]').attributes('disabled')).toBeUndefined()
    await wrapper.get('dialog').trigger('cancel')
    expect(wrapper.find('dialog').exists()).toBe(false)
    expect(http.delete).toHaveBeenCalledOnce()
  })
})
