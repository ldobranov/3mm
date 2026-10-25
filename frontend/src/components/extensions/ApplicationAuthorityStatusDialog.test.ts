import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
const locale = vi.hoisted(() => ({ language: 'en' }))
vi.mock('@/utils/dynamic-http', () => ({ default: http }))
vi.mock('@/utils/i18n', async () => {
  const { ref } = await import('vue')
  const { movedLanguageLabel } = await import('@/test-utils/language-messages')
  return { useI18n: () => ({ currentLanguage: ref(locale.language), t: (key: string, fallback: string) => movedLanguageLabel(key, fallback, locale.language) }) }
})
import ApplicationAuthorityDialog from './ApplicationAuthorityDialog.vue'
import { consentPreview, consentResult } from './application-consent.fixtures'

const id = (letter: string) => letter.repeat(32)
const moduleId = 'org.example.status-reference'
const base = `/api/v1/application-extensions/${moduleId}/authority`
const link = 'peer_' + id('a')
const scope = `status:${link}:read`
const sender = () => ({ identity_version: 1, installation_id: 'inst_' + id('b'), algorithm: 'ed25519',
  key_id: '21fe31dfa154a261626bf854046fd2271b7bed4b6abe45aa58877ef47f9721b9', public_key: '11qYAYKxCrfVS/7TyWQHOg7hcvPapiMlrwIaaPcHURo=',
  key_generation: 1, created_at: '2026-10-16T12:00:00Z' })
const resource = () => ({ owner: { core_installation_id: sender().installation_id, application_installation_id: '7', incarnation: id('c'), module_id: moduleId },
  package_artifact_sha256: 'a'.repeat(64), operation: 'installation.status.read', link_id: link, application_instance_id: 'd'.repeat(24),
  sender_identity: sender(), receiver_identity: { ...sender(), installation_id: 'inst_' + id('8'),
    key_id: '515a733d7320b35b2117893952f93a9400dc4d5ca8bb6972453cae4cab993a07', public_key: 'cnJy'.repeat(10) + 'cnI=' },
  origin: 'https://receiver.example', target_module_id: 'org.example.receiver', consent_revision: 3,
  consent: { consent_version: 1, summary_fields: ['core_version'], node_ids: ['dev_' + id('e')], node_fields: ['online', 'display_name'] } })
const status = () => ({ installation_id: 7, mode: 'enforced', installation_status: 'active', installation_enabled: true,
  artifact_sha256: 'a'.repeat(64), scopes: [scope], native_reviews: [{ native_review_id: id('1'), revision: id('2') }],
  grant_state: 'active', grant_record_revision: id('3'), grant_effective: true, isolation_proven: false })
const preview = () => consentPreview(status(), { commands: [], connectors: [], status_projections: [resource()] }, moduleId)
const wrappers: VueWrapper[] = []
const methods = ['showModal', 'close'].map(name => ({ name, descriptor: Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, name) }))
beforeEach(() => {
  vi.resetAllMocks(); locale.language = 'en'
  http.get.mockResolvedValue({ data: status() }); http.post.mockResolvedValue({ data: preview() })
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value: function(this: HTMLDialogElement) { this.open = true } })
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value: function(this: HTMLDialogElement) { this.open = false } })
})
afterEach(() => {
  wrappers.splice(0).forEach(wrapper => wrapper.unmount())
  for (const { name, descriptor } of methods) {
    if (descriptor) Object.defineProperty(HTMLDialogElement.prototype, name, descriptor)
    else Reflect.deleteProperty(HTMLDialogElement.prototype, name)
  }
  document.body.innerHTML = ''
})
async function open() {
  const wrapper = mount(ApplicationAuthorityDialog, { attachTo: document.body, props: { moduleId, name: 'Status reference' } })
  wrappers.push(wrapper); await flushPromises(); return wrapper
}
function button(wrapper: VueWrapper, text: string) {
  const found = wrapper.findAll('button').find(item => item.text() === text)
  if (!found) throw new Error('Missing button: ' + text)
  return found
}
describe('exact local status projection consent details', () => {
  it('previews public bindings and saves the exact selection with one explicit Allow', async () => {
    let saved = false
    const initial = preview()
    http.post.mockImplementation(async (path: string) => {
      if (path === base + '/consent/allow') {
        saved = true
        return { data: consentResult(initial) }
      }
      return { data: { ...initial, access_saved: saved } }
    })
    const wrapper = await open()
    expect(http.post).toHaveBeenCalledTimes(1)
    expect(http.post).toHaveBeenCalledWith(base + '/consent/preview', {
      request_id: expect.stringMatching(/^[a-f0-9]{32}$/),
    }, { timeout: 12000 })
    expect((wrapper.find('details.authority-details').element as HTMLDetailsElement).open).toBe(false)
    expect(wrapper.findAll('.authority-status_projections pre')).toHaveLength(1)
    expect(JSON.parse(wrapper.find('.authority-status_projections pre').text())).toEqual(resource())
    for (const text of ['Local status projections', link, 'https://receiver.example', 'org.example.receiver',
      'consent_revision', 'core_version', 'dev_' + id('e'), 'online', 'display_name',
      resource().receiver_identity.key_id, resource().receiver_identity.public_key, 'd'.repeat(24)]) {
      expect(wrapper.text()).toContain(text)
    }
    expect(wrapper.findAll('textarea, input:not([type=checkbox])')).toHaveLength(0)
    expect((wrapper.find('.authority-scope-choice input').element as HTMLInputElement).checked).toBe(true)
    expect(button(wrapper, 'Allow access').attributes('disabled')).toBeUndefined()
    await button(wrapper, 'Allow access').trigger('click'); await flushPromises()
    expect(http.post.mock.calls.map(call => call[0])).toEqual([
      base + '/consent/preview', base + '/consent/allow', base + '/consent/preview',
    ])
    expect(http.post.mock.calls[1]?.[1]).toEqual({
      request_id: expect.stringMatching(/^[a-f0-9]{32}$/), preview_id: initial.preview_id,
      expected_revision: initial.revision, fingerprint: initial.fingerprint,
      scopes: [scope], user_permissions: ['app_use'], accept_native_code: true,
    })
    expect(wrapper.emitted('changed')).toHaveLength(1)
    expect(button(wrapper, 'Allow access').attributes('disabled')).toBeDefined()
  })

  it('renders the Bulgarian resource category and exact public metadata without approving on open', async () => {
    locale.language = 'bg'
    const wrapper = await open()
    expect(wrapper.text()).toContain('Локален статус по съгласие')
    expect(JSON.parse(wrapper.find('.authority-status_projections pre').text())).toEqual(resource())
    for (const text of ['receiver_identity', 'consent_revision', 'node_ids', 'node_fields', 'dev_' + id('e'),
      resource().receiver_identity.key_id, resource().receiver_identity.public_key]) expect(wrapper.text()).toContain(text)
    expect((wrapper.find('.authority-scope-choice input').element as HTMLInputElement).checked).toBe(true)
    expect(http.post.mock.calls.map(call => call[0])).toEqual([base + '/consent/preview'])
    expect(wrapper.emitted('changed')).toBeUndefined()
  })

  it('refuses credential-bearing malformed resources without partial display, approval or automatic retry', async () => {
    const initial = preview()
    http.post.mockResolvedValue({ data: { ...initial, resources: { ...initial.resources,
      status_projections: [{ ...resource(), credential: 'PRIVATE_MUST_NOT_APPEAR' }] } } })
    const wrapper = await open()
    expect(wrapper.findAll('.authority-status_projections')).toHaveLength(0)
    expect(wrapper.findAll('.authority-scope-choice')).toHaveLength(0)
    expect(wrapper.text()).not.toContain('PRIVATE_MUST_NOT_APPEAR')
    expect(wrapper.find('[role=alert]').exists()).toBe(true)
    expect(button(wrapper, 'Allow access').attributes('disabled')).toBeDefined()
    await button(wrapper, 'Allow access').trigger('click'); await flushPromises()
    expect(http.post.mock.calls.map(call => call[0])).toEqual([base + '/consent/preview'])
    expect(http.get).not.toHaveBeenCalled()
    expect(wrapper.emitted('changed')).toBeUndefined()
  })
})
