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
    http.get.mockImplementation((url: string) => Promise.resolve({
      data: url.endsWith('/operation')
        ? { state: 'idle', message: 'No update is staged' }
        : response(),
    }))
    http.post.mockResolvedValue({ data: response('no_release') })
  })

  it('loads local release state without checking the remote catalog', async () => {
    const wrapper = mount(SystemUpdates)
    await flushPromises()

    expect(http.get).toHaveBeenCalledWith('/api/v1/system-updates/status')
    expect(http.get).toHaveBeenCalledWith('/api/v1/system-updates/operation')
    expect(http.post).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('current-release')
    expect(wrapper.text()).toContain('Downloading verifies the exact release first')
  })

  it('checks the release catalog only after an explicit action', async () => {
    const wrapper = mount(SystemUpdates)
    await flushPromises()

    await wrapper.find('.updates-header .button').trigger('click')
    await flushPromises()

    expect(http.post).toHaveBeenCalledWith('/api/v1/system-updates/check')
    expect(wrapper.text()).toContain('No published release')
  })

  it('does not offer staging when the published release is not newer', async () => {
    http.get.mockImplementation((url: string) => Promise.resolve({
      data: url.endsWith('/operation')
        ? { state: 'idle', message: 'No update is staged' }
        : response('not_newer'),
    }))

    const wrapper = mount(SystemUpdates)
    await flushPromises()

    expect(wrapper.text()).toContain('No newer release')
    expect(wrapper.text()).not.toContain('Download and verify')
  })

  it('stages a validated update and shows the exact review plan', async () => {
    const checked = {
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
      }
    http.get.mockImplementation((url: string) => Promise.resolve({
      data: url.endsWith('/operation')
        ? { state: 'idle', message: 'No update is staged' }
        : checked,
    }))
    http.post.mockImplementation((url: string) => Promise.resolve({
      data: url.endsWith('/stage')
        ? {
            staged: {
              release_id: 'v1.2.0',
              version: '1.2.0',
              commit: 'b'.repeat(40),
              architecture: 'aarch64',
              artifact_filename: '3mm-1.2.0-aarch64.tar.gz',
              artifact_sha256: 'c'.repeat(64),
              artifact_size_bytes: 1234,
              dependencies: ['rsync'],
              dependency_plan: [{ name: 'rsync', installed: false, action: 'install' }],
              frontend_origin: 'http://192.168.1.88:8080',
              staged_at: '2026-08-26T09:00:00Z',
              approval_expires_at: '2026-08-26T09:30:00Z',
              approval_nonce: 'd'.repeat(64),
              preflight: [{ name: 'archive.identity', passed: true, detail: 'Verified' }],
            },
          }
        : response('no_release'),
    }))

    const wrapper = mount(SystemUpdates)
    await flushPromises()

    expect(wrapper.text()).toContain('1.2.0')
    expect(wrapper.text()).toContain('rsync')
    expect(wrapper.text()).toContain('3mm-1.2.0-aarch64.tar.gz')

    const stageButton = wrapper.findAll('button').find(button => button.text().includes('Download and verify'))
    expect(stageButton).toBeTruthy()
    await stageButton!.trigger('click')
    await flushPromises()

    expect(http.post).toHaveBeenCalledWith('/api/v1/system-updates/stage')
    expect(wrapper.text()).toContain('Verified update plan')
    expect(wrapper.text()).toContain('Will install')
    expect(wrapper.text()).toContain('Release file verified')
  })

  it('requires restart acknowledgement before sending exact approval', async () => {
    const wrapper = mount(SystemUpdates)
    await flushPromises()
    ;(wrapper.vm as any).staged = {
      release_id: 'v1.2.0', version: '1.2.0', commit: 'b'.repeat(40), architecture: 'aarch64',
      approval_nonce: 'd'.repeat(64), dependency_plan: [], preflight: [],
    }
    await wrapper.vm.$nextTick()

    await wrapper.findAll('button').find(button => button.text().includes('Review and install'))!.trigger('click')
    const installButton = wrapper.findAll('button').find(button => button.text().includes('Install update'))!
    expect(installButton.attributes('disabled')).toBeDefined()

    await wrapper.find('.confirm-check input').setValue(true)
    http.post.mockResolvedValue({ data: { state: 'queued', message: 'queued', release_id: 'v1.2.0' } })
    await installButton.trigger('click')
    await flushPromises()

    expect(http.post).toHaveBeenCalledWith('/api/v1/system-updates/apply', {
      release_id: 'v1.2.0',
      approval_nonce: 'd'.repeat(64),
      confirmation: 'INSTALL 1.2.0',
    })
  })
})
