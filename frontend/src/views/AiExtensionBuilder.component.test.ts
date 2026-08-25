import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const http = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn()
}))

const projectApi = vi.hoisted(() => ({
  createExtensionProject: vi.fn(),
  createExtensionProjectBuild: vi.fn(),
  downloadExtensionProjectBuild: vi.fn(),
  listExtensionProjectBuilds: vi.fn(),
  listExtensionProjects: vi.fn(),
  markExtensionProjectBuildInstalled: vi.fn(),
  readExtensionProject: vi.fn(),
  readNextProjectVersion: vi.fn(),
  proposeExtensionProjectModification: vi.fn(),
  replaceExtensionProjectFiles: vi.fn(),
  updateExtensionProject: vi.fn()
}))

vi.mock('@/utils/dynamic-http', () => ({ default: http }))
vi.mock('@/utils/extension-projects', () => projectApi)
vi.mock('@/stores/settings', () => ({
  useSettingsStore: () => ({
    styleSettings: {
      cardBg: '#fff',
      textPrimary: '#111',
      cardBorder: '#ddd'
    }
  })
}))
vi.mock('@/utils/i18n', () => ({
  useI18n: () => ({
    t: (_key: string, fallback: string) => fallback
  })
}))

import AiExtensionBuilder from './AiExtensionBuilder.vue'

describe('AI Extension Builder guided workflow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    projectApi.listExtensionProjects.mockResolvedValue([])
  })

  it('turns a plain-language widget request into a reviewable plan', async () => {
    http.post.mockResolvedValue({
      data: {
        project_type: 'widget',
        template_key: 'simple',
        package_kind: 'compiled',
        needs_database: false,
        config_schema: {
          type: 'object',
          properties: {
            timezone: { type: 'string', default: 'UTC' }
          }
        },
        capability_plan: null,
        summary: 'A dashboard clock with editable timezone.',
        assumptions: ['The clock uses the browser locale.'],
        questions: []
      }
    })

    const wrapper = mount(AiExtensionBuilder)
    await flushPromises()

    await wrapper.find('.guided-form input').setValue('Clock')
    await wrapper.find('.guided-description textarea').setValue(
      'Show a clock on the dashboard with an editable timezone.'
    )
    await wrapper.find('.guided-actions .button-primary').trigger('click')
    await flushPromises()

    expect(http.post).toHaveBeenCalledWith('/api/ai/extensions/plan', {
      description: 'Show a clock on the dashboard with an editable timezone.',
      placement: 'auto',
      data_mode: 'auto'
    })
    expect(wrapper.text()).toContain('Here is what we will build')
    expect(wrapper.text()).toContain('A dashboard clock with editable timezone.')
    expect(wrapper.text()).toContain('Dashboard widget')
  })
})
