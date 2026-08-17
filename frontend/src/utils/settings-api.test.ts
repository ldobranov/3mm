import { beforeEach, describe, expect, it, vi } from 'vitest'

const http = vi.hoisted(() => ({
  get: vi.fn(),
  put: vi.fn(),
  post: vi.fn()
}))

vi.mock('@/utils/dynamic-http', () => ({ default: http }))

import { readSettings, upsertSettings } from './settings-api'

describe('settings API', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    http.put.mockResolvedValue({ data: {} })
    http.post.mockResolvedValue({ data: {} })
  })

  it('reads settings for a specific language', async () => {
    http.get.mockResolvedValue({ data: { items: [{ id: 1, key: 'site_name', value: 'Name' }] } })

    await expect(readSettings('bg')).resolves.toHaveLength(1)
    expect(http.get).toHaveBeenCalledWith('/settings/read?language=bg')
  })

  it('updates matching settings and creates missing settings after one read', async () => {
    http.get.mockResolvedValue({ data: { items: [{ id: 7, key: 'logo_url', value: 'old' }] } })

    await upsertSettings([
      { key: 'logo_url', value: 'new' },
      { key: 'light_body_bg', value: '#fff' }
    ])

    expect(http.get).toHaveBeenCalledTimes(1)
    expect(http.put).toHaveBeenCalledWith('/settings/update', { id: 7, key: 'logo_url', value: 'new' })
    expect(http.post).toHaveBeenCalledWith('/settings/create', { key: 'light_body_bg', value: '#fff' })
  })

  it('matches language-specific settings by language code', async () => {
    http.get.mockResolvedValue({
      data: { items: [{ id: 3, key: 'site_name', value: 'English', language_code: 'en' }] }
    })

    await upsertSettings([{ key: 'site_name', value: 'Български', language_code: 'bg' }])

    expect(http.put).not.toHaveBeenCalled()
    expect(http.post).toHaveBeenCalledWith('/settings/create', {
      key: 'site_name',
      value: 'Български',
      language_code: 'bg'
    })
  })
})
