import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { adaptLegacyUi, builtinUiDesign, buttonHoverBackground, contrastRatio, parseUiDesign, resolveUiShellMode, uiDesignVariables } from './ui-design'
import { BUILTIN_STYLES, parseThemeDefinition, resolveThemeStyle } from './theme-extension'
import { DEFAULT_HEADER_SETTINGS } from './header-settings'

vi.mock('@/utils/dynamic-http', () => ({ default: { getCurrentBackendUrl: async () => '' } }))
vi.mock('@/utils/settings-api', () => ({ readSettings: async () => [], upsertSettings: vi.fn() }))
vi.mock('@/utils/i18n', () => ({ useI18n: () => ({ currentLanguage: { value: 'en' } }) }))
import { useSettingsStore } from '@/stores/settings'
import { useThemeStore } from '@/stores/theme'

describe('Design API 2 contract and v1 compatibility', () => {
  beforeEach(() => { localStorage.clear(); setActivePinia(createPinia()) })
  afterEach(() => { document.documentElement.style.cssText = ''; vi.unstubAllGlobals() })
  it('validates built-in defaults, inheritance and exact zero radii', () => {
    expect(parseUiDesign(builtinUiDesign())).toEqual(builtinUiDesign())
    expect(parseUiDesign({ design_api_version: 2, scale: { radius_sm: 0 }, light: { accent: null } }))
      .toMatchObject({ scale: { radius_sm: 0 }, header_style: 'saved' })
  })
  it.each([
    { design_api_version: 3 }, { design_api_version: 2, css: 'body{}' },
    { design_api_version: 2, light: { canvas: 'url(https://example.test)' } },
    { design_api_version: 2, light: { text: '#ffffff' } },
    { design_api_version: 2, dark: { arbitrary: '#ffffff' } },
    { design_api_version: 2, typography: { font: 'https://example.test/font' } },
    { design_api_version: 2, scale: { radius_sm: -1 } },
    { design_api_version: 2, scale: { unit: '4' } },
    { design_api_version: 2, layout: { navigation: 'custom-template' } },
    { design_api_version: 2, layout: { sidebar_width: 9000 } },
    { design_api_version: 2, components: { handler: 'eval' } },
    { design_api_version: 2, header_style: 'erase' },
    { design_api_version: 2, assets: [] },
  ])('rejects unsafe, unsupported or unreadable values: %j', value => {
    expect(parseUiDesign(value)).toBeNull()
  })
  it('preserves all v1 palette values, saved legacy data and radii in the adapter', () => {
    const legacy = { ...BUILTIN_STYLES.light, bodyBg: '#ABCDEF' }
    const theme = parseThemeDefinition({
      theme_extension_version: 1, design_api_version: 1, module_id: 'org.example.theme', version: '1.0.0',
      name: { en: 'Example' }, base_theme: 'builtin.default', light: { radius_sm: 0 }, dark: { radius_lg: 0 },
    })!
    const style = resolveThemeStyle(theme, 'light', legacy)
    const adapted = adaptLegacyUi(style, 'light')
    expect(adapted.light).toMatchObject({ canvas: style.bodyBg, content: style.contentBg, surface: style.cardBg,
      surface_alt: style.panelBg, accent: style.buttonPrimaryBg, secondary: style.buttonSecondaryBg,
      danger: style.buttonDangerBg, border: style.cardBorder, text: style.textPrimary,
      text_secondary: style.textSecondary, text_muted: style.textMuted })
    expect(adapted.scale.radius_sm).toBe(0)
    expect(legacy.bodyBg).toBe('#ABCDEF')
    expect(adaptLegacyUi(resolveThemeStyle(theme, 'dark', legacy), 'dark').scale.radius_lg).toBe(0)
  })
  it('preserves header overrides unless explicitly opted out, without changing content', () => {
    const header = { ...DEFAULT_HEADER_SETTINGS, siteName: 'My name', backgroundColor: '#123456' }
    const design = builtinUiDesign()
    expect(uiDesignVariables(design, 'light', header)['--ui-header-bg']).toBe('#123456')
    design.header_style = 'theme'
    expect(uiDesignVariables(design, 'light', header)['--ui-header-bg']).toBe(design.light.surface)
    expect(header).toMatchObject({ siteName: 'My name', backgroundColor: '#123456' })
  })
  it('never reduces button contrast, including near-threshold and colored foregrounds', () => {
    const colors = ['#000000', '#ffffff', '#767676', '#777777', '#007bff', '#6c757d', '#dc3545', '#7198f2', '#123456', '#c8b1ff']
    for (const background of colors) for (const foreground of colors) {
      const hover = buttonHoverBackground(background, foreground)
      expect(hover).toMatch(/^#[a-f0-9]{6}$/i)
      expect(contrastRatio(hover, foreground)).toBeGreaterThanOrEqual(contrastRatio(background, foreground))
    }
    expect(buttonHoverBackground('#767676', '#ffffff')).not.toBe('#ffffff')
    expect(buttonHoverBackground('#eeeeee', '#20252d')).not.toBe('#eeeeee')
  })
  it.each(['light', 'dark'] as const)('keeps built-in/saved and package button states readable in %s', mode => {
    const saved = { ...BUILTIN_STYLES[mode], buttonPrimaryBg: '#eeeeee', buttonSecondaryBg: '#123456' }
    for (const design of [builtinUiDesign(), adaptLegacyUi(BUILTIN_STYLES[mode], mode), adaptLegacyUi(saved, mode)]) {
      const colors = design[mode], variables = uiDesignVariables(design, mode, DEFAULT_HEADER_SETTINGS)
      for (const name of ['accent', 'secondary', 'danger'] as const) {
        const foreground = colors[`${name}_text`]
        expect(contrastRatio(variables[`--ui-${name}-hover`]!, foreground)).toBeGreaterThanOrEqual(contrastRatio(colors[name], foreground))
        expect(contrastRatio(variables[`--ui-${name}-hover`]!, foreground)).toBeGreaterThanOrEqual(4.5)
      }
      for (const name of ['primary', 'danger']) {
        expect(contrastRatio(variables[`--ui-${name}-outline-text`]!, colors.surface)).toBeGreaterThanOrEqual(4.5)
        expect(contrastRatio(variables[`--ui-${name}-outline-hover-text`]!, colors.surface_alt)).toBeGreaterThanOrEqual(4.5)
      }
    }
  })
  it('updates legacy Core and SDK button pairs together through mode and preview changes', async () => {
    const settings = useSettingsStore(), modes = useThemeStore(), root = document.documentElement.style
    settings.lightStyleSettings.buttonSecondaryBg = '#eeeeee'
    for (const preview of [builtinUiDesign(), null]) {
      settings.setDesignPreview(preview)
      for (const mode of ['dark', 'light'] as const) {
        modes.setTheme(mode); await nextTick()
        const colors = settings.uiDesign[mode]
        for (const [legacy, token] of [['primary', 'accent'], ['secondary', 'secondary'], ['danger', 'danger']] as const) {
          const foreground = root.getPropertyValue(`--button-${legacy}-text`)
          expect(foreground).toBe(colors[`${token}_text`])
          expect(root.getPropertyValue(`--button-${legacy}-bg`)).toBe(root.getPropertyValue(`--ui-${token}`))
          expect(root.getPropertyValue(`--button-${legacy}-hover`)).toBe(root.getPropertyValue(`--ui-${token}-hover`))
          expect(contrastRatio(root.getPropertyValue(`--button-${legacy}-hover`), foreground)).toBeGreaterThanOrEqual(4.5)
        }
      }
    }
  })
  it('clears preview, refreshes mode/aliases, preserves installed theme and auth', async () => {
    const settings = useSettingsStore(), modes = useThemeStore()
    settings.lightStyleSettings.bodyBg = '#ABCDEF'
    localStorage.setItem('authToken', 'preserved')
    expect(settings.setDesignPreview({ design_api_version: 2, header_style: 'theme' })).toBe(true)
    expect(document.documentElement.style.getPropertyValue('--ui-canvas')).toBe('#f4f5f7')
    modes.setTheme('dark'); await nextTick()
    expect(document.documentElement.style.getPropertyValue('--ui-canvas')).toBe('#15191f')
    expect(localStorage.getItem('theme')).toBeNull()
    expect(settings.setDesignPreview({ design_api_version: 99 })).toBe(false)
    expect(settings.previewDesign).not.toBeNull()
    settings.setDesignPreview(null); modes.setTheme('light'); await nextTick()
    expect(settings.previewDesign).toBeNull()
    expect(document.documentElement.style.getPropertyValue('--ui-canvas')).toBe('#ABCDEF')
    expect(settings.activeTheme).toBeNull()
    expect(localStorage.getItem('authToken')).toBe('preserved')
  })
  it('resolves generic shell modes without concrete extension names', () => {
    expect(resolveUiShellMode({ requiresAuth: true })).toBe('application')
    expect(resolveUiShellMode({ applicationAudience: 'public' })).toBe('public')
    expect(resolveUiShellMode({ requiresKiosk: true })).toBe('kiosk')
    expect(resolveUiShellMode({ uiShell: 'display', requiresAuth: true })).toBe('display')
    expect(resolveUiShellMode({ uiShell: 'unknown' })).toBe('public')
  })
})
