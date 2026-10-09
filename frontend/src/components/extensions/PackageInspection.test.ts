import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import english from '@/locales/en.json'
import bulgarian from '@/locales/bg.json'

const http = vi.hoisted(() => ({ post: vi.fn() }))
const locale = vi.hoisted(() => ({ language: 'en' }))
vi.mock('@/utils/dynamic-http', () => ({ default: http }))
vi.mock('@/utils/i18n', async () => {
  const en = (await import('@/locales/en.json')).default
  const bg = (await import('@/locales/bg.json')).default
  return { useI18n: () => ({ t: (key: string, fallback: string) => {
    const source = locale.language === 'bg' ? bg : en
    const messages: Record<string, Record<string, string>> = {
      packageInspection: source.packageInspection, authorityReview: source.authorityReview,
    }
    const [namespace, name] = key.split('.')
    return messages[namespace]?.[name] || fallback
  } }) }
})
import PackageInspection from './PackageInspection.vue'

const result = (status = 'new', name = 'Example package') => ({
  inspection_version: 1, module_id: 'org.example.test', version: '1.0.0',
  sha256: 'a'.repeat(64), size_bytes: 1500, package_kind: 'application',
  manifest: { name, runtimes: ['core'], permissions: ['data.write'],
    capabilities: { provides: ['example.ready'], consumes: ['gpio.digital.control'] },
    configuration_schema: { type: 'object', required: ['DEVICE_ID'] } },
  descriptors: { application_extension: { application_extension_version: 1 } },
  catalog: { status, existing_sha256: status === 'new' ? null : 'b'.repeat(64) },
  compatibility: { core: 'matched', core_version: '0.3.0-beta.43' },
})
const authorityResult = () => ({
  review_version: 1, status: 'available', reason: null,
  configuration_source: 'saved_installation_reused',
  review: {
    baseline: 'previous_declarations', previous_version: '1.0.0', candidate_version: '2.0.0',
    previous_sha256: 'b'.repeat(64), candidate_sha256: 'a'.repeat(64), artifact_changed: true,
    permission_approval: 'not_evaluated', not_checked: ['approved_grants'],
    changes: [{ scope: 'command:pulse', change: 'changed', potential_expansion: true,
      before: { target_device_id: 'dev_' + '1'.repeat(32) }, after: { target_device_id: 'dev_' + '2'.repeat(32) } }],
    unresolved: [{ side: 'candidate', scope: 'command:pulse', reason: 'unresolved_configuration_binding:DEVICE_ID' }],
  },
})
const mounted: ReturnType<typeof mount>[] = []
const view = (file: File | null = new File(['test ZIP'], 'review.zip')) => {
  const wrapper = mount(PackageInspection, { props: { file } })
  mounted.push(wrapper)
  return wrapper
}
describe('Read-only package inspection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    locale.language = 'en'
    http.post.mockResolvedValue({ data: result() })
  })
  afterEach(() => mounted.splice(0).forEach(wrapper => wrapper.unmount()))

  it('sends the exact file to inspection only, with raw-byte serialization', async () => {
    const file = new File(['raw ZIP bytes'], 'review.zip')
    const wrapper = view(file)
    expect(wrapper.get('button').attributes('type')).toBe('button')
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(http.post).toHaveBeenCalledTimes(1)
    const [url, body, config] = http.post.mock.calls[0]
    expect(url).toBe('/api/v1/modules/packages/inspect')
    expect(body).toBe(file)
    expect(config.headers['Content-Type']).toBe('application/zip')
    expect(config.transformRequest[0](file)).toBe(file)
    expect(config.params).toEqual({ include_authority_review: true })
    expect(wrapper.text()).toContain('Example package')
    expect(wrapper.text()).toContain('data.write')
    expect(wrapper.text()).toContain('gpio.digital.control')
    expect(wrapper.text()).toContain('DEVICE_ID')
    expect(wrapper.text()).toContain('not approval')
    expect(wrapper.text()).toContain('not verified')
    expect(wrapper.text()).toContain('Not checked')
  })

  it.each(['exact_artifact', 'version_conflict'])('shows %s without install or replacement actions', async status => {
    http.post.mockResolvedValue({ data: result(status) })
    const wrapper = view()
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain(status === 'version_conflict' ? 'Version conflict' : 'already in the catalog')
    expect(wrapper.findAll('button')).toHaveLength(1)
  })

  it('does not fall back to legacy upload after an unsupported or failed inspection', async () => {
    http.post.mockRejectedValue({ response: { status: 422, data: { detail: 'manifest v2 required' } } })
    const wrapper = view()
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('manifest v2 required')
    expect(http.post).toHaveBeenCalledTimes(1)
    expect(wrapper.find('.inspection-result').exists()).toBe(false)
  })

  it('clears prior results on file changes and ignores late results for an old file', async () => {
    const wrapper = view()
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Example package')
    await wrapper.setProps({ file: new File(['old'], 'old.zip') })
    expect(wrapper.find('.inspection-result').exists()).toBe(false)
    let complete: (value: unknown) => void = () => {}
    http.post.mockImplementationOnce(() => new Promise(resolve => { complete = resolve }))
    await wrapper.get('button').trigger('click')
    const previousSignal = http.post.mock.calls.at(-1)![2].signal as AbortSignal
    await wrapper.setProps({ file: new File(['new'], 'new.zip') })
    expect(previousSignal.aborted).toBe(true)
    http.post.mockResolvedValue({ data: result('new', 'New file') })
    await wrapper.get('button').trigger('click')
    await flushPromises()
    complete({ data: result('new', 'Stale file') })
    await flushPromises()
    expect(wrapper.text()).toContain('New file')
    expect(wrapper.text()).not.toContain('Stale file')
  })

  it('requires a file and respects upload-in-progress disabling', async () => {
    const wrapper = view(null)
    expect(wrapper.get('button').attributes('disabled')).toBeDefined()
    await wrapper.setProps({ file: new File(['test'], 'test.zip'), disabled: true })
    expect(wrapper.get('button').attributes('disabled')).toBeDefined()
    expect(http.post).not.toHaveBeenCalled()
  })

  it('rejects empty and oversized files locally', async () => {
    const wrapper = view(new File([], 'empty.zip'))
    await wrapper.get('button').trigger('click')
    expect(wrapper.get('[role="alert"]').text()).toContain('10 MiB')
    const oversized = new File(['test'], 'large.zip')
    Object.defineProperty(oversized, 'size', { value: 10 * 1024 * 1024 + 1 })
    await wrapper.setProps({ file: oversized })
    await wrapper.get('button').trigger('click')
    expect(http.post).not.toHaveBeenCalled()
  })

  it('escapes package-supplied text and includes matching Bulgarian translations', async () => {
    locale.language = 'bg'
    expect(Object.keys(bulgarian.packageInspection).sort()).toEqual(Object.keys(english.packageInspection).sort())
    http.post.mockResolvedValue({ data: result('new', '<script>alert(1)</script>') })
    const wrapper = view()
    expect(wrapper.get('button').text()).toContain('Преглед на пакета')
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(wrapper.find('script').exists()).toBe(false)
    expect(wrapper.text()).toContain('<script>alert(1)</script>')
    expect(wrapper.text()).toContain('не е одобрение')
  })

  it('shows installed/candidate authority changes, unresolved scopes and no approval actions', async () => {
    http.post.mockResolvedValue({ data: { ...result(), authority_review: authorityResult() } })
    const wrapper = view()
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(wrapper.get('.authority-review').text()).toContain('Saved settings are reused')
    expect(wrapper.text()).toContain('Installed baseline')
    expect(wrapper.text()).toContain('Selected package')
    expect(wrapper.get('.authority-counts').text()).toContain('1 Changed')
    expect(wrapper.get('.authority-counts').text()).toContain('1 Unresolved')
    expect(wrapper.get('.authority-change').text()).toContain('command:pulse')
    expect(wrapper.get('.authority-change').text()).toContain('dev_' + '1'.repeat(32))
    expect(wrapper.get('.authority-change').text()).toContain('dev_' + '2'.repeat(32))
    expect(wrapper.text()).toContain('Unresolved binding: DEVICE_ID')
    expect(wrapper.text()).toContain('never authorizes')
    expect(wrapper.findAll('button')).toHaveLength(1)
    expect(http.post).toHaveBeenCalledTimes(1)
    await wrapper.setProps({ file: null })
    expect(wrapper.find('.authority-review').exists()).toBe(false)
  })

  it('does not represent an unavailable baseline as zero changes or a first install', async () => {
    http.post.mockResolvedValue({ data: { ...result(), authority_review: {
      review_version: 1, status: 'unavailable', reason: 'baseline_unavailable',
      configuration_source: 'saved_installation_reused', review: null,
    } } })
    const wrapper = view()
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(wrapper.get('.authority-review').text()).toContain('No comparison was made')
    expect(wrapper.find('.authority-counts').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('No application installation exists')
  })

  it('supports an older inspector response and keeps non-application packages unchanged', async () => {
    const wrapper = view()
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('This Core did not return an authority comparison')
    http.post.mockResolvedValue({ data: { ...result(), package_kind: 'theme' } })
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(wrapper.find('.authority-review').exists()).toBe(false)
  })

  it('translates authority review and escapes scope and before/after text', async () => {
    locale.language = 'bg'
    expect(Object.keys(bulgarian.authorityReview).sort()).toEqual(Object.keys(english.authorityReview).sort())
    const value = authorityResult()
    value.review.changes[0].scope = '<img src=x onerror=alert(1)>'
    value.review.changes[0].after = { target_device_id: '<script>alert(2)</script>' }
    http.post.mockResolvedValue({ data: { ...result(), authority_review: value } })
    const wrapper = view()
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(wrapper.get('.authority-review').text()).toContain('Промени в заявения достъп')
    expect(wrapper.text()).toContain('Неизяснено обвързване: DEVICE_ID')
    expect(wrapper.text()).toContain('<script>alert(2)</script>')
    expect(wrapper.find('script').exists()).toBe(false)
    expect(wrapper.find('img').exists()).toBe(false)
  })
})
