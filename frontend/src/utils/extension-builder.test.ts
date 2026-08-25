import { describe, expect, it } from 'vitest'

import {
  capabilityChannels,
  createCapabilityConfigSchema,
  createCrudEntityGoalBlock,
  createGuidedProjectName,
  createInitialExtensionSpec,
  createManifestPreview,
  createZipPathsPreview,
  deriveExtensionNamespace,
  extensionNameToSnakeCase,
  getHttpErrorMessage,
  routeRequiresAuth,
  setRouteRequiresAuth,
  type BuilderCapability,
  type CapabilityPlan
} from './extension-builder'

const capability = (overrides: Partial<BuilderCapability> = {}): BuilderCapability => ({
  device_id: 'device-1',
  device_name: 'Raspberry Pi',
  device_role: 'agent',
  capability_id: 'gpio.input',
  module_id: 'builtin.gpio',
  module_version: '1.0.0',
  metadata: { automation_channels: 'gpio.input.1, gpio.input.2' },
  ...overrides
})

describe('extension builder model', () => {
  it('creates independent defaults and stable generated identifiers', () => {
    const first = createInitialExtensionSpec()
    const second = createInitialExtensionSpec()
    first.frontend_routes[0].path = '/changed'

    expect(second.frontend_routes[0].path).toBe('/my')
    expect(deriveExtensionNamespace('Store Extension')).toBe('store')
    expect(extensionNameToSnakeCase('GPIOStatusExtension')).toBe('gpiostatus')
    expect(createGuidedProjectName('', 'status light widget for GPIO')).toBe('StatusLightWidget')
  })

  it('extracts useful backend errors without depending on the HTTP client', () => {
    expect(getHttpErrorMessage({ response: { data: { detail: 'Build failed' } } })).toBe('Build failed')
    expect(getHttpErrorMessage({ response: { data: { detail: [{ field: 'name' }] } } }))
      .toContain('"field": "name"')
    expect(getHttpErrorMessage(new Error('Network unavailable'))).toBe('Network unavailable')
  })

  it('normalizes capability channels and builds the settings schema', () => {
    const plan: CapabilityPlan = {
      schema_version: 1,
      target: 'dashboard_widget',
      settings: [
        { key: 'device', label: 'Device', kind: 'device' },
        { key: 'pin', label: 'Input', kind: 'capability_channel' },
        { key: 'color', label: 'Active color', kind: 'color', default: '#22c55e' }
      ],
      bindings: [],
      presentations: []
    }
    const available = [capability(), capability({ device_id: 'device-2', device_name: 'Second Pi' })]

    expect(capabilityChannels(available[0])).toEqual(['gpio.input.1', 'gpio.input.2'])
    expect(createCapabilityConfigSchema(plan, available)).toEqual({
      type: 'object',
      properties: {
        device: {
          title: 'Device', type: 'string', format: 'device',
          enum: ['device-1', 'device-2'], enumNames: ['Raspberry Pi', 'Second Pi'], default: 'device-1'
        },
        pin: {
          title: 'Input', type: 'string', format: 'capability-channel',
          enum: ['gpio.input.1', 'gpio.input.2'], default: 'gpio.input.1'
        },
        color: { title: 'Active color', type: 'string', format: 'color', default: '#22c55e' }
      }
    })
  })

  it('keeps route authentication metadata while toggling it', () => {
    const route = { path: '/clock', component: 'Clock.vue', meta: { title: 'Clock' } }
    expect(routeRequiresAuth(route)).toBe(false)
    setRouteRequiresAuth(route, true)
    expect(route.meta).toEqual({ title: 'Clock', requiresAuth: true })
  })

  it('creates consistent manifest and package previews', () => {
    const spec = createInitialExtensionSpec()
    spec.locales.directory = 'translations'
    spec.provides = {
      content_embedders: {
        item: { label: 'Item', component: 'ItemPicker' }
      }
    }

    expect(createManifestPreview(spec)).toMatchObject({
      name: 'MyExtension',
      locales: { directory: 'translations/' },
      provides: spec.provides
    })
    expect(createZipPathsPreview(spec)).toEqual([
      'manifest.json',
      'backend/my_extension.py',
      'frontend/MyExtension.vue',
      'frontend/ItemPicker.vue',
      'translations/en.json',
      'translations/bg.json'
    ])
  })

  it('renders CRUD requirements from the structured model', () => {
    const spec = createInitialExtensionSpec()
    spec.name = 'ClockExtension'
    spec.api_prefix = '/api/clock'
    const goal = createCrudEntityGoalBlock(spec, {
      table: '',
      entityName: 'settings',
      fields: [
        { name: 'timezone', type: 'text', required: true, translatable: false },
        { name: 'label', type: 'text', required: false, translatable: true }
      ]
    }, 'CRUD Data Model')

    expect(goal).toContain('Main table: ext_clock_items')
    expect(goal).toContain('GET /api/clock/settings')
    expect(goal).toContain('Translatable fields: label.')
  })
})
