import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { hardwareClient, newHardwareRequestId, parseHardwareStatus } from './hardware-interfaces'

const { request, backend } = vi.hoisted(() => ({ request: vi.fn(), backend: vi.fn() }))
vi.mock('axios', () => ({ default: { request, isAxiosError: (e: unknown) => !!e && typeof e === 'object' && 'response' in e } }))
vi.mock('./runtime-config', () => ({ getBackendUrl: backend }))
vi.mock('./auth', () => ({ getToken: () => 'test-token' }))
const DEVICE = 'dev_'+'a'.repeat(32)
const snapshot = () => ({ device_id: DEVICE, supported: true, can_enable: true, reason: null,
  revision: 'c'.repeat(64), configured: false, ready: false, reboot_required: false, changes: [], operation: null,
  live: { adapter_present: false, device_node_present: false, agent_running: true, agent_access: false, clock_hz: null } })
beforeEach(() => { request.mockReset(); backend.mockResolvedValue('http://core.test') })
afterEach(() => vi.unstubAllGlobals())

describe('hardware administration transport', () => {
  it('uses cryptographic bytes on LAN HTTP without randomUUID', () => {
    vi.stubGlobal('crypto', { getRandomValues: (v: Uint8Array) => { v.fill(171); return v } })
    expect(newHardwareRequestId()).toBe('ab'.repeat(16))
  })
  it('reads without any mutation then sends the exact reviewed device/revision once', async () => {
    const current = snapshot(), client = hardwareClient(DEVICE)
    request.mockResolvedValueOnce({ data: current })
    const reviewed = await client.inspect()
    expect(request.mock.calls[0]![0].method).toBe('GET')
    request.mockResolvedValueOnce({ data: { status: 'queued', request_id: 'b'.repeat(32) } })
    await client.mutate('enable', reviewed, 'b'.repeat(32))
    expect(request.mock.calls[1]![0]).toMatchObject({ method: 'POST',
      url: `http://core.test/api/v1/devices/${DEVICE}/hardware-interfaces/i2c/enable`,
      data: { request_id: 'b'.repeat(32), expected_revision: 'c'.repeat(64), confirmation: 'ENABLE I2C '+DEVICE } })
    expect(request).toHaveBeenCalledTimes(2)
  })
  it.each([401, 403, 409, 'timeout'])('does not retry a mutation after %s', async code => {
    request.mockRejectedValue(code === 'timeout' ? new Error('timeout') : { response: { status: code } })
    await expect(hardwareClient(DEVICE).mutate('enable', snapshot(), 'b'.repeat(32))).rejects.toThrow()
    expect(request).toHaveBeenCalledTimes(1)
  })
  it('rejects wrong-device, malformed and stale snapshots before changing anything', async () => {
    expect(() => parseHardwareStatus({ ...snapshot(), device_id: 'wrong' }, DEVICE)).toThrow()
    expect(() => parseHardwareStatus({ ...snapshot(), revision: 'wrong' }, DEVICE)).toThrow()
    await expect(hardwareClient(DEVICE).mutate('restart', snapshot(), 'b'.repeat(32))).rejects.toThrow()
    expect(request).not.toHaveBeenCalled()
  })
})
