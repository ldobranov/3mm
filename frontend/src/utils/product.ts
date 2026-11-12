import source from '../../../config_templates/product.json'

type SetupLabels = { title: string; wifi: string; networkHelp: string; success: string }
export interface ProductMetadata {
  schema_version: 1
  name: string
  display_name: string
  welcome_message: string
  description: string
  default_logo_url: string
  favicon_url: string
  setup: { page_title: string; header: string; labels: Record<'en' | 'bg', SetupLabels> }
}

// Neutral fallback keeps presentation usable; it never changes host identities.
const fallback: ProductMetadata = {
  schema_version: 1, name: 'Platform', display_name: 'Device platform',
  welcome_message: 'Welcome', description: 'Local application and device administration.',
  default_logo_url: '', favicon_url: '/favicon.ico',
  setup: { page_title: 'Device setup', header: 'Device platform', labels: {
    en: { title: 'Set up this device', wifi: 'Manage a Wi-Fi connection',
      networkHelp: 'Keeping the connection leaves it under operating-system control.',
      success: 'Setup saved. Reopen the application at the current device address.' },
    bg: { title: 'Настройка на устройството', wifi: 'Управление на Wi-Fi връзка',
      networkHelp: 'Запазената връзка остава под управлението на операционната система.',
      success: 'Настройката е запазена. Отвори приложението на текущия адрес на устройството.' },
  } },
}

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Invalid product metadata')
  return value as Record<string, unknown>
}
function text(value: unknown, limit = 1024): string {
  if (typeof value !== 'string' || !value.trim() || value.length > limit || /[\u0000-\u001f\u007f]/.test(value)) {
    throw new Error('Invalid product text')
  }
  for (const character of value) {
    const code = character.codePointAt(0)!
    if (code >= 0xd800 && code <= 0xdfff) throw new Error('Invalid product text')
  }
  return value
}
function asset(value: unknown, empty = false): string {
  if (empty && value === '') return ''
  if (typeof value !== 'string' || value.length > 256 || !/^\/[A-Za-z0-9_./-]+$/.test(value) ||
      value.includes('//') || value.split('/').includes('..')) throw new Error('Invalid product asset path')
  return value
}

export function parseProductMetadata(value: unknown): ProductMetadata {
  try {
    const raw = object(value), setup = object(raw.setup), labels = object(setup.labels)
    if (raw.schema_version !== 1) throw new Error('Unsupported product metadata')
    const localized = (locale: 'en' | 'bg'): SetupLabels => {
      const row = object(labels[locale])
      return { title: text(row.title), wifi: text(row.wifi),
        networkHelp: text(row.networkHelp), success: text(row.success) }
    }
    return { schema_version: 1, name: text(raw.name, 128), display_name: text(raw.display_name, 256),
      welcome_message: text(raw.welcome_message), description: text(raw.description, 2048),
      default_logo_url: asset(raw.default_logo_url, true), favicon_url: asset(raw.favicon_url),
      setup: { page_title: text(setup.page_title, 256), header: text(setup.header, 256),
        labels: { en: localized('en'), bg: localized('bg') } } }
  } catch {
    return JSON.parse(JSON.stringify(fallback)) as ProductMetadata
  }
}

export const product = parseProductMetadata(source)

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;',
    '"': '&quot;', "'": '&#39;' })[char]!)
}

export function renderProductHead(html: string, metadata = product): string {
  return html.replace(/__PRODUCT_TITLE__|__PRODUCT_FAVICON__/g, token =>
    escapeHtml(token === '__PRODUCT_TITLE__' ? metadata.display_name : metadata.favicon_url))
}
