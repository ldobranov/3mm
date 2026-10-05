import { contrastRatio, type UiDesign } from './ui-design'

export interface ThemePreferences {
  navigation: 'sidebar' | 'top'
  density: 'compact' | 'comfortable'
  button: 'solid' | 'outline'
  card: 'bordered' | 'raised'
  header_style: 'saved' | 'theme'
  header_background_color: string
  header_text_color: string
}

export function parseThemePreferences(value: unknown): ThemePreferences | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const p = value as Record<string, unknown>
  const variants = { navigation: ['sidebar', 'top'], density: ['compact', 'comfortable'],
    button: ['solid', 'outline'], card: ['bordered', 'raised'], header_style: ['saved', 'theme'] }
  const keys = [...Object.keys(variants), 'header_background_color', 'header_text_color']
  if (Object.keys(p).length !== keys.length || Object.keys(p).some(key => !keys.includes(key)) ||
    Object.entries(variants).some(([key, allowed]) => typeof p[key] !== 'string' || !allowed.includes(p[key] as string))) return null
  for (const key of ['header_background_color', 'header_text_color']) {
    if (typeof p[key] !== 'string' || !/^#[a-f\d]{6}$/i.test(p[key])) return null
  }
  if (p.header_style === 'saved' && contrastRatio(p.header_background_color as string, p.header_text_color as string) < 4.5) return null
  return { ...p } as unknown as ThemePreferences
}

export function applyThemePreferences(design: UiDesign, preferences: ThemePreferences | null): UiDesign {
  if (!preferences) return design
  return { ...design, layout: { ...design.layout, navigation: preferences.navigation, density: preferences.density },
    components: { ...design.components, button: preferences.button, card: preferences.card }, header_style: preferences.header_style }
}

export function designPreferences(design: UiDesign, header: { backgroundColor: string; textColor: string }): ThemePreferences {
  return { navigation: design.layout.navigation, density: design.layout.density,
    button: design.components.button, card: design.components.card, header_style: design.header_style,
    header_background_color: header.backgroundColor, header_text_color: header.textColor }
}
