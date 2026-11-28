// Older/unrelated conflicts are not proof that the operator's request was refused.
export function isUpdateRefusal(failure: unknown, code: 'runtime_update_not_accepted' | 'component_update_not_accepted', requestId: string): boolean {
  const response = (failure as { response?: { status?: number; data?: { detail?: { code?: string; request_id?: string } } } } | null)?.response
  return response?.status === 409 && response.data?.detail?.code === code && response.data.detail.request_id === requestId
}
