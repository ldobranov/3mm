import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/utils/dynamic-http', () => ({ default: http }))
vi.mock('@/utils/i18n', () => ({ useI18n: () => ({ t: (_key: string, fallback: string) => fallback }) }))
import PlatformRuntimeUpdates from './PlatformRuntimeUpdates.vue'
const dialogMethods = ['showModal', 'close'].map(name => ({ name, descriptor: Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, name) }))

const OLD = 'a'.repeat(64), NEW = 'b'.repeat(64), PREPARED = 'c'.repeat(32)
function response(candidate = false) {
  return { current_build_id: OLD, previous_build_id: null, ready: true, recovery_required: false,
    features: { query_execution_contract: null }, reason: null, operation: null,
    candidate: candidate ? { candidate_id: PREPARED, build_id: NEW, sha256: 'd'.repeat(64),
      bytes: 30720, compatible: true, features: { query_execution_contract: 1 } } : null }
}
function button(wrapper: ReturnType<typeof mount>, label: string) {
  return wrapper.findAll('button').find(b => b.text() === label)!
}

describe('Platform Runtime update card', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    http.get.mockResolvedValue({ data: response() })
    http.post.mockResolvedValue({ data: { request_id: 'e'.repeat(32), state: 'queued' } })
    Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value: function (this: HTMLDialogElement) { this.open = true } })
    Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value: function (this: HTMLDialogElement) { this.open = false } })
  })
  afterEach(() => {
    vi.clearAllTimers(); vi.useRealTimers(); vi.restoreAllMocks()
    for (const { name, descriptor } of dialogMethods) {
      if (descriptor) Object.defineProperty(HTMLDialogElement.prototype, name, descriptor)
      else Reflect.deleteProperty(HTMLDialogElement.prototype, name)
    }
  })

  it('reads status only, advertises no missing query support and does not poll a healthy idle component', async () => {
    const wrapper = mount(PlatformRuntimeUpdates)
    await flushPromises()
    expect(wrapper.text()).toContain('Not advertised')
    expect(http.post).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(15000)
    expect(http.get).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('prepares once without applying a candidate and without using randomUUID', async () => {
    const randomUUID = vi.spyOn(crypto, 'randomUUID').mockImplementation(() => { throw new Error('Unavailable on LAN HTTP') })
    const wrapper = mount(PlatformRuntimeUpdates)
    await flushPromises()
    await button(wrapper, 'Prepare from installed Core').trigger('click')
    await flushPromises()
    expect(http.post).toHaveBeenCalledTimes(1)
    expect(http.post.mock.calls[0]![0]).toBe('/api/v1/system-updates/runtime/prepare')
    expect(http.post.mock.calls[0]![1].request_id).toMatch(/^[0-9a-f]{32}$/)
    expect(http.post.mock.calls[0]![1].expected_operation_id).toBeNull()
    expect(randomUUID).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('requires separate exact-build acknowledgement and maintenance override before one apply', async () => {
    http.get.mockResolvedValue({ data: response(true) })
    const wrapper = mount(PlatformRuntimeUpdates, { props: { maintenanceOverrideRequired: true } })
    await flushPromises()
    await button(wrapper, 'Review Runtime update').trigger('click')
    await flushPromises()
    expect(wrapper.find('dialog').text()).toContain(NEW)
    expect(button(wrapper, 'Confirm once').attributes('disabled')).toBeDefined()
    const checks = wrapper.findAll('dialog input[type=checkbox]')
    await checks[0]!.setValue(true)
    expect(button(wrapper, 'Confirm once').attributes('disabled')).toBeDefined()
    await checks[1]!.setValue(true)
    await button(wrapper, 'Confirm once').trigger('click')
    await flushPromises()
    expect(http.post).toHaveBeenCalledTimes(1)
    expect(http.post.mock.calls[0]).toEqual(['/api/v1/system-updates/runtime/apply', expect.objectContaining({
      candidate_id: PREPARED, build_id: NEW, confirmation: 'UPDATE RUNTIME ' + NEW, maintenance_override: true })])
    wrapper.unmount()
  })

  it('disables stale and already-current candidates', async () => {
    const data = response(true)
    data.candidate!.compatible = false
    http.get.mockResolvedValue({ data })
    const wrapper = mount(PlatformRuntimeUpdates)
    await flushPromises()
    expect(button(wrapper, 'Review Runtime update').attributes('disabled')).toBeDefined()
    // Applying consumes the old current-build binding; matching bytes still do
    // not need another Prepare/Apply even when that binding is now incompatible.
    data.candidate!.build_id = OLD
    await button(wrapper, 'Refresh status').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('No update is needed')
    expect(wrapper.text()).not.toContain('Prepare a fresh candidate')
    expect(button(wrapper, 'Review Runtime update').attributes('disabled')).toBeDefined()
    expect(http.post).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('shows a completed apply without suggesting another update and retains the operation ID after reload', async () => {
    const data = response(true)
    data.current_build_id = NEW
    data.candidate!.compatible = false
    const state = { ...data, previous_build_id: OLD, operation: { request_id: 'e'.repeat(32), action: 'platform_runtime_apply',
      state: 'succeeded', reason: 'runtime_updated', updated_at: 1 } }
    http.get.mockResolvedValue({ data: state })
    const wrapper = mount(PlatformRuntimeUpdates)
    await flushPromises()
    expect(wrapper.text()).toContain('Runtime updated and checked; Core stayed running.')
    expect(wrapper.text()).toContain('No update is needed')
    expect(wrapper.text()).toContain('e'.repeat(32))
    expect(wrapper.text()).not.toContain('Prepare a fresh candidate')
    expect(button(wrapper, 'Review Runtime update').attributes('disabled')).toBeDefined()
    await vi.advanceTimersByTimeAsync(15000); await flushPromises()
    expect(http.get).toHaveBeenCalledTimes(1)
    expect(http.post).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('distinguishes missing candidate declarations from live advertised features', async () => {
    const data = response(true)
    http.get.mockResolvedValue({ data: { ...data, features: { query_execution_contract: 1 },
      candidate: { ...data.candidate!, features: {} } } })
    const wrapper = mount(PlatformRuntimeUpdates)
    await flushPromises()
    expect(wrapper.text()).toContain('Not declared in the Core contract')
    expect(wrapper.text()).toContain('Candidate features below are declarations, not a live health proof.')
    expect(http.post).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('cannot silently replace a reviewed build when refreshed state changes', async () => {
    http.get.mockResolvedValue({ data: response(true) })
    const wrapper = mount(PlatformRuntimeUpdates)
    await flushPromises()
    await button(wrapper, 'Review Runtime update').trigger('click'); await flushPromises()
    await wrapper.find('dialog input[type=checkbox]').setValue(true)
    const changed = response(true)
    changed.candidate!.build_id = 'f'.repeat(64)
    http.get.mockResolvedValue({ data: changed })
    await button(wrapper, 'Refresh status').trigger('click'); await flushPromises()
    expect(wrapper.find('dialog').text()).toContain(NEW)
    expect(wrapper.find('dialog').text()).toContain('reviewed state changed')
    expect(button(wrapper, 'Confirm once').attributes('disabled')).toBeDefined()
    expect(http.post).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it.each(['compatibility', 'already-current build', 'recovery requirement'])(
    'invalidates an acknowledged review when %s changes without different candidate IDs or digests', async change => {
      const initial = response(true)
      http.get.mockResolvedValue({ data: initial })
      const wrapper = mount(PlatformRuntimeUpdates, { props: { maintenanceOverrideRequired: true } })
      await flushPromises()
      await button(wrapper, 'Review Runtime update').trigger('click'); await flushPromises()
      for (const check of wrapper.findAll('dialog input[type=checkbox]')) await check.setValue(true)
      expect(button(wrapper, 'Confirm once').attributes('disabled')).toBeUndefined()

      const changed = response(true)
      if (change === 'compatibility') changed.candidate!.compatible = false
      else if (change === 'already-current build') changed.current_build_id = NEW
      else changed.recovery_required = true
      http.get.mockResolvedValue({ data: changed })
      await button(wrapper, 'Refresh status').trigger('click'); await flushPromises()
      expect(wrapper.get('dialog [role=alert]').text()).toContain('reviewed state changed')
      expect(button(wrapper, 'Confirm once').attributes('disabled')).toBeDefined()
      expect(wrapper.findAll('dialog input[type=checkbox]').every(check => !(check.element as HTMLInputElement).checked)).toBe(true)
      expect(http.post).not.toHaveBeenCalled()

      // Restored eligibility alone must not resurrect an old acknowledgement.
      http.get.mockResolvedValue({ data: initial })
      await button(wrapper, 'Refresh status').trigger('click'); await flushPromises()
      for (const check of wrapper.findAll('dialog input[type=checkbox]')) await check.setValue(true)
      expect(button(wrapper, 'Confirm once').attributes('disabled')).toBeDefined()
      expect(http.post).not.toHaveBeenCalled()

      await button(wrapper, 'Close').trigger('click'); await flushPromises()
      await button(wrapper, 'Review Runtime update').trigger('click'); await flushPromises()
      expect(wrapper.findAll('dialog input[type=checkbox]').every(check => !(check.element as HTMLInputElement).checked)).toBe(true)
      for (const check of wrapper.findAll('dialog input[type=checkbox]')) await check.setValue(true)
      expect(button(wrapper, 'Confirm once').attributes('disabled')).toBeUndefined()
      expect(http.post).not.toHaveBeenCalled()
      wrapper.unmount()
    },
  )

  it('reads state after a lost reply but never automatically resends or exposes backend errors', async () => {
    http.post.mockRejectedValue({ response: { data: { detail: 'password=private /root/path' } } })
    http.get.mockResolvedValue({ data: { ...response(), operation: { request_id: PREPARED,
      action: 'platform_runtime_prepare', state: 'succeeded', reason: 'candidate_prepared', updated_at: 1 } } })
    const wrapper = mount(PlatformRuntimeUpdates)
    await flushPromises()
    await button(wrapper, 'Prepare from installed Core').trigger('click'); await flushPromises()
    const ownRequestId = http.post.mock.calls[0]![1].request_id
    expect(wrapper.text()).toContain('Outcome unconfirmed')
    expect(wrapper.text()).toContain(ownRequestId)
    expect(wrapper.text()).not.toContain('password=private')
    await vi.advanceTimersByTimeAsync(15000); await flushPromises()
    expect(http.post).toHaveBeenCalledTimes(1)
    expect(button(wrapper, 'Prepare from installed Core').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('offers recovery explicitly without replaying an interrupted apply', async () => {
    const data = { ...response(), operation: { request_id: PREPARED, action: 'platform_runtime_apply',
      state: 'recovery_required', reason: 'worker_interrupted', updated_at: 1 } }
    http.get.mockResolvedValue({ data })
    const wrapper = mount(PlatformRuntimeUpdates)
    await flushPromises()
    expect(http.post).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('Do not repeat the update')
    await button(wrapper, 'Review interrupted-operation recovery').trigger('click'); await flushPromises()
    await wrapper.find('dialog input[type=checkbox]').setValue(true)
    await button(wrapper, 'Confirm once').trigger('click'); await flushPromises()
    expect(http.post.mock.calls[0]![0]).toBe('/api/v1/system-updates/runtime/recover')
    expect(http.post.mock.calls[0]![1].expected_operation_id).toBe(PREPARED)
    wrapper.unmount()
  })

  it('keeps the card isolated when Runtime/helper status is missing or malformed', async () => {
    http.get.mockResolvedValue({ data: { ready: 'yes', current_build_id: '/tmp/invalid' } })
    const wrapper = mount(PlatformRuntimeUpdates)
    await flushPromises()
    expect(wrapper.text()).toContain('Other Core administration remains available')
    expect(http.post).not.toHaveBeenCalled()
    expect(wrapper.findAll('.actions button')).toHaveLength(0)
    wrapper.unmount()
  })
})
