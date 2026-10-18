import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
const locale = vi.hoisted(() => ({ language: 'en' }))
vi.mock('@/utils/dynamic-http', () => ({ default: http }))
vi.mock('@/utils/i18n', async () => {
  const { ref } = await import('vue')
  return { useI18n: () => ({ currentLanguage: ref(locale.language), t: (_key: string, fallback: string) => fallback }) }
})
import ApplicationAuthorityDialog from './ApplicationAuthorityDialog.vue'
import { peerArtifact, peerModuleId, peerOwner, peerPlan, peerResources, peerScopes, peerStatus } from './authority-peer-reads.fixtures'

const base = `/api/v1/application-extensions/${peerModuleId}/authority`
const wrappers: VueWrapper[] = []
const methods = ['showModal', 'close'].map(name => ({ name, descriptor: Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, name) }))
beforeEach(() => {
  vi.resetAllMocks(); locale.language = 'en'
  http.get.mockResolvedValue({ data: peerStatus() })
  http.post.mockImplementation(async (_path, body) => ({ data: peerPlan(body.scopes) }))
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value: function(this: HTMLDialogElement) { this.open = true } })
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value: function(this: HTMLDialogElement) { this.open = false } })
})
afterEach(() => {
  wrappers.splice(0).forEach(wrapper => wrapper.unmount()); vi.useRealTimers()
  for (const { name, descriptor } of methods) {
    if (descriptor) Object.defineProperty(HTMLDialogElement.prototype, name, descriptor)
    else Reflect.deleteProperty(HTMLDialogElement.prototype, name)
  }
  document.body.innerHTML = ''
})
async function open() {
  const wrapper = mount(ApplicationAuthorityDialog, { attachTo: document.body, props: { moduleId: peerModuleId, name: 'Peer reference' } })
  wrappers.push(wrapper); await flushPromises(); return wrapper
}
function button(wrapper: VueWrapper, text: string) {
  const found = wrapper.findAll('button').find(item => item.text() === text)
  if (!found) throw new Error('Missing button: ' + text)
  return found
}
async function click(wrapper: VueWrapper, text: string) { await button(wrapper, text).trigger('click'); await flushPromises() }
const choices = (wrapper: VueWrapper) => wrapper.findAll('.authority-peer-choice input')
const acknowledge = async (wrapper: VueWrapper) => wrapper.find('.authority-acknowledge input').setValue(true)
const decision = (state: string, revision: string) => ({ plan_id: '4'.repeat(32), fingerprint: '6'.repeat(64), revision: revision.repeat(32), state })

describe('exact optional outbound peer-read review UI', () => {
  it('shows effective current rights when Core confirms executor support, not the old unavailable warning', async () => {
    http.get.mockResolvedValue({ data: { ...peerStatus(), grant_effective: true, runtime_blockers: [] } })
    const wrapper = await open()
    expect(wrapper.find('.authority-effective').text()).toBe('Current rights are effective')
    expect(wrapper.text()).not.toContain('SDK execution is not implemented yet')
    expect(http.post).not.toHaveBeenCalled()
  })

  it('starts with no peer rights and renders every public binding without claiming live access', async () => {
    const wrapper = await open()
    expect(http.post).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('Peer-read SDK is not available')
    expect(wrapper.find('.authority-effective').exists()).toBe(false)
    await click(wrapper, 'Review requested access')
    expect(http.post.mock.calls[0]?.[1].scopes).toEqual([])
    expect(choices(wrapper)).toHaveLength(2)
    expect(choices(wrapper).every(item => !(item.element as HTMLInputElement).checked)).toBe(true)
    for (const text of ['Existing outbound peer links', 'No rights selected', 'empty selection never means all links',
      'No enrollment, signing, reporting, remote calls, credentials or changes to peer consent', 'does not verify signatures',
      'remote_link', 'second_link', 'https://receiver.example', 'org.example.receiver', 'Local consent revision',
      peerResources()[0]!.receiver_identity.key_id, 'intent_opaque', '7'.repeat(64)]) expect(wrapper.text()).toContain(text)
    expect(button(wrapper, 'Approve review').attributes('disabled')).toBeDefined()
    expect(wrapper.findAll('textarea, input:not([type=checkbox])')).toHaveLength(0)
  })

  it('clears old plan/acknowledgment on each selection change; requires fresh review, approve, then apply', async () => {
    const wrapper = await open(); await click(wrapper, 'Review requested access'); await acknowledge(wrapper)
    await choices(wrapper)[0]!.setValue(true)
    expect(wrapper.find('.authority-acknowledge').exists()).toBe(false)
    expect(wrapper.find('.authority-review-plan').exists()).toBe(false)
    expect(wrapper.text()).toContain('previous review and acknowledgment were cleared')
    expect(wrapper.findAll('button').some(item => item.text() === 'Approve review')).toBe(false)
    expect(http.post).toHaveBeenCalledTimes(1)
    expect(choices(wrapper)).toHaveLength(2)
    await click(wrapper, 'Review changed selection')
    expect(http.post.mock.calls[1]?.[1].scopes).toEqual([peerScopes()[0]])
    expect(button(wrapper, 'Approve review').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('Not selected · no peer-read right')
    await acknowledge(wrapper)
    http.post.mockResolvedValueOnce({ data: decision('approved_pending_apply', '9') })
    await click(wrapper, 'Approve review')
    expect(wrapper.emitted('changed')).toBeUndefined()
    expect(wrapper.text()).toContain('Approved, not applied')
    expect(choices(wrapper).every(item => item.attributes('disabled') !== undefined)).toBe(true)
    http.post.mockResolvedValueOnce({ data: decision('applied', 'a') })
    await click(wrapper, 'Apply rights')
    expect(wrapper.emitted('changed')).toHaveLength(1)
    expect(wrapper.text()).toContain('SDK execution is not implemented yet')
    expect(wrapper.find('.authority-effective').exists()).toBe(false)
    expect(http.post.mock.calls.map(call => call[0])).toEqual([base + '/reviews', base + '/reviews',
      `${base}/reviews/${'4'.repeat(32)}/approve`, `${base}/reviews/${'4'.repeat(32)}/apply`])
    expect(http.post.mock.calls[0]?.[1].request_id).not.toBe(http.post.mock.calls[1]?.[1].request_id)
  })

  it('can explicitly approve an empty set and never substitutes all peer scopes', async () => {
    const wrapper = await open(); await click(wrapper, 'Review requested access'); await acknowledge(wrapper)
    http.post.mockResolvedValueOnce({ data: decision('approved_pending_apply', '9') })
    await click(wrapper, 'Approve review')
    http.post.mockResolvedValueOnce({ data: decision('applied', 'a') })
    await click(wrapper, 'Apply rights')
    expect(http.post.mock.calls[0]?.[1].scopes).toEqual([])
    expect(http.post).toHaveBeenCalledTimes(3)
    expect(http.get).toHaveBeenCalledTimes(2)
  })

  it('retains earlier required rights while changing optional peer choices', async () => {
    const checkpointScope = 'checkpoint:progress:read'
    const checkpoint = { owner: peerOwner(), package_artifact_sha256: peerArtifact, operation: 'read',
      declaration: { contract_version: 1, checkpoint_id: 'progress', mode: 'read', max_value_bytes: 128 } }
    http.get.mockResolvedValue({ data: { ...peerStatus(), scopes: [...peerScopes(), checkpointScope] } })
    http.post.mockImplementation(async (_path, body) => ({ data: { ...peerPlan(body.scopes), resources: { ...peerPlan().resources, checkpoints: [checkpoint] } } }))
    const wrapper = await open(); await click(wrapper, 'Review requested access')
    expect(wrapper.findAll('.authority-checkpoint')).toHaveLength(1)
    expect(http.post.mock.calls[0]?.[1].scopes).toEqual([checkpointScope])
    await choices(wrapper)[1]!.setValue(true); await click(wrapper, 'Review changed selection')
    expect(http.post.mock.calls[1]?.[1].scopes).toEqual([peerScopes()[1], checkpointScope])
    expect(wrapper.findAll('.authority-checkpoint')).toHaveLength(1)
  })

  it.each(['wider', 'narrower', 'omitted', 'secret'])('rejects a %s response before showing any peer card or approval', async kind => {
    const wrapper = await open()
    if (kind === 'narrower') {
      await click(wrapper, 'Review requested access'); await choices(wrapper)[0]!.setValue(true)
    }
    http.post.mockResolvedValueOnce({ data: kind === 'wider' ? peerPlan() : kind === 'narrower' ? peerPlan([])
      : { ...peerPlan([]), resources: { ...peerPlan().resources, peer_reads: kind === 'omitted' ? []
        : [{ ...peerResources()[0], credential: 'SECRET_MUST_NOT_RENDER' }, peerResources()[1]] } } })
    await click(wrapper, kind === 'narrower' ? 'Review changed selection' : 'Review requested access')
    expect(wrapper.find('.authority-peer-read').exists()).toBe(false)
    expect(wrapper.find('.authority-acknowledge').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('SECRET_MUST_NOT_RENDER')
    expect(wrapper.find('[role=alert]').exists()).toBe(true)
    expect(http.post).toHaveBeenCalledTimes(kind === 'narrower' ? 2 : 1)
  })

  it('clears selected rights on refresh; no previous approved intent is silently reselected', async () => {
    const wrapper = await open(); await click(wrapper, 'Review requested access'); await choices(wrapper)[0]!.setValue(true)
    await click(wrapper, 'Refresh status'); await click(wrapper, 'Review requested access')
    expect(http.post.mock.calls[1]?.[1].scopes).toEqual([])
    expect(choices(wrapper).every(item => !(item.element as HTMLInputElement).checked)).toBe(true)
  })

  it('does not retry uncertain approval or retain a usable stale selection', async () => {
    const wrapper = await open(); await click(wrapper, 'Review requested access'); await acknowledge(wrapper)
    http.post.mockRejectedValueOnce(new Error('connection lost'))
    await click(wrapper, 'Approve review')
    expect(http.post).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('No automatic retry was sent')
    expect(wrapper.find('.authority-peer-read').exists()).toBe(false)
    expect(wrapper.find('.authority-review-plan').exists()).toBe(false)
    expect(wrapper.emitted('changed')).toBeUndefined()
  })

  it('requires a fresh review after expiry and never auto-applies or reissues it', async () => {
    vi.useFakeTimers()
    http.post.mockImplementation(async (_path, body) => ({ data: { ...peerPlan(body.scopes), expires_in_seconds: 1 } }))
    const wrapper = await open(); await click(wrapper, 'Review requested access'); await acknowledge(wrapper)
    await vi.advanceTimersByTimeAsync(2000)
    expect(button(wrapper, 'Approve review').attributes('disabled')).toBeDefined()
    expect(choices(wrapper).every(item => item.attributes('disabled') !== undefined)).toBe(true)
    expect(wrapper.text()).toContain('This review expired')
    expect(http.post).toHaveBeenCalledTimes(1)
  })

  it('requires explicit revocation confirmation; cancellation and close send no mutation', async () => {
    const wrapper = await open()
    await click(wrapper, 'Revoke rights'); await click(wrapper, 'Cancel')
    expect(http.post).not.toHaveBeenCalled()
    await click(wrapper, 'Revoke rights')
    http.post.mockResolvedValueOnce({ data: { state: 'revoked' } })
    await click(wrapper, 'Confirm revocation')
    expect(http.post).toHaveBeenCalledTimes(1)
    expect(http.post.mock.calls[0]?.[0]).toBe(base + '/revoke')
    expect(http.post.mock.calls[0]?.[1].expected_revision).toBe('3'.repeat(32))
    await click(wrapper, 'Close')
    expect(wrapper.emitted('close')).toHaveLength(1)
  })

  it('shows the same optional choice, public pins and runtime boundary in Bulgarian', async () => {
    locale.language = 'bg'
    const wrapper = await open(); await click(wrapper, 'Прегледай заявения достъп')
    for (const text of ['Съществуващи изходящи peer връзки', 'Четене на peer метаданни', 'започва неизбрано',
      'SDK четенето на peer връзки е недостъпно', 'Изходяща · само четене', 'Публична идентичност на получателя',
      'екранът не проверява подписи', 'празният избор никога не означава всички връзки']) expect(wrapper.text()).toContain(text)
    expect(button(wrapper, 'Одобри прегледа').attributes('disabled')).toBeDefined()
  })
})
