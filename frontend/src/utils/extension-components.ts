const bundledComponentModules = import.meta.glob('../extensions/*/*.vue') as Record<
  string,
  () => Promise<{ default: any }>
>

function componentFileName(componentName: string): string {
  return componentName.endsWith('.vue') ? componentName : `${componentName}.vue`
}

export function extensionComponentKey(
  extensionName: string,
  version: string,
  componentName: string
): string {
  return `../extensions/${extensionName}_${version}/${componentFileName(componentName)}`
}

export function normalizeExtensionComponentPath(componentPath: string): string | null {
  const normalized = componentPath.replace(/\\/g, '/').split(/[?#]/, 1)[0]
  const marker = 'extensions/'
  const markerIndex = normalized.indexOf(marker)
  if (markerIndex < 0) return null

  const relativePath = normalized.slice(markerIndex + marker.length).replace(/^\/+/, '')
  if (!relativePath || relativePath.split('/').some(part => part === '..')) return null
  return `../extensions/${relativePath}`
}

export async function loadBundledExtensionComponent(
  extensionName: string,
  version: string,
  componentName: string
): Promise<any | null> {
  return loadBundledExtensionComponentByPath(
    extensionComponentKey(extensionName, version, componentName)
  )
}

export async function loadBundledExtensionComponentByPath(componentPath: string): Promise<any | null> {
  const key = componentPath.startsWith('../extensions/')
    ? componentPath
    : normalizeExtensionComponentPath(componentPath)
  if (!key) return null

  const loader = bundledComponentModules[key]
  if (!loader) return null

  const module = await loader()
  return module.default || null
}
