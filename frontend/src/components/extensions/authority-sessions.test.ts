import { describe, expect, it } from 'vitest'
import { readAuthorityPlan, readAuthorityStatus } from './authority-management'
import { sessionModuleId, sessionOwner, sessionPlan, sessionScope, sessionStatus } from './authority-sessions.fixtures'

describe('M20 session review DTO boundary', () => {
  it('keeps all exact requests visible with empty or selected scopes', () => {
    const status = readAuthorityStatus(sessionStatus())
    for (const scopes of [[], [sessionScope]]) {
      const plan = readAuthorityPlan(sessionPlan(scopes), status, sessionModuleId, scopes)
      expect(plan.resources.sessions).toHaveLength(1)
      expect(plan.scopes).toEqual(scopes)
    }
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
