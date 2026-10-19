import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import Capability from '../../../modules/application-reference/source/frontend/Capability.vue'
import { ApplicationHostError, applicationHostKey, type ApplicationHost, type ApplicationHostInfo } from '../extension-ui/application-v1'

const information: ApplicationHostInfo = {
  host_version: 1, module_id: 'org.3mm.application-reference', active_version: '1.1.0',
  artifact_sha256: 'a'.repeat(64), entrypoint_id: 'operations', audience: 'operator',
  features: { operations: true, resource_authority: 'separate', browser_isolation: false },
  operations: [
    { operation_id: 'probe', kind: 'command', idempotency: 'required' },
    { operation_id: 'lookup', kind: 'query', idempotency: 'forbidden' },
  ],
}
const wrappers: VueWrapper[] = []
afterEach(() => { wrappers.splice(0).forEach(wrapper => wrapper.unmount()); vi.restoreAllMocks() })

async function screen(info = information) {
  const host = { getInfo: vi.fn(async () => info), invoke: vi.fn<ApplicationHost['invoke']>() }
  const wrapper = mount(Capability, { global: { provide: { [applicationHostKey as symbol]: host } } })
  wrappers.push(wrapper)
  await flushPromises()
  return { host, wrapper }
}

describe('delivered scoped reference UI', () => {
  it('shows only host-declared operations, including kiosk without lookup', async () => {
    const { wrapper } = await screen({ ...information, audience: 'kiosk', operations: [information.operations[0]] })
    expect(wrapper.findAll('button').map(button => button.text())).toEqual(['Queue one mock request'])
    expect(wrapper.find('input').exists()).toBe(false)
    const inaccessible = await screen({ ...information, operations: [] })
    expect(inaccessible.wrapper.find('button').exists()).toBe(false)
  })
  it.each(['not JSON', '[]', 'null', '1'])('refuses invalid arguments %s without dispatch', async value => {
    const { host, wrapper } = await screen()
    await wrapper.get('textarea').setValue(value)
    await wrapper.get('button').trigger('click')
    expect(host.invoke).not.toHaveBeenCalled()
    expect(wrapper.get('[role=alert]').text()).toBeTruthy()
  })
  it('uses one cryptographic ID and the exact arguments without requiring HTTPS randomUUID', async () => {
    vi.spyOn(crypto, 'randomUUID').mockImplementation(() => { throw new Error('insecure origin') })
    const { host, wrapper } = await screen()
    host.invoke.mockResolvedValue({ status: 'queued' })
    await wrapper.get('textarea').setValue('{"channel":"output.1","duration_ms":50}')
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(host.invoke).toHaveBeenCalledOnce()
    const [operation, payload, options] = host.invoke.mock.calls[0]
    expect(operation).toBe('probe')
    expect(payload).toEqual({ arguments: { channel: 'output.1', duration_ms: 50 } })
    expect(options?.idempotencyKey).toMatch(/^[0-9a-f]{32}$/)
    expect(wrapper.get('code').text()).toBe(options?.idempotencyKey)
    expect(wrapper.text()).toContain('Queuing does not prove execution')
  })
  it.each(['unconfirmed', 'disposed'] as const)('preserves %s request and permits only read-only lookup', async code => {
    const { host, wrapper } = await screen()
    host.invoke.mockRejectedValueOnce(new ApplicationHostError(code)).mockResolvedValue({ status: 'found' })
    await wrapper.get('textarea').setValue('{"channel":"output.1","duration_ms":50}')
    await wrapper.get('button').trigger('click')
    await flushPromises()
    const key = host.invoke.mock.calls[0][2]?.idempotencyKey
    expect(wrapper.get('code').text()).toBe(key)
    expect(wrapper.get('textarea').attributes('disabled')).toBeDefined()
    await wrapper.get('button').trigger('click')
    expect(host.invoke).toHaveBeenCalledOnce()
    await wrapper.findAll('button')[1].trigger('click')
    await flushPromises()
    expect(host.invoke.mock.calls[1]).toEqual(['lookup', { request_id: key }])
    expect(wrapper.get('button').attributes('disabled')).toBeDefined()
    expect(wrapper.get('code').text()).toBe(key)
  })
  it('does not automatically retry a definite refusal', async () => {
    const { host, wrapper } = await screen()
    host.invoke.mockRejectedValue(new ApplicationHostError('access_denied'))
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(host.invoke).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('access_denied')
  })
})
