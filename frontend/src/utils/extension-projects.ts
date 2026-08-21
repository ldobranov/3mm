import http from '@/utils/dynamic-http'

export type ProjectChangeKind = 'patch' | 'minor' | 'major' | 'prerelease'

export interface ExtensionProjectFile {
  path: string
  content: string
  sha256: string
  updated_at: string
}

export interface ExtensionProjectSummary {
  project_id: string
  name: string
  slug: string
  project_type: 'extension' | 'widget'
  status: 'draft' | 'built' | 'installed' | 'failed'
  current_version: string
  revision: number
  created_at: string
  updated_at: string
}

export interface ExtensionProject extends ExtensionProjectSummary {
  owner_user_id: number
  spec: Record<string, unknown>
  files: ExtensionProjectFile[]
}

export interface ExtensionProjectBuild {
  build_id: string
  version: string
  status: string
  change_kind: ProjectChangeKind
  change_request?: string | null
  report: Record<string, unknown>
  artifact_sha256?: string | null
  has_artifact: boolean
  package_kind?: 'compiled' | 'legacy' | null
  installed_at?: string | null
  created_at: string
}

export interface ExtensionProjectModification {
  project_id: string
  base_revision: number
  changed_files: string[]
  proposed_files: Record<string, string>
  diffs: Record<string, string>
  warnings: Array<{ code: string; message: string }>
}

const filesPayload = (files: Record<string, string>) =>
  Object.entries(files).map(([path, content]) => ({ path, content }))

export async function listExtensionProjects(): Promise<ExtensionProjectSummary[]> {
  return (await http.get('/api/v1/extension-projects')).data || []
}

export async function readExtensionProject(projectId: string): Promise<ExtensionProject> {
  return (await http.get(`/api/v1/extension-projects/${encodeURIComponent(projectId)}`)).data
}

export async function createExtensionProject(payload: {
  name: string
  project_type: 'extension' | 'widget'
  spec: Record<string, unknown>
  files: Record<string, string>
}): Promise<ExtensionProject> {
  return (await http.post('/api/v1/extension-projects', {
    ...payload,
    files: filesPayload(payload.files)
  })).data
}

export async function updateExtensionProject(
  projectId: string,
  expectedRevision: number,
  payload: { name?: string; spec?: Record<string, unknown>; status?: string }
): Promise<ExtensionProject> {
  return (await http.patch(`/api/v1/extension-projects/${encodeURIComponent(projectId)}`, {
    expected_revision: expectedRevision,
    ...payload
  })).data
}

export async function replaceExtensionProjectFiles(
  projectId: string,
  expectedRevision: number,
  files: Record<string, string>
): Promise<ExtensionProject> {
  return (await http.put(`/api/v1/extension-projects/${encodeURIComponent(projectId)}/files`, {
    expected_revision: expectedRevision,
    files: filesPayload(files)
  })).data
}

export async function readNextProjectVersion(projectId: string, changeKind: ProjectChangeKind): Promise<string> {
  const response = await http.get(`/api/v1/extension-projects/${encodeURIComponent(projectId)}/next-version`, {
    params: { change_kind: changeKind }
  })
  return response.data.next_version
}

export async function createExtensionProjectBuild(
  projectId: string,
  expectedRevision: number,
  payload: { change_kind: ProjectChangeKind; change_request?: string; status?: 'built' | 'failed'; report?: Record<string, unknown>; artifact_base64?: string }
): Promise<ExtensionProjectBuild> {
  return (await http.post(`/api/v1/extension-projects/${encodeURIComponent(projectId)}/builds`, {
    expected_revision: expectedRevision,
    ...payload
  })).data
}

export async function downloadExtensionProjectBuild(projectId: string, buildId: string): Promise<Blob> {
  const response = await http.get(
    `/api/v1/extension-projects/${encodeURIComponent(projectId)}/builds/${encodeURIComponent(buildId)}/artifact`,
    { responseType: 'blob' }
  )
  return response.data
}

export async function markExtensionProjectBuildInstalled(projectId: string, buildId: string, artifactSha256: string): Promise<ExtensionProjectBuild> {
  return (await http.post(
    `/api/v1/extension-projects/${encodeURIComponent(projectId)}/builds/${encodeURIComponent(buildId)}/installed`,
    { artifact_sha256: artifactSha256 }
  )).data
}

export async function listExtensionProjectBuilds(projectId: string): Promise<ExtensionProjectBuild[]> {
  return (await http.get(`/api/v1/extension-projects/${encodeURIComponent(projectId)}/builds`)).data || []
}

export async function proposeExtensionProjectModification(
  projectId: string,
  expectedRevision: number,
  payload: { change_request: string; ai_provider: 'auto' | 'groq' | 'openrouter'; model?: string }
): Promise<ExtensionProjectModification> {
  return (await http.post(`/api/v1/extension-projects/${encodeURIComponent(projectId)}/modify`, {
    expected_revision: expectedRevision,
    ...payload
  })).data
}
