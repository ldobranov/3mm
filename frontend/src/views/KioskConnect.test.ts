import {beforeEach,afterEach,it,expect,vi} from 'vitest'
import {mount,flushPromises} from '@vue/test-utils'
import {ref} from 'vue'
import Connect from './KioskConnect.vue'
const api=vi.hoisted(()=>({claim:vi.fn(),recover:vi.fn(),info:vi.fn(),pending:vi.fn(),token:vi.fn(),link:vi.fn(),catalog:vi.fn(),routes:vi.fn(),replace:vi.fn(),forget:vi.fn()}))
vi.mock('@/utils/kiosk-session',()=>({beginKioskClaim:api.claim,recoverKioskClaim:api.recover,kioskClaimInfo:api.pending,kioskIdentity:api.info,forgetKioskConnection:api.forget,takeKioskLink:api.link,getKioskTokenFor:api.token}))
vi.mock('@/utils/compiled-ui',()=>({getCompiledUiCatalog:api.catalog}))
vi.mock('@/router',()=>({reloadCompiledUiRoutes:api.routes}))
vi.mock('vue-router',()=>({useRouter:()=>({replace:api.replace})}))
vi.mock('@/utils/i18n',()=>({useI18n:()=>({currentLanguage:ref('en')})}))
const module='org.example.kiosk',identity={module,artifact:'a'.repeat(64),build:'b'.repeat(64)}
let wrapper:ReturnType<typeof mount>|undefined
beforeEach(()=>{
  vi.clearAllMocks();api.info.mockReturnValue(null);api.pending.mockReturnValue(null);api.link.mockReturnValue({module,code:'x'.repeat(32)})
  api.claim.mockImplementation(async()=>{api.info.mockReturnValue(identity)});api.recover.mockImplementation(async()=>{api.info.mockReturnValue(identity);api.pending.mockReturnValue(null)})
  api.token.mockResolvedValue('kiosk-token');api.catalog.mockResolvedValue([{module_id:module,source_sha256:identity.artifact,built_ui_sha256:identity.build,entrypoints:[{kind:'route',application_audience:'kiosk',route:'/approved/kiosk'}]}])
})
afterEach(()=>wrapper?.unmount())
it('renews then loads the current kiosk catalog before entering its approved route',async()=>{
  wrapper=mount(Connect);expect(api.claim).not.toHaveBeenCalled()
  await wrapper.get('form').trigger('submit');await flushPromises()
  expect(api.claim).toHaveBeenCalledExactlyOnceWith(module,'x'.repeat(32))
  expect(api.token).toHaveBeenCalledWith(module,true);expect(api.catalog).toHaveBeenCalledWith(true)
  expect(api.token.mock.invocationCallOrder[0]).toBeLessThan(api.catalog.mock.invocationCallOrder[0]!)
  expect(api.catalog.mock.invocationCallOrder[0]).toBeLessThan(api.replace.mock.invocationCallOrder[0]!)
  expect(api.replace).toHaveBeenCalledWith('/approved/kiosk')
})
it('does not repeat claim or navigate when the installed UI binding changed',async()=>{
  api.info.mockReturnValue(identity);api.catalog.mockResolvedValue([{module_id:module,source_sha256:'f'.repeat(64),built_ui_sha256:identity.build,entrypoints:[]}])
  wrapper=mount(Connect);await wrapper.get('button').trigger('click');await flushPromises()
  expect(api.claim).not.toHaveBeenCalled();expect(api.recover).not.toHaveBeenCalled();expect(api.replace).not.toHaveBeenCalled()
  expect(wrapper.get('[role="alert"]').text()).toContain('unavailable')
})
it('offers explicit recovery of the original request without issuing a new claim',async()=>{
  api.pending.mockReturnValue({module,request_id:'c'.repeat(32)})
  wrapper=mount(Connect);expect(wrapper.text()).toContain('c'.repeat(32));expect(api.recover).not.toHaveBeenCalled()
  await wrapper.get('button').trigger('click');await flushPromises()
  expect(api.recover).toHaveBeenCalledOnce();expect(api.claim).not.toHaveBeenCalled();expect(api.replace).toHaveBeenCalledWith('/approved/kiosk')
})
