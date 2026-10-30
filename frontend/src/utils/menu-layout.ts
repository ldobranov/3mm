export const MENU_LOCATIONS = ['primary', 'header', 'sidebar', 'footer'] as const
export const MENU_REGIONS = ['header', 'sidebar', 'footer'] as const
export type MenuLocation = typeof MENU_LOCATIONS[number]
export type MenuRegion = typeof MENU_REGIONS[number]
export interface MenuPlacement { menu_id: number; location: MenuLocation }
export interface MenuLayout {
  // Omitted: follow the active menu. Empty: intentionally show no menus.
  placements?: MenuPlacement[]
  sticky: Record<MenuRegion, boolean>
}
export const defaultMenuLayout = (): MenuLayout => ({ sticky: { header: false, sidebar: false, footer: false } })

export function parseMenuLayout(value: unknown): MenuLayout | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const source = value as Record<string, unknown>
  if (Object.keys(source).some(key => !['placements', 'sticky'].includes(key)) ||
      !source.sticky || typeof source.sticky !== 'object' || Array.isArray(source.sticky)) return null
  const sticky = source.sticky as Record<string, unknown>
  if (Object.keys(sticky).length !== 3 || MENU_REGIONS.some(key => typeof sticky[key] !== 'boolean')) return null
  const result = defaultMenuLayout()
  result.sticky = { header: sticky.header as boolean, sidebar: sticky.sidebar as boolean, footer: sticky.footer as boolean }
  if ('placements' in source) {
    if (!Array.isArray(source.placements) || source.placements.length > 16) return null
    const ids = new Set<number>()
    result.placements = []
    for (const item of source.placements) {
      if (!item || typeof item !== 'object' || Array.isArray(item) ||
          Object.keys(item).length !== 2 || !Number.isInteger(item.menu_id) ||
          item.menu_id < 1 || item.menu_id > 2147483647 || ids.has(item.menu_id) ||
          !MENU_LOCATIONS.includes(item.location)) return null
      ids.add(item.menu_id)
      result.placements.push({ menu_id: item.menu_id, location: item.location })
    }
  }
  return result
}

export function resolveMenuRegions<T extends { id: number; is_active?: boolean }>(
  menus: readonly T[], layout: MenuLayout | null | undefined, primary: 'header' | 'sidebar',
): Record<MenuRegion, T[]> {
  const regions: Record<MenuRegion, T[]> = { header: [], sidebar: [], footer: [] }
  if (layout?.placements === undefined) {
    const active = menus.find(menu => menu.is_active)
    if (active) regions[primary].push(active)
  } else {
    for (const placement of layout.placements) {
      const menu = menus.find(menu => menu.id === placement.menu_id)
      // Deleted menus never fall back to an unrelated menu or generated links.
      if (menu) regions[placement.location === 'primary' ? primary : placement.location].push(menu)
    }
  }
  return regions
}
