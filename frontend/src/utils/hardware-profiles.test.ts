import { beforeEach, describe, expect, it, vi } from 'vitest'
import { hardwareProfilesClient, readHardwareProfiles, type HardwareProfilePackage } from './hardware-profiles'
const { request, backend } = vi.hoisted(() => ({ request: vi.fn(), backend: vi.fn() }))
vi.mock('axios', () => ({ default: { request, isAxiosError: (e: unknown) => !!e && typeof e === 'object' && 'response' in e } }))
vi.mock('./runtime-config', () => ({ getBackendUrl: backend }))
vi.mock('./auth', () => ({ getToken: () => 'test-token' }))
const DEVICE = 'dev_'+'a'.repeat(32)
const item = (): HardwareProfilePackage => ({ module_id: 'org.example.hardware', name: 'Example', version: '1.0.0',
  sha256: 'b'.repeat(64), profile: { schema_version: 1, simulated: false, profile_sha256: 'c'.repeat(64),
    configuration: { bus: 1, address: 39 } }, installed_exact: false, installation: null, request_id: null })
beforeEach(() => { request.mockReset(); backend.mockResolvedValue('http://core.test') })
describe('generic hardware-profile administration transport', () => {
  it('reads without writes and binds consent to exact package/profile/device with one request', async () => {
    const p = item(), client = hardwareProfilesClient(DEVICE)
    request.mockResolvedValueOnce({ data: { device_id: DEVICE, approval_supported: true, items: [p] } })
    await client.inspect()
    expect(request.mock.calls[0]![0].method).toBe('GET')
    request.mockResolvedValueOnce({ data: {} })
    await client.mutate('install', p, 'd'.repeat(32))
    expect(request.mock.calls[1]![0]).toMatchObject({ method: 'POST',
      url: `http://core.test/api/v1/modules/packages/${p.sha256}/devices/${DEVICE}/install`,
      data: { hardware_profile_approval: { schema_version: 1, device_id: DEVICE,
        package_sha256: p.sha256, profile_sha256: p.profile.profile_sha256 } },
      headers: { 'Idempotency-Key': 'd'.repeat(32) } })
    expect(request).toHaveBeenCalledTimes(2)
  })
  it('disables through normal lifecycle without a grant, frame or replacement approval', async () => {
    request.mockResolvedValue({ data: {} })
    await hardwareProfilesClient(DEVICE).mutate('disable', item(), 'd'.repeat(32))
    expect(request.mock.calls[0]![0]).toMatchObject({ method: 'POST', data: {},
      url: `http://core.test/api/v1/modules/org.example.hardware/devices/${DEVICE}/disable` })
  })
  it.each([401, 403, 409, 'timeout'])('does not retry installation after %s', async code => {
    request.mockRejectedValue(code === 'timeout' ? new Error('lost') : { response: { status: code } })
    await expect(hardwareProfilesClient(DEVICE).mutate('install', item(), 'd'.repeat(32))).rejects.toThrow()
    expect(request).toHaveBeenCalledTimes(1)
  })
  it('refuses malformed identity or a changed backend before a mutation', async () => {
    expect(() => readHardwareProfiles({ device_id: 'wrong', approval_supported: true, items: [] }, DEVICE)).toThrow()
    const client = hardwareProfilesClient(DEVICE)
    request.mockResolvedValueOnce({ data: { device_id: DEVICE, approval_supported: true, items: [] } })
    await client.inspect(); backend.mockResolvedValueOnce('http://other-core.test')
    await expect(client.mutate('install', item(), 'd'.repeat(32))).rejects.toThrow()
    expect(request).toHaveBeenCalledTimes(1)
  })
})
