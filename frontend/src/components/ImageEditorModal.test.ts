import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ post: vi.fn() }))
vi.mock('@/utils/dynamic-http', () => ({ default: api }))
vi.mock('@/utils/i18n', () => ({ useI18n: () => ({ t: (_key: string, fallback: string) => fallback }) }))
import ImageEditorModal from './ImageEditorModal.vue'

class TestImage {
  src = ''
  crossOrigin = ''
  width = 64
  height = 32
  onload: (() => Promise<void>) | null = null
  onerror: (() => void) | null = null
  constructor() { images.push(this) }
}
let images: TestImage[]
let wrappers: VueWrapper[]
const drawImage = vi.fn()
const revokeObjectURL = vi.fn()
const open = (show = true) => {
  const wrapper = mount(ImageEditorModal, { props: {
    show, maxSize: 2, extensionName: 'settings', uploadDirectory: 'settings',
    editingImage: { url: '/uploads/settings/logo.png?t=123&version=2', name: 'logo.png' },
  } })
  wrappers.push(wrapper)
  return wrapper
}

describe('logo image editor loading', () => {
  beforeEach(() => {
    images = []; wrappers = []; vi.clearAllMocks()
    vi.stubGlobal('Image', TestImage)
    vi.stubGlobal('URL', class extends URL {
      static createObjectURL = () => 'blob:replacement'
      static revokeObjectURL = revokeObjectURL
    })
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
      fillRect: vi.fn(), drawImage, clearRect: vi.fn(), strokeRect: vi.fn(),
    } as unknown as CanvasRenderingContext2D)
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue(new DOMRect(0, 0, 320, 240))
    vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation(callback => callback(new Blob(['png'], { type: 'image/png' })))
    api.post.mockResolvedValue({ data: { url: '/uploads/settings/new-logo.png' } })
    vi.spyOn(console, 'log').mockImplementation(() => {})
  })
  afterEach(() => {
    wrappers.forEach(wrapper => wrapper.unmount())
    vi.restoreAllMocks(); vi.unstubAllGlobals()
  })

  it('preserves query parameters and enables save only after decoding', async () => {
    const wrapper = open()
    expect(images).toHaveLength(1)
    expect(images[0].src).toBe('/uploads/settings/logo.png?t=123&version=2')
    expect(wrapper.text()).toContain('Max 2MB')
    expect(wrapper.get('.action-button.primary').attributes('disabled')).toBeDefined()
    await images[0].onload!(); await flushPromises()
    expect(drawImage).toHaveBeenCalled()
    expect(wrapper.get('.action-button.primary').attributes('disabled')).toBeUndefined()
    await wrapper.get('.action-button.primary').trigger('click'); await flushPromises()
    expect(api.post.mock.calls[0][0]).toBe('/api/settings/upload-image')
    expect(api.post.mock.calls[0][1].get('directory')).toBe('settings')
    expect(wrapper.emitted('upload-success')?.[0][0]).toMatchObject({
      url: expect.stringMatching(/^\/uploads\/settings\/new-logo.png\?t=/),
    })
  })

  it('reloads an unchanged logo when the modal is reopened and ignores late callbacks', async () => {
    const wrapper = open(false)
    expect(images).toHaveLength(0)
    await wrapper.setProps({ show: true })
    const old = images[0]
    await wrapper.setProps({ show: false })
    await old.onload!(); old.onerror!()
    await wrapper.setProps({ show: true })
    expect(images).toHaveLength(2)
    expect(wrapper.find('.error-message').exists()).toBe(false)
    expect(wrapper.get('.action-button.primary').attributes('disabled')).toBeDefined()
    await images[1].onload!(); await flushPromises()
    expect(wrapper.get('.action-button.primary').attributes('disabled')).toBeUndefined()
  })

  it('allows a replacement upload after a missing logo without stale errors', async () => {
    const wrapper = open()
    images[0].onerror!(); await flushPromises()
    expect(wrapper.text()).toContain('Failed to load image')
    expect(wrapper.get('.action-button.primary').attributes('disabled')).toBeDefined()
    const file = new File(['png'], 'replacement.png', { type: 'image/png' })
    Object.defineProperty(wrapper.get('input[type=file]').element, 'files', { value: [file] })
    await wrapper.get('input[type=file]').trigger('change')
    expect(wrapper.find('.error-message').exists()).toBe(false)
    expect(images[1].src).toBe('blob:replacement')
    await images[1].onload!(); await flushPromises()
    images[0].onerror!(); await flushPromises()
    expect(wrapper.find('.error-message').exists()).toBe(false)
    expect(wrapper.get('.action-button.primary').attributes('disabled')).toBeUndefined()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:replacement')
  })

  it('does not truncate embedded image data containing a question mark', async () => {
    const wrapper = open(false)
    const url = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg"><text>?</text></svg>'
    await wrapper.setProps({ show: true, editingImage: { url, name: 'logo.svg' } })
    expect(images[0].src).toBe(url)
  })

  it('names the close control and closes without uploading', async () => {
    const wrapper = open()
    expect(wrapper.get('.close-button').attributes('aria-label')).toBe('Close')
    await wrapper.get('.close-button').trigger('click')
    expect(wrapper.emitted('update:show')).toEqual([[false]])
    expect(api.post).not.toHaveBeenCalled()
  })
})
