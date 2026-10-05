import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { BUILTIN_STYLES, buttonTextColor, parseThemeDefinition, readThemeAppearance, resolveThemeStyle } from './theme-extension'

vi.mock('@/utils/dynamic-http', () => ({ default: { getCurrentBackendUrl: async () => '' } }))
vi.mock('@/utils/settings-api', () => ({ readSettings: async () => [], upsertSettings: vi.fn() }))
vi.mock('@/utils/i18n', () => ({ useI18n: () => ({ currentLanguage: { value: 'bg' } }) }))
import { useSettingsStore } from '@/stores/settings'
import { useThemeStore } from '@/stores/theme'

export const definition = () => ({
  theme_extension_version: 1, design_api_version: 1, module_id: 'org.example.theme', version: '1.0.0',
  name: { en: 'Example', translations: { bg: 'Пример' } }, base_theme: 'builtin.default',
  light: { body_bg: '#F5F6F8', button_primary_bg: '#356AE6', radius_sm: 0 },
  dark: { body_bg: '#181B20', button_primary_bg: '#7198F2', radius_sm: 0 },
})

describe('Theme Design API adapter and loader', () => {
  beforeEach(() => { localStorage.clear(); setActivePinia(createPinia()) })
  afterEach(() => { vi.unstubAllGlobals(); document.documentElement.style.cssText = '' })

  it('inherits built-in, not saved legacy defaults, including zero radii', () => {
    const theme = parseThemeDefinition(definition())!
    const legacy = { ...BUILTIN_STYLES.light, bodyBg: '#ABCDEF', textPrimary: '#123456' }
    expect(resolveThemeStyle(theme, 'light', legacy)).toMatchObject({ bodyBg: '#F5F6F8', textPrimary: '#222222', borderRadiusSm: 0 })
    expect(resolveThemeStyle(theme, 'dark', legacy).bodyBg).toBe('#181B20')
    expect(resolveThemeStyle(null, 'light', legacy)).toBe(legacy)
  })

  it('derives readable button text for light and dark accents', () => {
    expect(buttonTextColor('#7198F2')).toBe('#000000')
    expect(buttonTextColor('#123456')).toBe('#ffffff')
  })

  it.each([
    { ...definition(), design_api_version: 2 },
    { ...definition(), light: { body_bg: 'url(https://invalid)' } },
    { ...definition(), light: { arbitrary: '#FFFFFF' } },
    { ...definition(), light: { radius_sm: '1' } },
    { ...definition(), light: { radius_sm: 51 } },
    { ...definition(), light: { radius_sm: true } },
    { ...definition(), dark: {} },
    { ...definition(), script: 'do not execute' },
  ])('rejects unsafe or unsupported definitions', value => {
    expect(parseThemeDefinition(value)).toBeNull()
  })

  it('loads without authentication and fails closed without logout on HTTP/JSON errors', async () => {
    localStorage.setItem('authToken', 'unchanged-token')
    const fetch = vi.fn().mockResolvedValueOnce({ ok: true, text: async () => JSON.stringify({ theme: definition() }) })
      .mockResolvedValueOnce({ ok: false, status: 401 })
      .mockResolvedValueOnce({ ok: true, text: async () => '<html>bad</html>' })
      .mockRejectedValueOnce(new Error('offline'))
    vi.stubGlobal('fetch', fetch)
    expect(await readThemeAppearance('')).toEqual(definition())
    expect(fetch.mock.calls[0][1]).toMatchObject({ cache: 'no-store', credentials: 'omit' })
    for (let index = 0; index < 3; index++) expect(await readThemeAppearance('')).toBeNull()
    expect(localStorage.getItem('authToken')).toBe('unchanged-token')
  })

  it('updates real CSS aliases across light/dark, refresh and built-in fallback', async () => {
    const settings = useSettingsStore()
    const modes = useThemeStore()
    settings.lightStyleSettings.bodyBg = '#ABCDEF'
    settings.headerSettings.backgroundColor = '#121212'
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, text: async () => JSON.stringify({ theme: definition() }) }))
    await settings.loadThemeAppearance()
    expect(document.documentElement.style.getPropertyValue('--body-bg')).toBe('#F5F6F8')
    expect(document.documentElement.style.getPropertyValue('--primary-color')).toBe('#356AE6')
    expect(document.documentElement.style.getPropertyValue('--border-radius-sm')).toBe('0px')
    modes.setTheme('dark')
    await nextTick()
    expect(document.documentElement.style.getPropertyValue('--body-bg')).toBe('#181B20')
    expect(settings.headerSettings.backgroundColor).toBe('#121212')
    expect(settings.lightStyleSettings.bodyBg).toBe('#ABCDEF')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, text: async () => '{"theme":null}' }))
    await settings.loadThemeAppearance()
    modes.setTheme('light')
    await nextTick()
    expect(document.documentElement.style.getPropertyValue('--body-bg')).toBe('#ABCDEF')
    expect(settings.activeTheme).toBeNull()
  })

  it('ignores a late theme response after startup cancellation without changing the session', async () => {
    localStorage.setItem('authToken', 'unchanged-token')
    let respond!: (value: unknown) => void
    const fetch = vi.fn((_url: string, _options: RequestInit) => new Promise(resolve => { respond = resolve }))
    vi.stubGlobal('fetch', fetch)
    const settings = useSettingsStore()
    const controller = new AbortController()
    const loading = settings.loadThemeAppearance(controller.signal)
    await Promise.resolve()
    controller.abort()
    expect(fetch.mock.calls[0][1].signal?.aborted).toBe(true)
    respond({ ok: true, text: async () => JSON.stringify({ theme: definition() }) })
    await loading
    expect(settings.activeTheme).toBeNull()
    expect(localStorage.getItem('authToken')).toBe('unchanged-token')
  })
})
