export interface AuthorityInspection {
  review_version: 1
  status: 'available' | 'unavailable' | 'not_applicable'
  reason: 'application_only' | 'installation_not_stable' | 'baseline_unavailable' | 'review_failed' | null
  configuration_source: 'saved_installation_reused' | 'not_supplied'
  review: {
    baseline: 'no_previous_package' | 'previous_declarations'
    previous_version: string | null
    candidate_version: string
    previous_sha256: string | null
    candidate_sha256: string
    artifact_changed: boolean
    permission_approval: 'not_evaluated'
    changes: Array<{
      scope: string
      change: 'added' | 'removed' | 'changed'
      before: Record<string, unknown> | null
      after: Record<string, unknown> | null
      potential_expansion: boolean
    }>
    unresolved: Array<{ side: 'previous' | 'candidate'; scope: string; reason: string }>
    not_checked: string[]
  } | null
}
