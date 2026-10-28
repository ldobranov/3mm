import { afterEach, expect, it, vi } from 'vitest'
import axios from 'axios'
import { getToken } from '@/utils/auth'
import { createConnectorSettingsClient, readConnectorSettings } from './connector-settings'
import { connectorSettings, settingsSha } from './connector-settings.fixtures'
vi.mock('@/utils/runtime-config', () => ({ getBackendUrl: async () => 'https://core.example' }))
vi.mock('@/utils/auth', () => ({ getToken: vi.fn(() => 'core-login') }))
afterEach(() => { vi.restoreAllMocks(); vi.mocked(getToken).mockReturnValue('core-login') })

it('projects only redacted credential metadata, rejecting foreign artifacts', () => {
  const value = { ...connectorSettings(), password: 'must-not-return', ciphertext: 'must-not-return' }
  expect(JSON.stringify(readConnectorSettings(value, settingsSha))).not.toContain('must-not-return')
  expect(() => readConnectorSettings(value, 'c'.repeat(64))).toThrow('unavailable')
})
it('performs exactly one mutation with no refresh/replay and exposes only redacted errors', async () => {
  const send = vi.spyOn(axios, 'request').mockRejectedValue({ isAxiosError: true,
    config: { data: { credential: { password: 'private-password' } } }, response: { status: 500, data: 'private-password' } })
  await expect(createConnectorSettingsClient(settingsSha).save('business_api', {
    request_id: 'c'.repeat(32), expected_snapshot: 'b'.repeat(64), action: 'save',
  })).rejects.toMatchObject({ code: 'unconfirmed', message: 'unconfirmed' })
  expect(send).toHaveBeenCalledOnce()
  expect(send.mock.calls[0][0]).toMatchObject({ method: 'POST', headers: { Authorization: 'Bearer core-login' }, withCredentials: false })
})
it('treats a malformed success reply as unconfirmed rather than a rejected save', async () => {
  vi.spyOn(axios, 'request').mockResolvedValue({ data: { request_id: 'c'.repeat(32), status: 'unexpected' } })
  await expect(createConnectorSettingsClient(settingsSha).save('business_api', {
    request_id: 'c'.repeat(32), expected_snapshot: 'b'.repeat(64), action: 'save',
  })).rejects.toMatchObject({ code: 'unconfirmed', rejected: false })
})
it('distinguishes a missing login before dispatch from an unconfirmed mutation', async () => {
  vi.mocked(getToken).mockReturnValue('')
  const send = vi.spyOn(axios, 'request')
  await expect(createConnectorSettingsClient(settingsSha).save('business_api', {
    request_id: 'c'.repeat(32), expected_snapshot: 'b'.repeat(64), action: 'save',
  })).rejects.toMatchObject({ code: 'access_denied', rejected: true })
  expect(send).not.toHaveBeenCalled()
})
