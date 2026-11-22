import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import OutgoingReportApproval from './OutgoingReportApproval.vue'

const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/utils/dynamic-http', () => ({ default: http }))
vi.mock('@/utils/i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }))
const link = 'peer_'+'a'.repeat(32), moduleId = 'org.example.sender'
const view = () => mount(OutgoingReportApproval, { props: { moduleId } })
async function click(wrapper: ReturnType<typeof view>, label: string) {
  await wrapper.findAll('button').find(b => b.text().startsWith('outgoingReports.'+label))!.trigger('click')
  await flushPromises()
}
const load = (approved: boolean) => http.get.mockResolvedValueOnce({ data: {module_id:moduleId,links:[link]} })
  .mockResolvedValueOnce({data:{approved,review_hash:'b'.repeat(64),sequence:1,checkpoint:'unconfirmed',contact:'unknown',
    review:{module_id:moduleId,link_id:link,contract:'installation.status.report.v2',package_sha256:'c'.repeat(64),
      receiver_key:'d'.repeat(64),origin:'https://receiver.invalid',receiver_id:'inst_'+'e'.repeat(32),target:'org.example.target',
      metadata:{consent:{summary_fields:['sdk_version'],node_ids:[],node_fields:[]}}}}})

beforeEach(()=>{vi.resetAllMocks()})
it.each([true,false])('reads before changing the exact outgoing link, approved=%s',async approved=>{
  load(approved); http.post.mockResolvedValue({status:204})
  const wrapper=view()
  expect(http.get).not.toHaveBeenCalled()
  await click(wrapper,'check'); await click(wrapper,'review')
  expect(http.post).not.toHaveBeenCalled()
  expect(wrapper.text()).toContain('sdk_version')
  expect(wrapper.text()).toContain('https://receiver.invalid')
  await click(wrapper,approved?'withdraw':'allow')
  expect(http.post).toHaveBeenCalledExactlyOnceWith('/api/v1/installation-peers/applications/'+moduleId+'/outbound/'+link+'/sender-approval',
    {expected_review_hash:'b'.repeat(64),allow:!approved},{timeout:15000})
  expect(wrapper.find('section').exists()).toBe(false)
})
it('does not repeat an uncertain decision or let another application reuse it',async ()=>{
  load(false); http.post.mockRejectedValue(new Error('lost'))
  const wrapper=view(); await click(wrapper,'check'); await click(wrapper,'review'); await click(wrapper,'allow')
  expect(wrapper.get('[role=status]').text()).toContain('uncertain')
  expect(wrapper.find('section').exists()).toBe(false)
  await wrapper.setProps({moduleId:'org.example.other'})
  expect(wrapper.text()).not.toContain('receiver.invalid')
  expect(http.post).toHaveBeenCalledTimes(1)
})
