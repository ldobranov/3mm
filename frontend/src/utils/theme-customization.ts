import { contrastRatio, parseUiDesign, UI_COLOR_KEYS, type UiColors, type UiDesign } from './ui-design'
import { buttonTextColor } from './theme-extension'

export const LEGACY_UI_COLOR_KEYS = [
  'canvas', 'content', 'surface', 'surface_alt', 'text', 'text_secondary', 'text_muted',
  'border', 'accent', 'secondary', 'danger',
] as const
export type ThemeColorOverrides = Partial<Record<'light' | 'dark', Partial<UiColors>>>

export const THEME_VARIANTS = {
  navigation: ['sidebar', 'top'], density: ['compact', 'comfortable'],
  button: ['solid', 'outline'], card: ['bordered', 'raised'], header_style: ['saved', 'theme'],
} as const
export type ThemeOptionField = keyof typeof THEME_VARIANTS
export type ThemeCustomizationOptions = Record<ThemeOptionField, string[]> & { colors: (keyof UiColors)[] }

export function parseCustomizationOptions(value: unknown, design: UiDesign): ThemeCustomizationOptions | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const source = value as Record<string, unknown>
  if (Object.keys(source).some(key => ![...Object.keys(THEME_VARIANTS), 'colors'].includes(key))) return null
  const defaults = { navigation: design.layout.navigation, density: design.layout.density,
    button: design.components.button, card: design.components.card, header_style: design.header_style }
  const result = {} as ThemeCustomizationOptions
  for (const key of [...Object.keys(THEME_VARIANTS), 'colors'] as (ThemeOptionField | 'colors')[]) {
    const offered = source[key] === undefined ? [] : source[key]
    const allowed: readonly string[] = key === 'colors' ? UI_COLOR_KEYS : THEME_VARIANTS[key]
    if (!Array.isArray(offered) || offered.length > allowed.length || new Set(offered).size !== offered.length ||
        offered.some(option => typeof option !== 'string' || !allowed.includes(option)) ||
        (key !== 'colors' && offered.length && !offered.includes(defaults[key]))) return null
    Object.assign(result, { [key]: [...offered] })
  }
  return result
}

export function themeCustomizationOptions(theme: { theme_extension_version: 1 | 2; customization_options?: ThemeCustomizationOptions } | null): ThemeCustomizationOptions {
  if (theme?.theme_extension_version === 2 && theme.customization_options) return theme.customization_options
  // Old packages did not declare an editor. Preserve their existing controls.
  return { ...Object.fromEntries(Object.entries(THEME_VARIANTS).map(([key, values]) => [key, [...values]])),
    colors: theme ? [...(theme.theme_extension_version === 2 ? UI_COLOR_KEYS : LEGACY_UI_COLOR_KEYS)] : [] } as ThemeCustomizationOptions
}

export interface ThemePreferences {
  navigation: 'sidebar' | 'top'
  density: 'compact' | 'comfortable'
  button: 'solid' | 'outline'
  card: 'bordered' | 'raised'
  header_style: 'saved' | 'theme'
  header_background_color: string
  header_text_color: string
  colors?: ThemeColorOverrides
}

export function parseThemePreferences(value: unknown): ThemePreferences | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const p = value as Record<string, unknown>
  const variants = { navigation: ['sidebar', 'top'], density: ['compact', 'comfortable'],
    button: ['solid', 'outline'], card: ['bordered', 'raised'], header_style: ['saved', 'theme'] }
  const keys = [...Object.keys(variants), 'header_background_color', 'header_text_color']
  if (keys.some(key => !(key in p)) || Object.keys(p).some(key => ![...keys, 'colors'].includes(key)) ||
    Object.entries(variants).some(([key, allowed]) => typeof p[key] !== 'string' || !allowed.includes(p[key] as string))) return null
  for (const key of ['header_background_color', 'header_text_color']) {
    if (typeof p[key] !== 'string' || !/^#[a-f\d]{6}$/i.test(p[key])) return null
  }
  if (p.header_style === 'saved' && contrastRatio(p.header_background_color as string, p.header_text_color as string) < 4.5) return null
  const result = { ...p } as unknown as ThemePreferences
  if ('colors' in p) {
    if (!p.colors || typeof p.colors !== 'object' || Array.isArray(p.colors)) return null
    const colors = p.colors as Record<string, unknown>
    if (Object.keys(colors).some(mode => mode !== 'light' && mode !== 'dark')) return null
    for (const palette of Object.values(colors)) {
      if (!palette || typeof palette !== 'object' || Array.isArray(palette) ||
        Object.entries(palette).some(([key, value]) => !UI_COLOR_KEYS.includes(key as keyof UiColors) ||
          typeof value !== 'string' || !/^#[a-f\d]{6}$/i.test(value))) return null
    }
    if (!Object.values(colors).some(palette => Object.keys(palette as object).length)) return null
    result.colors = JSON.parse(JSON.stringify(colors))
  }
  return result
}

export function themePreferencesValid(design: UiDesign, preferences: ThemePreferences, version: 1 | 2 | null, options?: ThemeCustomizationOptions): boolean {
  if (!parseThemePreferences(preferences)) return false
  if (options) {
    const defaults = designPreferences(design, { backgroundColor: '#ffffff', textColor: '#000000' })
    if ((Object.keys(THEME_VARIANTS) as ThemeOptionField[]).some(key =>
      !(options[key].length ? options[key] : [defaults[key]]).includes(preferences[key])) ||
      Object.values(preferences.colors || {}).some(palette => Object.keys(palette).some(key => !options.colors.includes(key as keyof UiColors)))) return false
  }
  if (!preferences.colors) return true
  if (version === null) return false
  if (version === 1) return Object.values(preferences.colors).every(palette =>
    Object.keys(palette).every(key => LEGACY_UI_COLOR_KEYS.includes(key as typeof LEGACY_UI_COLOR_KEYS[number])))
  return parseUiDesign(applyThemePreferences(design, preferences)) !== null
}

export function applyThemePreferences(design: UiDesign, preferences: ThemePreferences | null, legacy = false): UiDesign {
  if (!preferences) return design
  const result = { ...design, layout: { ...design.layout, navigation: preferences.navigation, density: preferences.density },
    components: { ...design.components, button: preferences.button, card: preferences.card }, header_style: preferences.header_style }
  for (const mode of ['light', 'dark'] as const) {
    const overrides = preferences.colors?.[mode]
    if (!overrides) continue
    result[mode] = { ...design[mode], ...overrides }
    if (legacy) {
      for (const key of ['accent', 'secondary', 'danger'] as const) {
        result[mode][`${key}_text`] = buttonTextColor(result[mode][key])
      }
      result[mode].focus = result[mode].accent
    }
  }
  return result
}

export function designPreferences(design: UiDesign, header: { backgroundColor: string; textColor: string }): ThemePreferences {
  return { navigation: design.layout.navigation, density: design.layout.density,
    button: design.components.button, card: design.components.card, header_style: design.header_style,
    header_background_color: header.backgroundColor, header_text_color: header.textColor }
}
