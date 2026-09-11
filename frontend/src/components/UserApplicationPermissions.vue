<template>
  <section class="application-access" :aria-busy="busy">
    <h4>{{ t('users.applicationAccess', 'Application access') }}</h4>
    <p>{{ t('users.directAccessHint', 'Direct permissions for this user. Changes are saved immediately.') }}</p>
    <p v-if="isAdmin">{{ t('users.adminAccessHint', 'Global administrators already have operator and administrator access. These checkboxes show direct grants only; clearing them does not remove administrator access.') }}</p>
    <label>
      {{ t('users.application', 'Application') }}
      <select class="select" v-model="selected" :disabled="busy || !applications.length" @change="loadPermissions">
        <option value="">{{ t('users.chooseApplication', 'Choose an application') }}</option>
        <option v-for="app in applications" :key="app.module_id" :value="app.module_id">{{ app.module_id }} · {{ app.active_version }}</option>
      </select>
    </label>
    <p v-if="busy" role="status">{{ t('users.loading', 'Loading') }}</p>
    <div v-if="failed" role="alert" class="access-error">
      {{ t('users.accessFailed', 'Permissions could not be loaded or saved. Refresh before trying again.') }}
      <button class="button button-outline button-sm" :disabled="busy" @click="loadApplications">{{ t('users.accessRefresh', 'Refresh permissions') }}</button>
    </div>
    <p v-else-if="!busy && !applications.length">{{ t('users.noApplications', 'No active applications are available.') }}</p>
    <p v-else-if="selected && !busy && !permissions.length">{{ t('users.noPermissions', 'This application declares no user permissions.') }}</p>
    <label v-for="permission in permissions" :key="permission.permission_id" class="permission-row">
      <input type="checkbox" :checked="grants.includes(permission.permission_id)" :disabled="busy || failed" @change="toggle(permission.permission_id, $event)" />
      <span><strong>{{ localized(permission.label) }}</strong><small>{{ localized(permission.description) }}</small></span>
    </label>
  </section>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import http from '@/utils/dynamic-http'
import { useI18n } from '@/utils/i18n'

const props = defineProps<{ userId: number; isAdmin: boolean }>()
const { t, currentLanguage } = useI18n()
type Localized = { en: string; translations: Record<string, string> }
type Permission = { permission_id: string; label: Localized; description: Localized }
type Application = { module_id: string; active_version: string; enabled: boolean; status: string }
const base = '/api/v1/application-extensions'
const applications = ref<Application[]>([])
const selected = ref('')
const permissions = ref<Permission[]>([])
const grants = ref<string[]>([])
const busy = ref(false)
const failed = ref(false)
let generation = 0
const localized = (value: Localized) => value.translations?.[currentLanguage.value] || value.en
const endpoint = () => `${base}/${encodeURIComponent(selected.value)}/permissions`

async function loadApplications() {
  const request = ++generation
  busy.value = true
  failed.value = false
  permissions.value = []
  grants.value = []
  try {
    const response = await http.get(base)
    if (request !== generation) return
    applications.value = response.data.filter((app: Application) => app.enabled && app.status === 'active' && app.active_version)
    if (!applications.value.some(app => app.module_id === selected.value)) selected.value = ''
    if (selected.value) await loadPermissions()
  } catch {
    if (request === generation) failed.value = true
  } finally {
    if (request === generation) busy.value = false
  }
}

async function loadPermissions() {
  const request = ++generation
  permissions.value = []
  grants.value = []
  failed.value = false
  busy.value = true
  try {
    if (!selected.value) return
    const response = await http.get(endpoint())
    if (request !== generation) return
    permissions.value = response.data.permissions
    grants.value = response.data.grants.filter((grant: { user_id: number }) => grant.user_id === props.userId)
      .map((grant: { permission_id: string }) => grant.permission_id)
  } catch {
    if (request === generation) failed.value = true
  } finally {
    if (request === generation) busy.value = false
  }
}

async function toggle(permissionId: string, event: Event) {
  const input = event.target as HTMLInputElement
  const enable = input.checked
  input.checked = grants.value.includes(permissionId)
  if (busy.value || failed.value) return
  const request = ++generation
  busy.value = true
  try {
    if (enable) await http.post(`${endpoint()}/grants`, { user_id: props.userId, permission_id: permissionId })
    else await http.delete(`${endpoint()}/grants/${props.userId}/${encodeURIComponent(permissionId)}`)
    if (request === generation) await loadPermissions()
  } catch {
    if (request === generation) failed.value = true
  } finally {
    if (request === generation) busy.value = false
  }
}
onMounted(loadApplications)
onBeforeUnmount(() => { generation++ })
</script>

<style scoped>
.application-access { margin-top: 1rem; padding-top: 1rem; border-top: 1px solid var(--card-border); min-width: 0; }
h4 { font-size: 1rem; }
p, small { font-size: .875rem; color: var(--text-secondary); }
label, small { display: block; }
.select { width: 100%; min-width: 0; margin: .5rem 0; }
.permission-row { display: flex; align-items: flex-start; gap: .625rem; padding: .75rem 0; overflow-wrap: anywhere; }
.permission-row input { flex: 0 0 auto; margin-top: .25rem; accent-color: var(--accent); }
.permission-row span { min-width: 0; }
.access-error { color: var(--danger); }
.access-error button { margin-top: .5rem; }
</style>
