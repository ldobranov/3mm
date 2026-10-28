// Private Core transport for explicitly declared administrator reads.
import { resourceDiscovery, resourceScope } from './application-resources-host'
import { ApplicationHostError, type ApplicationAdministration, type ApplicationAdministrationRead,
  type ApplicationPayload, type ApplicationAdministrationAction, type ApplicationCapabilityInvocation, type ApplicationCommandReceipt, type ApplicationCommand, type ApplicationCapability, type ApplicationCapabilityState, type ApplicationModulePackage, type ApplicationDevice, type ApplicationDeviceDetail, type ApplicationHostInfo,
} from '../extension-ui/application-v1'

const object = (v: unknown): v is Record<string, unknown> => v !== null && typeof v === 'object' && !Array.isArray(v)
const nullableText = (v: unknown) => v === null || typeof v === 'string'
const DEVICE = /^dev_[a-f0-9]{32}$/
function invalid(): never { throw new ApplicationHostError('unavailable') }
function device(v: unknown): ApplicationDevice {
  if (!object(v) || typeof v.device_id !== 'string' || !DEVICE.test(v.device_id)
      || !nullableText(v.display_name) || typeof v.role !== 'string' || typeof v.protocol_version !== 'string'
      || typeof v.approved_at !== 'string' || !nullableText(v.revoked_at) || !nullableText(v.last_seen_at)
      || typeof v.online !== 'boolean' || (v.latest_inventory !== null
        && (!object(v.latest_inventory) || v.latest_inventory.schema_version !== 2))) invalid()
  // Only the documented projection crosses into the application, not extra server metadata.
  return { device_id: v.device_id, display_name: v.display_name, role: v.role,
    protocol_version: v.protocol_version, approved_at: v.approved_at, revoked_at: v.revoked_at,
    online: v.online, last_seen_at: v.last_seen_at,
    latest_inventory: structuredClone(v.latest_inventory) } as ApplicationDevice
}
export function createApplicationAdministration(context: {
  request(path: string, body?: unknown): Promise<unknown>; copyPayload(payload: ApplicationPayload): ApplicationPayload; getInfo(): Promise<ApplicationHostInfo>; live(): void
  ui: { entrypoint_id: string; artifact_sha256: string; built_ui_sha256?: string }
}): ApplicationAdministration {
  const root = `/ui-host/${encodeURIComponent(context.ui.entrypoint_id)}`
  const prefix = `${root}/devices`
  const identity = new URLSearchParams({ artifact_sha256: context.ui.artifact_sha256,
    built_ui_sha256: context.ui.built_ui_sha256 ?? '' })
  async function read(capability: ApplicationAdministrationRead, path: string, params = new URLSearchParams()) {
    context.live()
    if (!context.ui.built_ui_sha256) throw new ApplicationHostError('access_denied')
    const info = await context.getInfo()
    if (info.audience !== 'administrator' || !info.features.administration_reads?.includes(capability)) {
      throw new ApplicationHostError('access_denied')
    }
    return context.request(`${prefix}${path}?${identity}&${params}`)
  }
  const requestId = (id: string) => { if (typeof id !== 'string' || !/^[a-f0-9]{32}$/.test(id)) throw new ApplicationHostError('invalid_request') }
  const deviceId = (id: string) => { if (typeof id !== 'string' || !DEVICE.test(id)) throw new ApplicationHostError('invalid_request') }
  const capabilityId = (id: string) => { if (typeof id !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$/.test(id)) throw new ApplicationHostError('invalid_request') }
  async function allowed(name: ApplicationAdministrationRead | ApplicationAdministrationAction, write = false) {
    context.live()
    if (!context.ui.built_ui_sha256) throw new ApplicationHostError('access_denied')
    const info = await context.getInfo()
    const features: readonly string[] = (write ? info.features.administration_actions : info.features.administration_reads) ?? []
    if (info.audience !== 'administrator' || !features.includes(name)) throw new ApplicationHostError('access_denied')
  }
  async function get(name: ApplicationAdministrationRead, path: string) {
    await allowed(name)
    return context.request(`${root}${path}?${identity}`)
  }
  function receipt(value: unknown, expected: string): ApplicationCommandReceipt {
    if (!object(value) || value.request_id !== expected || typeof value.command_id !== 'string'
        || !/^cmd_[a-f0-9]{32}$/.test(value.command_id) || typeof value.device_id !== 'string'
        || !DEVICE.test(value.device_id) || typeof value.status !== 'string') invalid()
    return { request_id: expected, command_id: value.command_id, device_id: value.device_id, status: value.status }
  }
  async function send(name: ApplicationAdministrationAction, path: string, id: string, target: string, payload: ApplicationPayload) {
    requestId(id); deviceId(target)
    const copy = context.copyPayload(payload)
    await allowed(name, true)
    const value = await context.request(`${root}${path}`, { ...copy, artifact_sha256: context.ui.artifact_sha256,
      built_ui_sha256: context.ui.built_ui_sha256, request_id: id, device_id: target })
    try {
      const result = receipt(value, id)
      if (result.device_id !== target) throw new Error()
      return result
    } catch { throw new ApplicationHostError('unconfirmed') }
  }
  return Object.freeze({
    resources: Object.freeze({
      async inspect(scopes: readonly string[]) {
        if (!Array.isArray(scopes) || !scopes.length || scopes.length > 16
            || new Set(scopes).size !== scopes.length || !scopes.every(resourceScope)) throw new ApplicationHostError('invalid_request')
        const selection = [...scopes]
        await allowed('resources.inspect')
        const value = await context.request(`${root}/resources/inspect`, {scopes:selection,
          artifact_sha256:context.ui.artifact_sha256, built_ui_sha256:context.ui.built_ui_sha256})
        context.live()
        return resourceDiscovery(value, selection, context.ui.artifact_sha256)
      },
    }),
    modules: Object.freeze({
      async list(): Promise<readonly ApplicationModulePackage[]> {
        const value = await get('modules.list', '/module-packages')
        if (!Array.isArray(value) || value.length > 100) invalid()
        return value.map(item => {
          if (!object(item) || typeof item.module_id !== 'string' || typeof item.version !== 'string'
              || typeof item.sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(item.sha256) || typeof item.name !== 'string') invalid()
          return { module_id: item.module_id, version: item.version, sha256: item.sha256, name: item.name }
        })
      },
      install(target: string, sha: string, id: string) {
        if (typeof sha !== 'string' || !/^[a-f0-9]{64}$/.test(sha)) return Promise.reject(new ApplicationHostError('invalid_request'))
        return send('modules.install', '/modules/install', id, target, { package_sha256: sha })
      },
      disable(target: string, module: string, id: string) {
        if (typeof module !== 'string' || !/^[a-z0-9]+(?:[.-][a-z0-9]+)+$/.test(module)) return Promise.reject(new ApplicationHostError('invalid_request'))
        return send('modules.disable', '/modules/disable', id, target, { module_id: module })
      },
    }),
    capabilities: Object.freeze({
      async list(target: string): Promise<readonly ApplicationCapability[]> {
        deviceId(target)
        const value = await get('capabilities.list', `/devices/${target}/capabilities`)
        if (!Array.isArray(value) || value.length > 256) invalid()
        return value.map(item => {
          if (!object(item) || typeof item.capability_id !== 'string' || !nullableText(item.provider_type)
              || !nullableText(item.provider_id) || !nullableText(item.provider_version)
              || typeof item.registered !== 'boolean' || ![true, false, null].includes(item.available as boolean | null)
              || !nullableText(item.unavailable_reason) || !nullableText(item.declaration_digest)
              || !nullableText(item.contract_version) || !(item.contract === null || object(item.contract))) invalid()
          return { capability_id: item.capability_id, provider_type: item.provider_type, provider_id: item.provider_id,
            provider_version: item.provider_version, registered: item.registered, available: item.available,
            unavailable_reason: item.unavailable_reason, declaration_digest: item.declaration_digest,
            contract_version: item.contract_version, contract: structuredClone(item.contract) } as ApplicationCapability
        })
      },
      async state(target: string, capability: string): Promise<ApplicationCapabilityState> {
        deviceId(target); capabilityId(capability)
        const value = await get('capabilities.state', `/devices/${target}/capability-state/${encodeURIComponent(capability)}`)
        if (!object(value) || value.device_id !== target || value.capability_id !== capability || !object(value.values)
            || typeof value.observed_at !== 'string' || typeof value.received_at !== 'string') invalid()
        return { device_id: target, capability_id: capability, values: structuredClone(value.values),
          observed_at: value.observed_at, received_at: value.received_at } as ApplicationCapabilityState
      },
      invoke(target: string, input: ApplicationCapabilityInvocation, id: string) {
        capabilityId(input.capability_id)
        const payload = context.copyPayload(input as unknown as ApplicationPayload)
        return send('capabilities.invoke', '/capabilities/invoke', id, target, payload)
      },
    }),
    commands: Object.freeze({ async get(id: string): Promise<ApplicationCommand> {
      requestId(id)
      const value = await get('commands.get', `/commands/${id}`)
      const item = receipt(value, id)
      if (!object(value) || !(value.result === null || object(value.result)) || !nullableText(value.error)
          || typeof value.command_type !== 'string' || typeof value.created_at !== 'string' || typeof value.expires_at !== 'string') invalid()
      return { ...item, result: structuredClone(value.result), error: value.error, command_type: value.command_type,
        created_at: value.created_at, expires_at: value.expires_at } as ApplicationCommand
    } }),
    devices: Object.freeze({
    async list(options: { readonly offset?: number; readonly limit?: number } = {}) {
      const offset = options.offset ?? 0, limit = options.limit ?? 50
      if (!Number.isSafeInteger(offset) || offset < 0 || !Number.isSafeInteger(limit) || limit < 1 || limit > 100) {
        throw new ApplicationHostError('invalid_request')
      }
      const value = await read('devices.list', '', new URLSearchParams({ offset: String(offset), limit: String(limit) }))
      if (!object(value) || !Array.isArray(value.items) || value.items.length > limit
          || !Number.isSafeInteger(value.total) || (value.total as number) < value.items.length) invalid()
      return { items: value.items.map(device), total: value.total as number }
    },
    async detail(deviceId: string): Promise<ApplicationDeviceDetail> {
      if (typeof deviceId !== 'string' || !DEVICE.test(deviceId)) throw new ApplicationHostError('invalid_request')
      const value = await read('devices.detail', `/${encodeURIComponent(deviceId)}`)
      const item = device(value)
      if (item.device_id !== deviceId || !object(value) || !Array.isArray(value.modules)) invalid()
      const modules = value.modules.map(m => {
        if (!object(m) || typeof m.module_id !== 'string' || !nullableText(m.installed_version)
            || typeof m.desired_version !== 'string' || typeof m.status !== 'string'
            || typeof m.enabled !== 'boolean' || !nullableText(m.error)) invalid()
        return { module_id: m.module_id, installed_version: m.installed_version, desired_version: m.desired_version,
          status: m.status, enabled: m.enabled, error: m.error }
      })
      return { ...item, modules } as ApplicationDeviceDetail
    },
  }) })
}
