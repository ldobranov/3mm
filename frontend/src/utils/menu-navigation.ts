export interface NavigationItem {
  path: string
  label: string | Record<string, string>
}

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
