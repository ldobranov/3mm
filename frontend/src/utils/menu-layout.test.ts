import { describe, expect, it } from 'vitest'
import { defaultMenuLayout, parseMenuLayout, resolveMenuRegions } from './menu-layout'
import { designPreferences, parseThemePreferences } from './theme-customization'
import { builtinUiDesign } from './ui-design'

const menus = [{ id: 1, is_active: true }, { id: 2 }, { id: 3 }]
describe('bounded installation-owned menu placement', () => {
  it('follows the active menu and primary layout only when no placements are saved', () => {
    expect(resolveMenuRegions(menus, null, 'sidebar')).toEqual({ header: [], sidebar: [menus[0]], footer: [] })
    expect(resolveMenuRegions(menus, defaultMenuLayout(), 'header').header).toEqual([menus[0]])
    expect(resolveMenuRegions(menus, { ...defaultMenuLayout(), placements: [] }, 'header')).toEqual({ header: [], sidebar: [], footer: [] })
  })
  it('places several menus without replacing missing IDs or mutating the catalog', () => {
    const before = JSON.stringify(menus)
    const layout = { ...defaultMenuLayout(), placements: [
      { menu_id: 3, location: 'header' as const }, { menu_id: 2, location: 'footer' as const },
      { menu_id: 99, location: 'sidebar' as const }, { menu_id: 1, location: 'primary' as const },
    ] }
    expect(resolveMenuRegions(menus, layout, 'header')).toEqual({ header: [menus[2], menus[0]], footer: [menus[1]], sidebar: [] })
    expect(JSON.stringify(menus)).toBe(before)
  })
  it.each([
    { sticky: { header: 'true', sidebar: false, footer: false } },
    { sticky: { header: true } }, { ...defaultMenuLayout(), css: 'position:fixed' },
    { ...defaultMenuLayout(), placements: null },
    { ...defaultMenuLayout(), placements: [{ menu_id: 1, location: 'header' }, { menu_id: 1, location: 'footer' }] },
    { ...defaultMenuLayout(), placements: [{ menu_id: true, location: 'header' }] },
    { ...defaultMenuLayout(), placements: [{ menu_id: 2147483648, location: 'header' }] },
    { ...defaultMenuLayout(), placements: [{ menu_id: 1, location: 'external' }] },
    { ...defaultMenuLayout(), placements: Array.from({ length: 17 }, (_, i) => ({ menu_id: i + 1, location: 'primary' })) },
  ])('rejects unsafe or ambiguous menu layout %j', value => { expect(parseMenuLayout(value)).toBeNull() })
  it('round-trips the optional layout without changing existing preference shapes', () => {
    const base = designPreferences(builtinUiDesign(), { backgroundColor: '#ffffff', textColor: '#000000' })
    expect(parseThemePreferences(base)).toEqual(base)
    const menu_layout = { ...defaultMenuLayout(), placements: [{ menu_id: 1, location: 'footer' as const }] }
    menu_layout.sticky.footer = true
    const value = { ...base, menu_layout }
    expect(parseThemePreferences(value)).toEqual(value)
    expect(parseThemePreferences({ ...base, menu_layout: { sticky: {} } })).toBeNull()
  })
})
