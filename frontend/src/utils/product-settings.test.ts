import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { product } from './product'

const api = vi.hoisted(() => ({ readSettings: vi.fn(), upsertSettings: vi.fn() }))
vi.mock('@/utils/settings-api', () => api)
vi.mock('@/utils/dynamic-http', () => ({ default: { getCurrentBackendUrl: async () => '' } }))
vi.mock('@/utils/i18n', () => ({ useI18n: () => ({ currentLanguage: { value: 'bg' } }) }))
import { useSettingsStore } from '@/stores/settings'

const oldTitle = document.title
beforeEach(() => { localStorage.clear(); setActivePinia(createPinia()); vi.clearAllMocks() })
afterEach(() => { document.title = oldTitle })

it('keeps localized saved branding above product defaults without writing settings', async () => {
  const records = [
    { key: 'site_name', value: 'Custom <site>', language_code: 'bg' },
    { key: 'site_name', value: 'English site', language_code: 'en' },
    { key: 'header_message', value: 'Запазен поздрав', language_code: 'bg' },
    { key: 'logo_url', value: '/uploads/settings/saved.svg', language_code: null },
  ]
  api.readSettings.mockResolvedValue(records)
  const settings = useSettingsStore()
  expect(document.title).toBe(product.display_name)
  await settings.loadSettings()
  await nextTick()
  expect(settings.headerSettings.siteName).toBe('Custom <site>')
  expect(settings.headerSettings.headerMessage).toBe('Запазен поздрав')
  expect(settings.brandingLogo).toBe('/uploads/settings/saved.svg')
  expect(document.title).toBe('Custom <site>')
  expect(document.querySelector('site')).toBeNull()
  expect(api.upsertSettings).not.toHaveBeenCalled()
  settings.$dispose()
})
