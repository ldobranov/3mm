import { beforeEach, describe, expect, it, vi } from 'vitest'

const http = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn()
}))

vi.mock('@/utils/dynamic-http', () => ({ default: http }))

import {
  readAvailableLanguages,
  readFrontendTranslations,
  readLanguageSettings,
  saveCurrentUserLanguage
} from './language-api'

describe('language API', () => {
  beforeEach(() => vi.clearAllMocks())

  it('returns only normalized installed languages', async () => {
    http.get.mockResolvedValue({ data: { languages: ['en', 'bg', 'bg', null] } })

    await expect(readAvailableLanguages()).resolves.toEqual(['en', 'bg'])
    expect(http.get).toHaveBeenCalledWith('/language/available')
  })

  it('normalizes translation and language-setting responses', async () => {
    http.get
      .mockResolvedValueOnce({ data: { frontend: { menu: { login: 'Login' } } } })
      .mockResolvedValueOnce({ data: { items: [{ key: 'site_name', value: 'Name', language_code: null }] } })

    await expect(readFrontendTranslations('en')).resolves.toEqual({ menu: { login: 'Login' } })
    await expect(readLanguageSettings('en')).resolves.toEqual([
      { key: 'site_name', value: 'Name', language_code: undefined }
    ])
  })

  it('persists the current user language through the canonical endpoint', async () => {
    http.post.mockResolvedValue({ data: {} })

    await saveCurrentUserLanguage('bg')

    expect(http.post).toHaveBeenCalledWith('/api/user/language', { language: 'bg' })
  })
})
