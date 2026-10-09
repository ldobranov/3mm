<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from '@/utils/i18n'
import type { AuthorityInspection } from './authority-review'

const props = defineProps<{ value?: AuthorityInspection | null }>()
const { t } = useI18n()
const review = computed(() => props.value?.status === 'available' ? props.value.review : null)
const changeLabel = (kind: string) => kind === 'added'
  ? t('authorityReview.added', 'Added') : kind === 'removed'
    ? t('authorityReview.removed', 'Removed') : t('authorityReview.changed', 'Changed')
const count = (kind: string) => review.value?.changes.filter(item => item.change === kind).length || 0
const unavailable = computed(() => props.value?.reason === 'installation_not_stable'
  ? t('authorityReview.unstable', 'The installation is changing or has an inconsistent version. Compare again after it settles.')
  : t('authorityReview.unavailable', 'The installed baseline could not be verified. No comparison was made; this is not treated as a new installation.'))
const unresolvedLabel = (reason: string) => {
  if (reason.startsWith('unresolved_configuration_binding:')) {
    return t('authorityReview.bindingMissing', 'Unresolved binding') + ': ' + reason.split(':').slice(1).join(':')
  }
  switch (reason) {
    case 'effective_configuration_not_supplied': return t('authorityReview.configurationMissing', 'Effective configuration is not available.')
    case 'effective_configuration_invalid_or_incomplete': return t('authorityReview.configurationInvalid', 'The saved settings are incomplete or incompatible with this package.')
    case 'executable_frontend_effects_not_inferred': return t('authorityReview.frontendUnknown', 'Executable frontend effects cannot be determined from declarations.')
    case 'approved_peer_scope_not_supplied': return t('authorityReview.peerUnknown', 'Approved peer scope is not available.')
    default: return t('authorityReview.unresolvedScope', 'This scope could not be resolved.')
  }
}
const format = (value: Record<string, unknown> | null) => value === null ? '—' : JSON.stringify(value, null, 2)
</script>

<template>
  <section v-if="value?.status !== 'not_applicable'" class="authority-review ui-stack" :aria-label="t('authorityReview.title', 'Permission request changes')">
    <h4>{{ t('authorityReview.title', 'Permission request changes') }}</h4>
    <p class="authority-notice">{{ t('authorityReview.warning', 'Declarations only, not approved access. Added or changed requests may expand authority. This snapshot can become stale; it never authorizes installation or actions.') }}</p>
    <p v-if="!value" class="ui-help">{{ t('authorityReview.notAvailable', 'This Core did not return an authority comparison.') }}</p>
    <p v-else-if="!review" class="authority-unavailable" role="status">{{ unavailable }}</p>
    <template v-else>
      <p class="ui-help">{{ review.baseline === 'no_previous_package'
        ? t('authorityReview.noInstallation', 'No application installation exists. Showing new declarations; configuration remains unresolved.')
        : t('authorityReview.savedConfiguration', 'Compared with the installed package, including a disabled installation. Saved settings are reused for the candidate preview only; nothing is saved.') }}</p>
      <dl class="authority-identities">
        <div><dt>{{ t('authorityReview.previous', 'Installed baseline') }}</dt><dd>{{ review.previous_version || '—' }}<code v-if="review.previous_sha256">{{ review.previous_sha256 }}</code></dd></div>
        <div><dt>{{ t('authorityReview.candidate', 'Selected package') }}</dt><dd>{{ review.candidate_version }}<code>{{ review.candidate_sha256 }}</code></dd></div>
      </dl>
      <p v-if="review.artifact_changed" class="ui-help">{{ t('authorityReview.artifactChanged', 'The artifact has changed. An empty permission diff would not make the new code trusted or approved.') }}</p>
      <ul class="authority-counts" :aria-label="t('authorityReview.summary', 'Change summary')">
        <li v-for="kind in ['added', 'removed', 'changed']" :key="kind"><strong>{{ count(kind) }}</strong> {{ changeLabel(kind) }}</li>
        <li><strong>{{ review.unresolved.length }}</strong> {{ t('authorityReview.unresolved', 'Unresolved') }}</li>
      </ul>
      <p v-if="!review.changes.length" class="ui-help">{{ t('authorityReview.noChanges', 'No declaration changes found. This is not permission approval.') }}</p>
      <div v-else class="authority-changes">
        <details v-for="item in review.changes" :key="item.scope" class="authority-change">
          <summary><span class="authority-kind">{{ changeLabel(item.change) }}</span> <code>{{ item.scope }}</code></summary>
          <p v-if="item.potential_expansion" class="ui-help">{{ t('authorityReview.potentialExpansion', 'May expand access; requires review, not an automatic grant.') }}</p>
          <div class="authority-diff">
            <div><h5>{{ t('authorityReview.before', 'Before') }}</h5><pre>{{ format(item.before) }}</pre></div>
            <div><h5>{{ t('authorityReview.after', 'After') }}</h5><pre>{{ format(item.after) }}</pre></div>
          </div>
        </details>
      </div>
      <details v-if="review.unresolved.length" class="authority-unresolved">
        <summary>{{ t('authorityReview.unresolved', 'Unresolved') }} · {{ review.unresolved.length }}</summary>
        <ul><li v-for="(item, index) in review.unresolved" :key="index">
          <span>{{ item.side === 'previous' ? t('authorityReview.previous', 'Installed baseline') : t('authorityReview.candidate', 'Selected package') }}</span>
          · <code>{{ item.scope }}</code> — {{ unresolvedLabel(item.reason) }}
        </li></ul>
      </details>
      <p class="ui-help">{{ t('authorityReview.notChecked', 'Approved grants, device availability/contracts, stored connector bindings and credential rotations, publisher/signature trust, dependencies and OS/browser isolation are not checked.') }}</p>
    </template>
  </section>
</template>

<style scoped>
.authority-review { min-width: 0; border-top: 1px solid var(--ui-border); padding-top: calc(var(--ui-space) * 4); }
h4, h5, p, dl { margin: 0; }
h4 { font-size: 1rem; font-weight: 650; }
h5 { font-size: .85rem; color: var(--ui-text-secondary); }
.authority-notice, .authority-unavailable { border-left: 3px solid var(--ui-accent); padding-left: calc(var(--ui-space) * 3); overflow-wrap: anywhere; }
.authority-notice { color: var(--ui-text-secondary); }
.authority-identities { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: calc(var(--ui-space) * 4); }
.authority-identities dt { color: var(--ui-text-secondary); font-size: .85em; }
.authority-identities dd { margin: calc(var(--ui-space) * 1) 0 0; }
code { color: inherit; overflow-wrap: anywhere; }
.authority-identities code { display: block; font-size: .75rem; margin-top: calc(var(--ui-space) * 1); }
.authority-counts { display: flex; flex-wrap: wrap; gap: calc(var(--ui-space) * 2); padding: 0; margin: 0; list-style: none; }
.authority-counts li { background: var(--ui-surface-alt); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-sm); padding: calc(var(--ui-space) * 2) calc(var(--ui-space) * 3); }
.authority-changes { max-height: 32rem; overflow: auto; }
.authority-change { border-bottom: 1px solid var(--ui-border); padding: calc(var(--ui-space) * 3) 0; }
.authority-kind { color: var(--ui-text-secondary); margin-right: calc(var(--ui-space) * 2); }
summary { cursor: pointer; overflow-wrap: anywhere; color: var(--ui-text); }
.authority-change > p, .authority-diff { margin-top: calc(var(--ui-space) * 3); }
.authority-diff { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: calc(var(--ui-space) * 3); }
.authority-diff > div { min-width: 0; }
pre { max-height: 16rem; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; color: var(--ui-text); background: var(--ui-surface-alt); padding: calc(var(--ui-space) * 3); margin: calc(var(--ui-space) * 2) 0 0; }
.authority-unresolved ul { padding-left: calc(var(--ui-space) * 5); margin-bottom: 0; }
.authority-unresolved li { overflow-wrap: anywhere; margin-top: calc(var(--ui-space) * 2); }
@media (max-width: 720px) {
  .authority-identities, .authority-diff { grid-template-columns: minmax(0, 1fr); }
  .authority-changes { max-height: none; overflow: visible; }
}
</style>
