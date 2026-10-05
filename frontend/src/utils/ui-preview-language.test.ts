import { afterEach, describe, expect, it, vi } from 'vitest'

const writes = vi.hoisted(() => ({ save: vi.fn() }))
vi.mock('@/utils/language-api', () => ({ readFrontendTranslations: async () => ({}), saveCurrentUserLanguage: writes.save }))
vi.mock('@/utils/dynamic-http', () => ({ default: { get: async () => ({ data: { items: [] } }) } }))
import { i18n, useI18n } from './i18n'

afterEach(async () => { await i18n.setLanguage('en', false); localStorage.clear(); vi.clearAllMocks() })
describe('preview locale is not a saved user preference', () => {
  it('switches actual translations locally and restores them without writes', async () => {
    localStorage.setItem('preferredLanguage', 'en')
    const { setPreviewLanguage } = useI18n()
    await setPreviewLanguage('bg')
    expect(i18n.getCurrentLanguage()).toBe('bg')
    expect(i18n.t('menu.logout')).toBe('Излез')
    expect(localStorage.getItem('preferredLanguage')).toBe('en')
    expect(writes.save).not.toHaveBeenCalled()
    await setPreviewLanguage('en')
    expect(i18n.getCurrentLanguage()).toBe('en')
    expect(writes.save).not.toHaveBeenCalled()
  })
  it('keeps the existing persisted language-switch behavior outside preview', async () => {
    await i18n.setLanguage('bg')
    expect(localStorage.getItem('preferredLanguage')).toBe('bg')
    expect(writes.save).toHaveBeenCalledWith('bg')
  })
})
