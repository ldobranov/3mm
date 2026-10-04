// Design API v1 only: never turn arbitrary package keys into CSS properties.
export const COLOR_TOKENS = {
  body_bg: 'bodyBg', content_bg: 'contentBg', card_bg: 'cardBg', panel_bg: 'panelBg',
  button_primary_bg: 'buttonPrimaryBg', button_secondary_bg: 'buttonSecondaryBg',
  button_danger_bg: 'buttonDangerBg', card_border: 'cardBorder',
  text_primary: 'textPrimary', text_secondary: 'textSecondary', text_muted: 'textMuted',
} as const
export const RADIUS_TOKENS = {
  radius_sm: 'borderRadiusSm', radius_md: 'borderRadiusMd', radius_lg: 'borderRadiusLg',
} as const
export type ThemeMode = 'light' | 'dark'
export type ThemeTokens = Partial<Record<keyof typeof COLOR_TOKENS, string | null>> &
  Partial<Record<keyof typeof RADIUS_TOKENS, number | null>>
export interface ThemeDefinition {
  theme_extension_version: 1
  design_api_version: 1
  module_id: string
  version: string
  name: { en: string; translations?: Record<string, string> }
  base_theme: 'builtin.default'
  light: ThemeTokens
  dark: ThemeTokens
}
export const BUILTIN_STYLES = {
  light: {
    bodyBg: '#ffffff', contentBg: '#ffffff', cardBg: '#ffffff', panelBg: '#ffffff',
    buttonPrimaryBg: '#007bff', buttonSecondaryBg: '#6c757d', buttonDangerBg: '#dc3545',
    cardBorder: '#e3e3e3', textPrimary: '#222222', textSecondary: '#666666', textMuted: '#999999',
    borderRadiusSm: 4, borderRadiusMd: 8, borderRadiusLg: 12,
  },
  dark: {
    bodyBg: '#1f2937', contentBg: '#1f2937', cardBg: '#374151', panelBg: '#374151',
    buttonPrimaryBg: '#3b82f6', buttonSecondaryBg: '#6b7280', buttonDangerBg: '#ef4444',
    cardBorder: '#4b5563', textPrimary: '#e5e7eb', textSecondary: '#9ca3af', textMuted: '#6b7280',
    borderRadiusSm: 4, borderRadiusMd: 8, borderRadiusLg: 12,
  },
}
export type StyleSettings = typeof BUILTIN_STYLES.light
const object = (value: unknown): value is Record<string, any> =>
  value !== null && typeof value === 'object' && !Array.isArray(value)
const tokensValid = (value: unknown): value is ThemeTokens => {
  if (!object(value) || !Object.values(value).some(token => token != null)) return false
  return Object.entries(value).every(([key, token]) => {
    if (Object.prototype.hasOwnProperty.call(COLOR_TOKENS, key)) return token == null || typeof token === 'string' && /^#[\da-f]{6}$/i.test(token)
    if (Object.prototype.hasOwnProperty.call(RADIUS_TOKENS, key)) return token == null || typeof token === 'number' && Number.isInteger(token) && token >= 0 && token <= 50
    return false
  })
}
export function parseThemeDefinition(value: unknown): ThemeDefinition | null {
  if (!object(value) || value.theme_extension_version !== 1 || value.design_api_version !== 1 ||
      value.base_theme !== 'builtin.default' || !tokensValid(value.light) || !tokensValid(value.dark)) return null
  const keys = ['theme_extension_version', 'design_api_version', 'module_id', 'version', 'name', 'base_theme', 'light', 'dark']
  if (Object.keys(value).some(key => !keys.includes(key)) ||
      typeof value.module_id !== 'string' || value.module_id.length > 160 || !/^[a-z0-9]+(?:[.-][a-z0-9]+)+$/.test(value.module_id) ||
      typeof value.version !== 'string' || value.version.length > 64 || !/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$/.test(value.version)) return null
  const name = value.name
  if (!object(name) || typeof name.en !== 'string' || !name.en.length || name.en.length > 160 ||
      Object.keys(name).some(key => key !== 'en' && key !== 'translations')) return null
  const translations = name.translations ?? {}
  if (!object(translations) || Object.keys(translations).length > 32 ||
      Object.entries(translations).some(([locale, text]) => !locale.length || locale.length > 24 || typeof text !== 'string' || !text.length || text.length > 160)) return null
  return value as ThemeDefinition
}
export function resolveThemeStyle(theme: ThemeDefinition | null, mode: ThemeMode, legacy: StyleSettings): StyleSettings {
  if (!theme) return legacy
  const style = { ...BUILTIN_STYLES[mode] }
  const tokens = theme[mode]
  for (const key of Object.keys(COLOR_TOKENS) as (keyof typeof COLOR_TOKENS)[]) {
    const value = tokens[key]
    if (value != null) style[COLOR_TOKENS[key]] = value
  }
  for (const key of Object.keys(RADIUS_TOKENS) as (keyof typeof RADIUS_TOKENS)[]) {
    const value = tokens[key]
    if (value != null) style[RADIUS_TOKENS[key]] = value
  }
  return style
}

// Aliases stay Core-owned. Use a readable foreground for package accents;
// retain the legacy button foreground when no package is selected.
export function buttonTextColor(color: string): string {
  const channels = [1, 3, 5].map(offset => {
    const value = parseInt(color.slice(offset, offset + 2), 16) / 255
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
  })
  const luminance = channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722
  return (luminance + 0.05) / 0.05 >= 1.05 / (luminance + 0.05) ? '#000000' : '#ffffff'
}

export async function readThemeAppearance(baseUrl: string): Promise<ThemeDefinition | null> {
  // Public appearance must never refresh/clear a browser's authentication.
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), 5000)
  try {
    const response = await fetch(`${baseUrl}/api/v1/modules/themes/appearance`, {
      cache: 'no-store', credentials: 'omit', signal: controller.signal,
    })
    if (!response.ok) return null
    const text = await response.text()
    if (text.length > 64 * 1024) return null
    return parseThemeDefinition(JSON.parse(text)?.theme)
  } catch {
    return null
  } finally {
    window.clearTimeout(timeout)
  }
}
