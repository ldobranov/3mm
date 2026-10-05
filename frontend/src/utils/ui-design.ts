import { buttonTextColor, type StyleSettings, type ThemeMode } from './theme-extension'
import type { ResolvedHeaderSettings } from './header-settings'
import defaults from '../../../three_mm_protocol/theme_design_defaults.json'

// Design API is independent of device protocol and application SDK versions.
export const UI_COLOR_KEYS = [
  'canvas', 'content', 'surface', 'surface_alt', 'text', 'text_secondary', 'text_muted',
  'border', 'accent', 'accent_text', 'secondary', 'secondary_text', 'danger', 'danger_text', 'success', 'warning', 'focus',
] as const
export type UiColors = Record<typeof UI_COLOR_KEYS[number], string>
export type UiShellMode = 'application' | 'auth' | 'public' | 'kiosk' | 'display'
export interface UiDesign {
  design_api_version: 2
  light: UiColors
  dark: UiColors
  typography: { font: 'system' | 'sans' | 'mono'; base_size: number; line_height: number }
  scale: { unit: number; radius_sm: number; radius_md: number; radius_lg: number }
  layout: { navigation: 'sidebar' | 'top'; density: 'compact' | 'comfortable'; content_width: number; sidebar_width: number }
  components: { button: 'solid' | 'outline'; card: 'bordered' | 'raised' }
  header_style: 'saved' | 'theme'
}

// Shared limits enforced by the package validator and bounded client loader.
export const UI_ASSET_BUDGET = Object.freeze({
  maxFiles: 16, maxTotalBytes: 4 * 1024 * 1024, maxFontBytes: 512 * 1024,
  maxImageBytes: 1024 * 1024, maxImageDimension: 2048,
})

export function builtinUiDesign(): UiDesign {
  return JSON.parse(JSON.stringify(defaults)) as UiDesign
}

const record = (value: unknown): value is Record<string, unknown> => value !== null &&
  typeof value === 'object' && !Array.isArray(value) &&
  [Object.prototype, null].includes(Object.getPrototypeOf(value))
const bounded = (value: unknown, min: number, max: number, integer = true) =>
  typeof value === 'number' && Number.isFinite(value) && value >= min && value <= max &&
  (!integer || Number.isInteger(value))

export function contrastRatio(first: string, second: string): number {
  const luminance = (color: string) => {
    const rgb = [1, 3, 5].map(offset => {
      const channel = parseInt(color.slice(offset, offset + 2), 16) / 255
      return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4
    })
    return rgb[0]! * .2126 + rgb[1]! * .7152 + rgb[2]! * .0722
  }
  const a = luminance(first), b = luminance(second)
  return (Math.max(a, b) + .05) / (Math.min(a, b) + .05)
}

export function parseUiDesign(value: unknown): UiDesign | null {
  if (!record(value) || value.design_api_version !== 2) return null
  const result = builtinUiDesign()
  const allowed = ['design_api_version', 'light', 'dark', 'typography', 'scale', 'layout', 'components', 'header_style']
  if (Object.keys(value).some(key => !allowed.includes(key))) return null
  for (const mode of ['light', 'dark'] as const) {
    const source = value[mode]
    if (source !== undefined) {
      if (!record(source)) return null
      for (const [key, token] of Object.entries(source)) {
        if (!UI_COLOR_KEYS.includes(key as typeof UI_COLOR_KEYS[number])) return null
        if (token === null) continue
        if (typeof token !== 'string' || !/^#[\da-f]{6}$/i.test(token)) return null
        result[mode][key as keyof UiColors] = token
      }
    }
    const colors = result[mode]
    for (const surface of [colors.canvas, colors.content, colors.surface, colors.surface_alt]) {
      if ([colors.text, colors.text_secondary, colors.text_muted, colors.success, colors.warning, colors.accent, colors.danger]
        .some(text => contrastRatio(text, surface) < 4.5) || contrastRatio(colors.focus, surface) < 3) return null
    }
    if (contrastRatio(colors.accent, colors.accent_text) < 4.5 || contrastRatio(colors.secondary, colors.secondary_text) < 4.5 || contrastRatio(colors.danger, colors.danger_text) < 4.5) return null
  }
  const groups = ['typography', 'scale', 'layout', 'components'] as const
  for (const group of groups) {
    const source = value[group]
    if (source === undefined) continue
    if (!record(source) || Object.keys(source).some(key => !Object.prototype.hasOwnProperty.call(result[group], key))) return null
    Object.assign(result[group], Object.fromEntries(Object.entries(source).filter(([, token]) => token !== null)))
  }
  const { typography: t, scale: s, layout: l, components: c } = result
  if (!['system', 'sans', 'mono'].includes(t.font) || !bounded(t.base_size, 12, 18) || !bounded(t.line_height, 1.35, 1.8, false) ||
    !bounded(s.unit, 2, 8) || ![s.radius_sm, s.radius_md, s.radius_lg].every(n => bounded(n, 0, 50)) ||
    !['sidebar', 'top'].includes(l.navigation) || !['compact', 'comfortable'].includes(l.density) ||
    !bounded(l.content_width, 960, 1800) || !bounded(l.sidebar_width, 216, 320) ||
    !['solid', 'outline'].includes(c.button) || !['bordered', 'raised'].includes(c.card)) return null
  if (value.header_style !== undefined) {
    if (value.header_style !== 'saved' && value.header_style !== 'theme') return null
    result.header_style = value.header_style
  }
  return result
}

// v1 keeps exactly its effective colors/radii. It never opts into a new shell.
export function adaptLegacyUi(style: StyleSettings, mode: ThemeMode): UiDesign {
  const design = builtinUiDesign()
  Object.assign(design[mode], {
    canvas: style.bodyBg, content: style.contentBg, surface: style.cardBg, surface_alt: style.panelBg,
    text: style.textPrimary, text_secondary: style.textSecondary, text_muted: style.textMuted,
    border: style.cardBorder, accent: style.buttonPrimaryBg, accent_text: buttonTextColor(style.buttonPrimaryBg),
    secondary: style.buttonSecondaryBg, secondary_text: buttonTextColor(style.buttonSecondaryBg),
    danger: style.buttonDangerBg, danger_text: buttonTextColor(style.buttonDangerBg), focus: style.buttonPrimaryBg,
  })
  Object.assign(design.scale, { radius_sm: style.borderRadiusSm, radius_md: style.borderRadiusMd, radius_lg: style.borderRadiusLg })
  return design
}

const fonts = {
  system: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  sans: 'Arial, "Helvetica Neue", sans-serif',
  mono: 'ui-monospace, Consolas, monospace',
}
export function uiDesignVariables(design: UiDesign, mode: ThemeMode, header: ResolvedHeaderSettings): Record<string, string> {
  const colors = design[mode]
  const variables: Record<string, string> = Object.fromEntries(UI_COLOR_KEYS.map(key => [`--ui-${key.replace(/_/g, '-')}`, colors[key]]))
  Object.assign(variables, {
    '--ui-font': fonts[design.typography.font], '--ui-font-size': `${design.typography.base_size}px`,
    '--ui-line-height': `${design.typography.line_height}`, '--ui-space': `${design.scale.unit}px`,
    '--ui-radius-sm': `${design.scale.radius_sm}px`, '--ui-radius-md': `${design.scale.radius_md}px`,
    '--ui-radius-lg': `${design.scale.radius_lg}px`, '--ui-content-width': `${design.layout.content_width}px`,
    '--ui-sidebar-width': `${design.layout.sidebar_width}px`, '--ui-control-height': design.layout.density === 'compact' ? '36px' : '44px',
    '--ui-header-bg': design.header_style === 'saved' ? header.backgroundColor : colors.surface,
    '--ui-header-text': design.header_style === 'saved' ? header.textColor : colors.text,
  })
  return variables
}

export function resolveUiShellMode(meta: Record<string, unknown>): UiShellMode {
  if (['application', 'auth', 'public', 'kiosk', 'display'].includes(String(meta.uiShell))) return meta.uiShell as UiShellMode
  if (meta.requiresKiosk === true || meta.applicationAudience === 'kiosk') return 'kiosk'
  return meta.requiresAuth === true ? 'application' : 'public'
}
