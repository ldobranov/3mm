import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import PeerReportLookup from './PeerReportLookup.vue'
const { get, save } = vi.hoisted(() => ({ get: vi.fn(), save: vi.fn() }))
vi.mock('@/utils/dynamic-http', () => ({ default: { get } }))
vi.mock('@/utils/save-diagnostic-json', () => ({ saveDiagnosticJson: save }))
vi.mock('@/utils/i18n', () => ({ useI18n: () => ({t: (key: string) => key.split('.').at(-1)}) }))
const owner = 'org.example.meter'
const link = 'peer_' + '1'.repeat(32), report = 'report_' + '2'.repeat(32)
const base = {kind:'peer_report_observation', schema_version:1, source:'local_outbound_slot',
  module_id:owner, link_id:link, report_id:report, state:'outcome_unconfirmed', automatic_replay_allowed:false}
const setup = () => mount(PeerReportLookup, {props:{moduleId:owner}})
async function prepare(view: ReturnType<typeof setup>) {
  const inputs = view.findAll('input')
  await inputs[0].setValue(link)
  await inputs[1].setValue(report)
}
beforeEach(() => vi.resetAllMocks())
it('an empty continuation does not claim that the preceding page had no records', async () => {
  const view = setup()
  try {
    get.mockResolvedValueOnce({data:{module_id:owner, limited:true, references:[{link_id:link, report_id:report}]}})
    await view.get('button[type=button]').trigger('click'); await flushPromises()
    get.mockResolvedValueOnce({data:{module_id:owner, limited:false, references:[]}})
    await view.findAll('button').find(b => b.text() === 'nextPage')!.trigger('click'); await flushPromises()
    expect(view.get('[role=status]').text()).toBe('noMore')
    expect(get).toHaveBeenCalledTimes(2)
  } finally { view.unmount() }
})
it('never queries on mount, expand or edit; queries one original pair and exports only known evidence', async () => {
  const view = setup()
  try {
    await view.get('summary').trigger('click')
    await view.get('form').trigger('submit')
    expect(view.get('button[type=submit]').attributes('disabled')).toBeDefined()
    await prepare(view)
    expect(get).not.toHaveBeenCalled()
    get.mockResolvedValue({data:{...base, projection:'private data', origin:'private URL'}})
    await view.get('form').trigger('submit'); await flushPromises()
    expect(get).toHaveBeenCalledExactlyOnceWith('/api/v1/installation-peers/applications/' + owner +
      '/outbound/' + link + '/reports/' + report, {signal:expect.any(AbortSignal), timeout:10000})
    expect(view.get('[role=status]').text()).toContain('outcome_unconfirmed')
    await view.get('[role=status] button').trigger('click')
    expect(save).toHaveBeenCalledExactlyOnceWith(base, 'peer-report.json')
    await view.findAll('input')[1].setValue('')
    expect(view.find('[role=status]').exists()).toBe(false)
  } finally { view.unmount() }
})
it('drops a delayed answer after the selected app changes and refuses malformed, mismatched and denied answers', async () => {
  const view = setup()
  try {
    await prepare(view)
    let finish!: (result: unknown) => void
    get.mockReturnValueOnce(new Promise((r) => { finish = r }))
    await view.get('form').trigger('submit')
    await view.get('form').trigger('submit')
    expect(get).toHaveBeenCalledTimes(1)
    await view.setProps({moduleId:'org.example.other'})
    expect(get.mock.calls[0][1].signal.aborted).toBe(true)
    finish({data:base}); await flushPromises()
    expect(view.find('[role=status]').exists()).toBe(false)
    await prepare(view)
    for (const bad of [base, {...base,module_id:'org.example.other', state:'private text'},
                       {...base,module_id:'org.example.other', automatic_replay_allowed:true}]) {
      get.mockResolvedValueOnce({data:bad})
      await view.get('form').trigger('submit'); await flushPromises()
      expect(view.get('[role=alert]').text()).toContain('failed')
      expect(view.find('[role=status]').exists()).toBe(false)
    }
    get.mockRejectedValueOnce({response:{status:403, data:'private text'}})
    await view.get('form').trigger('submit'); await flushPromises()
    expect(view.text()).not.toContain('private')
    expect(save).not.toHaveBeenCalled()
  } finally { view.unmount() }
})
it('finds references only on demand and selecting one does not read or resend its report', async () => {
  const view = setup()
  try {
    get.mockResolvedValueOnce({data:{module_id:owner,limited:false,references:[]}})
    await view.get('button[type=button]').trigger('click'); await flushPromises()
    expect(view.get('[role=status]').text()).toContain('empty')
    get.mockResolvedValueOnce({data:{module_id:owner,limited:true,references:[{link_id:link,report_id:report,private:'secret'}]}})
    await view.get('button[type=button]').trigger('click'); await flushPromises()
    expect(get.mock.calls.map(c=>c[0])).toEqual(Array(2).fill('/api/v1/installation-peers/applications/' + owner + '/outbound/report-references'))
    expect(view.text()).toContain('limited')
    await view.get('select').setValue('0')
    expect(view.findAll('input').map(i=>(i.element as HTMLInputElement).value)).toEqual([link,report])
    expect(get).toHaveBeenCalledTimes(2)
    expect(view.text()).not.toContain('secret')
    const later = 'peer_'+'3'.repeat(32)
    get.mockResolvedValueOnce({data:{module_id:owner,limited:false,references:[{link_id:later,report_id:report}]}})
    const next = view.findAll('button').find(b => b.text() === 'nextPage')!
    await next.trigger('click'); await flushPromises()
    expect(get.mock.calls[2][1]).toEqual({signal:expect.any(AbortSignal),timeout:10000,params:{after:link}})
    expect(view.findAll('input').map(i=>(i.element as HTMLInputElement).value)).toEqual(['',''])
    expect(view.get('select').text()).toContain(later)
    expect(view.findAll('button').some(b => b.text() === 'nextPage')).toBe(false)
    expect(get).toHaveBeenCalledTimes(3)
    await view.setProps({moduleId:'org.example.other'})
    expect(view.find('select').exists()).toBe(false)
    expect(view.findAll('input').map(i=>(i.element as HTMLInputElement).value)).toEqual(['',''])
  } finally { view.unmount() }
})
