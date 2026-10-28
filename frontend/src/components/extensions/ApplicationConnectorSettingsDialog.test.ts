import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick, type Ref } from 'vue'
import { useI18n } from '@/utils/i18n'
import { ConnectorSettingsError } from './connector-settings'
import { connectorSettings, settingsSha } from './connector-settings.fixtures'
import Dialog from './ApplicationConnectorSettingsDialog.vue'

const client = vi.hoisted(() => ({ inspect: vi.fn(), save: vi.fn(), outcome: vi.fn() }))
vi.mock('./connector-settings', async importOriginal => ({
  ...await importOriginal<typeof import('./connector-settings')>(), createConnectorSettingsClient: () => client,
}))
vi.mock('@/utils/i18n', async () => {
  const { ref } = await import('vue')
  const currentLanguage = ref('en')
  return { useI18n: () => ({ currentLanguage }) }
})
const wrappers: ReturnType<typeof mount>[] = []
const nativeMethods = ['showModal', 'close'].map(name => ({ name, descriptor: Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, name) }))
const testLanguage = () => useI18n().currentLanguage as Ref<string>
beforeEach(() => {
  testLanguage().value = 'en'
  sessionStorage.clear(); vi.clearAllMocks()
  for (const name of ['showModal', 'close']) Object.defineProperty(HTMLDialogElement.prototype, name, { configurable: true,
    value() { (this as HTMLDialogElement).open = name === 'showModal' } })
  client.inspect.mockResolvedValue(connectorSettings())
  client.outcome.mockImplementation(async request_id => ({ request_id, status: 'unknown' }))
})
afterEach(() => {
  wrappers.splice(0).forEach(w => w.unmount())
  for (const { name, descriptor } of nativeMethods) {
    if (descriptor) Object.defineProperty(HTMLDialogElement.prototype, name, descriptor)
    else delete (HTMLDialogElement.prototype as any)[name]
  }
})
async function render() {
  const wrapper = mount(Dialog, { props: { packageSha: settingsSha, name: 'Connection app' } })
  wrappers.push(wrapper); await flushPromises(); return wrapper
}
async function draft(wrapper: ReturnType<typeof mount>) {
  await wrapper.get('.connector-origin').setValue('https://service.example')
  await wrapper.get('.connector-label').setValue('Local account')
  await wrapper.get('.connector-username').setValue('operator')
  await wrapper.get('.connector-password').setValue('private-password')
}

describe('Core-owned connector settings', () => {
  it('cancel and initial reads do not create credentials, configure or contact the service', async () => {
    const wrapper = await render(); await draft(wrapper)
    await wrapper.findAll('button').find(b => b.text() === 'Close')!.trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)
    expect(client.inspect).toHaveBeenCalledOnce()
    expect(client.save).not.toHaveBeenCalled()
    expect(sessionStorage.length).toBe(0)
  })
  it('keeps drafts during Core locale changes and falls back to English', async () => {
    const wrapper = await render(); await draft(wrapper)
    testLanguage().value = 'bg-BG'; await nextTick()
    expect(wrapper.get('h2').text()).toBe('Настройки на приложението')
    expect((wrapper.get('.connector-password').element as HTMLInputElement).value).toBe('private-password')
    expect((wrapper.get('.connector-origin').element as HTMLInputElement).value).toBe('https://service.example')
    testLanguage().value = 'de'; await nextTick()
    expect(wrapper.get('h2').text()).toBe('Application settings')
    expect(client.inspect).toHaveBeenCalledOnce(); expect(client.save).not.toHaveBeenCalled()
  })
  it('saves once with a stable request identity and persists no credentials', async () => {
    client.save.mockImplementation(async (_id, body) => {
      expect(JSON.parse(sessionStorage.getItem(`3mm.connector-settings.pending:${settingsSha}`)!)).toEqual({ request_id: body.request_id, rejected: null })
      expect(JSON.stringify(sessionStorage)).not.toContain('private-password')
      expect(body.credential).toEqual({ username: 'operator', password: 'private-password' })
      return { request_id: body.request_id, status: 'applied', state: connectorSettings().connectors[0] }
    })
    const wrapper = await render(); await draft(wrapper)
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(client.save).toHaveBeenCalledOnce()
    expect(wrapper.emitted('changed')).toHaveLength(1)
    expect(sessionStorage.length).toBe(0)
    expect(wrapper.get('.connector-saved').text()).toContain('not a connection test')
    expect((wrapper.get('.connector-password').element as HTMLInputElement).value).toBe('')
  })
  it('recovers a lost reply on reopen by outcome only and never repeats Save', async () => {
    client.save.mockRejectedValue(new ConnectorSettingsError('unconfirmed'))
    const first = await render(); await draft(first)
    await first.get('form').trigger('submit'); await flushPromises()
    const requestId = client.save.mock.calls[0][1].request_id
    expect(first.find('.connector-pending').exists()).toBe(true)
    first.unmount()
    const second = await render()
    expect(second.find('.connector-pending').text()).toContain(requestId)
    expect(client.inspect).toHaveBeenCalledOnce()
    expect(client.save).toHaveBeenCalledOnce()
    client.outcome.mockResolvedValue({ request_id: requestId, status: 'applied', state: connectorSettings().connectors[0] })
    await second.findAll('button').find(b => b.text() === 'Check result')!.trigger('click'); await flushPromises()
    expect(second.find('.connector-pending').exists()).toBe(false)
    expect(client.save).toHaveBeenCalledOnce()
    expect(sessionStorage.length).toBe(0)
  })
  it('checks an existing receipt after conflict before allowing any new action', async () => {
    client.save.mockRejectedValue(new ConnectorSettingsError('conflict'))
    client.outcome.mockImplementation(async request_id => ({ request_id, status: 'applied', state: connectorSettings().connectors[0] }))
    const wrapper = await render(); await draft(wrapper)
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(client.outcome).toHaveBeenCalledExactlyOnceWith(client.save.mock.calls[0][1].request_id)
    expect(wrapper.find('.connector-saved').exists()).toBe(true)
    expect(client.save).toHaveBeenCalledOnce()
  })
  it('retains a bare conflict as unknown and resolves a definite rejection only after outcome lookup', async () => {
    client.save.mockRejectedValue(new ConnectorSettingsError('conflict'))
    const first = await render(); await draft(first)
    await first.get('form').trigger('submit'); await flushPromises()
    expect(first.find('.connector-pending').exists()).toBe(true)
    first.unmount(); sessionStorage.clear()
    client.save.mockRejectedValue(new ConnectorSettingsError('conflict', true))
    client.outcome.mockRejectedValueOnce(new ConnectorSettingsError('unavailable'))
    const second = await render(); await draft(second)
    await second.get('form').trigger('submit'); await flushPromises()
    expect(second.find('.connector-pending').exists()).toBe(true)
    second.unmount()
    const third = await render()
    expect(third.find('.connector-pending').exists()).toBe(false)
    expect(third.get('[role="alert"]').text()).toContain('settings changed')
    expect(client.save).toHaveBeenCalledTimes(2)
  })
  it('requires confirmation of rotation/revocation and shows affected connectors', async () => {
    const settings = connectorSettings()
    settings.connectors[0].credential = { secret_ref: 'secret_' + 'd'.repeat(32), label: 'API login', version: 1, revoked: false }
    settings.connectors[0].affected_connector_ids = ['business_api', 'shared_api']
    client.inspect.mockResolvedValue(settings)
    const wrapper = await render()
    await wrapper.get('.connector-revoke').trigger('click')
    expect(wrapper.text()).toContain('business_api, shared_api')
    expect(wrapper.get('.connector-apply-credential').attributes('disabled')).toBeDefined()
    expect(client.save).not.toHaveBeenCalled()
    client.save.mockImplementation(async (_id, body) => ({ request_id: body.request_id, status: 'applied', state: settings.connectors[0] }))
    await wrapper.get('.connector-confirm').setValue(true)
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(client.save.mock.calls[0][1]).toMatchObject({ action: 'revoke', confirm_credential_change: true, secret_ref: settings.connectors[0].credential!.secret_ref })
    expect(client.save.mock.calls[0][1]).not.toHaveProperty('destination_origin')
  })
  it('refuses credential creation without encryption and does not send on failed pending storage', async () => {
    const settings = connectorSettings(); settings.encryption_available = false
    client.inspect.mockResolvedValue(settings)
    const wrapper = await render(); await draft(wrapper)
    expect(wrapper.get('.connector-save').attributes('disabled')).toBeDefined()
    expect(client.save).not.toHaveBeenCalled()
    settings.encryption_available = true; client.inspect.mockResolvedValue(settings)
    await wrapper.findAll('button').find(b => b.text() === 'Refresh')!.trigger('click'); await flushPromises(); await draft(wrapper)
    const storage = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('storage unavailable') })
    try { await wrapper.get('form').trigger('submit'); await flushPromises(); expect(client.save).not.toHaveBeenCalled() }
    finally { storage.mockRestore() }
  })
})
