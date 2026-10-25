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
const plan = () => ({ plan_id: id('4'), revision: id('5'), fingerprint: '6'.repeat(64), state: 'review_required',
  artifact_sha256: 'a'.repeat(64), scopes: [scope], expires_in_seconds: 900, isolation_proven: false,
  resources: { commands: [], connectors: [], status_projections: [resource()] } })
const wrappers: VueWrapper[] = []
const methods = ['showModal', 'close'].map(name => ({ name, descriptor: Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, name) }))
beforeEach(() => {
  vi.resetAllMocks(); locale.language = 'en'
  http.get.mockResolvedValue({ data: status() }); http.post.mockResolvedValue({ data: plan() })
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
async function review(wrapper: VueWrapper, text = 'Review requested access') {
  await button(wrapper, text).trigger('click'); await flushPromises()
}

describe('exact local status projection review card', () => {
  it('shows public bindings and separate acknowledge/approve/apply without editing consent', async () => {
    const wrapper = await open()
    expect(http.post).not.toHaveBeenCalled()
    await review(wrapper)
    expect(wrapper.findAll('.authority-status-projection')).toHaveLength(1)
    for (const text of ['Local status projections', 'Read selected local status', link, 'https://receiver.example',
      'org.example.receiver', 'Local consent revision', 'core_version', 'dev_' + id('e'), 'online, display_name',
      resource().receiver_identity.key_id, resource().receiver_identity.public_key, 'd'.repeat(24),
      'No enrollment, signing, reporting or remote approval is granted']) expect(wrapper.text()).toContain(text)
    expect(wrapper.findAll('textarea, input:not([type=checkbox])')).toHaveLength(0)
    expect(button(wrapper, 'Approve review').attributes('disabled')).toBeDefined()
    await wrapper.find('input[type=checkbox]').setValue(true)
    http.post.mockResolvedValueOnce({ data: { plan_id: id('4'), fingerprint: '6'.repeat(64), revision: id('9'), state: 'approved_pending_apply' } })
    await button(wrapper, 'Approve review').trigger('click'); await flushPromises()
    expect(wrapper.emitted('changed')).toBeUndefined()
    expect(wrapper.text()).toContain('Approved, not applied')
    http.post.mockResolvedValueOnce({ data: { plan_id: id('4'), fingerprint: '6'.repeat(64), revision: id('a'), state: 'applied' } })
    await button(wrapper, 'Apply rights').trigger('click'); await flushPromises()
    expect(http.post.mock.calls.map(call => call[0])).toEqual([base + '/reviews', base + '/reviews/' + id('4') + '/approve', base + '/reviews/' + id('4') + '/apply'])
    expect(http.post.mock.calls[0]?.[1].scopes).toEqual([scope])
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('renders Bulgarian boundaries and exact IDs without exposing live values', async () => {
    locale.language = 'bg'
    const wrapper = await open(); await review(wrapper, 'Прегледай заявения достъп')
    for (const text of ['Локален статус по съгласие', 'Четене на избрания локален статус', 'Ревизия на локалното съгласие',
      'Инсталация получател', 'Избрани устройства', 'Избрани полета от устройствата', 'Не дава право за свързване',
      'Публична идентичност на получателя', 'dev_' + id('e')]) expect(wrapper.text()).toContain(text)
    expect(button(wrapper, 'Одобри прегледа').attributes('disabled')).toBeDefined()
  })

  it('refuses malformed credential-bearing resources without partial review or automatic retry', async () => {
    http.post.mockResolvedValue({ data: { ...plan(), resources: { ...plan().resources,
      status_projections: [{ ...resource(), credential: 'PRIVATE_MUST_NOT_APPEAR' }] } } })
    const wrapper = await open(); await review(wrapper)
    expect(wrapper.findAll('.authority-status-projection')).toHaveLength(0)
    expect(wrapper.text()).not.toContain('PRIVATE_MUST_NOT_APPEAR')
    expect(wrapper.findAll('button').some(control => control.text() === 'Approve review')).toBe(false)
    expect(http.post).toHaveBeenCalledTimes(1)
  })
})
