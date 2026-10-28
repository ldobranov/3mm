import { describe, expect, it, vi } from 'vitest'

vi.mock('@/utils/dynamic-http', () => ({
  default: { get: vi.fn() },
}))
import {
  buildRuntimeRouteRecords,
  localizedText,
  type RuntimeDefinitionResponse,
} from './runtime-extensions'

const response: RuntimeDefinitionResponse = {
  module_id: 'org.3mm.contacts',
  version: '1.0.0',
  enabled: true,
  definition: {
    runtime_extension_version: 1,
    module_id: 'org.3mm.contacts',
    version: '1.0.0',
    name: { en: 'Contacts' },
    description: { en: 'Manage contacts' },
    entities: [{ entity_id: 'contact', label: { en: 'Contact' }, fields: [] }],
    pages: [{
      page_id: 'contacts', path: '/contacts', title: { en: 'Contacts' },
      entity_id: 'contact', view: 'table', actions: ['read'], requires_role: 'admin',
    }],
    navigation: [{
      navigation_id: 'contacts_menu', page_id: 'contacts',
      label: { en: 'Contacts', translations: { bg: 'Контакти' } }, order: 20,
    }],
    permissions: ['runtime.data.read'],
  },
}

describe('runtime extension routes', () => {
  it('creates a generic authenticated route with data-driven navigation', () => {
    const route = buildRuntimeRouteRecords([response])[0]
    expect(route.path).toBe('/contacts')
    expect(route.props).toEqual({ moduleId: 'org.3mm.contacts', pageId: 'contacts' })
    expect(route.meta).toMatchObject({
      requiresAuth: true,
      requiresRole: 'admin',
      menuLabel: { en: 'Contacts', bg: 'Контакти' },
      isRuntimeExtensionRoute: true,
    })
  })

  it('uses English when the requested translation is unavailable', () => {
    expect(localizedText(response.definition.name, 'bg')).toBe('Contacts')
  })
})
