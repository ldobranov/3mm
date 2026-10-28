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

  it('builds and installs accepted AI changes as a new patch version', async () => {
    const projectId = 'project-1'
    const now = '2026-08-25T08:00:00Z'
    const originalFiles = {
      'manifest.json': JSON.stringify({ name: 'DoorSensor', version: '1.0.0', type: 'widget' }),
      'compiled-ui.json': JSON.stringify({ kind: 'widget' }),
      'source/frontend/Widget.vue': '<template>Old widget</template>'
    }
    const proposedFiles = {
      ...originalFiles,
      'source/frontend/Widget.vue': '<template>Updated widget</template>'
    }
    let revision = 1
    let currentVersion = '1.0.0'
    let status: 'draft' | 'built' | 'installed' = 'installed'
    let storedFiles = { ...originalFiles }
    let storedSpec: Record<string, unknown> = {
      extension_spec: {
        name: 'DoorSensor',
        version: currentVersion,
        type: 'widget',
        description: 'Door sensor widget',
        author: '3mm',
        frontend_routes: [],
        permissions: [],
        public_endpoints: [],
        dependencies: [],
        config_schema: {}
      },
      builder_state: { template_key: 'simple' }
    }
    let built = false

    const project = () => ({
      project_id: projectId,
      owner_user_id: 1,
      name: 'DoorSensor',
      slug: 'door-sensor',
      project_type: 'widget' as const,
      status,
      current_version: currentVersion,
      revision,
      created_at: now,
      updated_at: now,
      spec: storedSpec,
      files: Object.entries(storedFiles).map(([path, content]) => ({ path, content, sha256: path, updated_at: now }))
    })
    const summary = () => {
      const { owner_user_id: _owner, spec: _spec, files: _files, ...value } = project()
      return value
    }
    const newBuild = {
      build_id: 'build-1',
      version: '1.0.1',
      status: 'built',
      change_kind: 'patch',
      change_request: 'Make reset work',
      report: { files: [], warnings: [] },
      has_artifact: true,
      package_kind: 'compiled',
      created_at: now
    }

    projectApi.listExtensionProjects.mockImplementation(async () => [summary()])
    projectApi.readExtensionProject.mockImplementation(async () => project())
    projectApi.listExtensionProjectBuilds.mockImplementation(async () => built ? [newBuild] : [])
    projectApi.updateExtensionProject.mockImplementation(async (_id, _expectedRevision, payload) => {
      revision += 1
      storedSpec = payload.spec || storedSpec
      status = payload.status || status
      return project()
    })
    projectApi.replaceExtensionProjectFiles.mockImplementation(async (_id, _expectedRevision, files) => {
      revision += 1
      storedFiles = { ...files }
      return project()
    })
    projectApi.readNextProjectVersion.mockResolvedValue('1.0.1')
    projectApi.proposeExtensionProjectModification.mockImplementation(async () => ({
      project_id: projectId,
      base_revision: revision,
      changed_files: ['source/frontend/Widget.vue'],
      proposed_files: proposedFiles,
      diffs: { 'source/frontend/Widget.vue': 'diff' },
      warnings: []
    }))
    projectApi.createExtensionProjectBuild.mockImplementation(async () => {
      built = true
      status = 'built'
      currentVersion = '1.0.1'
      revision += 1
      return newBuild
    })
    projectApi.markExtensionProjectBuildInstalled.mockImplementation(async () => {
      status = 'installed'
      return { ...newBuild, status: 'installed' }
    })
    http.post.mockImplementation(async (url: string) => {
      if (url === '/api/ai/extensions/package') {
        return { data: { report: { files: [], warnings: [] }, zip_base64: 'UEs=', files_text: storedFiles } }
      }
      if (url === '/api/v1/modules/packages') {
        return { data: { sha256: 'artifact-sha256' } }
      }
      throw new Error(`Unexpected POST ${url}`)
    })

    const wrapper = mount(AiExtensionBuilder)
    await flushPromises()

    await wrapper.find('.project-switcher select').setValue(projectId)
    await flushPromises()
    await wrapper.find('.modify-panel textarea').setValue('Make reset work')
    await wrapper.find('.modify-panel .button-primary').trigger('click')
    await flushPromises()

    const acceptButton = wrapper.find('.diff-review .button-primary')
    expect(acceptButton.text()).toBe('Accept, build & install')
    await acceptButton.trigger('click')
    await flushPromises()

    expect(projectApi.createExtensionProjectBuild).toHaveBeenCalledWith(
      projectId,
      expect.any(Number),
      expect.objectContaining({
        change_kind: 'patch',
        change_request: 'Make reset work',
        artifact_base64: 'UEs='
      })
    )
    expect(http.post).toHaveBeenCalledWith('/api/v1/modules/packages', expect.any(FormData))
    expect(projectApi.markExtensionProjectBuildInstalled).toHaveBeenCalledWith(
      projectId,
      'build-1',
      'artifact-sha256'
    )
    expect(wrapper.text()).toContain('Changes accepted, built and installed')
  })
})
