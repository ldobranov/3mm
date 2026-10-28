import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Ref } from 'vue'
import { useI18n } from '@/utils/i18n'

const http = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn()
}))
const compiledUi = vi.hoisted(() => ({ getCatalog: vi.fn() }))
const connectorClient = vi.hoisted(() => ({ inspect: vi.fn(), save: vi.fn(), outcome: vi.fn() }))
const settingsStore = vi.hoisted(() => ({
  uiDesign: { components: { card: 'raised', button: 'outline' } },
  loadSettings: vi.fn(),
  loadThemeAppearance: vi.fn(),
  updateCSSVariables: vi.fn()
}))

vi.mock('@/utils/dynamic-http', () => ({ default: http }))
vi.mock('@/utils/compiled-ui', () => ({ getCompiledUiCatalog: compiledUi.getCatalog }))
vi.mock('@/components/extensions/connector-settings', async importOriginal => ({
  ...await importOriginal<typeof import('@/components/extensions/connector-settings')>(),
  createConnectorSettingsClient: () => connectorClient,
}))
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
    i18n: { refreshLanguages: vi.fn() }
  }
})

import Extensions from './Extensions.vue'
import { consentPreview, consentResult } from '@/components/extensions/application-consent.fixtures'
import { connectorSettings } from '@/components/extensions/connector-settings.fixtures'

const nativeMethods = ['showModal', 'close'].map(name => ({ name, descriptor: Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, name) }))
const mounted: Array<ReturnType<typeof mount>> = []

const oldRuntimeFixture = {
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
    (useI18n().currentLanguage as Ref<string>).value = 'en'
    Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value: function(this: HTMLDialogElement) { this.open = true } })
    Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value: function(this: HTMLDialogElement) { this.open = false; this.dispatchEvent(new Event('close')) } })
    vi.clearAllMocks()
    localStorage.clear()
    localStorage.setItem('role', 'admin')
    http.get.mockImplementation((url: string) => Promise.resolve({data:
      url === '/api/v1/modules/packages' ? [{module_id:'org.3mm.clock',version:'1.2.0',sha256:'a'.repeat(64),manifest:{name:'Clock',entrypoints:{core:'application-extension.json'}}}]
      : url === '/api/v1/application-extensions' ? [{module_id:'org.3mm.clock',active_version:'1.2.0',status:'active',enabled:true}]
      : []}))
    http.post.mockResolvedValue({ data: {} })
    http.patch.mockResolvedValue({ data: {} })
    http.delete.mockResolvedValue({ data: {} })
    compiledUi.getCatalog.mockResolvedValue([{
      module_id: 'org.3mm.indicator',
      version: '1.0.0',
      name: 'Indicator',
      source_sha256: 'b'.repeat(64)
    }])
    settingsStore.loadSettings.mockResolvedValue(undefined)
    settingsStore.loadThemeAppearance.mockResolvedValue(undefined)
  })

  it('shows applications and compiled extensions without querying retired catalogs', async () => {
    const wrapper = await mountView()

    expect(wrapper.text()).toContain('Clock')
    expect(wrapper.text()).toContain('Application')
    expect(http.get.mock.calls.some(([url]) => url.includes('runtime-extensions'))).toBe(false)
    expect(wrapper.text()).toContain('Indicator')
    expect(wrapper.text()).toContain('Compiled UI')
  })

  it.each([['admin', true], ['user', false]])('shows settings only for declared connector packages and current admin UI (%s)', async (role, visible) => {
    localStorage.setItem('role', role)
    http.get.mockImplementation((url: string) => Promise.resolve({ data:
      url === '/api/v1/modules/packages' ? [
        { module_id: 'org.example.connection', version: '1.0.0', sha256: 'c'.repeat(64), has_connector_settings: true,
          manifest: { name: 'Connection app', entrypoints: { core: 'application-extension.json' } } },
        { module_id: 'org.example.plain', version: '1.0.0', sha256: 'd'.repeat(64), has_connector_settings: false,
          manifest: { name: 'Plain app', entrypoints: { core: 'application-extension.json' } } },
      ] : [] }))
    const wrapper = await mountView()
    expect(wrapper.findAll('.application-settings-btn')).toHaveLength(visible ? 1 : 0)
    if (visible) expect(wrapper.get('.application-settings-btn').attributes('aria-label')).toBe('Application settings')
    expect(http.post).not.toHaveBeenCalled()
  })
  it('keeps the Core settings draft mounted when the Extensions language changes', async () => {
    http.get.mockImplementation((url: string) => Promise.resolve({ data: url === '/api/v1/modules/packages'
      ? [{ module_id: 'org.example.connection', version: '1.0.0', sha256: 'a'.repeat(64), has_connector_settings: true,
        manifest: { name: 'Connection app', entrypoints: { core: 'application-extension.json' } } }] : [] }))
    connectorClient.inspect.mockResolvedValue(connectorSettings())
    const wrapper = await mountView()
    await wrapper.get('.application-settings-btn').trigger('click'); await flushPromises()
    await wrapper.get('.connector-origin').setValue('https://draft.example')
    await wrapper.get('.connector-password').setValue('private-draft')
    ;(useI18n().currentLanguage as Ref<string>).value = 'bg'
    await flushPromises()
    expect(wrapper.get('dialog h2').text()).toBe('Настройки на приложението')
    expect((wrapper.get('.connector-origin').element as HTMLInputElement).value).toBe('https://draft.example')
    expect((wrapper.get('.connector-password').element as HTMLInputElement).value).toBe('private-draft')
    expect(connectorClient.inspect).toHaveBeenCalledOnce()
    expect(connectorClient.save).not.toHaveBeenCalled()
  })

  it.each([['admin', true, true], ['admin', false, false], ['user', true, false]])(
    'authority entry is scoped to an installed administrator-managed application (%s, %s)',
    async (role, installed, visible) => {
      localStorage.setItem('role', String(role))
      http.get.mockImplementation((url: string) => Promise.resolve({ data:
        url === '/api/v1/modules/packages' ? [{ module_id: 'org.example.reference', version: '1.0.0', sha256: '1'.repeat(64),
          manifest: { name: 'Reference application', entrypoints: { core: 'application-extension.json' } } }]
        : url === '/api/v1/application-extensions' && installed ? [{ module_id: 'org.example.reference', active_version: '1.0.0', status: 'disabled', enabled: false }]
        : url === '/api/v1/runtime-extensions/catalog' ? [oldRuntimeFixture] : [],
      }))
      const wrapper = await mountView()
      expect(wrapper.find('.authority-manage-btn').exists()).toBe(visible)
      expect(wrapper.find('.command-resources-btn').exists()).toBe(visible)
      expect(http.get.mock.calls.some(([url]) => url.endsWith('/authority'))).toBe(false)
      expect(wrapper.findAll('.extension-card').filter(card => !card.text().includes('Reference application'))
        .every(card => !card.find('.authority-manage-btn').exists())).toBe(true)
      if (visible) {
        http.post.mockRejectedValueOnce({ response: { status: 409, data: { detail: { code: 'authority_unavailable' } } } })
        await wrapper.get('.authority-manage-btn').trigger('click'); await flushPromises()
        expect(http.post).toHaveBeenCalledWith('/api/v1/application-extensions/org.example.reference/authority/consent/preview', expect.objectContaining({ request_id: expect.any(String) }), { timeout: 12000 })
        expect(wrapper.get('dialog h2').text()).toBe('Application access')
      }
      expect(http.post.mock.calls.some(([url]) => url.endsWith('/consent/allow'))).toBe(false)
    },
  )

  it('shows and activates a staged application extension', async () => {
    const packageSha = 'c'.repeat(64)
    http.get.mockImplementation((url: string) => {
      if (url === '/api/v1/runtime-extensions/catalog') {
        return Promise.resolve({ data: [oldRuntimeFixture] })
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

  it.each([false, true])('opens access after first activation, preserves saved consent on re-enable (%s)', async (saved) => {
    const original = http.get.getMockImplementation()!
    http.get.mockImplementation((url: string, ...args: unknown[]) => {
      if (url === '/api/v1/modules/packages') return Promise.resolve({ data: [{
        module_id: 'org.example.fresh', version: '1.0.0', sha256: 'd'.repeat(64),
        manifest: { name: 'Fresh application', entrypoints: { core: 'application-extension.json' } },
      }] })
      if (url === '/api/v1/application-extensions') return Promise.resolve({ data: saved ? [{
        module_id: 'org.example.fresh', active_version: '1.0.0', status: 'disabled', enabled: false,
      }] : [] })
      if (url.endsWith('/configuration')) return Promise.resolve({ data: { fields: [], devices: [] } })
      if (url.endsWith('/authority')) return Promise.resolve({ data: { access_saved: saved, grant_effective: false } })
      return original(url, ...args)
    })
    http.post.mockResolvedValue({ data: {} })
    const wrapper = await mountView()
    const activate = wrapper.findAll('.extension-card').find(card => card.text().includes('Fresh application'))!
      .findAll('button').find(button => button.text() === (saved ? 'Activate version' : 'Install and activate'))!
    await activate.trigger('click'); await flushPromises()
    expect(http.post).toHaveBeenCalledWith('/api/v1/application-extensions/packages/' + 'd'.repeat(64) + '/activate')
    expect(wrapper.find('.authority-dialog').exists()).toBe(!saved)
    expect(http.post.mock.calls.some(([url]) => url.endsWith('/consent/preview'))).toBe(!saved)
    expect(http.post.mock.calls.some(([url]) => url.endsWith('/consent/allow'))).toBe(false)
  })

  it.each([false, true])('prepares an update without execution and requires new consent before activation (configuration: %s)', async configurable => {
    const moduleId = 'org.example.reference'
    const oldSha = 'a'.repeat(64), newSha = 'b'.repeat(64)
    let enabled = true, prepared = false, saved = false
    const status = () => ({ installation_id: 7, mode: 'enforced', installation_status: enabled ? 'active' : 'disabled',
      installation_enabled: enabled, artifact_sha256: prepared ? newSha : oldSha, scopes: [], native_reviews: [],
      grant_state: 'active', grant_record_revision: '3'.repeat(32), grant_effective: enabled && saved, isolation_proven: false })
    const reviewed = () => consentPreview(status(), { commands: [], connectors: [] }, moduleId)
    http.get.mockImplementation((url: string) => Promise.resolve({ data:
      url === '/api/v1/modules/packages' ? [1, 2, 3].map(id => ({ id, module_id: moduleId,
        version: `1.0.${id}`, sha256: id === 1 ? oldSha : id === 2 ? newSha : 'c'.repeat(64),
        manifest: { name: 'Reference application', entrypoints: { core: 'application-extension.json' } } }))
      : url === '/api/v1/application-extensions' ? [{ module_id: moduleId, package_sha256: prepared ? newSha : oldSha,
        active_version: prepared ? null : '1.0.1', enabled, status: enabled ? 'active' : 'disabled' }]
      : url.endsWith('/authority') ? status()
      : url.endsWith('/configuration') ? { fields: configurable ? [{ key: 'DEVICE_ID', kind: 'device', label: 'Device', required: true, value: 'dev_' + '1'.repeat(32) }] : [],
        devices: [{ device_id: 'dev_' + '1'.repeat(32), display_name: 'Device', role: 'node' }] } : [] }))
    http.post.mockImplementation((url: string) => {
      if (url.endsWith('/disable')) enabled = false
      if (url.endsWith('/stage')) prepared = true
      if (url.endsWith('/consent/preview')) return Promise.resolve({ data: reviewed() })
      if (url.endsWith('/consent/allow')) { saved = true; return Promise.resolve({ data: consentResult(reviewed()) }) }
      if (url.endsWith('/activate')) { expect(saved).toBe(true); enabled = true }
      return Promise.resolve({ data: {} })
    })
    const wrapper = await mountView()
    const card = () => wrapper.get('.extension-card')
    await card().get('select').setValue('1.0.2')
    expect(card().get('.version-btn').attributes('disabled')).toBeDefined()
    expect(card().text()).toContain('Turn off the current version')
    await card().get('input[type="checkbox"]').setValue(false); await flushPromises()
    await card().get('select').setValue('1.0.2')
    expect(card().get('.version-btn').text()).toBe('Prepare version')
    await card().get('.version-btn').trigger('click'); await flushPromises()
    if (configurable) { await wrapper.get('.ui-dialog-actions .version-btn').trigger('click'); await flushPromises() }
    expect(http.post).toHaveBeenCalledWith(`/api/v1/application-extensions/packages/${newSha}/stage`, {
      request_id: expect.stringMatching(/^[0-9a-f]{32}$/), expected_artifact_sha256: oldSha,
      expected_revision: '3'.repeat(32), configuration: configurable ? { DEVICE_ID: 'dev_' + '1'.repeat(32) } : {},
    }, { timeout: 12000 })
    expect(card().get('.extension-version').text()).toContain('1.0.2') // Prepared pin, not newer catalog 1.0.3.
    expect(wrapper.find('.authority-dialog').exists()).toBe(true)
    expect(http.post.mock.calls.some(([url]) => url.endsWith('/activate'))).toBe(false)
    const allow = wrapper.findAll('button').find(button => button.text() === 'Allow access')!
    await allow.trigger('click'); await flushPromises()
    const close = wrapper.findAll('.authority-dialog button').find(button => button.text() === 'Close')!
    await close.trigger('click'); await flushPromises()
    await card().get('.version-btn').trigger('click'); await flushPromises()
    if (configurable) { await wrapper.get('.ui-dialog-actions .version-btn').trigger('click'); await flushPromises() }
    expect(http.post.mock.calls.filter(([url]) => url.endsWith('/activate'))).toHaveLength(1)
    expect(http.post.mock.calls.filter(([url]) => url.endsWith('/stage'))).toHaveLength(1)
  })

  it.each(['stale', 'timeout'])('does not dispatch activation or repeat preparation after %s', async fault => {
    const moduleId = 'org.example.reference'
    http.get.mockImplementation((url: string) => Promise.resolve({ data:
      url === '/api/v1/modules/packages' ? [1, 2].map(id => ({ id, module_id: moduleId, version: `1.0.${id}`,
        sha256: String(id).repeat(64), manifest: { name: 'Reference', entrypoints: { core: 'application-extension.json' } } }))
      : url === '/api/v1/application-extensions' ? [{ module_id: moduleId, package_sha256: '1'.repeat(64), active_version: '1.0.1', status: 'disabled', enabled: false }]
      : url.endsWith('/authority') ? { installation_id: 7, mode: 'enforced', installation_status: 'disabled', installation_enabled: false,
        artifact_sha256: (fault === 'stale' ? 'f' : '1').repeat(64), scopes: [], native_reviews: [], grant_state: 'active',
        grant_record_revision: '3'.repeat(32), grant_effective: false, isolation_proven: false } : [] }))
    http.post.mockRejectedValue({ response: { status: 409, data: { detail: 'Preparation outcome could not be confirmed' } } })
    const wrapper = await mountView()
    await wrapper.get('select').setValue('1.0.2')
    await wrapper.get('.version-btn').trigger('click'); await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toBeTruthy()
    expect(http.post.mock.calls.filter(([url]) => url.endsWith('/stage'))).toHaveLength(fault === 'stale' ? 0 : 1)
    expect(http.post.mock.calls.some(([url]) => url.endsWith('/activate') || url.endsWith('/consent/allow'))).toBe(false)
    expect(wrapper.find('.authority-dialog').exists()).toBe(false)
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
            }, { key:'OPTIONAL_DEVICE_ID', kind:'device', label:'Optional device', required:false, value:null }],
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

  it.each([false,true])('allows every optional reader to remain empty or be cleared (available: %s)',async available=>{
    const sha='8'.repeat(64),device='dev_'+'1'.repeat(32)
    http.get.mockImplementation((url:string)=>Promise.resolve({data:url==='/api/v1/modules/packages'?
      [{module_id:'org.example.optional',version:'1.0.0',sha256:sha,manifest:{name:'Optional readers',entrypoints:{core:'application-extension.json'}}}]
      :url.endsWith('/configuration')?{fields:[{key:'READER_DEVICE_ID',kind:'device',label:'Reader',required:false,value:available?device:null}],devices:available?[{device_id:device,display_name:'Reader',role:'node'}]:[]}:[]}))
    const wrapper=await mountView()
    await wrapper.findAll('.extension-card').find(c=>c.text().includes('Optional readers'))!.findAll('button').find(b=>b.text()==='Install and activate')!.trigger('click')
    await flushPromises()
    const selector=wrapper.get('#application-config-READER_DEVICE_ID')
    expect(selector.get('option[value=""]').attributes('disabled')).toBeUndefined()
    if(available)await selector.setValue('')
    expect(wrapper.get('.ui-dialog-actions .version-btn').attributes('disabled')).toBeUndefined()
    await wrapper.get('.ui-dialog-actions .version-btn').trigger('click');await flushPromises()
    expect(http.post).toHaveBeenCalledWith(`/api/v1/application-extensions/packages/${sha}/activate`,{configuration:{}})
  })

  it.each(['admin','user'])('derives kiosk management from the installed artifact and admin (%s)',async role=>{
    localStorage.setItem('role',role)
    const current='6'.repeat(64),candidate='7'.repeat(64)
    http.get.mockImplementation((url:string)=>Promise.resolve({data:url==='/api/v1/modules/packages'?[
      {module_id:'org.example.terminal',version:'1.0.0',sha256:current,has_kiosk_interface:false,manifest:{name:'Terminals',entrypoints:{core:'application-extension.json'}}},
      {module_id:'org.example.terminal',version:'1.0.1',sha256:candidate,has_kiosk_interface:true,manifest:{name:'Terminals',entrypoints:{core:'application-extension.json'}}}]
      :url==='/api/v1/application-extensions'?[{module_id:'org.example.terminal',active_version:'1.0.0',package_sha256:current,status:'active',enabled:true}]:[]}))
    const wrapper=await mountView()
    expect(wrapper.findAll('button').some(b=>b.text()==='Kiosk terminals')).toBe(false)
  })

  it.each(['activating', 'disabling', 'uninstalling', 'recovering', 'recovery_required'])(
    'keeps an unfinished %s installation removable before any version became active', async status => {
      const moduleId = 'org.example.failed-install'
      const sha = '2'.repeat(64)
      let installed = true
      http.get.mockImplementation((url: string) => Promise.resolve({ data:
        url === '/api/v1/modules/packages' ? [{ module_id: moduleId, version: '0.1.0', sha256: sha,
          manifest: { name: 'Failed Application', entrypoints: { core: 'application-extension.json' } } }]
        : url === '/api/v1/application-extensions' && installed ? [{ module_id: moduleId,
          active_version: null, status, enabled: false }]
        : [],
      }))
      http.delete.mockImplementation(async (url: string) => {
        expect(url).toBe(`/api/v1/application-extensions/${moduleId}`)
        installed = false
        return { data: { status: 'uninstalled' } }
      })
      const wrapper = await mountView()
      const card = () => wrapper.findAll('.extension-card').find(item => item.text().includes('Failed Application'))!
      expect(card().text()).toContain('Recovery required')
      expect(card().text()).toContain('Recover to a verified stopped state')
      expect(card().text()).not.toContain('Delete package')
      expect(card().text()).not.toContain('Erase data')
      expect(card().get('input[type="checkbox"]').attributes('disabled')).toBeDefined()
      expect(card().get('.version-btn').attributes('disabled')).toBeDefined()
      await card().findAll('button').find(button => button.text() === 'Uninstall')!.trigger('click')
      expect(wrapper.get('dialog').text()).toContain('If runtime cleanup cannot be confirmed, removal will remain blocked')
      expect(wrapper.get('dialog').text()).toContain('data and the uploaded package will be preserved')
      await wrapper.get('.ui-dialog-actions .ui-button--danger').trigger('click')
      await flushPromises()
      expect(http.delete).toHaveBeenCalledExactlyOnceWith(`/api/v1/application-extensions/${moduleId}`)
      expect(http.post).not.toHaveBeenCalled()
      expect(card().text()).toContain('Delete package')
    },
  )

  it('recovers through the web and opens a fresh access review without activation or deletion', async () => {
    const moduleId = 'org.example.recover'
    const sha = '4'.repeat(64)
    let status = 'recovery_required'
    http.get.mockImplementation((url: string) => Promise.resolve({ data:
      url === '/api/v1/modules/packages' ? [{ module_id: moduleId, version: '1.0.0', sha256: sha,
        manifest: { name: 'Recover example', entrypoints: { core: 'application-extension.json' } } }]
      : url === '/api/v1/application-extensions' ? [{ module_id: moduleId, package_sha256: sha,
        active_version: null, status, enabled: false, error: null }] : [],
    }))
    http.post.mockImplementation(async (url: string) => {
      if (!url.endsWith('/lifecycle/recover')) throw new Error('Access preview unavailable in this fixture')
      status = 'disabled'
      return { data: { module_id: moduleId, active_version: null, status, enabled: false } }
    })
    const wrapper = await mountView()
    await wrapper.get('.application-recovery-btn').trigger('click'); await flushPromises()
    await wrapper.get('.application-recovery input').setValue(true)
    await wrapper.get('.recover-confirm-btn').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('The application is stopped. Review access')
    expect(wrapper.find('.application-recovery-btn').exists()).toBe(false)
    expect(wrapper.get('dialog').text()).toContain('Application access')
    expect(http.post.mock.calls.filter(([url]) => String(url).endsWith('/lifecycle/recover'))).toHaveLength(1)
    expect(http.post.mock.calls.some(([url]) => String(url).endsWith('/activate'))).toBe(false)
    expect(http.delete).not.toHaveBeenCalled()
  })

  it('keeps recovery available without the optional compiled UI and package catalogs', async () => {
    compiledUi.getCatalog.mockRejectedValue(new Error('UI unavailable'))
    http.get.mockImplementation((url: string) => url.startsWith('/api/v1/modules/')
      ? Promise.reject(new Error('Packages unavailable'))
      : Promise.resolve({ data: url === '/api/v1/application-extensions'
        ? [{ module_id: 'org.example.unavailable', active_version: null, status: 'recovery_required', enabled: false }]
        : [] }))
    const wrapper = await mountView()
    expect(wrapper.text()).toContain('org.example.unavailable')
    expect(wrapper.text()).toContain('Some package details are unavailable')
    expect(wrapper.get('.application-recovery-btn').attributes('disabled')).toBeUndefined()
    await wrapper.get('.application-recovery-btn').trigger('click'); await flushPromises()
    expect(wrapper.get('.application-recovery').text()).toContain('recovery_required')
    expect(http.post).not.toHaveBeenCalled()
  })

  it.each(['version', 'configuration', 'toggle'])(
    'refreshes a failed %s activation into the removable installation without retrying it', async action => {
      const moduleId = 'org.example.failed-activation'
      const sha = '3'.repeat(64)
      const deviceId = `dev_${'2'.repeat(32)}`
      let failed = false
      http.get.mockImplementation((url: string) => Promise.resolve({ data:
        url === '/api/v1/modules/packages' ? [{ module_id: moduleId, version: '0.1.0', sha256: sha,
          manifest: { name: 'Activation Failure', entrypoints: { core: 'application-extension.json' } } }]
        : url === '/api/v1/application-extensions' ? (failed || action === 'toggle' ? [{ module_id: moduleId,
          active_version: null, status: failed ? 'recovery_required' : 'disabled', enabled: false }] : [])
        : url.endsWith('/configuration') ? { fields: action === 'configuration' ? [{ key: 'DEVICE_ID', kind: 'device',
          label: 'Device', required: true, value: deviceId }] : [], devices: [{ device_id: deviceId, display_name: 'Node' }] }
        : [],
      }))
      http.post.mockImplementation(async (url: string) => {
        expect(url).toBe(`/api/v1/application-extensions/packages/${sha}/activate`)
        failed = true
        throw { response: { status: 409, data: { detail: 'Application activation requires recovery' } } }
      })
      const wrapper = await mountView()
      const card = () => wrapper.findAll('.extension-card').find(item => item.text().includes('Activation Failure'))!
      if (action === 'toggle') {
        await card().get('input[type="checkbox"]').setValue(true)
      } else {
        await card().findAll('button').find(button => button.text() === 'Install and activate')!.trigger('click')
        await flushPromises()
        if (action === 'configuration') {
          await wrapper.get('.ui-dialog-actions .version-btn').trigger('click')
        }
      }
      await flushPromises()
      expect(http.post).toHaveBeenCalledOnce()
      expect(http.get.mock.calls.filter(([url]) => url === '/api/v1/application-extensions').length).toBeGreaterThanOrEqual(2)
      expect(wrapper.find('dialog').exists()).toBe(false)
      expect(wrapper.text()).toContain('Application activation requires recovery')
      expect(card().text()).toContain('Recovery required')
      expect(card().findAll('button').some(button => button.text() === 'Uninstall')).toBe(true)
      expect(card().text()).not.toContain('Delete package')
      expect(card().text()).not.toContain('Erase data')
      expect(card().get('.version-btn').attributes('disabled')).toBeDefined()
      expect(http.delete).not.toHaveBeenCalled()
    },
  )

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

  it('keeps preserved data visible after the last application package is deleted', async () => {
    let packagePresent = true
    let dataPresent = true
    const moduleId = 'org.example.retired'
    http.get.mockImplementation((url: string) => Promise.resolve({ data:
      url === '/api/v1/modules/packages' && packagePresent
        ? [{ module_id: moduleId, version: '1.0.0', sha256: 'e'.repeat(64),
          manifest: { name: 'Retired application', entrypoints: { core: 'application-extension.json' } } }]
        : url === '/api/v1/application-extensions/retained-data' && dataPresent
          ? [{ module_id: moduleId, instance_id: '1'.repeat(24), name: 'Retired application' }]
          : [],
    }))
    http.delete.mockImplementation(async (url: string) => {
      if (url.endsWith('/data')) dataPresent = false
      else packagePresent = false
      return { data: {} }
    })
    const wrapper = await mountView()
    expect(wrapper.find('.retained-data-section').exists()).toBe(false)
    const remove = wrapper.findAll('.extension-card button').find(button => button.text() === 'Delete package')
    await remove!.trigger('click')
    await wrapper.get('.ui-dialog-actions .ui-button--danger').trigger('click'); await flushPromises()
    expect(wrapper.findAll('.extension-card').some(card => card.text().includes('Retired application'))).toBe(false)
    expect(wrapper.get('.retained-data-row').text()).toContain('Retired application')
    expect(http.delete).not.toHaveBeenCalledWith(`/api/v1/application-extensions/${moduleId}/data`)
    await wrapper.get('.retained-data-row button').trigger('click')
    expect(wrapper.get('dialog').text()).toContain('This cannot be undone')
    expect(wrapper.get('dialog').text()).not.toContain(' v1.0.0')
    await wrapper.get('.ui-dialog-actions .ui-button--danger').trigger('click'); await flushPromises()
    expect(http.delete).toHaveBeenLastCalledWith(`/api/v1/application-extensions/${moduleId}/data`)
    expect(wrapper.find('.retained-data-section').exists()).toBe(false)
  })

  it('keeps retained data available after erasure fails', async () => {
    http.get.mockImplementation((url: string) => Promise.resolve({ data:
      url === '/api/v1/application-extensions/retained-data'
        ? [{ module_id: 'org.example.retired', instance_id: '1'.repeat(24), name: 'Retired application' }] : [],
    }))
    http.delete.mockRejectedValue({ response: { status: 409, data: { detail: 'Runtime stop is unconfirmed' } } })
    const wrapper = await mountView()
    await wrapper.get('.retained-data-row button').trigger('click')
    await wrapper.get('.ui-dialog-actions .ui-button--danger').trigger('click'); await flushPromises()
    expect(wrapper.get('dialog').text()).toContain('Runtime stop is unconfirmed')
    expect(wrapper.find('.retained-data-row').exists()).toBe(true)
  })

  it('reports a retained-data catalog failure without hiding extension management', async () => {
    const original = http.get.getMockImplementation()!
    http.get.mockImplementation((url: string, ...args: unknown[]) => url === '/api/v1/application-extensions/retained-data'
      ? Promise.reject(new Error('catalog unavailable')) : original(url, ...args))
    const wrapper = await mountView()
    expect(wrapper.text()).toContain('Clock')
    expect(wrapper.text()).toContain('Preserved application data could not be loaded')
    expect(http.delete).not.toHaveBeenCalled()
  })

  it('does not request or expose retained application data to a non-administrator', async () => {
    localStorage.setItem('role', 'user')
    const wrapper = await mountView()
    expect(http.get.mock.calls.some(([url]) => url === '/api/v1/application-extensions/retained-data')).toBe(false)
    expect(wrapper.find('.retained-data-section').exists()).toBe(false)
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

  it('disables the application through its common lifecycle', async () => {
    const wrapper = await mountView()
    await wrapper.get('.extension-card .toggle-switch input').setValue(false); await flushPromises()
    expect(http.post).toHaveBeenCalledWith('/api/v1/application-extensions/org.3mm.clock/disable')
    expect(http.patch).not.toHaveBeenCalled()
  })

  it('uses the single upload and enables only the exact theme version without selecting it', async () => {
    http.get.mockImplementation((url: string) => Promise.resolve({ data:
      url.endsWith('/themes/catalog') ? { items: [themePackage, { ...themePackage, version: '2.0.0', sha256: '8'.repeat(64) }] }
        : url.endsWith('/runtime-extensions/catalog') ? [oldRuntimeFixture] : [],
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
    expect(wrapper.find('dialog input[type=checkbox]').exists()).toBe(false)
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
      '/api/v1/application-extensions/org.3mm.clock',
    )
  })

  it('keeps public compiled controls read-only and private application management hidden', async () => {
    localStorage.setItem('role', 'user')
    const wrapper = await mountView()
    expect(wrapper.text()).toContain('Indicator')
    expect(wrapper.text()).not.toContain('Clock')
    expect(wrapper.get('.extension-card input[type=checkbox]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('.delete-btn').exists()).toBe(false)
    expect(http.get.mock.calls.some(([url]) => url === '/api/v1/modules/packages')).toBe(false)
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


describe('Current package installation boundary', () => {
  it('never falls back to retired upload when manifest-v2 validation fails', async () => {
    localStorage.setItem('role','admin')
    http.get.mockResolvedValue({ data: [] }); compiledUi.getCatalog.mockResolvedValue([])
    http.post.mockClear(); http.post.mockRejectedValueOnce({ response: { status:422, data:{ detail:'manifest v2 required' } } })
    const wrapper=await mountView()
    const input=wrapper.get('#extension-file')
    Object.defineProperty(input.element,'files',{configurable:true,value:[new File(['old package'],'old.zip')]})
    await input.trigger('change'); await wrapper.get('.upload-form').trigger('submit'); await flushPromises()
    expect(http.post).toHaveBeenCalledTimes(1)
    expect(http.post.mock.calls[0][0]).toBe('/api/v1/modules/packages')
    expect(wrapper.text()).toContain('manifest v2 required')
    wrapper.unmount()
  })
})
