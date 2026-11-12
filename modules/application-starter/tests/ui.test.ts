import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { ApplicationHostError, applicationHostKey } from '@platform/application-ui/v1'
import Notes from '../source/frontend/Notes.vue'

const wrappers: ReturnType<typeof mount>[] = []
function setup(options: { write?: boolean; state?: string; lost?: boolean; locale?: string; saveError?: Error } = {}) {
  let saved = { text: 'Saved note', revision: 2 }
  const invoke = vi.fn(async (name, payload) => {
    if (name === 'read_note') return saved
    if (name === 'observe_resource') return { state: options.state || 'ready' }
    if (options.saveError) throw options.saveError
    if (options.lost) throw new Error('lost acknowledgement')
    saved = { text: payload.text, revision: payload.revision + 1 }
    return saved
  })
  const host = { invoke, getInfo: vi.fn().mockResolvedValue({ operations: options.write === false ? [] : [{ operation_id: 'save_note' }] }),
    presentation: { getInfo: () => ({ locale: options.locale || 'en' }), subscribe: () => () => {} } }
  const wrapper = mount(Notes, { global: { provide: { [applicationHostKey as symbol]: host } } })
  wrappers.push(wrapper)
  return { wrapper, host }
}
afterEach(() => { wrappers.splice(0).forEach(w => w.unmount()); vi.restoreAllMocks() })
const save = (wrapper: ReturnType<typeof mount>) => wrapper.find('button[type=submit]')

describe('starter through the public UI host', () => {
  it('loads without saving or operating any resource and preserves edits until explicit submit', async () => {
    const { wrapper, host } = setup(); await flushPromises()
    expect(host.invoke.mock.calls.map(c => c[0])).toEqual(['read_note', 'observe_resource'])
    await wrapper.find('textarea').setValue('Draft')
    expect(host.invoke).toHaveBeenCalledTimes(2)
    await wrapper.find('form').trigger('submit'); await flushPromises()
    expect(host.invoke).toHaveBeenLastCalledWith('save_note', { text: 'Draft', revision: 2 }, { idempotencyKey: expect.stringMatching(/^[a-f0-9]{32}$/) })
    expect(wrapper.text()).toContain('Saved.')
  })
  it('does not grant editing merely because the page is visible', async () => {
    const { wrapper, host } = setup({ write: false }); await flushPromises()
    expect(wrapper.find('textarea').attributes('readonly')).toBeDefined()
    expect(save(wrapper).attributes('disabled')).toBeDefined()
    await wrapper.find('form').trigger('submit'); await flushPromises()
    expect(host.invoke.mock.calls.every(c => c[0] !== 'save_note')).toBe(true)
  })
  it.each(['access_required', 'unavailable'])('keeps note editing separate from %s resource', async state => {
    const { wrapper } = setup({ state }); await flushPromises()
    await wrapper.find('textarea').setValue('Still editable')
    expect(save(wrapper).attributes('disabled')).toBeUndefined()
    expect(wrapper.text()).toContain(state === 'unavailable' ? 'Provider is unavailable' : 'approve resource access')
  })
  it.each([
    ['en', 'Save was refused: editing access is unavailable.', 'Editing requires the note_write'],
    ['bg', 'Записът е отказан: нямате текущ достъп за редактиране.', 'Редактирането изисква право note_write'],
  ])('explains revoked edit access in %s while retaining the draft and saved note', async (locale, denied, readOnly) => {
    const options = { locale, saveError: new ApplicationHostError('access_denied') as Error | undefined }
    const { wrapper, host } = setup(options); await flushPromises()
    await wrapper.find('textarea').setValue('Denied draft')
    await wrapper.find('form').trigger('submit'); await flushPromises()
    expect(wrapper.find('[role=alert]').text()).toContain(denied)
    expect(wrapper.find('textarea').element.value).toBe('Denied draft')
    expect(wrapper.find('textarea').attributes('readonly')).toBeDefined()
    expect(save(wrapper).attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain(readOnly)
    expect(host.invoke.mock.calls.map(c => c[0])).toEqual(['read_note', 'observe_resource', 'save_note'])
    await wrapper.find('form').trigger('submit'); await flushPromises()
    expect(host.invoke.mock.calls.filter(c => c[0] === 'save_note')).toHaveLength(1)
    host.getInfo.mockResolvedValue({ operations: [] })
    await wrapper.findAll('button')[1].trigger('click'); await flushPromises()
    expect(wrapper.find('[role=alert]').exists()).toBe(false)
    expect(wrapper.find('textarea').element.value).toBe('Saved note')
    expect(wrapper.find('textarea').attributes('readonly')).toBeDefined()
    // Restoring edit rights takes a fresh, explicit read; it never repeats the refused save.
    options.saveError = undefined
    host.getInfo.mockResolvedValue({ operations: [{ operation_id: 'save_note' }] })
    await wrapper.findAll('button')[1].trigger('click'); await flushPromises()
    expect(wrapper.find('textarea').attributes('readonly')).toBeUndefined()
    await wrapper.find('textarea').setValue('New explicit edit')
    expect(save(wrapper).attributes('disabled')).toBeUndefined()
    expect(host.invoke.mock.calls.filter(c => c[0] === 'save_note')).toHaveLength(1)
  })
  it.each([undefined, new ApplicationHostError('unconfirmed')])('retains the draft after unknown outcome (%#) and reads saved state without replay', async saveError => {
    const { wrapper, host } = setup({ lost: true, saveError }); await flushPromises()
    await wrapper.find('textarea').setValue('Unconfirmed')
    await wrapper.find('form').trigger('submit'); await flushPromises()
    expect(wrapper.find('textarea').element.value).toBe('Unconfirmed')
    expect(save(wrapper).attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('Save was not confirmed')
    expect(wrapper.text()).not.toContain('Save was refused')
    await wrapper.findAll('button')[1].trigger('click'); await flushPromises()
    expect(host.invoke.mock.calls.filter(c => c[0] === 'save_note')).toHaveLength(1)
    expect(wrapper.find('textarea').element.value).toBe('Saved note')
  })
})
