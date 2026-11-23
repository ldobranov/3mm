import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ApplicationLimitsDialog from './ApplicationLimitsDialog.vue'

const get = vi.hoisted(() => vi.fn())
vi.mock('@/utils/dynamic-http', () => ({ default: { get } }))
const dialogs: ReturnType<typeof mount>[] = []
function open() {
  const dialog = mount(ApplicationLimitsDialog, {
    props: { moduleId: 'org.example.sample', name: 'Sample' },
    global: { stubs: { UiDialog: { template: '<div><slot/><slot name="actions"/></div>' } } },
  })
  dialogs.push(dialog)
  return dialog
}
afterEach(() => { dialogs.splice(0).forEach(d => d.unmount()); get.mockReset(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

describe('Service resource report', () => {
  it('labels the latest Core offer separately from device time, for this reference only', async () => {
    vi.stubGlobal('URL', {createObjectURL: () => 'blob:fixture', revokeObjectURL: vi.fn()})
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    get.mockResolvedValueOnce({data:{state:'not_running'}})
    const d = open(); await flushPromises()
    const id = 'cmd_' + '4'.repeat(32)
    await d.get('input').setValue(id)
    get.mockResolvedValueOnce({data:{kind:'application_support',schema_version:1,status:'ready',cases:[],
      application:{module_id:'org.example.sample'},work:{reference:id,status:'found',recorded_state:'delivered',
        delivery:{recorded_attempts:2,queue_to_latest_offer_seconds:24,permit_claimed:false}}}})
    await d.findAll('button').find(b => b.text() === 'Save app diagnostics')!.trigger('click')
    await flushPromises()
    expect(d.text()).toContain('24 s.')
    expect(d.text()).toContain('This is not device execution time.')
    expect(d.text()).toContain('Core has not recorded a one-use permit claim')
    await d.get('input').setValue('task_' + '2'.repeat(32))
    expect(d.text()).not.toContain('24 s.')
    expect(get).toHaveBeenCalledTimes(2)
  })
  it('does not look up work while typing or accept an export for a different reference', async () => {
    get.mockResolvedValueOnce({data:{state:'not_running'}})
    const d = open(); await flushPromises()
    const save = d.findAll('button').find(b => b.text() === 'Save app diagnostics')!
    const ref = 'cmd_' + 'a'.repeat(32)
    await d.get('input').setValue('private text')
    expect(save.attributes('disabled')).toBeDefined()
    await d.get('input').setValue(ref)
    expect(get).toHaveBeenCalledTimes(1)
    get.mockResolvedValueOnce({data:{kind:'application_support',schema_version:1,status:'ready',cases:[],
      application:{module_id:'org.example.sample'},work:{reference:'cmd_'+'b'.repeat(32)}}})
    await save.trigger('click'); await flushPromises()
    expect(get).toHaveBeenLastCalledWith(expect.stringContaining('support-snapshot'),expect.objectContaining({params:{reference:ref}}))
    expect(d.get('[role="alert"]').text()).toContain('Could not download')
  })
  it.each(['partial', 'wrong-package', 'revoked'])('downloads only an explicit, matching %s support report', async mode => {
    const create = vi.fn(() => 'blob:fixture'), revoke = vi.fn()
    vi.stubGlobal('URL', {createObjectURL: create, revokeObjectURL: revoke})
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    get.mockResolvedValueOnce({data:{state:'not_running'}})
    const d = open(); await flushPromises()
    expect(get).toHaveBeenCalledTimes(1)
    const save = d.findAll('button').find(b => b.text() === 'Save app diagnostics')!
    if (mode === 'revoked') get.mockRejectedValueOnce({response:{status:401}})
    else get.mockResolvedValueOnce({data:{kind:'application_support',schema_version:1,status:'partial',cases:[],
      application:{module_id:mode === 'partial' ? 'org.example.sample' : 'org.example.other'}}})
    await save.trigger('click'); await flushPromises()
    expect(get).toHaveBeenLastCalledWith('/api/v1/application-extensions/org.example.sample/support-snapshot', expect.anything())
    expect(get).toHaveBeenCalledTimes(2)
    if (mode === 'partial') {
      expect(d.text()).toContain('Downloaded a partial report')
      expect(click).toHaveBeenCalledOnce(); expect(revoke).toHaveBeenCalledWith('blob:fixture')
    } else {
      expect(d.get('[role="alert"]').text()).toContain('Could not download')
      expect(create).not.toHaveBeenCalled()
    }
  })
  it('distinguishes a live process limit from configured service policies', async () => {
    get.mockResolvedValueOnce({data:{state:'observed',
      main_process_fds:{state:'os_enforced', soft:128, hard:256},
      service_policy:{start_burst:5,start_window:'1min',restart_delay:'3s',stop_timeout:null,
        private_network:true,unix_sockets_only:null}}})
    const d = open()
    await flushPromises()
    const details = d.get('details')
    expect(details.element.open).toBe(false)
    expect(details.text()).toContain('128 / 256')
    expect(details.text()).toContain('5 / 1min')
    expect(details.text()).toContain('Local-only policy not verified')
    expect(details.text()).not.toContain('Private network; local Unix sockets only')
    expect(get).toHaveBeenCalledTimes(1)
  })
  it('distinguishes a shared lower ceiling from an incomplete hierarchy', async () => {
    get.mockResolvedValueOnce({ data: { state: 'observed',
      limits: {tasks: {state:'os_enforced', max_tasks:64}, cpu:{state:'not_set_here'}},
      hierarchy_limits: {tasks:{state:'os_enforced', source:'parent', max_tasks:32, complete:true},
        cpu:{state:'unavailable', complete:false}} } })
    const dialog = open()
    await flushPromises()
    expect(dialog.text()).toContain('Shared group ceiling: 32')
    expect(dialog.text()).toContain('Could not verify the entire hierarchy')
    expect(dialog.text()).toContain('64')
  })
  it('separates a measured zero from an unknown usage and an unenforced limit', async () => {
    get.mockResolvedValueOnce({ data: {
      state: 'observed', usage: { memory_bytes: null, tasks: 0 },
      limits: { memory: { state: 'unavailable', reason: 'controller_not_available_on_host' },
        cpu: { state: 'os_enforced', quota_usec: 50000, period_usec: 100000 },
        tasks: { state: 'not_set_here' } },
      supervision: { state: 'active', result: 'success', restart_count: 0 },
    } })
    const d = open()
    await flushPromises()
    const fields = Object.fromEntries(d.findAll('dt').map(e => [e.text(), e.element.nextElementSibling?.textContent?.trim()]))
    expect(fields).toMatchObject({ RAM: 'Controller unavailable on this host', 'CPU quota': '50%',
      'RAM in use': 'Could not verify', 'Tasks in use (including threads)': '0',
      'Current state': 'Running', 'Automatic restarts': '0' })
    expect(get).toHaveBeenCalledExactlyOnceWith('/api/v1/application-extensions/org.example.sample/resource-limits', expect.anything())
  })

  it('discards the previous sample while refreshing and shows failure even without limits', async () => {
    get.mockResolvedValueOnce({ data: { state: 'observed', usage: { memory_bytes: 5242880, tasks: 3 } } })
    let finish!: (r: unknown) => void
    get.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    const d = open()
    await flushPromises()
    expect(d.text()).toContain('5 MiB')
    await d.findAll('button').find(b => b.text() === 'Refresh')!.trigger('click')
    expect(d.text()).not.toContain('5 MiB')
    finish({ data: { state: 'not_running', supervision: { state: 'failed', result: 'oom-kill', restart_count: null } } })
    await flushPromises()
    expect(d.text()).toContain('Process killed due to memory pressure')
    expect(d.findAll('dt').find(e => e.text() === 'Automatic restarts')?.element.nextElementSibling?.textContent).toBe('Could not verify')
    expect(d.text()).not.toContain('Usage at last check')
    expect(get).toHaveBeenCalledTimes(2)
  })

  it.each([[401, 'Administrator access is required'], [409, 'changed'], [429, 'in progress']])(
    'presents the HTTP %i refusal without retrying', async (status, message) => {
      get.mockRejectedValueOnce({ isAxiosError: true, response: { status } })
      const d = open()
      await flushPromises()
      expect(d.get('[role="alert"]').text()).toContain(message)
      expect(get).toHaveBeenCalledTimes(1)
    })
})
