import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
const locale = vi.hoisted(() => ({ value: 'en' }))
vi.mock('@/utils/dynamic-http', () => ({ default: http }))
vi.mock('@/utils/i18n', async () => {
  const { ref } = await import('vue')
  return { useI18n: () => ({ currentLanguage: ref(locale.value), t: (_: string, fallback: string) => fallback }) }
})
import Dialog from './ApplicationCommandResourcesDialog.vue'
import { base, moduleId, sha, first, second, configuration, authority, discovery, preview, status, candidate } from './command-resources.fixtures'
const wrappers: VueWrapper[] = []
const nativeMethods = ['showModal', 'close'].map(name => ({ name, descriptor: Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, name) }))
let currentStatus = status()
const get = (url: string) => {
  if (url === base) return { data: { pending: null } }
  if (url.endsWith('/configuration')) return { data: configuration() }
  if (url.endsWith('/discovery')) return { data: discovery() }
  if (url.endsWith('/authority')) return { data: authority() }
  if (url === base + '/' + preview().preview_id) return { data: currentStatus }
  throw new Error('Unexpected GET ' + url)
}
async function open() {
  const wrapper = mount(Dialog, { props: { moduleId, packageSha: sha, name: 'Door controller' } })
  wrappers.push(wrapper); await flushPromises(); return wrapper
}
function button(wrapper: VueWrapper, text: string) { return wrapper.findAll('button').find(item => item.text() === text)! }
async function review(wrapper: VueWrapper) {
  await wrapper.get(`input[value="${second}"]`).setValue(true)
  await button(wrapper, 'Review change').trigger('click'); await flushPromises()
}
beforeEach(() => {
  vi.clearAllMocks(); locale.value = 'en'; currentStatus = status()
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value: function (this: HTMLDialogElement) { this.open = true } })
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value: function (this: HTMLDialogElement) { this.open = false } })
  http.get.mockImplementation(async (url: string) => get(url))
  http.post.mockImplementation(async (url: string) => ({ data: url === base ? preview() : {} }))
})
afterEach(() => {
  wrappers.splice(0).forEach(item => item.unmount()); vi.restoreAllMocks(); vi.useRealTimers()
  for (const { name, descriptor } of nativeMethods) {
    if (descriptor) Object.defineProperty(HTMLDialogElement.prototype, name, descriptor)
    else Reflect.deleteProperty(HTMLDialogElement.prototype, name)
  }
})

describe('Command resource management', () => {
  it('only observes on open and separates compatibility from readiness', async () => {
    http.get.mockImplementation(async (url: string) => url.endsWith('/discovery') ? { data: { ...discovery(), candidates: [candidate(),
      { ...candidate(second), readiness: 'unknown', readiness_reason: 'health_missing' },
      { ...candidate('dev_' + '3'.repeat(32)), compatible: false, selectable: false, blockers: ['contract_version_mismatch'] }] } } : get(url))
    const w = await open()
    expect(http.post).not.toHaveBeenCalled()
    expect(w.text()).toContain('Entrance controller')
    expect(w.text()).toContain('Readiness unknown')
    expect(w.get(`input[value="${first}"]`).attributes('disabled')).toBeDefined()
    expect(w.get(`input[value="${second}"]`).attributes('disabled')).toBeUndefined()
    expect(w.get(`input[value="dev_${'3'.repeat(32)}"]`).attributes('disabled')).toBeDefined()
    expect(button(w, 'Review change').attributes('disabled')).toBeDefined()
  })
  it('reviews both providers and requires explicit acknowledgment before one apply', async () => {
    const w = await open(); await review(w)
    expect(http.post).toHaveBeenCalledTimes(1)
    expect(w.findAll('.resource-comparison > div')).toHaveLength(2)
    expect(w.text()).toContain('org.example.second')
    expect(button(w, 'Change resource and restart').attributes('disabled')).toBeDefined()
    await w.get('.resource-review input[type="checkbox"]').setValue(true)
    await button(w, 'Change resource and restart').trigger('click'); await flushPromises()
    expect(http.post.mock.calls.filter(([url]) => url.endsWith('/apply'))).toHaveLength(1)
    expect(w.text()).toContain('resource change completed')
    expect(w.emitted('changed')).toHaveLength(1)
  })
  it('reconciles a lost apply reply from status without repeating the mutation', async () => {
    currentStatus = status('recovery_required')
    http.post.mockImplementation(async (url: string) => {
      if (url.endsWith('/apply')) throw new Error('Reply lost')
      return { data: preview() }
    })
    const w = await open(); await review(w)
    await w.get('.resource-review input[type="checkbox"]').setValue(true)
    await button(w, 'Change resource and restart').trigger('click'); await flushPromises()
    expect(w.text()).toContain('resource change is unfinished')
    expect(w.text()).not.toContain('Resources could not be read')
    expect(button(w, 'Stop and verify runtime').attributes('disabled')).toBeDefined()
    expect(http.post.mock.calls.filter(([url]) => url.endsWith('/apply'))).toHaveLength(1)
  })
  it('keeps apply blocked while both mutation reply and status are unknown', async () => {
    http.post.mockImplementation(async (url: string) => {
      if (url.endsWith('/apply')) throw new Error('Reply lost')
      return { data: preview() }
    })
    http.get.mockImplementation(async (url: string) => {
      if (url === base + '/' + preview().preview_id) throw new Error('No connection')
      return get(url)
    })
    const w = await open(); await review(w)
    await w.get('.resource-review input[type="checkbox"]').setValue(true)
    await button(w, 'Change resource and restart').trigger('click'); await flushPromises()
    expect(w.text()).toContain('change could not be confirmed')
    await button(w, 'Refresh status').trigger('click'); await flushPromises()
    expect(http.post.mock.calls.filter(([url]) => url.endsWith('/apply'))).toHaveLength(1)
    expect(w.find('.resource-review').exists()).toBe(false)
  })
  it('finds interrupted work after reopening without depending on manifest or permission preview', async () => {
    currentStatus = status('recovery_required')
    http.get.mockImplementation(async (url: string) => {
      if (url === base) return { data: { pending: currentStatus } }
      if (url === base + '/' + preview().preview_id) return { data: currentStatus }
      throw new Error('Optional resource unavailable')
    })
    const w = await open()
    expect(w.text()).toContain('resource change is unfinished')
    expect(http.get).toHaveBeenCalledTimes(1)
    await w.get('input[type="checkbox"]').setValue(true)
    http.post.mockImplementation(async () => { currentStatus = status('recovered_disabled'); return { data: currentStatus } })
    await button(w, 'Stop and verify runtime').trigger('click'); await flushPromises()
    expect(w.text()).toContain('application is stopped')
    expect(http.post.mock.calls.map(([url]) => url)).toEqual([base + '/' + preview().preview_id + '/recover'])
    expect(w.find('.resource-review').exists()).toBe(false)
  })
  it('expires review and clears acknowledgment when the device choice changes', async () => {
    vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] })
    const w = await open(); await review(w)
    await w.get('.resource-review input[type="checkbox"]').setValue(true)
    vi.advanceTimersByTime(901000); await flushPromises()
    expect(w.text()).toContain('review has expired')
    expect(button(w, 'Change resource and restart').attributes('disabled')).toBeDefined()
    expect(http.post.mock.calls.some(([url]) => url.endsWith('/apply'))).toBe(false)
    await button(w, 'Change selection').trigger('click')
    expect(w.find('.resource-review').exists()).toBe(false)
  })
  it('refuses a malformed or foreign preview without an apply button', async () => {
    http.post.mockResolvedValue({ data: { ...preview(), module_id: 'org.other.app' } })
    const w = await open(); await review(w)
    expect(w.find('.resource-review').exists()).toBe(false)
    expect(http.post.mock.calls.some(([url]) => url.endsWith('/apply'))).toBe(false)
  })
  it('discards late observations after closing', async () => {
    let complete!: (value: unknown) => void
    http.get.mockImplementation(() => new Promise(resolve => { complete = resolve }))
    const w = mount(Dialog, { props: { moduleId, packageSha: sha, name: 'Door controller' } })
    w.unmount(); complete({ data: { pending: null } }); await flushPromises()
    expect(http.get).toHaveBeenCalledTimes(1)
    expect(http.post).not.toHaveBeenCalled()
  })
  it('provides Bulgarian labels', async () => {
    locale.value = 'bg'
    const w = await open()
    expect(w.text()).toContain('Ресурси за команди')
    expect(w.text()).toContain('Изберете съвместимо устройство')
  })
  it('loads bounded candidate pages only on request and preserves an off-page selection', async () => {
    const ids = Array.from({ length: 32 }, (_, index) => 'dev_' + (index + 1).toString(16).padStart(32, '0'))
    http.get.mockImplementation(async (url: string, options?: { params?: { after_device_id?: string } }) => {
      if (!url.endsWith('/discovery')) return get(url)
      return { data: { ...discovery(), candidates: options?.params?.after_device_id ? [candidate(second)] : ids.map(id => candidate(id)),
        next_after_device_id: options?.params?.after_device_id ? null : ids[31] } }
    })
    const w = await open()
    expect(w.text()).toContain('Current device: Entrance controller')
    expect(http.get.mock.calls.filter(([url]) => url.endsWith('/discovery'))).toHaveLength(1)
    await button(w, 'Load more devices').trigger('click'); await flushPromises()
    expect(w.findAll('input[type="radio"]')).toHaveLength(33)
    expect(http.get.mock.calls.filter(([url]) => url.endsWith('/discovery'))[1]?.[1]).toEqual({
      timeout: 12000, params: { after_device_id: ids[31] } })
    expect(http.post).not.toHaveBeenCalled()
  })
  it('does not trap a refused stale apply as an unfinished operation', async () => {
    currentStatus = status('preview')
    http.post.mockImplementation(async (url: string) => {
      if (url.endsWith('/apply')) throw { response: { status: 409 } }
      return { data: preview() }
    })
    const w = await open(); await review(w)
    await w.get('.resource-review input[type="checkbox"]').setValue(true)
    await button(w, 'Change resource and restart').trigger('click'); await flushPromises()
    expect(w.text()).toContain('application or its resources changed')
    expect(w.text()).not.toContain('resource change is unfinished')
    await button(w, 'Refresh status').trigger('click'); await flushPromises()
    expect(w.find(`input[value="${second}"]`).exists()).toBe(true)
    expect(http.post.mock.calls.filter(([url]) => url.endsWith('/apply'))).toHaveLength(1)
  })
  it('does not show resource choices when administrator access is revoked', async () => {
    http.get.mockRejectedValue({ response: { status: 403 } })
    const w = await open()
    expect(w.text()).toContain('current administrator login is required')
    expect(w.find('input[type="radio"]').exists()).toBe(false)
    expect(http.post).not.toHaveBeenCalled()
  })
  it('discards historical interrupted work once the current epoch has superseded it', async () => {
    let pending = true
    currentStatus = status('recovery_required')
    http.get.mockImplementation(async (url: string) => url === base
      ? { data: { pending: pending ? currentStatus : null } } : get(url))
    const w = await open()
    expect(w.text()).toContain('resource change is unfinished')
    pending = false
    await button(w, 'Refresh status').trigger('click'); await flushPromises()
    expect(w.text()).not.toContain('resource change is unfinished')
    expect(w.find(`input[value="${second}"]`).exists()).toBe(true)
    expect(w.findAll('button').some(item => item.text() === 'Stop and verify runtime')).toBe(false)
    expect(http.post).not.toHaveBeenCalled()
  })
})
