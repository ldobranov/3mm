import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { builtinUiDesign } from './ui-design'
import { loadThemeAssets, parseInstalledTheme, type ThemePackageV2 } from './theme-package-v2'

vi.mock('@/utils/dynamic-http', () => ({ default: { getCurrentBackendUrl: async () => '', post: vi.fn() } }))
vi.mock('@/utils/settings-api', () => ({ readSettings: async () => [], upsertSettings: vi.fn() }))
vi.mock('@/utils/i18n', () => ({ useI18n: () => ({ currentLanguage: { value: 'bg' } }) }))
import { useSettingsStore } from '@/stores/settings'
import { useThemeStore } from '@/stores/theme'

const projection = () => ({ package_sha256: 'a'.repeat(64), theme: {
  theme_extension_version: 2, design_api_version: 2, module_id: 'org.example.theme', version: '2.0.0',
  name: { en: 'Example' }, base_theme: 'builtin.default', design: { design_api_version: 2, scale: { radius_sm: 0 } }, assets: [],
} })
const imageTheme = () => parseInstalledTheme({ ...projection(), theme: { ...projection().theme, assets: [{
  asset_id: 'logo', path: 'assets/logo.png', sha256: 'b'.repeat(64), role: 'logo_light', media_type: 'image/png',
}] } }) as ThemePackageV2

describe('installed v2 contract and asset fallback', () => {
  beforeEach(() => { localStorage.clear(); setActivePinia(createPinia()) })
  afterEach(() => { vi.unstubAllGlobals(); document.documentElement.style.cssText = '' })
  it('uses shared defaults and preserves zero radius', () => {
    const theme = parseInstalledTheme(projection()) as ThemePackageV2
    expect(theme.design.light).toEqual(builtinUiDesign().light)
    expect(theme.design.scale.radius_sm).toBe(0)
  })
  it.each([
    { colors: null }, { css: 'body{}' }, { navigation: ['top'] },
    { navigation: ['sidebar', 'sidebar'] }, { colors: ['unknown'] },
  ])('rejects unsafe or incompatible package-declared controls', customization_options => {
    expect(parseInstalledTheme({ ...projection(), theme: { ...projection().theme, customization_options } })).toBeNull()
  })
  it('retains the last verified theme and customization after a failed foreground refresh', async () => {
    const settings = useSettingsStore()
    localStorage.setItem('authToken', 'preserved')
    const customization = { navigation: 'top', density: 'compact', button: 'solid', card: 'raised',
      header_style: 'theme', header_background_color: '#123456', header_text_color: '#ffffff' }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, text: async () => JSON.stringify({ ...projection(), customization }) }))
    await settings.loadThemeAppearance()
    const original = settings.activeTheme
    for (const response of [null, { ok: false, status: 503 },
      { ok: true, text: async () => '<html>offline</html>' },
      { ok: true, text: async () => JSON.stringify({ theme: { unsafe: true } }) }]) {
      vi.stubGlobal('fetch', response ? vi.fn().mockResolvedValue(response) : vi.fn().mockRejectedValue(new Error('ERR_NAME_NOT_RESOLVED')))
      await settings.loadThemeAppearance()
      expect(settings.activeTheme).toBe(original)
      expect(settings.themePreferences).toEqual(customization)
      expect(settings.uiDesign.layout.navigation).toBe('top')
      expect(settings.appearanceUnavailable).toBe(true)
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, text: async () => '{"theme":null}' }))
    await settings.loadThemeAppearance()
    expect(settings.activeTheme).toBeNull()
    expect(settings.themePreferences).toBeNull()
    expect(settings.appearanceUnavailable).toBe(false)
    expect(localStorage.getItem('authToken')).toBe('preserved')
  })
  it.each([
    { ...projection(), package_sha256: '../other' },
    { ...projection(), theme: { ...projection().theme, script: 'bad' } },
    { ...projection(), theme: { ...projection().theme, design: { design_api_version: 3 } } },
    { ...projection(), theme: { ...projection().theme, assets: [{ ...imageTheme().assets[0], path: 'https://external.test/logo.png' }] } },
    { ...projection(), theme: { ...projection().theme, assets: [{ ...imageTheme().assets[0], path: 'assets/logo.svg' }] } },
    { ...projection(), theme: { ...projection().theme, assets: [imageTheme().assets[0], imageTheme().assets[0]] } },
  ])('rejects unsafe package or asset declarations', value => expect(parseInstalledTheme(value)).toBeNull())
  it('applies v2 colors/layout and recovery bypass, without saving or logout', async () => {
    const settings = useSettingsStore(), modes = useThemeStore()
    settings.lightStyleSettings.bodyBg = '#ABCDEF'
    settings.headerSettings.logoUrl = 'saved-logo'
    localStorage.setItem('authToken', 'preserved')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, text: async () => JSON.stringify(projection()) }))
    await settings.loadThemeAppearance()
    expect(settings.installedDesign?.layout.navigation).toBe('sidebar')
    expect(document.documentElement.style.getPropertyValue('--body-bg')).toBe('#f4f5f7')
    expect(document.documentElement.style.getPropertyValue('--border-radius-sm')).toBe('0px')
    expect(settings.brandingLogo).toBe('saved-logo')
    modes.setTheme('dark'); await nextTick()
    expect(document.documentElement.style.getPropertyValue('--ui-canvas')).toBe('#15191f')
    settings.appearanceRecovery = true; modes.setTheme('light'); await nextTick()
    expect(document.documentElement.style.getPropertyValue('--body-bg')).toBe('#ABCDEF')
    expect(settings.activeTheme?.theme_extension_version).toBe(2)
    expect(localStorage.getItem('authToken')).toBe('preserved')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, text: async () => '{"theme":null}' }))
    settings.appearanceRecovery = false
    await settings.loadThemeAppearance()
    expect(settings.installedDesign).toBeNull()
    expect(document.documentElement.style.getPropertyValue('--body-bg')).toBe('#ABCDEF')
  })
  it('uses only the pinned public endpoint; auth/MIME failures retain fallback', async () => {
    const fetch = vi.fn().mockResolvedValue({ ok: false, status: 401 })
    vi.stubGlobal('fetch', fetch)
    localStorage.setItem('authToken', 'preserved')
    const result = await loadThemeAssets(imageTheme(), '', new AbortController().signal)
    expect(result.warnings).toEqual(['logo_light'])
    expect(result.logos).toEqual({})
    expect(fetch.mock.calls[0][0]).toBe(`/api/v1/modules/themes/packages/${'a'.repeat(64)}/assets/logo`)
    expect(fetch.mock.calls[0][1].credentials).toBe('omit')
    expect(localStorage.getItem('authToken')).toBe('preserved')
    result.dispose()
  })
  it('bounds streamed asset bytes before any decoder sees them', async () => {
    const cancel = vi.fn(), decode = vi.fn()
    vi.stubGlobal('createImageBitmap', decode)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, headers: new Headers({ 'content-type': 'image/png' }),
      body: { getReader: () => ({ read: async () => ({ done: false, value: new Uint8Array(1024 * 1024 + 1) }), cancel }) },
    }))
    const result = await loadThemeAssets(imageTheme(), '', new AbortController().signal)
    expect(result.warnings).toEqual(['logo_light'])
    expect(cancel).toHaveBeenCalledOnce()
    expect(decode).not.toHaveBeenCalled()
  })
  it('registers and removes the loaded font on built-in fallback', async () => {
    vi.stubGlobal('crypto', {}) // Same server-authoritative path as LAN HTTP.
    vi.stubGlobal('FontFace', class {
      family: string
      constructor(family: string) { this.family = family }
      load() { return Promise.resolve(this) }
    })
    const previous = Object.getOwnPropertyDescriptor(document, 'fonts')
    const fonts = new Set()
    Object.defineProperty(document, 'fonts', { configurable: true, value: fonts })
    const asset = { asset_id: 'font', path: 'assets/local.woff2', sha256: 'b'.repeat(64), media_type: 'font/woff2', role: 'font', license: 'Test-only' }
    let read = false
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce({ ok: true, text: async () => JSON.stringify({ ...projection(), theme: { ...projection().theme, assets: [asset] } }) })
      .mockResolvedValueOnce({ ok: true, headers: new Headers({ 'content-type': 'font/woff2' }), body: { getReader: () => ({
        read: async () => read ? { done: true } : (read = true, { done: false, value: new Uint8Array([1, 2, 3]) }), cancel: async () => {},
      }) } })
      .mockRejectedValueOnce(new Error('offline after tab idle'))
      .mockResolvedValueOnce({ ok: true, text: async () => '{"theme":null}' }))
    try {
      const settings = useSettingsStore()
      await settings.loadThemeAppearance()
      expect(fonts.size).toBe(1)
      expect(document.documentElement.style.getPropertyValue('--ui-font')).toContain(`UiTheme_${'a'.repeat(64)}`)
      await settings.loadThemeAppearance()
      expect(fonts.size).toBe(1)
      expect(settings.appearanceUnavailable).toBe(true)
      expect(document.documentElement.style.getPropertyValue('--ui-font')).toContain(`UiTheme_${'a'.repeat(64)}`)
      await settings.loadThemeAppearance()
      expect(fonts.size).toBe(0)
      expect(document.documentElement.style.getPropertyValue('--ui-font')).not.toContain('UiTheme_')
    } finally {
      if (previous) Object.defineProperty(document, 'fonts', previous)
      else Reflect.deleteProperty(document, 'fonts')
    }
  })
  it('keeps the installed selection intact during v2/v1/built-in previews and background refresh', async () => {
    const settings = useSettingsStore()
    settings.lightStyleSettings.bodyBg = '#ABCDEF'
    localStorage.setItem('authToken', 'preserved')
    const fetch = vi.fn().mockResolvedValue({ ok: true, text: async () => JSON.stringify(projection()) })
    vi.stubGlobal('fetch', fetch)
    await settings.loadThemeAppearance()
    const candidate = { ...projection(), package_sha256: 'b'.repeat(64), theme: { ...projection().theme,
      design: { design_api_version: 2, layout: { navigation: 'top', density: 'comfortable' } } } }
    expect(await settings.previewThemeAppearance(candidate, '', new AbortController().signal)).toBe(true)
    expect(settings.activeTheme).toHaveProperty('package_sha256', 'a'.repeat(64))
    expect(settings.uiDesign.layout.navigation).toBe('top')
    expect(settings.uiDesign.layout.density).toBe('comfortable')
    // A focus refresh cannot replace a local preview; Cancel uses the latest installed state.
    await settings.loadThemeAppearance()
    expect(settings.uiDesign.layout.navigation).toBe('top')
    settings.clearPackagePreview()
    expect(settings.isPackagePreview).toBe(false)
    expect(settings.uiDesign.layout.navigation).toBe('sidebar')
    const legacy = { ...projection().theme, theme_extension_version: 1, design_api_version: 1,
      light: { body_bg: '#123456' }, dark: { body_bg: '#345678' } } as Record<string, unknown>
    delete legacy.design; delete legacy.assets
    expect(await settings.previewThemeAppearance({ theme: legacy }, '', new AbortController().signal)).toBe(true)
    expect(document.documentElement.style.getPropertyValue('--body-bg')).toBe('#123456')
    expect(await settings.previewThemeAppearance({ theme: null }, '', new AbortController().signal)).toBe(true)
    expect(document.documentElement.style.getPropertyValue('--body-bg')).toBe('#ABCDEF')
    expect(settings.activeTheme?.theme_extension_version).toBe(2)
    settings.clearPackagePreview()
    expect(document.documentElement.style.getPropertyValue('--body-bg')).toBe('#f4f5f7')
    expect(await settings.previewThemeAppearance({ theme: { script: 'bad' } }, '', new AbortController().signal)).toBe(false)
    expect(settings.isPackagePreview).toBe(false)
    expect(localStorage.getItem('authToken')).toBe('preserved')
  })
  it('uses protected preview resources and releases only the preview font on Cancel', async () => {
    vi.stubGlobal('crypto', {})
    vi.stubGlobal('FontFace', class {
      family: string
      constructor(family: string) { this.family = family }
      load() { return Promise.resolve(this) }
    })
    const previous = Object.getOwnPropertyDescriptor(document, 'fonts')
    const fonts = new Set()
    Object.defineProperty(document, 'fonts', { configurable: true, value: fonts })
    const asset = { asset_id: 'font', path: 'assets/local.woff2', sha256: 'b'.repeat(64), media_type: 'font/woff2', role: 'font', license: 'Test-only' }
    const fontTheme = { ...projection(), theme: { ...projection().theme, assets: [asset] } }
    const resource = () => {
      let read = false
      return { ok: true, headers: new Headers({ 'content-type': 'font/woff2' }), body: { getReader: () => ({
        read: async () => read ? { done: true } : (read = true, { done: false, value: new Uint8Array([1, 2, 3]) }), cancel: async () => {},
      }) } }
    }
    const fetch = vi.fn().mockResolvedValueOnce({ ok: true, text: async () => JSON.stringify(fontTheme) })
      .mockResolvedValueOnce(resource()).mockResolvedValueOnce(resource())
    vi.stubGlobal('fetch', fetch)
    localStorage.setItem('authToken', 'preserved')
    const settings = useSettingsStore()
    try {
      await settings.loadThemeAppearance()
      expect(fonts.size).toBe(1)
      expect(await settings.previewThemeAppearance({ ...fontTheme, package_sha256: 'c'.repeat(64) }, '', new AbortController().signal)).toBe(true)
      expect(fonts.size).toBe(2)
      expect(fetch.mock.calls[2][0]).toBe(`/api/v1/modules/themes/packages/${'c'.repeat(64)}/preview/assets/font`)
      expect(fetch.mock.calls[2][1]).toHaveProperty('headers.Authorization', 'Bearer preserved')
      expect(fetch.mock.calls[1][1].headers).toBeUndefined()
      expect(document.documentElement.style.getPropertyValue('--ui-font')).toContain(`UiTheme_${'c'.repeat(64)}`)
      settings.clearPackagePreview()
      expect(fonts.size).toBe(1)
      expect(document.documentElement.style.getPropertyValue('--ui-font')).toContain(`UiTheme_${'a'.repeat(64)}`)
      expect(document.documentElement.style.getPropertyValue('--ui-font')).not.toContain(`UiTheme_${'c'.repeat(64)}`)
    } finally {
      settings.$dispose()
      if (previous) Object.defineProperty(document, 'fonts', previous)
      else Reflect.deleteProperty(document, 'fonts')
    }
  })
  it('does not resurrect preview images after Cancel while a decoder is still loading', async () => {
    vi.stubGlobal('crypto', {})
    let decode!: (image: unknown) => void
    vi.stubGlobal('createImageBitmap', vi.fn(() => new Promise(resolve => { decode = resolve })))
    let read = false
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, headers: new Headers({ 'content-type': 'image/png' }), body: { getReader: () => ({
      read: async () => read ? { done: true } : (read = true, { done: false, value: new Uint8Array([1]) }), cancel: async () => {},
    }) } }))
    localStorage.setItem('authToken', 'preserved')
    const settings = useSettingsStore()
    const pending = settings.previewThemeAppearance({ ...projection(), theme: { ...projection().theme, assets: imageTheme().assets } }, '', new AbortController().signal)
    await vi.waitFor(() => expect(decode).toBeDefined())
    settings.clearPackagePreview()
    const close = vi.fn()
    decode({ width: 1, height: 1, close })
    expect(await pending).toBe(false)
    expect(settings.isPackagePreview).toBe(false)
    expect(settings.brandingLogo).toBe('')
    expect(close).toHaveBeenCalledOnce()
  })
})
