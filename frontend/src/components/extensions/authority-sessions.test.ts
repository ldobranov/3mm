import { describe, expect, it } from 'vitest'
import { readAuthorityPlan, readAuthorityStatus } from './authority-management'
import { hostSessionAccount, sessionModuleId, sessionOwner, sessionPlan, sessionScope, sessionStatus } from './authority-sessions.fixtures'

describe('M20 session review DTO boundary', () => {
  it('keeps all exact requests visible with empty or selected scopes', () => {
    const status = readAuthorityStatus(sessionStatus())
    for (const scopes of [[], [sessionScope]]) {
      const plan = readAuthorityPlan(sessionPlan(scopes), status, sessionModuleId, scopes)
      expect(plan.resources.sessions).toHaveLength(1)
      expect(plan.scopes).toEqual(scopes)
    }
  })
  it('accepts only the explicit host-account profile without changing isolated session resources', () => {
    const status = readAuthorityStatus(sessionStatus())
    const isolated = sessionPlan() as any
    isolated.resources.sessions[0].host_account = null
    expect(readAuthorityPlan(isolated, status, sessionModuleId).resources.sessions![0]!.host_account).toBeNull()
    const host = sessionPlan() as any
    host.resources.sessions[0].declaration.provider_id = sessionModuleId
    host.resources.sessions[0].host_account = hostSessionAccount()
    expect(readAuthorityPlan(host, status, sessionModuleId).resources.sessions![0]!.host_account).toEqual(hostSessionAccount())
  })
  it.each([
    { account: 'root' }, { account: 'raspberry' }, { uid: 0 }, { gid: 0 }, { uid: true }, { uid: '993' },
    { gid: -1 }, { uid: 1.5 }, { uid: 4294967295 }, { home: '/root' }, { policy_sha256: 'invalid' },
    { resource_profile: 'isolated_session_v1' }, { executable: '/bin/sh' },
  ])('refuses invalid host-account policy metadata %j', changed => {
    const host = sessionPlan() as any
    host.resources.sessions[0].declaration.provider_id = sessionModuleId
    host.resources.sessions[0].host_account = { ...hostSessionAccount(), ...changed }
    expect(() => readAuthorityPlan(host, readAuthorityStatus(sessionStatus()), sessionModuleId)).toThrow()
  })
  it('refuses incomplete host metadata and a host account for a different provider', () => {
    const host = sessionPlan() as any
    host.resources.sessions[0].host_account = hostSessionAccount()
    expect(() => readAuthorityPlan(host, readAuthorityStatus(sessionStatus()), sessionModuleId)).toThrow()
    host.resources.sessions[0].declaration.provider_id = sessionModuleId
    delete host.resources.sessions[0].host_account.policy_sha256
    expect(() => readAuthorityPlan(host, readAuthorityStatus(sessionStatus()), sessionModuleId)).toThrow()
  })
  it.each(['missing', 'extra', 'owner', 'artifact', 'control', 'profile', 'options', 'device', 'permission', 'duplicate'])('rejects %s resource mismatch', kind => {
    const plan = sessionPlan() as any, resource = plan.resources.sessions[0]
    if (kind === 'missing') plan.resources.sessions = []
    if (kind === 'extra') resource.secret = 'MUST_NOT_RENDER'
    if (kind === 'owner') resource.owner.incarnation = '0'.repeat(32)
    if (kind === 'owner') plan.resources.checkpoints = [{ declaration: { contract_version: 1, checkpoint_id: 'progress', mode: 'read', max_value_bytes: 128 }, owner: sessionOwner(), package_artifact_sha256: 'a'.repeat(64), operation: 'read' }]
    if (kind === 'artifact') resource.package_artifact_sha256 = '0'.repeat(64)
    if (kind === 'control') resource.declaration.control_actions = ['delete']
    if (kind === 'profile') resource.contract.contract_version = '1'
    if (kind === 'options') resource.declaration.options = { text: 'x'.repeat(8192) }
    if (kind === 'device') resource.target_device_id = 'dev_1'
    if (kind === 'permission') resource.declaration.required_permission = '*'
    if (kind === 'duplicate') plan.resources.sessions.push(resource)
    const status = sessionStatus()
    if (kind === 'owner') { status.scopes.push('checkpoint:progress:read'); plan.scopes.push('checkpoint:progress:read') }
    expect(() => readAuthorityPlan(plan, readAuthorityStatus(status), sessionModuleId)).toThrow()
  })
  it('never accepts widened selections or silent omission of required older scopes', () => {
    const status = readAuthorityStatus(sessionStatus())
    expect(() => readAuthorityPlan(sessionPlan([sessionScope]), status, sessionModuleId, [])).toThrow()
    expect(() => readAuthorityPlan(sessionPlan(), { ...status, scopes: [...status.scopes, 'command:required'] })).toThrow()
  })
  it('supports mixed runtime blockers, rejects duplicate or effective blocked status', () => {
    const status = { ...sessionStatus(), scopes: [sessionScope, 'storage:relational_read'], runtime_blockers: ['session_runtime_not_connected', 'relational_runtime_unavailable'] }
    expect(readAuthorityStatus(status)).toEqual(status)
    expect(() => readAuthorityStatus({ ...status, grant_effective: true })).toThrow()
    expect(() => readAuthorityStatus({ ...status, runtime_blockers: ['session_runtime_not_connected', 'session_runtime_not_connected'] })).toThrow()
  })
})
