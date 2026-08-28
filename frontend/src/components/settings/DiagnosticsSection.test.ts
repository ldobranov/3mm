import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const http = vi.hoisted(() => ({ get: vi.fn() }))

vi.mock('@/utils/dynamic-http', () => ({ default: http }))
vi.mock('@/utils/i18n', () => ({
  useI18n: () => ({ t: (_key: string, fallback: string) => fallback }),
}))

import DiagnosticsSection from './DiagnosticsSection.vue'

describe('Support diagnostics settings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    http.get.mockResolvedValue({
      data: {
        estimated_size_bytes: 2048,
        check_count: 3,
        warning_count: 0,
        checks: [{ name: 'database', status: 'ok', summary: 'SQLite quick check passed' }],
      },
      headers: {},
    })
  })

  it('loads the redacted diagnostics preview', async () => {
    const wrapper = mount(DiagnosticsSection)
    await flushPromises()

    expect(http.get).toHaveBeenCalledWith('/api/v1/diagnostics/preview')
    expect(wrapper.text()).toContain('SQLite quick check passed')
    expect(wrapper.text()).toContain('3 checks')
  })

  it('downloads the authenticated bundle without navigating away', async () => {
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    const createObjectURL = vi.fn(() => 'blob:diagnostics')
    const revokeObjectURL = vi.fn()
    vi.stubGlobal('URL', { createObjectURL, revokeObjectURL })
    http.get
      .mockResolvedValueOnce({ data: { estimated_size_bytes: 1, check_count: 0, warning_count: 0, checks: [] }, headers: {} })
      .mockResolvedValueOnce({
        data: new Blob(['{}'], { type: 'application/json' }),
        headers: { 'content-disposition': 'attachment; filename="3mm-diagnostics-test.json"' },
      })
    const wrapper = mount(DiagnosticsSection)
    await flushPromises()

    await wrapper.find('button').trigger('click')
    await flushPromises()

    expect(http.get).toHaveBeenLastCalledWith('/api/v1/diagnostics/bundle', { responseType: 'blob' })
    expect(createObjectURL).toHaveBeenCalled()
    expect(click).toHaveBeenCalled()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:diagnostics')
  })
})
