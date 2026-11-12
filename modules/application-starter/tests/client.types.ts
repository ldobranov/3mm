// Compile-only regression: common check runs these against the actual public host.
import type { ApplicationHost } from '@platform/application-ui/v1'
import { createApplicationClient } from '../source/frontend/client.generated'

export function checkClientTypes(host: Pick<ApplicationHost, 'invoke'>) {
  const client = createApplicationClient(host)
  const note: Promise<{ text: string; revision: number }> = client.read_note({})
  const receipt: Promise<{ status: 'found' | 'not_found'; revision: number | null }> =
    client.lookup_save({ request_id: 'a'.repeat(32) })
  void note; void receipt
  void client.save_note({ text: 'Explicit edit', revision: 0 }, { idempotencyKey: 'a'.repeat(32) })
  // @ts-expect-error Internal health is not exposed by the UI client.
  client.health({})
  // @ts-expect-error Commands require the caller-owned original identity.
  client.save_note({ text: 'No key', revision: 0 })
  // @ts-expect-error An integer-shaped field is still a number, not text.
  client.save_note({ text: 'Wrong revision', revision: '0' }, { idempotencyKey: 'a' })
  // @ts-expect-error Nullable lookup output does not make save revision nullable.
  client.save_note({ text: 'Wrong revision', revision: null }, { idempotencyKey: 'a' })
  // @ts-expect-error Queries cannot receive command dispatch options.
  client.read_note({}, { idempotencyKey: 'a' })
  // @ts-expect-error Undeclared literal properties are rejected.
  client.read_note({ unexpected: true })
}
