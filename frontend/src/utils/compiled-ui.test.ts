import { beforeEach, describe, expect, it, vi } from 'vitest'

import http from '@/utils/dynamic-http'
import { compiledWidgetType, findCompiledEntrypoint, getCompiledUiCatalog } from './compiled-ui'

vi.mock('@/utils/dynamic-http', () => ({
  default: { get: vi.fn(), getCurrentBackendUrl: vi.fn() },
}))

const clockPackage = {
  module_id: 'org.3mm.clock',
  name: 'Digital Clock',
  version: '1.0.0',
  source_sha256: 'a'.repeat(64),
  styles: ['/compiled/clock.css'],
  entrypoints: [{
    entrypoint_id: 'clock',
    kind: 'widget' as const,
    source: 'source/frontend/Clock.vue',
    label: { en: 'Digital Clock' },
    asset_url: '/compiled/clock.mjs',
  }],
}

describe('compiled UI catalog', () => {
  beforeEach(() => {
    vi.mocked(http.get).mockResolvedValue({ data: { items: [clockPackage] } })
    vi.mocked(http.getCurrentBackendUrl).mockResolvedValue('http://device.test:8887')
  })

  it('uses an immutable package version in persisted widget types', () => {
    expect(compiledWidgetType(clockPackage, clockPackage.entrypoints[0])).toBe(
      'compiled:org.3mm.clock:1.0.0:clock'
    )
  })

  it('resolves a widget entrypoint from catalog metadata', async () => {
    await getCompiledUiCatalog(true)
    const resolved = await findCompiledEntrypoint('compiled:org.3mm.clock:1.0.0:clock')
    expect(resolved?.pkg.source_sha256).toBe('a'.repeat(64))
    expect(resolved?.entrypoint.asset_url).toBe('http://device.test:8887/compiled/clock.mjs')
  })

  it('rejects malformed and unknown widget types', async () => {
    await getCompiledUiCatalog(true)
    await expect(findCompiledEntrypoint('compiled:broken')).resolves.toBeNull()
    await expect(findCompiledEntrypoint('compiled:org.3mm.clock:2.0.0:clock')).resolves.toBeNull()
  })
})
