import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
const save = vi.hoisted(() => vi.fn())
vi.mock('@/utils/save-diagnostic-json', () => ({saveDiagnosticJson:save}))

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
      if (url.endsWith('/readiness')) return Promise.resolve({ data: { schema_version:1, ready: true, entry_count: 4, estimated_backup_bytes: 100, available_bytes: 1000, issues: [],
        inventory:'available', applications:[{instance_id:'1'.repeat(24),module_id:'org.example.note',catalog_state:'retained',files:1,size_bytes:92}],unlisted_application_files:0 } })
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

  it('does not scan a hidden section; entering reads only catalog and status; preflight is explicit', async () => {
    const wrapper = mount(BackupRecoverySection, {props:{active:false}})
    await flushPromises()
    expect(http.get).not.toHaveBeenCalled()
    await wrapper.setProps({active:true})
    await flushPromises()
    expect(http.get.mock.calls.map(call=>call[0])).toEqual(['/api/v1/backups','/api/v1/backups/operation'])
    expect(wrapper.text()).toContain('has not been checked')
    await wrapper.findAll('button').find(b=>b.text()==='Check readiness')!.trigger('click')
    await flushPromises()
    expect(http.get).toHaveBeenCalledWith('/api/v1/backups/readiness',expect.anything())
    expect(wrapper.text()).toContain('org.example.note')
    expect(wrapper.text()).toContain(backupId)
    expect(http.post).not.toHaveBeenCalled()
  })

  it('shares only the latest compact inventory, without another scan, private details or a restore', async () => {
    const view = mount(BackupRecoverySection)
    await flushPromises()
    const button = (text:string) => view.findAll('button').find(b=>b.text()===text)
    expect(button('Save check summary')).toBeUndefined()
    const summary = {schema_version:1,kind:'backup_inventory_check',scope:'capture_preflight_only',archive_verified:false,
      ready_to_capture:true,inventory:'available',file_count:4,listed_application_groups:1,unlisted_application_files:0,
      issues:[{severity:'warning',code:'state.application_separate_preparation',occurrences:1}]}
    const reply = {schema_version:1,ready:true,inventory:'available',applications:[],issues:[],private_path:'/private/app',
      support_summary:{...summary,private:'do not export',issues:[{...summary.issues[0],message:'private details'}]}}
    http.get.mockResolvedValueOnce({data:reply})
    await button('Check readiness')!.trigger('click'); await flushPromises()
    const reads=http.get.mock.calls.length
    await button('Save check summary')!.trigger('click')
    expect(save).toHaveBeenCalledWith(summary,'backup-readiness.json')
    expect(http.get).toHaveBeenCalledTimes(reads)
    expect(http.post).not.toHaveBeenCalled()
    await button('Refresh')!.trigger('click'); await flushPromises()
    expect(button('Save check summary')).toBeUndefined()
  })

  it('requires exact create and restore confirmations', async () => {
    vi.stubGlobal('prompt', vi.fn()
      .mockReturnValueOnce('CREATE BACKUP')
      .mockReturnValueOnce(`RESTORE ${backupId}`))
    const wrapper = mount(BackupRecoverySection)
    await flushPromises()

    await wrapper.findAll('button').find(button => button.text() === 'Check readiness')!.trigger('click')
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

  it('retains the catalog if operation state is unavailable, without allowing a new action',async()=>{
    http.get.mockImplementation(async(url:string)=>{
      if(url.endsWith('/operation'))throw new Error('unavailable')
      return {data:{items:[{backup_id:backupId,created_at:'2026-08-28T12:00:00Z',archive_size_bytes:12}]}}
    })
    const wrapper=mount(BackupRecoverySection)
    await flushPromises()
    expect(wrapper.text()).toContain(backupId)
    expect(wrapper.findAll('button').find(b=>b.text()==='Restore')?.attributes('disabled')).toBeDefined()
    expect(http.post).not.toHaveBeenCalled()
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
