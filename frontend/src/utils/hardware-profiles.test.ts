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
  it('preserves bounded plain-text instructions for a non-display template', () => {
    const template = { template_id: 'example.button', name: 'Button', simulated: false,
      fields: [{ key: 'pin', label: 'Pin', type: 'number', default: 17 }], help: 'Contact to GND only.' }
    const catalog = { device_id: DEVICE, approval_supported: true, items: [], templates: [template] }
    expect(readHardwareProfiles(catalog, DEVICE).templates[0]?.help).toBe(template.help)
    expect(() => readHardwareProfiles({ ...catalog, templates: [{ ...template, help: '<x>'.repeat(400) }] }, DEVICE)).toThrow()
  })
  it('prepares only settings through the inert endpoint and validates its identity', async () => {
    request.mockResolvedValueOnce({ data: { device_id: DEVICE, package_sha256: 'b'.repeat(64),
      profile_sha256: 'c'.repeat(64), activation: 'not_requested' } })
    expect(await hardwareProfilesClient(DEVICE).prepare('example.display', { columns: 16 })).toBe('b'.repeat(64))
    expect(request).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({ method: 'POST',
      url: `http://core.test/api/v1/modules/devices/${DEVICE}/hardware-profiles/prepare`,
      data: { template_id: 'example.display', configuration: { columns: 16 } } }))
    request.mockResolvedValueOnce({ data: { device_id: 'wrong', activation: 'not_requested' } })
    await expect(hardwareProfilesClient(DEVICE).prepare('example.display', {})).rejects.toThrow()
    expect(request).toHaveBeenCalledTimes(2)
  })
  it('rejects a malformed template catalog instead of inventing configurable drivers', () => {
    expect(() => readHardwareProfiles({ device_id: DEVICE, approval_supported: true, items: [],
      templates: [{ template_id: 'example.display', name: 'Test', simulated: false, fields: [
        { key: 'command', type: 'shell', default: '' }] }] }, DEVICE)).toThrow()
  })
  it('reads a real configurable field catalog and distinguishes invalid input from a lost preparation result', async () => {
    const fields = [
      { key: 'display_id', label: 'Display ID', type: 'text', default: 'display.main', maxlength: 64 },
      { key: 'columns', label: 'Columns', type: 'number', default: 16, min: 1, max: 40 },
      { key: 'rows', label: 'Rows', type: 'select', default: 2, options: [{ value: '2', label: '2' }] },
      { key: 'backlight_active_high', label: 'Backlight', type: 'checkbox', default: true },
    ]
    const parsed = readHardwareProfiles({ device_id: DEVICE, approval_supported: true, items: [],
      templates: [{ template_id: 'example.display', name: 'Example', simulated: false, fields }] }, DEVICE)
    expect(parsed.templates[0]?.fields).toEqual(fields)
    request.mockRejectedValueOnce({ response: { status: 422 } })
    await expect(hardwareProfilesClient(DEVICE).prepare('example.display', { columns: 41 })).rejects.toThrow('invalidConfiguration')
    expect(request).toHaveBeenCalledTimes(1)
  })
  it('reads without writes and binds consent to exact package/profile/device with one request', async () => {
    const p = item(), client = hardwareProfilesClient(DEVICE)
    request.mockResolvedValueOnce({ data: { device_id: DEVICE, approval_supported: true, items: [p], templates: [] } })
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
    request.mockResolvedValueOnce({ data: { device_id: DEVICE, approval_supported: true, items: [], templates: [] } })
    await client.inspect(); backend.mockResolvedValueOnce('http://other-core.test')
    await expect(client.mutate('install', item(), 'd'.repeat(32))).rejects.toThrow()
    expect(request).toHaveBeenCalledTimes(1)
  })
})
