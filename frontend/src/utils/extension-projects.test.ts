import { beforeEach, describe, expect, it, vi } from 'vitest'

const http = vi.hoisted(() => ({
  get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn()
}))
vi.mock('@/utils/dynamic-http', () => ({ default: http }))

import {
  createExtensionProject,
  downloadExtensionProjectBuild,
  markExtensionProjectBuildInstalled,
  proposeExtensionProjectModification,
  readNextProjectVersion,
  replaceExtensionProjectFiles
} from './extension-projects'

describe('extension projects API', () => {
  beforeEach(() => vi.clearAllMocks())

  it('serializes editable files when creating a project', async () => {
    http.post.mockResolvedValue({ data: { project_id: 'extproj_1' } })
    await createExtensionProject({
      name: 'Clock', project_type: 'widget', spec: { goal: 'clock' },
      files: { 'source/frontend/Widget.vue': '<template />' }
    })
    expect(http.post).toHaveBeenCalledWith('/api/v1/extension-projects', {
      name: 'Clock', project_type: 'widget', spec: { goal: 'clock' },
      files: [{ path: 'source/frontend/Widget.vue', content: '<template />' }]
    })
  })

  it('uses revision checks when replacing project source', async () => {
    http.put.mockResolvedValue({ data: { revision: 4 } })
    await replaceExtensionProjectFiles('extproj_1', 3, { 'manifest.json': '{}' })
    expect(http.put).toHaveBeenCalledWith('/api/v1/extension-projects/extproj_1/files', {
      expected_revision: 3,
      files: [{ path: 'manifest.json', content: '{}' }]
    })
  })

  it('asks the server for the next semantic version', async () => {
    http.get.mockResolvedValue({ data: { next_version: '1.1.0' } })
    await expect(readNextProjectVersion('extproj_1', 'minor')).resolves.toBe('1.1.0')
    expect(http.get).toHaveBeenCalledWith('/api/v1/extension-projects/extproj_1/next-version', {
      params: { change_kind: 'minor' }
    })
  })

  it('requests a non-persistent AI modification against an exact project revision', async () => {
    http.post.mockResolvedValue({ data: { changed_files: [], proposed_files: {}, diffs: {} } })
    await proposeExtensionProjectModification('extproj_1', 7, {
      change_request: 'Add a color option', ai_provider: 'groq', model: 'fast-model'
    })
    expect(http.post).toHaveBeenCalledWith('/api/v1/extension-projects/extproj_1/modify', {
      expected_revision: 7,
      change_request: 'Add a color option',
      ai_provider: 'groq',
      model: 'fast-model'
    })
  })

  it('downloads and marks the exact immutable build as installed', async () => {
    const artifact = new Blob(['zip'])
    http.get.mockResolvedValue({ data: artifact })
    http.post.mockResolvedValue({ data: { build_id: 'extbuild_1', status: 'installed' } })
    await expect(downloadExtensionProjectBuild('extproj_1', 'extbuild_1')).resolves.toBe(artifact)
    expect(http.get).toHaveBeenCalledWith(
      '/api/v1/extension-projects/extproj_1/builds/extbuild_1/artifact',
      { responseType: 'blob' }
    )
    await markExtensionProjectBuildInstalled('extproj_1', 'extbuild_1', 'a'.repeat(64))
    expect(http.post).toHaveBeenCalledWith(
      '/api/v1/extension-projects/extproj_1/builds/extbuild_1/installed',
      { artifact_sha256: 'a'.repeat(64) }
    )
  })
})
