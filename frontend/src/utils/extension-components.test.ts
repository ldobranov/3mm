import { describe, expect, it, vi } from 'vitest'

vi.mock('@/utils/dynamic-http', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn()
  }
}))
import {
  extensionComponentKey,
  loadBundledExtensionComponent,
  normalizeExtensionComponentPath
} from './extension-components'

describe('extension component paths', () => {
  it('builds a bundled key from manifest fields', () => {
    expect(extensionComponentKey('Clock', '1.2.3', 'ClockWidget')).toBe(
      '../extensions/Clock_1.2.3/ClockWidget.vue'
    )
  })

  it('normalizes supported legacy source paths', () => {
    expect(normalizeExtensionComponentPath('@/extensions/Clock_1.0.0/ClockWidget.vue')).toBe(
      '../extensions/Clock_1.0.0/ClockWidget.vue'
    )
    expect(normalizeExtensionComponentPath('/src/extensions/Clock_1.0.0/ClockWidget.vue')).toBe(
      '../extensions/Clock_1.0.0/ClockWidget.vue'
    )
  })

  it('rejects non-extension and traversal paths', () => {
    expect(normalizeExtensionComponentPath('@/components/Menu.vue')).toBeNull()
    expect(normalizeExtensionComponentPath('/src/extensions/Clock_1.0.0/../Menu.vue')).toBeNull()
  })

  it('loads a component included in the production bundle', async () => {
    await expect(
      loadBundledExtensionComponent(
        'MultilingualClockWidget',
        '1.0.0',
        'MultilingualClockWidget.vue'
      )
    ).resolves.toBeTruthy()
  })
})
