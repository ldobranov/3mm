import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import StorageSample from './StorageContentionSample.vue'
const { post, save } = vi.hoisted(() => ({ post: vi.fn(), save: vi.fn() }))
vi.mock('@/utils/dynamic-http', () => ({ default: { post } }))
vi.mock('@/utils/save-diagnostic-json', () => ({ saveDiagnosticJson: save }))
vi.mock('@/utils/i18n', () => ({ useI18n: () => ({ t: (_: string, fallback: string) => fallback }) }))
const base = { schema_version: 1, kind: 'sqlite_write_sample', coverage: 'new_core_engine_connections',
  window_ms: 5000, limited: false, families: [{ source: 'accounts', observed: 3, longest_ms: 30, open_at_end: 1 }] }
beforeEach(() => vi.resetAllMocks())
it('only measures on demand and exports the fixed, bounded fields', async () => {
  const view = mount(StorageSample)
  try {
    expect(post).not.toHaveBeenCalled()
    post.mockResolvedValue({ data: { ...base, secret: 'extra', families: [{ ...base.families[0], value: 'private' }] } })
    await view.get('button').trigger('click'); await flushPromises()
    expect(post).toHaveBeenCalledExactlyOnceWith('/api/v1/diagnostics/storage-sample')
    expect(view.text()).toContain('Accounts: 3'); expect(view.text()).toContain('open at end: 1')
    await view.findAll('button')[1].trigger('click')
    expect(save).toHaveBeenCalledExactlyOnceWith(base, 'core-database-sample.json')
    post.mockRejectedValue({ response: { status: 429, data: { detail: 'private' } } })
    await view.get('button').trigger('click'); await flushPromises()
    expect(view.text()).not.toContain('Accounts: 3'); expect(view.text()).not.toContain('private')
    expect(view.get('[role=alert]').text()).toContain('Wait a moment'); expect(view.findAll('button')).toHaveLength(1)
  } finally { view.unmount() }
})
it('distinguishes no observed writes from failed or malformed measurements', async () => {
  const view = mount(StorageSample)
  try {
    post.mockResolvedValueOnce({ data: { ...base, limited: true, families: [] } })
    await view.get('button').trigger('click'); await flushPromises()
    expect(view.text()).toContain('No eligible writes'); expect(view.text()).toContain('dropped')
    for (const value of [{ ...base, families: [{ ...base.families[0], source: 'private' }] }, {}]) {
      post.mockResolvedValueOnce({ data: value })
      await view.get('button').trigger('click'); await flushPromises()
      expect(view.text()).not.toContain('No eligible writes'); expect(view.text()).not.toContain('private')
      expect(view.get('[role=alert]').text()).toContain('No current measurement')
    }
  } finally { view.unmount() }
})
