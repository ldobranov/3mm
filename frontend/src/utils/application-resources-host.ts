import { ApplicationHostError, type ApplicationResourceDiscovery, type ApplicationResourceObservation } from '../extension-ui/application-v1'
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v)
const keys = (v: Record<string, unknown>, names: readonly string[]) => Object.keys(v).length === names.length && Object.keys(v).every(k => names.includes(k))
const nullableText = (v: unknown, length: number) => v === null || (typeof v === 'string' && v.length <= length)
export const resourceScope = (v: unknown): v is string => typeof v === 'string' && /^[a-z][a-z0-9_.:-]{0,191}$/.test(v)
function invalid(): never { throw new ApplicationHostError('unavailable') }
export function resourceDiscovery(v: unknown, scopes: readonly string[], artifact: string): ApplicationResourceDiscovery {
  if (!object(v) || !keys(v, ['discovery_version','instance_id','artifact_sha256','observed_at','resources','admission_required'])
      || v.discovery_version !== 1 || v.admission_required !== true || v.artifact_sha256 !== artifact
      || typeof v.instance_id !== 'string' || !/^[a-f0-9]{24}$/.test(v.instance_id)
      || typeof v.observed_at !== 'string' || !/(Z|[+-]\d\d:\d\d)$/.test(v.observed_at) || !Number.isFinite(Date.parse(v.observed_at))
      || !Array.isArray(v.resources) || v.resources.length !== scopes.length) invalid()
  const resources = v.resources.map((row, index): ApplicationResourceObservation => {
    if (!object(row) || !keys(row, ['scope','required','declared','configured','access','readiness','reasons','provider','selected_resource_id'])
        || typeof row.required !== 'boolean'
        || row.scope !== scopes[index] || ![true,false,null].includes(row.declared as boolean | null)
        || ![true,false,null].includes(row.configured as boolean | null)
        || !['not_evaluated','required','granted'].includes(String(row.access))
        || !['not_evaluated','unknown','unavailable','ready'].includes(String(row.readiness))
        || !Array.isArray(row.reasons) || row.reasons.length > 8
        || row.reasons.some(reason => typeof reason !== 'string' || !/^[a-z][a-z0-9_]{0,95}$/.test(reason))
        || !nullableText(row.selected_resource_id, 160)) invalid()
    if (row.access !== 'granted' && (row.provider !== null || row.selected_resource_id !== null
        || row.configured !== null || row.readiness !== 'not_evaluated')) invalid()
    if (row.access === 'granted' && row.declared !== true) invalid()
    if (row.readiness === 'ready' && (row.configured !== true || row.reasons.length)) invalid()
    if (['unknown','unavailable'].includes(String(row.readiness)) && !row.reasons.length) invalid()
    let provider: ApplicationResourceObservation['provider'] = null
    if (row.provider !== null) {
      const p = row.provider
      if (!object(p) || !keys(p, ['provider_type','provider_id','provider_version','contract_version'])
          || typeof p.provider_type !== 'string' || !p.provider_type.length || p.provider_type.length > 64
          || typeof p.provider_id !== 'string' || !p.provider_id.length || p.provider_id.length > 160
          || !nullableText(p.provider_version,64) || !nullableText(p.contract_version,32)) invalid()
      provider = Object.freeze({provider_type:p.provider_type, provider_id:p.provider_id,
        provider_version:p.provider_version, contract_version:p.contract_version}) as ApplicationResourceObservation['provider']
    }
    return Object.freeze({scope:scopes[index]!, required:row.required, declared:row.declared, configured:row.configured,
      access:row.access, readiness:row.readiness, reasons:Object.freeze([...row.reasons]), provider,
      selected_resource_id:row.selected_resource_id}) as ApplicationResourceObservation
  })
  return Object.freeze({discovery_version:1, instance_id:v.instance_id, artifact_sha256:artifact,
    observed_at:v.observed_at, resources:Object.freeze(resources), admission_required:true})
}
