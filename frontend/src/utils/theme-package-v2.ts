import { parseThemeDefinition, readThemeProjection, type ThemeDefinition, type StyleSettings, type ThemeMode } from './theme-extension'
import { parseUiDesign, UI_ASSET_BUDGET, type UiDesign } from './ui-design'
import { parseCustomizationOptions, type ThemeCustomizationOptions } from './theme-customization'

export interface ThemeAsset {
  asset_id: string; path: string; sha256: string
  media_type: 'font/woff2' | 'image/png' | 'image/webp'
  role: 'font' | 'logo_light' | 'logo_dark'; license?: string
}
export interface ThemePackageV2 {
  theme_extension_version: 2; design_api_version: 2
  module_id: string; version: string; name: ThemeDefinition['name']; base_theme: 'builtin.default'
  design: UiDesign; assets: ThemeAsset[]; package_sha256: string
  customization_options?: ThemeCustomizationOptions
}
export type InstalledTheme = ThemeDefinition | ThemePackageV2
const record = (v: unknown): v is Record<string, unknown> => v !== null && typeof v === 'object' && !Array.isArray(v)
const hash = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v)

export function parseInstalledTheme(projection: unknown): InstalledTheme | null {
  if (!record(projection) || !record(projection.theme)) return null
  const value = projection.theme
  if (value.theme_extension_version === 1) return parseThemeDefinition(value)
  if (value.theme_extension_version !== 2 || value.design_api_version !== 2 || !hash(projection.package_sha256) ||
    Object.keys(value).some(key => !['theme_extension_version', 'design_api_version', 'module_id', 'version', 'name', 'base_theme', 'design', 'assets', 'customization_options'].includes(key))) return null
  const identity = parseThemeDefinition({ theme_extension_version: 1, design_api_version: 1, module_id: value.module_id,
    version: value.version, name: value.name, base_theme: value.base_theme, light: { radius_sm: 0 }, dark: { radius_sm: 0 } })
  const design = parseUiDesign(value.design)
  const assets = value.assets ?? []
  if (!identity || !design || !Array.isArray(assets) || assets.length > UI_ASSET_BUDGET.maxFiles) return null
  const options = value.customization_options === undefined ? undefined : parseCustomizationOptions(value.customization_options, design)
  if (options === null) return null
  for (const asset of assets) {
    if (!record(asset) || Object.keys(asset).some(key => !['asset_id', 'path', 'sha256', 'media_type', 'role', 'license'].includes(key)) ||
      typeof asset.asset_id !== 'string' || !/^[a-z][a-z0-9_-]{0,63}$/.test(asset.asset_id) || !hash(asset.sha256) ||
      typeof asset.path !== 'string' || asset.path.length > 160 || !/^assets\/[a-zA-Z0-9_-]+\.(woff2|png|webp)$/.test(asset.path) ||
      !['font', 'logo_light', 'logo_dark'].includes(String(asset.role))) return null
    const suffix = { 'font/woff2': '.woff2', 'image/png': '.png', 'image/webp': '.webp' }[String(asset.media_type)]
    if (!suffix || !asset.path.endsWith(suffix) || (asset.role === 'font') !== (asset.media_type === 'font/woff2') ||
      (asset.license !== undefined && (typeof asset.license !== 'string' || !asset.license.trim() || asset.license.length > 512)) ||
      (asset.role === 'font' && !asset.license)) return null
  }
  for (const key of ['asset_id', 'path', 'role']) if (new Set(assets.map(asset => asset[key])).size !== assets.length) return null
  return { ...identity, theme_extension_version: 2, design_api_version: 2, design, assets, package_sha256: projection.package_sha256,
    ...(options ? { customization_options: options } : {}) }
}

export async function readInstalledTheme(baseUrl: string, signal?: AbortSignal): Promise<InstalledTheme | null> {
  return parseInstalledTheme(await readThemeProjection(baseUrl, signal))
}

export function designLegacyStyle(design: UiDesign, mode: ThemeMode): StyleSettings {
  const c = design[mode], s = design.scale
  return { bodyBg: c.canvas, contentBg: c.content, cardBg: c.surface, panelBg: c.surface_alt,
    buttonPrimaryBg: c.accent, buttonSecondaryBg: c.secondary, buttonDangerBg: c.danger, cardBorder: c.border,
    textPrimary: c.text, textSecondary: c.text_secondary, textMuted: c.text_muted,
    borderRadiusSm: s.radius_sm, borderRadiusMd: s.radius_md, borderRadiusLg: s.radius_lg }
}

export interface LoadedThemeAssets {
  font: FontFace | null; logos: Partial<Record<ThemeMode, string>>; warnings: string[]; dispose: () => void
}
export async function loadThemeAssets(theme: ThemePackageV2, baseUrl: string, signal: AbortSignal, previewToken?: string): Promise<LoadedThemeAssets> {
  const result: LoadedThemeAssets = { font: null, logos: {}, warnings: [], dispose: () => {
    if (result.font) document.fonts?.delete(result.font)
    Object.values(result.logos).forEach(url => URL.revokeObjectURL(url))
  } }
  for (const asset of theme.assets) {
    if (signal.aborted) break
    const controller = new AbortController()
    const abort = () => controller.abort()
    signal.addEventListener('abort', abort, { once: true })
    const timeout = window.setTimeout(abort, 5000)
    const boundedDecode = <T>(promise: Promise<T>): Promise<T> => Promise.race([promise, new Promise<never>((_, reject) => {
      if (controller.signal.aborted) reject(new Error('cancelled'))
      else controller.signal.addEventListener('abort', () => reject(new Error('cancelled')), { once: true })
    })])
    try {
      // Core owns the URL; never use package path as an HTTP URL or a CSS value.
      const scope = previewToken ? 'preview/assets' : 'assets'
      const response = await fetch(`${baseUrl}/api/v1/modules/themes/packages/${theme.package_sha256}/${scope}/${asset.asset_id}`, {
        credentials: 'omit', cache: 'no-store', signal: controller.signal,
        // Preview resources are protected. Never send credentials to the public loader.
        ...(previewToken ? { headers: { Authorization: `Bearer ${previewToken}` } } : {}),
      })
      const limit = asset.role === 'font' ? UI_ASSET_BUDGET.maxFontBytes : UI_ASSET_BUDGET.maxImageBytes
      if (!response.ok || response.headers.get('content-type')?.split(';')[0] !== asset.media_type || !response.body) throw new Error('unavailable')
      const reader = response.body.getReader(), chunks: Uint8Array[] = []
      let size = 0
      try {
        while (true) {
          const chunk = await reader.read()
          if (chunk.done) break
          size += chunk.value.length
          if (size > limit) throw new Error('size')
          chunks.push(chunk.value)
        }
      } finally { await reader.cancel() }
      if (!size || controller.signal.aborted) throw new Error('cancelled')
      const bytes = new Uint8Array(size)
      let offset = 0
      chunks.forEach(chunk => { bytes.set(chunk, offset); offset += chunk.length })
      // LAN HTTP can lack WebCrypto; Core already verifies artifact + asset hashes.
      if (globalThis.crypto?.subtle) {
        const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))).map(n => n.toString(16).padStart(2, '0')).join('')
        if (digest !== asset.sha256) throw new Error('checksum')
      }
      if (asset.role === 'font') {
        if (typeof FontFace === 'undefined') throw new Error('unsupported font')
        const font = new FontFace(`UiTheme_${theme.package_sha256}`, bytes.buffer, { display: 'swap' })
        // Browser font sanitizer performs final glyph/codec validation.
        const loaded = await boundedDecode(font.load())
        if (signal.aborted) throw new Error('cancelled')
        result.font = loaded
      } else {
        const blob = new Blob([bytes], { type: asset.media_type })
        if (typeof createImageBitmap !== 'function') throw new Error('unsupported image decoder')
        const image = await boundedDecode(createImageBitmap(blob).then(image => {
          if (controller.signal.aborted) { image.close(); throw new Error('cancelled') }
          return image
        }))
        try {
          if (signal.aborted || controller.signal.aborted || !image.width || !image.height || image.width > UI_ASSET_BUDGET.maxImageDimension || image.height > UI_ASSET_BUDGET.maxImageDimension) throw new Error('dimensions')
        } finally { image.close() }
        result.logos[asset.role === 'logo_dark' ? 'dark' : 'light'] = URL.createObjectURL(blob)
      }
    } catch { result.warnings.push(asset.role) }
    finally { window.clearTimeout(timeout); signal.removeEventListener('abort', abort) }
  }
  return result
}
