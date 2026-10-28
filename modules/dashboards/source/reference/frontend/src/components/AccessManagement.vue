<template>
  <section class="access-manager card" :aria-busy="busy">
    <h2>{{ t('access.title', 'Roles and groups') }}</h2>
    <p>{{ t('access.hint', 'Roles contain resource permissions. Assign roles to users or groups. Changes are saved immediately; system administration remains separate.') }}</p>
    <p v-if="error" role="alert">{{ t('access.failed', 'Access could not be loaded or saved. Refresh before continuing.') }}</p>
    <button class="button button-outline button-sm" :disabled="busy" @click="refresh">{{ t('access.refresh', 'Refresh') }}</button>
    <fieldset :disabled="busy || error">
      <legend>{{ t('access.create', 'Create a role or group') }}</legend>
      <form class="create-row" @submit.prevent="create">
        <select v-model="kind" class="select" :aria-label="t('access.kind', 'Type')"><option value="roles">{{ t('access.role', 'Role') }}</option><option value="groups">{{ t('access.group', 'Group') }}</option></select>
        <input v-model="name" class="input" required maxlength="100" :aria-label="t('access.name', 'Name')" :placeholder="t('access.name', 'Name')" />
        <button class="button button-primary" :disabled="!name.trim()">{{ t('access.add', 'Create') }}</button>
      </form>
      <div class="access-columns">
        <section>
          <h3>{{ t('access.membership', 'User membership') }}</h3>
          <label>{{ t('access.user', 'User') }}<select class="select" v-model="userId"><option :value="0">—</option><option v-for="u in users" :key="u.id" :value="u.id">{{ u.username }}</option></select></label>
          <template v-if="userId">
            <h4>{{ t('access.directRoles', 'Direct roles') }}</h4>
            <label v-for="r in data.roles" :key="r.id" class="check"><input type="checkbox" :checked="bound('user-role', userId, r.id)" @change="binding('user-role', userId, r.id, $event)" />{{ r.name }}</label>
            <h4>{{ t('access.groups', 'Groups') }}</h4>
            <label v-for="g in data.groups" :key="g.id" class="check"><input type="checkbox" :checked="bound('user-group', userId, g.id)" @change="binding('user-group', userId, g.id, $event)" />{{ g.name }}</label>
          </template>
        </section>
        <section>
          <h3>{{ t('access.groupRoles', 'Roles assigned to a group') }}</h3>
          <label>{{ t('access.group', 'Group') }}<select class="select" v-model="groupId"><option :value="0">—</option><option v-for="g in data.groups" :key="g.id" :value="g.id">{{ g.name }}</option></select></label>
          <template v-if="groupId"><label v-for="r in data.roles" :key="r.id" class="check"><input type="checkbox" :checked="bound('group-role', groupId, r.id)" @change="binding('group-role', groupId, r.id, $event)" />{{ r.name }}</label></template>
        </section>
        <section>
          <h3>{{ t('access.roleRights', 'Resource permissions for a role') }}</h3>
          <label>{{ t('access.role', 'Role') }}<select class="select" v-model="roleId"><option :value="0">—</option><option v-for="r in data.roles" :key="r.id" :value="r.id">{{ r.name }}</option></select></label>
          <template v-if="roleId">
            <label>{{ t('access.application', 'Application') }}<select class="select" v-model="moduleId" @change="loadApplication"><option value="">—</option><option v-for="a in applications" :key="a.module_id" :value="a.module_id">{{ a.module_id }}</option></select></label>
            <label v-for="p in permissions" :key="p.permission_id" class="check"><input type="checkbox" :checked="hasGrant(p.permission_id)" @change="grant(p.permission_id, $event)" /><span>{{ localized(p.label) }}<small>{{ localized(p.description) }}</small></span></label>
            <p v-if="moduleId">{{ t('access.delegationHint', 'The extension must declare delegated management as permission-based operator access. Administrator-only pages remain restricted to system administrators.') }}</p>
            <h4>{{ t('access.dashboards', 'Dashboards') }}</h4>
            <p>{{ t('access.dashboardHint', 'View reads widgets; Edit changes widgets; Delete also removes widgets. Dashboard ownership and sharing remain owner-only.') }}</p>
            <label v-for="d in data.dashboards" :key="d.id">{{ d.name }}<select class="select" :value="dashboardLevel(d.id)" @change="dashboardGrant(d.id, $event)"><option v-for="level in levels" :key="level" :value="level">{{ t(`access.level.${level}`, level) }}</option></select></label>
          </template>
        </section>
      </div>
    </fieldset>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import http from '@/utils/dynamic-http'
import { useI18n } from '@/utils/i18n'
defineProps<{ users: { id: number; username: string }[] }>()
const emit = defineEmits<{ changed: [] }>()
const { t, currentLanguage } = useI18n()
type Item = { id: number; name: string }
type Localized = { en: string; translations?: Record<string, string> }
type Permission = { permission_id: string; label: Localized; description: Localized }
type Catalog = { roles: Item[]; groups: Item[]; dashboards: Item[]; user_roles: {user_id: number; role_id: number}[]; user_groups: {user_id: number; group_id: number}[]; group_roles: {group_id: number; role_id: number}[]; application_grants: {role_id: number; installation_id: number; permission_id: string}[]; dashboard_grants: {role_id: number; display_id: number; permission_level: string}[] }
type Kind = 'user-role' | 'user-group' | 'group-role'
const data = ref<Catalog>({roles: [], groups: [], dashboards: [], user_roles: [], user_groups: [], group_roles: [], application_grants: [], dashboard_grants: []})
const busy = ref(false), error = ref(false), kind = ref('roles'), name = ref('')
const roleId = ref(0), groupId = ref(0), userId = ref(0), moduleId = ref(''), installationId = ref(0)
const applications = ref<{module_id: string}[]>([]), permissions = ref<Permission[]>([])
const levels = ['none', 'view', 'edit', 'delete', 'admin']
const localized = (v: Localized) => v.translations?.[currentLanguage.value] || v.en
const bound = (kind: Kind, subject: number, target: number) => kind === 'user-role'
  ? data.value.user_roles.some(b => b.user_id === subject && b.role_id === target)
  : kind === 'user-group' ? data.value.user_groups.some(b => b.user_id === subject && b.group_id === target)
    : data.value.group_roles.some(b => b.group_id === subject && b.role_id === target)
const hasGrant = (id: string) => data.value.application_grants.some(g => g.role_id === roleId.value && g.installation_id === installationId.value && g.permission_id === id)
const dashboardLevel = (id: number) => data.value.dashboard_grants.find(g => g.role_id === roleId.value && g.display_id === id)?.permission_level || 'none'
async function reload() {
  const [catalog, apps] = await Promise.all([http.get('/api/access'), http.get('/api/v1/application-extensions')])
  data.value = catalog.data
  applications.value = apps.data.filter((a: {enabled: boolean; status: string}) => a.enabled && a.status === 'active')
}
async function run(action: () => Promise<void>) {
  if (busy.value) return
  busy.value = true
  try { await action(); error.value = false } catch { error.value = true } finally { busy.value = false }
}
async function refresh() { await run(async () => { await reload(); permissions.value = []; moduleId.value = '' }) }
async function write(action: () => Promise<unknown>) { await run(async () => { await action(); await reload(); emit('changed') }) }
async function create() { await write(async () => { await http.post(`/api/${kind.value}`, {name: name.value.trim()}); name.value = '' }) }
async function binding(kind: Kind, subject: number, target: number, event: Event) {
  const input = event.target as HTMLInputElement, enabled = input.checked
  input.checked = bound(kind, subject, target)
  await write(() => http.put('/api/access/bindings', {kind, subject_id: subject, target_id: target, enabled}))
}
async function loadApplication() {
  permissions.value = []; installationId.value = 0
  if (!moduleId.value) return
  await run(async () => { const result = await http.get(`/api/access/applications/${encodeURIComponent(moduleId.value)}`); permissions.value = result.data.permissions; installationId.value = result.data.installation_id })
}
async function grant(id: string, event: Event) {
  const input = event.target as HTMLInputElement, enabled = input.checked
  input.checked = hasGrant(id)
  await write(() => http.put(`/api/access/roles/${roleId.value}/applications/${encodeURIComponent(moduleId.value)}/permissions/${encodeURIComponent(id)}`, {enabled}))
}
async function dashboardGrant(id: number, event: Event) {
  const input = event.target as HTMLSelectElement, level = input.value
  input.value = dashboardLevel(id)
  await write(() => http.put(`/api/access/roles/${roleId.value}/dashboards/${id}`, {level}))
}
onMounted(refresh)
</script>

<style scoped>
.access-manager { padding: 1rem; margin: 1rem 0; min-width: 0; }
h2 { font-size: 1.15rem; } h3, h4 { font-size: 1rem; margin-top: 1rem; }
p, small { color: var(--text-secondary); font-size: .875rem; } small { display: block; }
fieldset { border: 0; padding: 0; min-width: 0; margin-top: 1rem; }
legend { font-size: 1rem; }
.access-columns { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 260px), 1fr)); gap: 1.5rem; }
.access-columns section, label { min-width: 0; overflow-wrap: anywhere; }
label { display: block; margin: .625rem 0; }
.select, .input { width: 100%; min-width: 0; }
.check { display: flex; align-items: flex-start; gap: .5rem; }
.check input { margin-top: .3rem; flex-shrink: 0; }
.create-row { display: flex; flex-wrap: wrap; gap: .5rem; }
.create-row .input { flex: 1 1 180px; } .create-row .select { flex: 0 1 160px; }
[role=alert] { color: var(--danger); }
</style>
