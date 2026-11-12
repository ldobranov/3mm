import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { applicationHostKey, type ApplicationHostInfo } from '@platform/application-ui/v1'
import { createPreview } from '../preview/host'
import Notes from '../source/frontend/Notes.vue'

const info: ApplicationHostInfo = { host_version: 1, module_id: 'org.example.preview', active_version: '1.0.0',
  artifact_sha256: '0'.repeat(64), entrypoint_id: 'note', audience: 'operator',
  features: { operations: true, resource_authority: 'separate', browser_isolation: false },
  operations: [
    ...['read_note', 'observe_resource', 'lookup_save'].map(operation_id => ({ operation_id, kind: 'query' as const, idempotency: 'forbidden' as const })),
    { operation_id: 'save_note', kind: 'command', idempotency: 'required' },
  ] }
const wrappers: ReturnType<typeof mount>[] = []
function screen() {
  const simulation = createPreview(info)
  const wrapper = mount(Notes, { global: { provide: { [applicationHostKey as symbol]: simulation.host } } })
  wrappers.push(wrapper)
  return { ...simulation, wrapper }
}
afterEach(() => { wrappers.splice(0).forEach(w => w.unmount()); vi.restoreAllMocks() })

describe('project-owned local simulation', () => {
  it('keeps its data in memory and never uses an HTTP transport', async () => {
    const network = vi.spyOn(globalThis, 'fetch')
    const { wrapper, host } = screen(); await flushPromises()
    await wrapper.get('textarea').setValue('Local only')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(await host.invoke('read_note', {})).toEqual({ text: 'Local only', revision: 1 })
    expect(await createPreview(info).host.invoke('read_note', {})).toEqual({ text: 'Sample note', revision: 0 })
    expect(network).not.toHaveBeenCalled()
  })
  it('reproduces revocation on an already opened editor without losing its draft', async () => {
    const s = screen(); await flushPromises()
    await s.wrapper.get('textarea').setValue('Denied draft'); s.selectScenario('read_only')
    await s.wrapper.get('form').trigger('submit'); await flushPromises()
    expect(s.wrapper.text()).toContain('Save was refused')
    expect(s.wrapper.get('textarea').element.value).toBe('Denied draft')
    expect(await s.host.invoke('read_note', {})).toMatchObject({ text: 'Sample note' })
  })
  it.each(['provider_unavailable', 'access_required'])('keeps editing usable with %s', async value => {
    const s = screen(); s.selectScenario(value); await flushPromises()
    await s.wrapper.findAll('button')[1].trigger('click'); await flushPromises()
    await s.wrapper.get('textarea').setValue('Still editable')
    await s.wrapper.get('form').trigger('submit'); await flushPromises()
    expect(await s.host.invoke('read_note', {})).toMatchObject({ text: 'Still editable' })
    expect(await s.host.invoke('observe_resource', {})).toEqual({ state: value === 'provider_unavailable' ? 'unavailable' : 'access_required' })
  })
  it('shows completed-but-unconfirmed save and explicit reload without a second command', async () => {
    const s = screen(); await flushPromises(); s.selectScenario('unconfirmed')
    const invoke = vi.spyOn(s.host, 'invoke')
    await s.wrapper.get('textarea').setValue('Saved without acknowledgement')
    await s.wrapper.get('form').trigger('submit'); await flushPromises()
    expect(s.wrapper.text()).toContain('Save was not confirmed')
    await s.wrapper.get('form').trigger('submit'); await flushPromises()
    expect(invoke.mock.calls.filter(call => call[0] === 'save_note')).toHaveLength(1)
    await s.wrapper.findAll('button')[1].trigger('click'); await flushPromises()
    expect(s.wrapper.get('textarea').element.value).toBe('Saved without acknowledgement')
    expect(invoke.mock.calls.filter(call => call[0] === 'save_note')).toHaveLength(1)
  })
  it('keeps a stale draft separate from the conflicting saved revision', async () => {
    const s = screen(); await flushPromises(); s.selectScenario('conflict')
    await s.wrapper.get('textarea').setValue('Stale draft')
    await s.wrapper.get('form').trigger('submit'); await flushPromises()
    expect(s.wrapper.text()).toContain('Save was not confirmed')
    expect(await s.host.invoke('read_note', {})).toMatchObject({ text: 'Changed in another simulated editor' })
  })
  it('switches real app messages and resets only simulated data', async () => {
    const s = screen(); await flushPromises(); s.setLocale('bg'); await flushPromises()
    expect(s.wrapper.text()).toContain('Примерна бележка')
    s.selectScenario('read_only'); s.reset()
    expect((await s.host.getInfo()).operations.some(op => op.operation_id === 'save_note')).toBe(true)
    expect(() => s.selectScenario('invalid')).toThrow()
    expect(() => s.host.administration).toThrow()
  })
})
