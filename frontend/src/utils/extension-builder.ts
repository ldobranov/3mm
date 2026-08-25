export type FrontendRoute = {
  path: string
  component: string
  name?: string
  meta?: Record<string, unknown>
  props?: boolean
}

export type ProviderEmbedderConfig = {
  label: string
  component: string
  format_api?: string
  ui_translations_api?: string
  description?: string
}

export type ProvidesConfig = {
  content_embedders?: Record<string, ProviderEmbedderConfig>
}

export type ConsumesConfig = {
  content_embedders?: Record<string, string[]>
}

export type CapabilityPresentationState = {
  state: 'value' | 'stale' | 'offline' | 'error'
  value?: string | number | boolean | null
  label: string
  color: string
}

export type CapabilityPlan = {
  schema_version: 1
  target: 'dashboard_widget' | 'application_page'
  settings: Array<{
    key: string
    label: string
    kind: string
    required?: boolean
    default?: string | number | boolean | null
    options?: Array<string | number | boolean>
  }>
  bindings: Array<{
    alias: string
    capability_id: string
    operation: string
    action?: string | null
    device_setting: string
    channel_setting?: string | null
    permissions: string[]
    stale_after_seconds: number
  }>
  presentations: Array<{
    kind: 'indicator' | 'metric' | 'text' | 'list' | 'chart' | 'form'
    source_binding?: string | null
    states: CapabilityPresentationState[]
  }>
}

export type ExtensionSpec = {
  name: string
  version: string
  type: 'extension' | 'widget'
  description: string
  author: string
  api_prefix: string
  backend_entry: string
  frontend_entry: string
  frontend_components: string[]
  frontend_routes: FrontendRoute[]
  locales: { supported: string[]; default: string; directory: string }
  permissions: string[]
  public_endpoints: string[]
  dependencies: Record<string, unknown>
  config_schema: Record<string, unknown>
  capability_plan?: CapabilityPlan | null
  provides?: ProvidesConfig
  consumes?: ConsumesConfig
  goal?: string
}

export type BuildReport = {
  extension_id: string
  files: string[]
  warnings: Array<{ code: string; message: string }>
}

export type ClarifyQuestion = {
  id: string
  question: string
  suggestions: string[]
}

export type ExtensionIntentPlan = {
  project_type: 'extension' | 'widget'
  template_key: 'simple' | 'crud'
  package_kind: 'compiled' | 'legacy'
  needs_database: boolean
  config_schema: Record<string, unknown>
  capability_plan?: CapabilityPlan | null
  summary: string
  assumptions: string[]
  questions: ClarifyQuestion[]
}

export type BuilderCapability = {
  device_id: string
  device_name: string
  device_role: string
  capability_id: string
  module_id: string
  module_version: string
  metadata: Record<string, string | number | boolean>
}

export type CrudFieldType = 'text' | 'int' | 'bool' | 'json' | 'timestamp'

export type CrudField = {
  name: string
  type: CrudFieldType
  required: boolean
  translatable: boolean
}

export type CrudEntityModel = {
  table: string
  entityName: string
  fields: CrudField[]
}

export type ProviderEmbedder = {
  typeKey: string
  label: string
  component: string
  format_api?: string
  ui_translations_api?: string
  description?: string
}

export type ConsumerEmbedder = {
  typeKey: string
  providersCsv: string
}

export const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null

export const getHttpErrorMessage = (error: unknown): string => {
  if (isRecord(error)) {
    const response = error.response
    if (isRecord(response)) {
      const data = response.data
      if (isRecord(data) && 'detail' in data) {
        const detail = data.detail
        if (typeof detail === 'string') return detail
        try {
          return JSON.stringify(detail, null, 2)
        } catch {
          return String(detail)
        }
      }
    }
    if (typeof error.message === 'string') return error.message
  }
  return String(error)
}

export const deriveExtensionNamespace = (name: string): string => {
  const base = (name || '').replace(/Extension$/i, '').trim() || name
  return base.toLowerCase().replace(/[^a-z0-9]/g, '')
}

export const extensionNameToSnakeCase = (name: string): string => {
  const value = (name || '')
    .replace(/Extension$/i, '')
    .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
    .replace(/\W+/g, '_')
    .toLowerCase()
    .replace(/^_+|_+$/g, '')
  return value || 'my_extension'
}

export const createInitialExtensionSpec = (): ExtensionSpec => ({
  name: 'MyExtension',
  version: '0.0.0',
  type: 'extension',
  description: 'AI generated extension',
  author: 'AI',
  api_prefix: '/api/my',
  backend_entry: 'my_extension.py',
  frontend_entry: 'MyExtension.vue',
  frontend_components: [],
  frontend_routes: [
    {
      path: '/my',
      component: 'MyExtension.vue',
      name: 'MyExtension',
      meta: { requiresAuth: true }
    }
  ],
  locales: { supported: ['en', 'bg'], default: 'en', directory: 'locales/' },
  permissions: [],
  public_endpoints: [],
  dependencies: {},
  config_schema: {},
  goal: ''
})

export const createGuidedProjectName = (name: string, description: string): string => {
  const source = name.trim() || description.trim().split(/\s+/).slice(0, 3).join(' ')
  const words = source.match(/[A-Za-z0-9]+/g) || []
  const result = words.map(word => `${word.charAt(0).toUpperCase()}${word.slice(1)}`).join('')
  return result || 'GeneratedExtension'
}

export const capabilityChannels = (capability: BuilderCapability): string[] => String(
  capability.metadata.automation_channels || ''
).split(',').map(value => value.trim()).filter(Boolean)

export const createCapabilityConfigSchema = (
  plan: CapabilityPlan,
  matchingCapabilities: BuilderCapability[]
): Record<string, unknown> => {
  const devices = Array.from(new Map(
    matchingCapabilities.map(item => [item.device_id, item])
  ).values())
  const channels = Array.from(new Set(matchingCapabilities.flatMap(capabilityChannels)))
  const properties: Record<string, Record<string, unknown>> = {}

  for (const setting of plan.settings) {
    const item: Record<string, unknown> = {
      title: setting.label,
      type: setting.kind === 'boolean' ? 'boolean' : setting.kind === 'number' ? 'number' : 'string'
    }
    if (setting.kind === 'color') item.format = 'color'
    if (setting.kind === 'device') {
      item.format = 'device'
      item.enum = devices.map(device => device.device_id)
      item.enumNames = devices.map(device => device.device_name)
      if (devices.length) item.default = devices[0].device_id
    } else if (setting.kind === 'capability_channel') {
      item.format = 'capability-channel'
      item.enum = channels
      if (channels.length) item.default = channels[0]
    } else if (setting.options?.length) {
      item.enum = setting.options
    }
    if (setting.default !== undefined && setting.default !== null) item.default = setting.default
    properties[setting.key] = item
  }

  return { type: 'object', properties }
}

export const routeRequiresAuth = (route: FrontendRoute): boolean =>
  Boolean(route?.meta?.requiresAuth)

export const setRouteRequiresAuth = (route: FrontendRoute, value: boolean): void => {
  const current = route.meta && typeof route.meta === 'object' ? route.meta : {}
  route.meta = { ...current, requiresAuth: value }
}

export const createManifestPreview = (spec: ExtensionSpec): Record<string, unknown> => {
  const localesDirectory = spec.locales?.directory || 'locales/'
  const normalizedLocalesDirectory = localesDirectory.endsWith('/')
    ? localesDirectory
    : `${localesDirectory}/`
  const manifest: Record<string, unknown> = {
    name: spec.name,
    version: spec.version,
    type: spec.type,
    description: spec.description,
    author: spec.author,
    backend_entry: spec.backend_entry,
    frontend_entry: spec.frontend_entry,
    frontend_components: spec.frontend_components,
    frontend_routes: spec.frontend_routes,
    locales: {
      supported: spec.locales?.supported || ['en', 'bg'],
      default: spec.locales?.default || 'en',
      directory: normalizedLocalesDirectory
    },
    permissions: spec.permissions,
    public_endpoints: spec.public_endpoints,
    dependencies: spec.dependencies
  }

  if (spec.provides) manifest.provides = spec.provides
  if (spec.consumes) manifest.consumes = spec.consumes
  return manifest
}

export const createZipPathsPreview = (spec: ExtensionSpec): string[] => {
  const localesDirectory = spec.locales?.directory || 'locales/'
  const normalizedLocalesDirectory = localesDirectory.endsWith('/')
    ? localesDirectory
    : `${localesDirectory}/`
  const languages = spec.locales?.supported || ['en', 'bg']
  const localeFiles = languages.map(language => `${normalizedLocalesDirectory}${language}.json`)
  const providedComponents: string[] = []

  const contentEmbedders = spec.provides?.content_embedders
  if (contentEmbedders) {
    for (const config of Object.values(contentEmbedders)) {
      const component = config.component
      if (typeof component === 'string' && component.trim()) {
        const file = component.endsWith('.vue') ? component : `${component}.vue`
        providedComponents.push(`frontend/${file}`)
      }
    }
  }

  return [
    'manifest.json',
    `backend/${spec.backend_entry}`,
    `frontend/${spec.frontend_entry}`,
    ...providedComponents,
    ...localeFiles
  ]
}

export const createCrudDefaultTable = (extensionName: string): string => {
  const namespace = deriveExtensionNamespace(extensionName)
  return `ext_${namespace || 'my'}_items`
}

export const createCrudEntityGoalBlock = (
  spec: ExtensionSpec,
  model: CrudEntityModel,
  title: string
): string => {
  const namespace = deriveExtensionNamespace(spec.name)
  const entity = (model.entityName || 'items').trim()
  const table = (model.table || createCrudDefaultTable(spec.name)).trim()
  const fields = (model.fields || [])
    .filter(field => (field.name || '').trim())
    .map(field => {
      const flags = [
        field.required ? 'required' : 'optional',
        field.translatable ? 'translatable' : 'not translatable'
      ]
      return `- ${field.name.trim()}: ${field.type} (${flags.join(', ')})`
    })
    .join('\n')
  const translatableFields = (model.fields || [])
    .filter(field => (field.name || '').trim() && field.translatable)
    .map(field => field.name.trim())
  const translationsNote = translatableFields.length
    ? `Translatable fields: ${translatableFields.join(', ')}. Use an extension translations table (e.g. ext_${namespace || 'my'}_translations with (record_id, language_code, translation_data JSONB) UNIQUE) and merge translations on reads.`
    : 'No translatable fields.'

  return (
    `${title}\n` +
    `Entity: ${entity}\n` +
    `Main table: ${table} (PostgreSQL, lowercase)\n` +
    `Fields:\n${fields || '- (none)'}\n\n` +
    'API:\n' +
    `- GET ${spec.api_prefix}/${entity} (list)\n` +
    `- POST ${spec.api_prefix}/${entity} (create)\n` +
    `- PUT ${spec.api_prefix}/${entity}/{id} (update)\n` +
    `- DELETE ${spec.api_prefix}/${entity}/{id} (delete)\n` +
    'Auth: protect endpoints with require_user.\n' +
    translationsNote
  )
}
