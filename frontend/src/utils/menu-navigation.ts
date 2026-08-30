export interface NavigationItem {
  path: string
  label: string | Record<string, string>
  audience?: MenuAudience
}

export type MenuAudience = 'public' | 'authenticated' | 'admin' | 'kiosk'

export function mergeNavigationItems(
  customItems: NavigationItem[],
  dynamicItems: NavigationItem[],
): NavigationItem[] {
  const merged = [...customItems]
  for (const item of dynamicItems) {
    if (!merged.some(existing => existing.path === item.path)) merged.push(item)
  }
  return merged
}

export function normalizeAvailableLanguages(languages: unknown): string[] {
  const installed = Array.isArray(languages)
    ? languages.filter((language): language is string => typeof language === 'string' && language.length > 0)
    : []
  return Array.from(new Set(['en', ...installed]))
}

export function isMenuRouteEligible(
  path: string,
  requiredRole: string | undefined,
  currentRole: string,
): boolean {
  if (!path || path === '/' || path.includes(':')) return false
  if (['/user/login', '/user/register', '/user/logout'].includes(path)) return false
  return !requiredRole || requiredRole === currentRole
}

export function isNavigationItemVisible(
  item: NavigationItem,
  options: {
    isLoggedIn: boolean
    isKiosk?: boolean
    currentRole: string
    routeRequiresAuth?: boolean
    routeRequiredRole?: string
  },
): boolean {
  const { isLoggedIn, isKiosk = false, currentRole, routeRequiresAuth, routeRequiredRole } = options

  if (item.audience === 'public') {
    if (routeRequiresAuth) return false
  } else if (item.audience === 'authenticated') {
    if (!isLoggedIn) return false
  } else if (item.audience === 'admin') {
    if (!isLoggedIn || currentRole !== 'admin') return false
  } else if (item.audience === 'kiosk') {
    if (!isKiosk) return false
  } else if (routeRequiresAuth && !isLoggedIn) {
    return false
  }

  return !routeRequiredRole || (isLoggedIn && currentRole === routeRequiredRole)
}
