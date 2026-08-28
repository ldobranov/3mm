import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))

vi.mock('@/utils/dynamic-http', () => ({ default: http }))
vi.mock('@/utils/i18n', () => ({
  useI18n: () => ({ t: (_key: string, fallback: string) => fallback }),
}))

import BackupRecoverySection from './BackupRecoverySection.vue'

const backupId = 'bkp_20260828T120000Z_0123abcd'

describe('Backup and recovery settings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    http.get.mockImplementation((url: string) => {
      if (url.includes('/exports/')) return Promise.resolve({ data: new Blob(['recovery']) })
      if (url.endsWith('/preview')) return Promise.resolve({ data: { ready: true, entry_count: 4, estimated_backup_bytes: 100, available_bytes: 1000, issues: [] } })
      if (url.endsWith('/operation')) return Promise.resolve({ data: { state: 'idle', message: 'idle' } })
      return Promise.resolve({ data: { retention_count: 5, items: [{ backup_id: backupId, created_at: '2026-08-28T12:00:00Z', application_version: '0.3.0-beta.9', architecture: 'aarch64', archive_size_bytes: 200 }] } })
    })
    http.post.mockImplementation((url: string) => {
      if (url.endsWith('/export')) return Promise.resolve({ data: { status: 'ready', export_id: 'a'.repeat(32) } })
      return Promise.resolve({ data: { status: 'queued' } })
    })
    vi.stubGlobal('confirm', vi.fn(() => true))
    vi.stubGlobal('URL', {
      createObjectURL: vi.fn(() => 'blob:recovery'),
      revokeObjectURL: vi.fn(),
    })
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  })

  it('loads preview, catalog and operation status', async () => {
    const wrapper = mount(BackupRecoverySection)
    await flushPromises()

    expect(http.get).toHaveBeenCalledWith('/api/v1/backups/preview')
    expect(http.get).toHaveBeenCalledWith('/api/v1/backups')
    expect(http.get).toHaveBeenCalledWith('/api/v1/backups/operation')
    expect(wrapper.text()).toContain(backupId)
  })

  it('requires exact create and restore confirmations', async () => {
    vi.stubGlobal('prompt', vi.fn()
      .mockReturnValueOnce('CREATE BACKUP')
      .mockReturnValueOnce(`RESTORE ${backupId}`))
    const wrapper = mount(BackupRecoverySection)
    await flushPromises()

    await wrapper.findAll('button').find(button => button.text().includes('Create backup'))!.trigger('click')
    await flushPromises()
    await wrapper.findAll('button').find(button => button.text().trim() === 'Restore')!.trigger('click')
    await flushPromises()

    expect(http.post).toHaveBeenCalledWith('/api/v1/backups', { confirmation: 'CREATE BACKUP' })
    expect(http.post).toHaveBeenCalledWith('/api/v1/backups/restore', {
      backup_id: backupId,
      confirmation: `RESTORE ${backupId}`,
    })
  })

  it('downloads a password-protected portable recovery file', async () => {
    vi.stubGlobal('prompt', vi.fn()
      .mockReturnValueOnce('recovery-password')
      .mockReturnValueOnce('recovery-password'))
    const wrapper = mount(BackupRecoverySection)
    await flushPromises()

    await wrapper.findAll('button').find(button => button.text().includes('Download'))!.trigger('click')
    await flushPromises()

    expect(http.post).toHaveBeenCalledWith(`/api/v1/backups/${backupId}/export`, {
      passphrase: 'recovery-password',
      confirmation: `DOWNLOAD ${backupId}`,
    })
    expect(http.get).toHaveBeenCalledWith(`/api/v1/backups/exports/${'a'.repeat(32)}`, { responseType: 'blob' })
  })

  it('uploads a portable recovery file for restore', async () => {
    vi.stubGlobal('prompt', vi.fn(() => 'recovery-password'))
    const wrapper = mount(BackupRecoverySection)
    await flushPromises()
    const input = wrapper.find('input[type="file"]')
    const file = new File(['recovery'], 'device.3mmrecovery', { type: 'application/octet-stream' })
    Object.defineProperty(input.element, 'files', { value: [file] })

    await input.trigger('change')
    await flushPromises()

    const request = http.post.mock.calls.find(([url]) => url === '/api/v1/backups/restore-file')
    expect(request).toBeTruthy()
    expect(request![1]).toBeInstanceOf(FormData)
    expect((request![1] as FormData).get('confirmation')).toBe('RESTORE FILE')
  })
})
