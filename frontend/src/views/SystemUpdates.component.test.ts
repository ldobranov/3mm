import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const http = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}))

vi.mock('@/utils/dynamic-http', () => ({ default: http }))
vi.mock('@/utils/i18n', () => ({
  useI18n: () => ({ t: (_key: string, fallback: string) => fallback }),
}))

import SystemUpdates from './SystemUpdates.vue'

const current = {
  release_id: 'current-release',
  commit: 'a'.repeat(40),
  branch: 'main',
  version: null,
  created_at: '2026-08-26T08:00:00Z',
  includes_working_tree: false,
  metadata_available: true,
}

function response(status = 'not_checked') {
  return {
    status,
    message: 'Catalog state',
    repository: 'ldobranov/3mm',
    repository_url: 'https://github.com/ldobranov/3mm',
    architecture: 'aarch64',
    current,
    latest: null,
    update_available: null,
    checked_at: null,
  }
}

describe('System updates catalog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    http.get.mockResolvedValue({ data: response() })
    http.post.mockResolvedValue({ data: response('no_release') })
  })

  it('loads local release state without checking the remote catalog', async () => {
    const wrapper = mount(SystemUpdates)
    await flushPromises()

    expect(http.get).toHaveBeenCalledWith('/api/v1/system-updates/status')
    expect(http.post).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('current-release')
    expect(wrapper.text()).toContain('Installation, downloads and restarts are disabled')
  })

  it('checks the release catalog only after an explicit action', async () => {
    const wrapper = mount(SystemUpdates)
    await flushPromises()

    await wrapper.find('.updates-header .button').trigger('click')
    await flushPromises()

    expect(http.post).toHaveBeenCalledWith('/api/v1/system-updates/check')
    expect(wrapper.text()).toContain('No published release')
  })

  it('shows validated dependencies and artifacts without an install action', async () => {
    http.get.mockResolvedValue({
      data: {
        ...response('update_available'),
        update_available: true,
        latest: {
          tag: 'v1.2.0',
          name: '3mm 1.2.0',
          published_at: '2026-08-26T08:30:00Z',
          html_url: 'https://github.com/ldobranov/3mm/releases/tag/v1.2.0',
          manifest_validated: true,
          version: '1.2.0',
          release_id: 'v1.2.0',
          commit: 'b'.repeat(40),
          channel: 'stable',
          artifacts: [{
            architecture: 'aarch64',
            filename: '3mm-1.2.0-aarch64.tar.gz',
            download_url: 'https://github.com/ldobranov/3mm/releases/download/v1.2.0/3mm-1.2.0-aarch64.tar.gz',
            sha256: 'c'.repeat(64),
            size_bytes: 1234,
          }],
          dependencies: { apt_packages: ['rsync'] },
        },
      },
    })

    const wrapper = mount(SystemUpdates)
    await flushPromises()

    expect(wrapper.text()).toContain('1.2.0')
    expect(wrapper.text()).toContain('rsync')
    expect(wrapper.text()).toContain('3mm-1.2.0-aarch64.tar.gz')
    expect(wrapper.findAll('button')).toHaveLength(1)
    expect(wrapper.find('button').text()).toContain('Check for updates')
  })
})
