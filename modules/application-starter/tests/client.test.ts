import { describe, expect, it, vi } from 'vitest'
import { ApplicationHostError } from '@platform/application-ui/v1'
import { createApplicationClient } from '../source/frontend/client.generated'

describe('generated public-host client', () => {
  it('forwards the exact original identity once and returns the host result', async () => {
    const result = { text: 'Saved', revision: 1 }
    const invoke = vi.fn().mockResolvedValue(result)
    const client = createApplicationClient({ invoke })
    const payload = { text: 'Saved', revision: 0 }
    expect(await client.save_note(payload, { idempotencyKey: 'a'.repeat(32) })).toBe(result)
    expect(invoke.mock.calls).toEqual([['save_note', payload, { idempotencyKey: 'a'.repeat(32) }]])
    expect('health' in client).toBe(false)
  })

  it.each(['unconfirmed', 'access_denied'] as const)('does not reinterpret or retry %s', async code => {
    const failure = new ApplicationHostError(code, 'original-request')
    const invoke = vi.fn().mockRejectedValue(failure)
    const client = createApplicationClient({ invoke })
    await expect(client.save_note({ text: 'Draft', revision: 0 }, { idempotencyKey: 'a'.repeat(32) })).rejects.toBe(failure)
    expect(invoke).toHaveBeenCalledTimes(1)
  })

  it('reads without creating a command identity', async () => {
    const invoke = vi.fn().mockResolvedValue({ text: 'Saved', revision: 1 })
    await createApplicationClient({ invoke }).read_note({})
    expect(invoke.mock.calls).toEqual([['read_note', {}]])
  })
})
