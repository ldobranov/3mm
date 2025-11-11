<template>
  <div class="view">
    <div class="view-header">
      <h1 class="view-title">Security & Permissions</h1>
    </div>

    <!-- Navigation Tabs -->
    <div class="tabs-container">
      <div class="tabs-header">
        <button
          class="tab-button"
          :class="{ 'active': activeTab === 'sessions' }"
          @click="activeTab = 'sessions'"
        >
          Active Sessions
        </button>
        <button
          class="tab-button"
          :class="{ 'active': activeTab === 'audit' }"
          @click="activeTab = 'audit'"
        >
          Audit Logs
        </button>
        <button
          v-if="isAdmin"
          class="tab-button"
          :class="{ 'active': activeTab === 'roles' }"
          @click="activeTab = 'roles'"
        >
          Roles
        </button>
        <button
          v-if="isAdmin"
          class="tab-button"
          :class="{ 'active': activeTab === 'groups' }"
          @click="activeTab = 'groups'"
        >
          Groups
        </button>
        <button
          v-if="isAdmin"
          class="tab-button"
          :class="{ 'active': activeTab === 'permissions' }"
          @click="activeTab = 'permissions'"
        >
          Permissions
        </button>
      </div>
    </div>

    <!-- Sessions Tab -->
    <div v-if="activeTab === 'sessions'">
      <div class="card security-card" :style="{ backgroundColor: styleSettings.cardBg, color: styleSettings.textPrimary, borderColor: styleSettings.cardBorder }">
        <div class="card-header">
          <h3 class="card-title">Your Active Sessions</h3>
          <button
            class="button button-danger button-sm"
            @click="logoutAllSessions"
            :disabled="sessions.length <= 1"
          >
            Logout All Other Sessions
          </button>
        </div>
        <div class="card-content">
          <div v-if="loadingSessions" class="text-center loading-state">
            <div class="spinner" role="status" aria-label="Loading"></div>
          </div>

          <div v-else-if="sessions.length === 0" class="text-center empty-state">
            <p>No active sessions found</p>
          </div>

          <div v-else class="sessions-list">
            <div
              v-for="session in sessions"
              :key="session.id"
              class="session-item"
              :style="{ backgroundColor: styleSettings.cardBg, borderColor: styleSettings.cardBorder }"
            >
              <div class="session-content">
                <div class="session-info">
                  <h4 class="session-title">
                    <i class="bi bi-laptop"></i>
                    {{ session.device_name || 'Unknown Device' }}
                    <span v-if="session.is_current" class="session-current">Current</span>
                  </h4>
                  <p class="session-location">
                    <i class="bi bi-geo-alt"></i>
                    {{ session.location || session.ip_address || 'Unknown Location' }}
                  </p>
                  <small class="session-last-active">
                    Last active: {{ formatDate(session.last_activity) }}
                  </small>
                </div>
                <button
                  v-if="!session.is_current"
                  class="button button-outline button-sm button-danger"
                  @click="revokeSession(session.id)"
                >
                  Revoke
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Audit Logs Tab -->
    <div v-if="activeTab === 'audit'">
      <div class="card security-card" :style="{ backgroundColor: styleSettings.cardBg, color: styleSettings.textPrimary, borderColor: styleSettings.cardBorder }">
        <div class="card-header">
          <h3 class="card-title">Activity History</h3>

          <!-- Filters -->
          <div class="filters-grid">
            <select v-model="auditFilters.action" class="select">
              <option value="">All Actions</option>
              <option value="CREATE">Create</option>
              <option value="UPDATE">Update</option>
              <option value="DELETE">Delete</option>
              <option value="LOGIN">Login</option>
              <option value="LOGOUT">Logout</option>
            </select>
            <select v-model="auditFilters.entity_type" class="select">
              <option value="">All Types</option>
              <option value="page">Pages</option>
              <option value="dashboard">Dashboards</option>
              <option value="widget">Widgets</option>
              <option value="settings">Settings</option>
              <option value="user">Users</option>
            </select>
            <input
              type="date"
              v-model="auditFilters.start_date"
              class="input"
              placeholder="Start Date"
            >
            <button
              class="button button-primary"
              @click="loadAuditLogs"
            >
              Apply Filters
            </button>
          </div>
        </div>
        
        <div class="card-content">
          <div v-if="loadingAudit" class="text-center loading-state">
            <div class="spinner" role="status" aria-label="Loading"></div>
          </div>

          <div v-else-if="auditLogs.length === 0" class="text-center empty-state">
            <p>No audit logs found</p>
          </div>

          <div v-else>
            <div class="audit-table-container">
              <table class="table audit-table">
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Action</th>
                    <th>Type</th>
                    <th>Entity</th>
                    <th v-if="isAdmin">User</th>
                    <th>IP Address</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="log in auditLogs" :key="log.id">
                    <td>{{ formatDate(log.timestamp) }}</td>
                    <td>
                      <span class="action-badge" :style="{ backgroundColor: getActionBadgeBg(log.action) }">
                        {{ log.action }}
                      </span>
                    </td>
                    <td>{{ log.entity_type || '-' }}</td>
                    <td>{{ log.entity_name || '-' }}</td>
                    <td v-if="isAdmin">{{ getUserName(log.user_id) }}</td>
                    <td>{{ log.ip_address || '-' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- Pagination -->
          <div v-if="auditLogs.length > 0" class="pagination-controls">
            <button
              class="button button-outline button-sm"
              @click="loadMoreAuditLogs"
              :disabled="!hasMoreAuditLogs"
            >
              Load More
            </button>
            <small class="records-count">
              Showing {{ auditLogs.length }} records
            </small>
          </div>
        </div>
      </div>

      <!-- Audit Statistics (Admin Only) -->
      <div v-if="isAdmin && auditStats" class="card security-card stats-card" :style="{ backgroundColor: styleSettings.cardBg, color: styleSettings.textPrimary, borderColor: styleSettings.cardBorder }">
        <div class="card-header">
          <h5 class="card-title">Activity Statistics (Last 7 Days)</h5>
        </div>
        <div class="card-content">
          <div class="stats-grid">
            <div class="stat-item">
              <div class="stat-number">{{ auditStats.total_actions }}</div>
              <div class="stat-label">Total Actions</div>
            </div>
            <div class="stat-item">
              <div class="stat-number">{{ auditStats.actions_by_type?.create || 0 }}</div>
              <div class="stat-label">Created</div>
            </div>
            <div class="stat-item">
              <div class="stat-number">{{ auditStats.actions_by_type?.update || 0 }}</div>
              <div class="stat-label">Updated</div>
            </div>
            <div class="stat-item">
              <div class="stat-number">{{ auditStats.actions_by_type?.delete || 0 }}</div>
              <div class="stat-label">Deleted</div>
            </div>
          </div>

          <div class="stats-divider"></div>

          <h6 class="active-users-title">Most Active Users</h6>
          <ul class="active-users-list">
            <li v-for="user in auditStats.most_active_users" :key="user.username" class="active-user-item">
              {{ user.username }}: {{ user.actions }} actions
            </li>
          </ul>
        </div>
      </div>
    </div>

    <!-- Roles Tab (Admin Only) -->
    <div v-if="activeTab === 'roles' && isAdmin">
      <div class="card security-card" :style="{ backgroundColor: styleSettings.cardBg, color: styleSettings.textPrimary, borderColor: styleSettings.cardBorder }">
        <div class="card-header">
          <h3 class="card-title">Role Management</h3>
          <button
            class="button button-primary"
            @click="showCreateRoleForm = true"
          >
            <i class="bi bi-plus-lg"></i>
            Create Role
          </button>
        </div>
        <div class="card-content">
          <p class="roles-description">
            Define and manage user roles to control system access and permissions.
          </p>

          <!-- Roles List -->
          <div v-if="roles.length > 0">
            <div class="roles-grid">
              <div
                v-for="role in roles"
                :key="role.id"
                class="role-card"
                :class="{ 'system-role': role.is_system_role }"
              >
                <div class="role-header">
                  <h4 class="role-name">{{ role.name }}</h4>
                  <span v-if="role.is_system_role" class="system-badge">System</span>
                </div>
                <p class="role-description">{{ role.description || 'No description' }}</p>
                <div class="role-meta">
                  <small>Created: {{ formatDate(role.created_at) }}</small>
                  <small v-if="role.updated_at">Updated: {{ formatDate(role.updated_at) }}</small>
                </div>
                <div class="role-actions">
                  <button
                    v-if="!role.is_system_role"
                    class="button button-outline button-sm"
                    @click="editRole(role)"
                  >
                    <i class="bi bi-pencil"></i>
                    Edit
                  </button>
                  <button
                    v-if="!role.is_system_role"
                    class="button button-outline button-sm button-danger"
                    @click="deleteRole(role)"
                  >
                    <i class="bi bi-trash"></i>
                    Delete
                  </button>
                  <button
                    class="button button-outline button-sm"
                    @click="manageRoleUsers(role)"
                  >
                    <i class="bi bi-people"></i>
                    Users ({{ getRoleUserCount(role.id) }})
                  </button>
                </div>
              </div>
            </div>
          </div>
          <div v-else class="empty-roles">
            <i class="bi bi-shield-check"></i>
            No roles have been created yet. Create your first role to get started.
          </div>
        </div>
      </div>
    </div>

    <!-- Groups Tab (Admin Only) -->
    <div v-if="activeTab === 'groups' && isAdmin">
      <div class="card security-card" :style="{ backgroundColor: styleSettings.cardBg, color: styleSettings.textPrimary, borderColor: styleSettings.cardBorder }">
        <div class="card-header">
          <h3 class="card-title">Group Management</h3>
          <button
            class="button button-primary"
            @click="showCreateGroupForm = true"
          >
            <i class="bi bi-plus-lg"></i>
            Create Group
          </button>
        </div>
        <div class="card-content">
          <p class="groups-description">
            Organize users into groups to manage permissions and access more efficiently.
          </p>

          <!-- Groups List -->
          <div v-if="groups.length > 0">
            <div class="groups-grid">
              <div
                v-for="group in groups"
                :key="group.id"
                class="group-card"
              >
                <div class="group-header">
                  <h4 class="group-name">{{ group.name }}</h4>
                </div>
                <p class="group-description">{{ group.description || 'No description' }}</p>
                <div class="group-meta">
                  <small>Created: {{ formatDate(group.created_at) }}</small>
                  <small v-if="group.updated_at">Updated: {{ formatDate(group.updated_at) }}</small>
                </div>
                <div class="group-actions">
                  <button
                    class="button button-outline button-sm"
                    @click="editGroup(group)"
                  >
                    <i class="bi bi-pencil"></i>
                    Edit
                  </button>
                  <button
                    class="button button-outline button-sm button-danger"
                    @click="deleteGroup(group)"
                  >
                    <i class="bi bi-trash"></i>
                    Delete
                  </button>
                  <button
                    class="button button-outline button-sm"
                    @click="manageGroupUsers(group)"
                  >
                    <i class="bi bi-people"></i>
                    Members ({{ getGroupUserCount(group.id) }})
                  </button>
                </div>
              </div>
            </div>
          </div>
          <div v-else class="empty-groups">
            <i class="bi bi-collection"></i>
            No groups have been created yet. Create your first group to get started.
          </div>
        </div>
      </div>
    </div>

    <!-- Permissions Tab (Admin Only) -->
    <div v-if="activeTab === 'permissions' && isAdmin">
      <div class="card security-card" :style="{ backgroundColor: styleSettings.cardBg, color: styleSettings.textPrimary, borderColor: styleSettings.cardBorder }">
        <div class="card-header">
          <h3 class="card-title">Permission Management</h3>
        </div>
        <div class="card-content">
          <p class="permissions-description">
            Grant or revoke access to specific dashboards, extensions, and widgets for users.
          </p>

          <!-- Add Permission Form -->
          <div class="permission-form-grid">
            <div class="form-group">
              <label class="form-label">Type</label>
              <select
                v-model="newPermission.entity_type"
                class="select"
                @change="onEntityTypeChange"
              >
                <option value="">Select Type</option>
                <option value="dashboard">Dashboard</option>
                <option value="extension">Extension</option>
              </select>
            </div>
            <div class="form-group">
              <label class="form-label">
                {{ newPermission.entity_type === 'dashboard' ? 'Dashboard' :
                   newPermission.entity_type === 'extension' ? 'Extension' :
                   'Entity' }}
              </label>
              <select
                v-model="newPermission.entity_id"
                class="select"
                @change="onEntitySelect"
                :disabled="!newPermission.entity_type"
              >
                <option value="">
                  {{ !newPermission.entity_type ? 'Select type first' :
                     `Select ${newPermission.entity_type}` }}
                </option>
                <option
                  v-for="entity in availableEntities"
                  :key="entity.id"
                  :value="entity.id"
                >
                  {{ 
                     newPermission.entity_type === 'dashboard' ? entity.title :
                     newPermission.entity_type === 'extension' ? entity.name :
                     entity.name }}
                  {{ entity.slug ? `(${entity.slug})` : '' }}
                </option>
              </select>
            </div>
            <div class="form-group">
              <label class="form-label">User</label>
              <select v-model="newPermission.user_id" class="select">
                <option value="">Select User</option>
                <option v-for="user in users" :key="user.id" :value="user.id">
                  {{ user.username }} ({{ user.email }})
                </option>
              </select>
            </div>
            <div class="form-group">
              <label class="form-label">Permission</label>
              <select v-model="newPermission.permission_level" class="select">
                <option value="view">View</option>
                <option value="edit">Edit</option>
                <option value="delete">Delete</option>
                <option value="admin">Admin</option>
              </select>
            </div>
            <div class="form-group">
              <label class="form-label">&nbsp;</label>
              <button
                class="button button-primary"
                @click="grantPermission"
                :disabled="!canGrantPermission"
                title="Grant Permission"
              >
                <i class="bi bi-plus-lg"></i>
                Grant
              </button>
            </div>
          </div>
          
          <!-- Selected Entity Info -->
          <div v-if="selectedEntity" class="selected-entity-info">
            <strong>Selected:</strong>
            {{ 
               newPermission.entity_type === 'dashboard' ? selectedEntity.title :
               newPermission.entity_type === 'extension' ? selectedEntity.name :
               selectedEntity.name }}
            <span v-if="selectedEntity.slug" class="entity-slug">
              (Slug: {{ selectedEntity.slug }})
            </span>
            <span v-if="selectedEntity.description" class="entity-description">
              - {{ selectedEntity.description }}
            </span>
            <span v-if="selectedEntity.extension_type" class="entity-extension-type">
              - Type: {{ selectedEntity.extension_type }}
            </span>
          </div>

          <!-- Permissions List -->
          <div v-if="permissions.length > 0">
            <h4 class="permissions-title">Active Permissions</h4>
            <div class="permissions-table-container">
              <table class="table permissions-table">
                <thead>
                  <tr>
                    <th>User</th>
                    <th>Type</th>
                    <th>Entity</th>
                    <th>Level</th>
                    <th>Granted</th>
                    <th>Expires</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="perm in permissions" :key="perm.id">
                    <td>
                      <strong>{{ perm.username || getUserName(perm.user_id) }}</strong>
                      <br>
                      <small class="user-email">{{ perm.user_email }}</small>
                    </td>
                    <td>
                      <span class="entity-type-badge">{{ perm.entity_type }}</span>
                    </td>
                    <td>
                      <strong>{{ perm.entity_name || `ID: ${perm.entity_id}` }}</strong>
                      <br v-if="perm.entity_slug">
                      <small v-if="perm.entity_slug" class="entity-slug">
                        /{{ perm.entity_slug }}
                      </small>
                      <small v-if="perm.extension_type" class="extension-type">
                        - {{ perm.extension_type }}
                      </small>
                    </td>
                    <td>
                      <span class="permission-badge" :style="{ backgroundColor: getPermissionBadgeBg(perm.permission_level) }">
                        {{ perm.permission_level }}
                      </span>
                    </td>
                    <td>
                      <small>{{ formatDate(perm.granted_at) }}</small>
                    </td>
                    <td>
                      <small v-if="perm.expires_at">{{ formatDate(perm.expires_at) }}</small>
                      <span v-else class="never-expires">Never</span>
                    </td>
                    <td>
                      <button
                        class="button button-outline button-sm button-danger"
                        @click="revokePermission(perm.id)"
                        title="Revoke Permission"
                      >
                        <i class="bi bi-trash"></i>
                        Revoke
                      </button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
          <div v-else class="empty-permissions">
            <i class="bi bi-info-circle"></i>
            No permissions have been granted yet. Use the form above to grant permissions to users.
          </div>
        </div>
      </div>
    </div>

    <!-- Success/Error Messages -->
    <div v-if="successMessage" class="alert alert-success" style="margin-top: 1rem;">
      {{ successMessage }}
    </div>
    <div v-if="errorMessage" class="alert alert-danger" style="margin-top: 1rem;">
      {{ errorMessage }}
    </div>
  </div>

  <!-- Create/Edit Role Modal -->
  <div 
    v-if="showCreateRoleForm || showEditRoleForm" 
    class="modal-overlay" 
    @click="closeRoleModals"
    @keyup.esc="closeRoleModals"
    ref="roleModal"
  >
    <div class="modal-content" @click.stop>
      <div class="modal-header">
        <h3>{{ showCreateRoleForm ? 'Create New Role' : 'Edit Role' }}</h3>
        <button class="button-close" @click="closeRoleModals">×</button>
      </div>
      <div class="modal-body">
        <div class="form-group">
          <label class="form-label">Role Name</label>
          <input
            v-model="editingRole.name"
            type="text"
            class="input"
            placeholder="Enter role name"
            ref="roleNameInput"
            @keyup.enter="saveRole"
            required
          >
        </div>
        <div class="form-group">
          <label class="form-label">Description</label>
          <textarea
            v-model="editingRole.description"
            class="textarea"
            placeholder="Enter role description"
            rows="3"
            @keyup.enter="saveRole"
          ></textarea>
        </div>
      </div>
      <div class="modal-footer">
        <button
          class="button button-secondary"
          @click="closeRoleModals"
        >
          Cancel
        </button>
        <button
          class="button button-primary"
          @click="saveRole"
          :disabled="!editingRole.name"
        >
          {{ showCreateRoleForm ? 'Create Role' : 'Save Changes' }}
        </button>
      </div>
    </div>
  </div>

  <!-- Create/Edit Group Modal -->
  <div 
    v-if="showCreateGroupForm || showEditGroupForm" 
    class="modal-overlay" 
    @click="closeGroupModals"
    @keyup.esc="closeGroupModals"
    ref="groupModal"
  >
    <div class="modal-content" @click.stop>
      <div class="modal-header">
        <h3>{{ showCreateGroupForm ? 'Create New Group' : 'Edit Group' }}</h3>
        <button class="button-close" @click="closeGroupModals">×</button>
      </div>
      <div class="modal-body">
        <div class="form-group">
          <label class="form-label">Group Name</label>
          <input
            v-model="editingGroup.name"
            type="text"
            class="input"
            placeholder="Enter group name"
            ref="groupNameInput"
            @keyup.enter="saveGroup"
            required
          >
        </div>
        <div class="form-group">
          <label class="form-label">Description</label>
          <textarea
            v-model="editingGroup.description"
            class="textarea"
            placeholder="Enter group description"
            rows="3"
            @keyup.enter="saveGroup"
          ></textarea>
        </div>
      </div>
      <div class="modal-footer">
        <button
          class="button button-secondary"
          @click="closeGroupModals"
        >
          Cancel
        </button>
        <button
          class="button button-primary"
          @click="saveGroup"
          :disabled="!editingGroup.name"
        >
          {{ showCreateGroupForm ? 'Create Group' : 'Save Changes' }}
        </button>
      </div>
    </div>
  </div>

  <!-- Manage Role Users Modal -->
  <div 
    v-if="showManageRoleUsers" 
    class="modal-overlay" 
    @click="closeManageRoleUsers"
    @keyup.esc="closeManageRoleUsers"
    ref="manageRoleUsersModal"
  >
    <div class="modal-content modal-large" @click.stop>
      <div class="modal-header">
        <h3>Manage Users for Role: {{ selectedRole?.name }}</h3>
        <button class="button-close" @click="closeManageRoleUsers">×</button>
      </div>
      <div class="modal-body">
        <div class="user-management">
          <div class="user-list-section">
            <h4>Current Members</h4>
            <div v-if="roleUsers.length > 0" class="user-list">
              <div 
                v-for="user in roleUsers" 
                :key="user.id" 
                class="user-item"
              >
                <div class="user-info">
                  <strong>{{ user.username }}</strong>
                  <small>{{ user.email }}</small>
                </div>
                <button 
                  class="button button-outline button-sm button-danger"
                  @click="removeUserFromRole(user.id)"
                >
                  Remove
                </button>
              </div>
            </div>
            <div v-else class="empty-state">
              <p>No users assigned to this role</p>
            </div>
          </div>
          
          <div class="user-list-section">
            <h4>Add User</h4>
            <div class="form-group">
              <select v-model="selectedUserToAdd" class="select">
                <option value="">Select a user</option>
                <option 
                  v-for="user in availableUsers" 
                  :key="user.id" 
                  :value="user.id"
                >
                  {{ user.username }} ({{ user.email }})
                </option>
              </select>
            </div>
            <button 
              class="button button-primary"
              @click="addUserToRole"
              :disabled="!selectedUserToAdd"
            >
              Add User to Role
            </button>
          </div>
        </div>
      </div>
      <div class="modal-footer">
        <button
          class="button button-secondary"
          @click="closeManageRoleUsers"
        >
          Close
        </button>
      </div>
    </div>
  </div>

  <!-- Manage Group Users Modal -->
  <div 
    v-if="showManageGroupUsers" 
    class="modal-overlay" 
    @click="closeManageGroupUsers"
    @keyup.esc="closeManageGroupUsers"
    ref="manageGroupUsersModal"
  >
    <div class="modal-content modal-large" @click.stop>
      <div class="modal-header">
        <h3>Manage Members for Group: {{ selectedGroup?.name }}</h3>
        <button class="button-close" @click="closeManageGroupUsers">×</button>
      </div>
      <div class="modal-body">
        <div class="user-management">
          <div class="user-list-section">
            <h4>Current Members</h4>
            <div v-if="groupUsers.length > 0" class="user-list">
              <div 
                v-for="user in groupUsers" 
                :key="user.id" 
                class="user-item"
              >
                <div class="user-info">
                  <strong>{{ user.username }}</strong>
                  <small>{{ user.email }}</small>
                </div>
                <button 
                  class="button button-outline button-sm button-danger"
                  @click="removeUserFromGroup(user.id)"
                >
                  Remove
                </button>
              </div>
            </div>
            <div v-else class="empty-state">
              <p>No users in this group</p>
            </div>
          </div>
          
          <div class="user-list-section">
            <h4>Add User</h4>
            <div class="form-group">
              <select v-model="selectedUserToAdd" class="select">
                <option value="">Select a user</option>
                <option 
                  v-for="user in availableUsers" 
                  :key="user.id" 
                  :value="user.id"
                >
                  {{ user.username }} ({{ user.email }})
                </option>
              </select>
            </div>
            <button 
              class="button button-primary"
              @click="addUserToGroup"
              :disabled="!selectedUserToAdd"
            >
              Add User to Group
            </button>
          </div>
        </div>
      </div>
      <div class="modal-footer">
        <button
          class="button button-secondary"
          @click="closeManageGroupUsers"
        >
          Close
        </button>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, onMounted, computed, nextTick } from 'vue';
import http from '@/utils/http';
import { useSettingsStore } from '@/stores/settings';

export default defineComponent({
  name: 'Security',
  setup() {
    const settingsStore = useSettingsStore();
    const styleSettings = computed(() => settingsStore.styleSettings);
    const activeTab = ref('sessions');
    const sessions = ref<any[]>([]);
    const auditLogs = ref<any[]>([]);
    const permissions = ref<any[]>([]);
    const users = ref<any[]>([]);
    const pages = ref<any[]>([]);
    const dashboards = ref<any[]>([]);
    const extensions = ref<any[]>([]);
    const roles = ref<any[]>([]);
    const groups = ref<any[]>([]);
    const roleUserCounts = ref<{[key: number]: number}>({});
    const groupUserCounts = ref<{[key: number]: number}>({});
    const auditStats = ref<any>(null);
    
    const loadingSessions = ref(false);
    const loadingAudit = ref(false);
    const loadingRoles = ref(false);
    const loadingGroups = ref(false);
    const auditOffset = ref(0);
    const hasMoreAuditLogs = ref(true);
    
    const successMessage = ref('');
    const errorMessage = ref('');
    
    const isAdmin = computed(() => localStorage.getItem('role') === 'admin');
    
    const auditFilters = ref({
      action: '',
      entity_type: '',
      start_date: '',
      user_id: null
    });
    
    const newPermission = ref({
      entity_type: '',
      entity_id: null,
      entity_name: '',
      user_id: null,
      permission_level: 'view'
    });
    
    const selectedEntity = ref<any>(null);
    
    // Modal states
    const showCreateRoleForm = ref(false);
    const showEditRoleForm = ref(false);
    const showCreateGroupForm = ref(false);
    const showEditGroupForm = ref(false);
    const showManageRoleUsers = ref(false);
    const showManageGroupUsers = ref(false);
    
    // Form data
    const editingRole = ref({
      id: null as number | null,
      name: '',
      description: ''
    });
    
    const editingGroup = ref({
      id: null as number | null,
      name: '',
      description: ''
    });
    
    // User management
    const selectedRole = ref<any>(null);
    const selectedGroup = ref<any>(null);
    const roleUsers = ref<any[]>([]);
    const groupUsers = ref<any[]>([]);
    const selectedUserToAdd = ref<number | null>(null);
    
    // Refs for focus management
    const roleModal = ref<HTMLElement>();
    const groupModal = ref<HTMLElement>();
    const manageRoleUsersModal = ref<HTMLElement>();
    const manageGroupUsersModal = ref<HTMLElement>();
    const roleNameInput = ref<HTMLElement>();
    const groupNameInput = ref<HTMLElement>();
    
    const canGrantPermission = computed(() => {
      return newPermission.value.entity_type &&
             newPermission.value.entity_id &&
             newPermission.value.user_id;
    });
    
    // Get available entities based on type
    const availableEntities = computed(() => {
      if (newPermission.value.entity_type === 'dashboard') {
        return dashboards.value;
      } else if (newPermission.value.entity_type === 'extension') {
        return extensions.value;
      }
      return [];
    });
    
    // Get available users (not in current role/group)
    const availableUsers = computed(() => {
      if (showManageRoleUsers.value && selectedRole.value) {
        const roleUserIds = roleUsers.value.map(u => u.id);
        return users.value.filter(u => !roleUserIds.includes(u.id));
      } else if (showManageGroupUsers.value && selectedGroup.value) {
        const groupUserIds = groupUsers.value.map(u => u.id);
        return users.value.filter(u => !groupUserIds.includes(u.id));
      }
      return users.value;
    });
    
    // Helper functions for role and group management
    const getRoleUserCount = (roleId: number) => {
      return roleUserCounts.value[roleId] || 0;
    };
    
    const getGroupUserCount = (groupId: number) => {
      return groupUserCounts.value[groupId] || 0;
    };

    const loadUserCounts = async () => {
      // Load user counts for all roles
      for (const role of roles.value) {
        try {
          const response = await http.get(`/roles/${role.id}/count`);
          roleUserCounts.value[role.id] = response.data.user_count;
        } catch (error) {
          console.error(`Failed to load user count for role ${role.id}:`, error);
          roleUserCounts.value[role.id] = 0;
        }
      }
      
      // Load user counts for all groups
      for (const group of groups.value) {
        try {
          const response = await http.get(`/groups/${group.id}/count`);
          groupUserCounts.value[group.id] = response.data.user_count;
        } catch (error) {
          console.error(`Failed to load user count for group ${group.id}:`, error);
          groupUserCounts.value[group.id] = 0;
        }
      }
    };
    
    // Load functions
    const loadSessions = async () => {
      loadingSessions.value = true;
      try {
        const response = await http.get('/api/sessions/my');
        sessions.value = response.data;
      } catch (error) {
        console.error('Failed to load sessions:', error);
        errorMessage.value = 'Failed to load sessions';
      } finally {
        loadingSessions.value = false;
      }
    };
    
    const loadAuditLogs = async () => {
      loadingAudit.value = true;
      auditOffset.value = 0;
      try {
        const params: any = {
          limit: 50,
          offset: 0
        };
        
        if (auditFilters.value.action) params.action = auditFilters.value.action;
        if (auditFilters.value.entity_type) params.entity_type = auditFilters.value.entity_type;
        if (auditFilters.value.start_date) params.start_date = auditFilters.value.start_date;
        
        const response = await http.get('/api/audit-logs', { params });
        auditLogs.value = response.data;
        hasMoreAuditLogs.value = response.data.length === 50;
      } catch (error) {
        console.error('Failed to load audit logs:', error);
        errorMessage.value = 'Failed to load audit logs';
      } finally {
        loadingAudit.value = false;
      }
    };
    
    const loadMoreAuditLogs = async () => {
      auditOffset.value += 50;
      try {
        const params: any = {
          limit: 50,
          offset: auditOffset.value
        };
        
        if (auditFilters.value.action) params.action = auditFilters.value.action;
        if (auditFilters.value.entity_type) params.entity_type = auditFilters.value.entity_type;
        if (auditFilters.value.start_date) params.start_date = auditFilters.value.start_date;
        
        const response = await http.get('/api/audit-logs', { params });
        auditLogs.value.push(...response.data);
        hasMoreAuditLogs.value = response.data.length === 50;
      } catch (error) {
        console.error('Failed to load more audit logs:', error);
      }
    };
    
    const loadAuditStats = async () => {
      if (!isAdmin.value) return;
      
      try {
        const response = await http.get('/api/audit-logs/stats');
        auditStats.value = response.data;
      } catch (error) {
        console.error('Failed to load audit stats:', error);
      }
    };
    
    const loadUsers = async () => {
      if (!isAdmin.value) return;
      
      try {
        const response = await http.get('/user/read');
        users.value = response.data.items || [];
      } catch (error) {
        console.error('Failed to load users:', error);
        // If we can't load users, try to get basic user info
        users.value = [];
      }
    };
    
    const loadPages = async () => {
      // Pages are no longer used in the Security component
      // The permissions system now works with dashboards and extensions
      pages.value = [];
    };
    
    const loadDashboards = async () => {
      try {
        const response = await http.get('/display/read?limit=100');
        dashboards.value = response.data.items || [];
      } catch (error) {
        console.error('Failed to load dashboards:', error);
        dashboards.value = [];
      }
    };
    
    const loadExtensions = async () => {
      try {
        const response = await http.get('/api/extensions');
        extensions.value = response.data.items || [];
      } catch (error) {
        console.error('Failed to load extensions:', error);
        extensions.value = [];
      }
    };
    
    const loadRoles = async () => {
      if (!isAdmin.value) return;
      
      try {
        const response = await http.get('/roles');
        roles.value = response.data || [];
        // Load user counts for roles
        await loadUserCounts();
      } catch (error) {
        console.error('Failed to load roles:', error);
        errorMessage.value = 'Failed to load roles - please ensure backend is running with proper database setup';
        roles.value = [];
      }
    };
    
    const loadGroups = async () => {
      if (!isAdmin.value) return;
      
      try {
        const response = await http.get('/groups');
        groups.value = response.data || [];
        // Load user counts for groups
        await loadUserCounts();
      } catch (error) {
        console.error('Failed to load groups:', error);
        errorMessage.value = 'Failed to load groups - please ensure backend is running with proper database setup';
        groups.value = [];
      }
    };
    
    const onEntityTypeChange = () => {
      // Reset entity selection when type changes
      newPermission.value.entity_id = null;
      newPermission.value.entity_name = '';
      selectedEntity.value = null;
    };
    
    const onEntitySelect = (event: any) => {
      const entityId = parseInt(event.target.value);
      
      if (newPermission.value.entity_type === 'dashboard') {
        const dashboard = dashboards.value.find(d => d.id === entityId);
        if (dashboard) {
          newPermission.value.entity_id = dashboard.id;
          newPermission.value.entity_name = dashboard.name;
          selectedEntity.value = dashboard;
        }
      } else if (newPermission.value.entity_type === 'extension') {
        const extension = extensions.value.find(e => e.id === entityId);
        if (extension) {
          newPermission.value.entity_id = extension.id;
          newPermission.value.entity_name = extension.name;
          selectedEntity.value = extension;
        }
      }
    };
    
    // Role management methods
    const createRole = async () => {
      try {
        await http.post('/roles', editingRole.value);
        successMessage.value = 'Role created successfully';
        editingRole.value = { id: null, name: '', description: '' };
        showCreateRoleForm.value = false;
        await loadRoles();
      } catch (error) {
        console.error('Failed to create role:', error);
        errorMessage.value = 'Failed to create role';
      }
    };
    
    const editRole = (role: any) => {
      editingRole.value = { 
        id: role.id, 
        name: role.name, 
        description: role.description || '' 
      };
      showEditRoleForm.value = true;
      nextTick(() => {
        roleNameInput.value?.focus();
      });
    };
    
    const updateRole = async () => {
      try {
        await http.put(`/roles/${editingRole.value.id}`, {
          name: editingRole.value.name,
          description: editingRole.value.description
        });
        successMessage.value = 'Role updated successfully';
        editingRole.value = { id: null, name: '', description: '' };
        showEditRoleForm.value = false;
        await loadRoles();
      } catch (error) {
        console.error('Failed to update role:', error);
        errorMessage.value = 'Failed to update role';
      }
    };
    
    const deleteRole = async (role: any) => {
      if (!confirm(`Are you sure you want to delete the role "${role.name}"?`)) return;
      
      try {
        await http.delete(`/roles/${role.id}`);
        successMessage.value = 'Role deleted successfully';
        await loadRoles();
      } catch (error) {
        console.error('Failed to delete role:', error);
        errorMessage.value = 'Failed to delete role';
      }
    };
    
    const manageRoleUsers = async (role: any) => {
      selectedRole.value = role;
      showManageRoleUsers.value = true;
      await loadRoleUsers(role.id);
    };
    
    const loadRoleUsers = async (roleId: number) => {
      try {
        const response = await http.get(`/roles/${roleId}/users`);
        roleUsers.value = response.data || [];
      } catch (error) {
        console.error('Failed to load role users:', error);
        roleUsers.value = [];
      }
    };
    
    const addUserToRole = async () => {
      if (!selectedRole.value || !selectedUserToAdd.value) return;
      
      try {
        await http.post(`/roles/${selectedRole.value.id}/assign/${selectedUserToAdd.value}`);
        successMessage.value = 'User added to role successfully';
        selectedUserToAdd.value = null;
        await loadRoleUsers(selectedRole.value.id);
        // Refresh the user count for this role
        await refreshRoleUserCount(selectedRole.value.id);
      } catch (error) {
        console.error('Failed to add user to role:', error);
        errorMessage.value = 'Failed to add user to role';
      }
    };
    
    const removeUserFromRole = async (userId: number) => {
      if (!selectedRole.value) return;
      
      try {
        await http.delete(`/roles/${selectedRole.value.id}/unassign/${userId}`);
        successMessage.value = 'User removed from role successfully';
        await loadRoleUsers(selectedRole.value.id);
        // Refresh the user count for this role
        await refreshRoleUserCount(selectedRole.value.id);
      } catch (error) {
        console.error('Failed to remove user from role:', error);
        errorMessage.value = 'Failed to remove user from role';
      }
    };
    
    // Group management methods
    const createGroup = async () => {
      try {
        await http.post('/groups', editingGroup.value);
        successMessage.value = 'Group created successfully';
        editingGroup.value = { id: null, name: '', description: '' };
        showCreateGroupForm.value = false;
        await loadGroups();
      } catch (error) {
        console.error('Failed to create group:', error);
        errorMessage.value = 'Failed to create group';
      }
    };
    
    const editGroup = (group: any) => {
      editingGroup.value = { 
        id: group.id, 
        name: group.name, 
        description: group.description || '' 
      };
      showEditGroupForm.value = true;
      nextTick(() => {
        groupNameInput.value?.focus();
      });
    };
    
    const updateGroup = async () => {
      try {
        await http.put(`/groups/${editingGroup.value.id}`, {
          name: editingGroup.value.name,
          description: editingGroup.value.description
        });
        successMessage.value = 'Group updated successfully';
        editingGroup.value = { id: null, name: '', description: '' };
        showEditGroupForm.value = false;
        await loadGroups();
      } catch (error) {
        console.error('Failed to update group:', error);
        errorMessage.value = 'Failed to update group';
      }
    };
    
    const deleteGroup = async (group: any) => {
      if (!confirm(`Are you sure you want to delete the group "${group.name}"?`)) return;
      
      try {
        await http.delete(`/groups/${group.id}`);
        successMessage.value = 'Group deleted successfully';
        await loadGroups();
      } catch (error) {
        console.error('Failed to delete group:', error);
        errorMessage.value = 'Failed to delete group';
      }
    };
    
    const manageGroupUsers = async (group: any) => {
      selectedGroup.value = group;
      showManageGroupUsers.value = true;
      await loadGroupUsers(group.id);
    };
    
    const loadGroupUsers = async (groupId: number) => {
      try {
        const response = await http.get(`/groups/${groupId}/users`);
        groupUsers.value = response.data || [];
      } catch (error) {
        console.error('Failed to load group users:', error);
        groupUsers.value = [];
      }
    };
    
    const addUserToGroup = async () => {
      if (!selectedGroup.value || !selectedUserToAdd.value) return;
      
      try {
        await http.post(`/groups/${selectedGroup.value.id}/add/${selectedUserToAdd.value}`);
        successMessage.value = 'User added to group successfully';
        selectedUserToAdd.value = null;
        await loadGroupUsers(selectedGroup.value.id);
        // Refresh the user count for this group
        await refreshGroupUserCount(selectedGroup.value.id);
      } catch (error) {
        console.error('Failed to add user to group:', error);
        errorMessage.value = 'Failed to add user to group';
      }
    };
    
    const removeUserFromGroup = async (userId: number) => {
      if (!selectedGroup.value) return;
      
      try {
        await http.delete(`/groups/${selectedGroup.value.id}/remove/${userId}`);
        successMessage.value = 'User removed from group successfully';
        await loadGroupUsers(selectedGroup.value.id);
        // Refresh the user count for this group
        await refreshGroupUserCount(selectedGroup.value.id);
      } catch (error) {
        console.error('Failed to remove user from group:', error);
        errorMessage.value = 'Failed to remove user from group';
      }
    };

    // Refresh individual role/group user counts
    const refreshRoleUserCount = async (roleId: number) => {
      try {
        const response = await http.get(`/roles/${roleId}/count`);
        roleUserCounts.value[roleId] = response.data.user_count;
      } catch (error) {
        console.error(`Failed to refresh user count for role ${roleId}:`, error);
        roleUserCounts.value[roleId] = 0;
      }
    };

    const refreshGroupUserCount = async (groupId: number) => {
      try {
        const response = await http.get(`/groups/${groupId}/count`);
        groupUserCounts.value[groupId] = response.data.user_count;
      } catch (error) {
        console.error(`Failed to refresh user count for group ${groupId}:`, error);
        groupUserCounts.value[groupId] = 0;
      }
    };
    
    // Modal management
    const closeRoleModals = () => {
      showCreateRoleForm.value = false;
      showEditRoleForm.value = false;
      editingRole.value = { id: null, name: '', description: '' };
    };
    
    const closeGroupModals = () => {
      showCreateGroupForm.value = false;
      showEditGroupForm.value = false;
      editingGroup.value = { id: null, name: '', description: '' };
    };
    
    const closeManageRoleUsers = () => {
      showManageRoleUsers.value = false;
      selectedRole.value = null;
      roleUsers.value = [];
      selectedUserToAdd.value = null;
    };
    
    const closeManageGroupUsers = () => {
      showManageGroupUsers.value = false;
      selectedGroup.value = null;
      groupUsers.value = [];
      selectedUserToAdd.value = null;
    };
    
    // Save methods
    const saveRole = () => {
      if (showCreateRoleForm.value) {
        createRole();
      } else if (showEditRoleForm.value) {
        updateRole();
      }
    };
    
    const saveGroup = () => {
      if (showCreateGroupForm.value) {
        createGroup();
      } else if (showEditGroupForm.value) {
        updateGroup();
      }
    };
    
    // Other methods
    const logoutAllSessions = async () => {
      if (!confirm('Are you sure you want to logout from all other sessions?')) return;
      
      try {
        await http.post('/api/sessions/logout-all');
        successMessage.value = 'Successfully logged out from all other sessions';
        await loadSessions();
      } catch (error) {
        console.error('Failed to logout sessions:', error);
        errorMessage.value = 'Failed to logout from other sessions';
      }
    };
    
    const revokeSession = async (sessionId: number) => {
      if (!confirm('Are you sure you want to revoke this session?')) return;
      
      try {
        await http.delete(`/api/sessions/${sessionId}`);
        successMessage.value = 'Session revoked successfully';
        await loadSessions();
      } catch (error) {
        console.error('Failed to revoke session:', error);
        errorMessage.value = 'Failed to revoke session';
      }
    };
    
    const grantPermission = async () => {
      try {
        await http.post('/api/permissions', newPermission.value);
        successMessage.value = 'Permission granted successfully';
        newPermission.value = {
          entity_type: '',
          entity_id: null,
          entity_name: '',
          user_id: null,
          permission_level: 'view'
        };
        selectedEntity.value = null;
        // Reload permissions if needed
        await loadPermissions();
      } catch (error) {
        console.error('Failed to grant permission:', error);
        errorMessage.value = 'Failed to grant permission';
      }
    };
    
    const revokePermission = async (permissionId: number) => {
      if (!confirm('Are you sure you want to revoke this permission?')) return;
      
      try {
        await http.delete(`/api/permissions/${permissionId}`);
        successMessage.value = 'Permission revoked successfully';
        // Reload permissions
        await loadPermissions();
      } catch (error) {
        console.error('Failed to revoke permission:', error);
        errorMessage.value = 'Failed to revoke permission';
      }
    };
    
    const loadPermissions = async () => {
      if (!isAdmin.value) return;
      
      try {
        const response = await http.get('/api/permissions/all');
        permissions.value = response.data || [];
      } catch (error) {
        console.error('Failed to load permissions:', error);
      }
    };
    
    const formatDate = (dateString: string) => {
      if (!dateString) return '-';
      const date = new Date(dateString);
      return date.toLocaleString();
    };
    
    const getActionBadgeBg = (action: string) => {
      const colors: any = {
        CREATE: '#10b981',
        UPDATE: '#3b82f6',
        DELETE: '#ef4444',
        LOGIN: '#6366f1',
        LOGOUT: '#6b7280'
      };
      return colors[action] || '#6b7280';
    };

    const getActionBadgeColor = (action: string) => {
      return '#ffffff';
    };
    
    const getPermissionBadgeBg = (level: string) => {
      const colors: any = {
        view: '#3b82f6',
        edit: '#f59e0b',
        delete: '#ef4444',
        admin: '#10b981'
      };
      return colors[level] || '#6b7280';
    };

    const getPermissionBadgeColor = (level: string) => {
      return '#ffffff';
    };
    
    const getUserName = (userId: number) => {
      const user = users.value.find(u => u.id === userId);
      return user ? user.username : `User ${userId}`;
    };
    
    onMounted(() => {
      loadSessions();
      loadAuditLogs();
      loadAuditStats();
      loadUsers();
      loadPages();
      loadDashboards();
      loadExtensions();
      loadRoles();
      loadGroups();
      loadPermissions();
      
      // Clear messages after 5 seconds
      setInterval(() => {
        if (successMessage.value) successMessage.value = '';
        if (errorMessage.value) errorMessage.value = '';
      }, 5000);
    });
    
    return {
      activeTab,
      sessions,
      auditLogs,
      permissions,
      users,
      pages,
      dashboards,
      extensions,
      roles,
      groups,
      roleUserCounts,
      groupUserCounts,
      auditStats,
      selectedEntity,
      availableEntities,
      availableUsers,
      loadingSessions,
      loadingAudit,
      loadingRoles,
      loadingGroups,
      hasMoreAuditLogs,
      successMessage,
      errorMessage,
      isAdmin,
      auditFilters,
      newPermission,
      showCreateRoleForm,
      showEditRoleForm,
      showCreateGroupForm,
      showEditGroupForm,
      showManageRoleUsers,
      showManageGroupUsers,
      editingRole,
      editingGroup,
      selectedRole,
      selectedGroup,
      roleUsers,
      groupUsers,
      selectedUserToAdd,
      roleModal,
      groupModal,
      manageRoleUsersModal,
      manageGroupUsersModal,
      roleNameInput,
      groupNameInput,
      canGrantPermission,
      styleSettings,
      getRoleUserCount,
      getGroupUserCount,
      loadSessions,
      loadAuditLogs,
      loadMoreAuditLogs,
      logoutAllSessions,
      revokeSession,
      grantPermission,
      revokePermission,
      loadPermissions,
      loadExtensions,
      loadRoles,
      loadGroups,
      onEntityTypeChange,
      onEntitySelect,
      formatDate,
      getActionBadgeBg,
      getActionBadgeColor,
      getPermissionBadgeBg,
      getPermissionBadgeColor,
      getUserName,
      editRole,
      deleteRole,
      manageRoleUsers,
      editGroup,
      deleteGroup,
      manageGroupUsers,
      addUserToRole,
      removeUserFromRole,
      addUserToGroup,
      removeUserFromGroup,
      closeRoleModals,
      closeGroupModals,
      closeManageRoleUsers,
      closeManageGroupUsers,
      saveRole,
      saveGroup,
      loadUserCounts,
      refreshRoleUserCount,
      refreshGroupUserCount
    };
  }
});
</script>

<style scoped>
/* Security tabs */
.tabs-container {
  margin-bottom: 2rem;
}

.tabs-header {
  display: flex;
  border-bottom: 1px solid var(--card-border);
}

.tab-button {
  padding: 0.5rem 1rem;
  border: none;
  background: none;
  color: var(--text-secondary);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: all 0.2s ease;
}

.tab-button:hover {
  color: var(--text-primary);
  background-color: var(--panel-bg);
}

.tab-button.active {
  color: var(--button-primary-text);
  background-color: var(--button-primary-bg);
  border-bottom-color: var(--button-primary-bg);
}

.tab-button.active:hover {
  color: var(--button-primary-text);
}

/* Security cards */
.security-card {
  margin-bottom: 1.5rem;
  border-radius: var(--border-radius-md);
  box-shadow: var(--card-shadow);
  transition: box-shadow 0.2s ease;
}

.security-card:hover {
  box-shadow: var(--card-hover-shadow);
}

.card-header {
  padding: 1rem;
  border-bottom: 1px solid var(--card-border);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-title {
  margin: 0;
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--text-primary);
}

.card-content {
  padding: 1rem;
}

/* Sessions */
.loading-state,
.empty-state {
  padding: 2rem 0;
  text-align: center;
}

.empty-state p {
  color: var(--text-secondary);
  margin: 0;
}

.sessions-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.session-item {
  padding: 1rem;
  border: 1px solid var(--card-border);
  border-radius: var(--border-radius-md);
  transition: border-color 0.2s ease;
}

.session-item:hover {
  border-color: var(--button-primary-bg);
}

.session-content {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
}

.session-info {
  flex: 1;
}

.session-title {
  margin: 0 0 0.5rem 0;
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.session-title i {
  color: var(--text-secondary);
}

.session-current {
  display: inline-block;
  padding: 0.25rem 0.5rem;
  background-color: #10b981;
  color: white;
  border-radius: var(--border-radius-sm);
  font-size: 0.75rem;
  font-weight: 500;
}

.session-location {
  margin: 0 0 0.5rem 0;
  color: var(--text-secondary);
  font-size: 0.9rem;
}

.session-location i {
  margin-right: 0.25rem;
}

.session-last-active {
  color: var(--text-secondary);
  font-size: 0.875rem;
}

/* Audit logs */
.filters-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 0.5rem;
  margin-top: 1rem;
}

.audit-table-container {
  overflow-x: auto;
  max-height: 500px;
  overflow-y: auto;
  border: 1px solid var(--card-border);
  border-radius: var(--border-radius-md);
}

.audit-table {
  width: 100%;
  border-collapse: collapse;
  background-color: var(--table-bg);
  color: var(--text-primary);
}

.audit-table th,
.audit-table td {
  padding: 0.75rem;
  text-align: left;
  border-bottom: 1px solid var(--card-border);
}

.audit-table th,
.audit-table td {
  background-color: var(--table-bg);
  color: var(--text-primary);
  border-bottom: 1px solid var(--card-border);
}

.audit-table th {
  background-color: var(--panel-bg);
  font-weight: 600;
  color: var(--text-primary);
  position: sticky;
  top: 0;
}

.audit-table tbody tr:hover {
  background-color: var(--panel-bg);
}

.audit-table tbody tr {
  background-color: var(--table-bg);
}

.action-badge {
  display: inline-block;
  padding: 0.25rem 0.5rem;
  border-radius: var(--border-radius-sm);
  font-size: 0.75rem;
  font-weight: 500;
  color: #ffffff;
}

.pagination-controls {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 1rem;
}

.records-count {
  color: var(--text-secondary);
  font-size: 0.875rem;
}

/* Statistics */
.stats-card {
  margin-top: 1.5rem;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.stat-item {
  text-align: center;
  padding: 1rem;
  background-color: var(--panel-bg);
  border-radius: var(--border-radius-md);
}

.stat-number {
  font-size: 2rem;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 0.5rem;
}

.stat-label {
  color: var(--text-secondary);
  font-size: 0.875rem;
  font-weight: 500;
}

.stats-divider {
  height: 1px;
  background-color: var(--card-border);
  margin: 1.5rem 0;
}

.active-users-title {
  margin: 0 0 1rem 0;
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary);
}

.active-users-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.active-user-item {
  padding: 0.5rem;
  background-color: var(--panel-bg);
  border-radius: var(--border-radius-sm);
  color: var(--text-primary);
}

/* Permissions */
.permissions-description {
  color: var(--text-secondary);
  margin-bottom: 1.5rem;
}

.permission-form-grid {
  display: grid;
  grid-template-columns: 1fr 2fr 1.5fr 1fr auto;
  gap: 0.5rem;
  margin-bottom: 2rem;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.form-label {
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--text-primary);
}

.selected-entity-info {
  padding: 1rem;
  background-color: rgba(0, 123, 255, 0.1);
  border: 1px solid rgba(0, 123, 255, 0.2);
  border-radius: var(--border-radius-md);
  margin-bottom: 2rem;
  color: var(--text-primary);
}

.entity-slug,
.entity-description {
  color: var(--text-secondary);
  margin-left: 0.5rem;
}

.permissions-title {
  margin: 0 0 1rem 0;
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--text-primary);
}

.permissions-table-container {
  overflow-x: auto;
  border: 1px solid var(--card-border);
  border-radius: var(--border-radius-md);
}

.permissions-table {
  width: 100%;
  border-collapse: collapse;
  background-color: var(--table-bg);
  color: var(--text-primary);
}

.permissions-table th,
.permissions-table td {
  padding: 0.75rem;
  text-align: left;
  border-bottom: 1px solid var(--card-border);
}

.permissions-table th,
.permissions-table td {
  background-color: var(--table-bg);
  color: var(--text-primary);
  border-bottom: 1px solid var(--card-border);
}

.permissions-table th {
  background-color: var(--panel-bg);
  font-weight: 600;
  color: var(--text-primary);
  position: sticky;
  top: 0;
}

.permissions-table tbody tr:hover {
  background-color: var(--panel-bg);
}

.permissions-table tbody tr {
  background-color: var(--table-bg);
}

.entity-type-badge {
  display: inline-block;
  padding: 0.25rem 0.5rem;
  background-color: #6b7280;
  color: white;
  border-radius: var(--border-radius-sm);
  font-size: 0.75rem;
  font-weight: 500;
}

.permission-badge {
  display: inline-block;
  padding: 0.25rem 0.5rem;
  border-radius: var(--border-radius-sm);
  font-size: 0.75rem;
  font-weight: 500;
  color: #ffffff;
}

.user-email {
  color: var(--text-secondary);
}

.never-expires {
  color: var(--text-secondary);
}

.empty-permissions {
  text-align: center;
  padding: 2rem;
  color: var(--text-secondary);
}

.empty-permissions i {
  font-size: 2rem;
  margin-bottom: 1rem;
  display: block;
}

/* Modal styles */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
}

.modal-content {
  background-color: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: var(--border-radius-md);
  width: 90%;
  max-width: 500px;
  max-height: 80vh;
  overflow-y: auto;
  box-shadow: var(--card-shadow);
}

.modal-content.modal-large {
  max-width: 800px;
}

.modal-header {
  padding: 1rem;
  border-bottom: 1px solid var(--card-border);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.modal-header h3 {
  margin: 0;
  color: var(--text-primary);
}

.button-close {
  background: none;
  border: none;
  font-size: 1.5rem;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 0.25rem;
  line-height: 1;
}

.button-close:hover {
  color: var(--text-primary);
}

.modal-body {
  padding: 1rem;
}

.modal-footer {
  padding: 1rem;
  border-top: 1px solid var(--card-border);
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}

/* Roles and Groups Grid */
.roles-grid,
.groups-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 1rem;
  margin-top: 1rem;
}

.role-card,
.group-card {
  padding: 1rem;
  border: 1px solid var(--card-border);
  border-radius: var(--border-radius-md);
  background-color: var(--card-bg);
  transition: all 0.2s ease;
}

.role-card:hover,
.group-card:hover {
  border-color: var(--button-primary-bg);
  box-shadow: var(--card-hover-shadow);
}

.role-card.system-role {
  background-color: var(--panel-bg);
  border-color: var(--button-primary-bg);
  border-width: 2px;
}

.role-header,
.group-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}

.role-name,
.group-name {
  margin: 0;
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--text-primary);
}

.system-badge {
  display: inline-block;
  padding: 0.25rem 0.5rem;
  background-color: var(--button-primary-bg);
  color: var(--button-primary-text);
  border-radius: var(--border-radius-sm);
  font-size: 0.75rem;
  font-weight: 500;
}

.role-description,
.group-description {
  color: var(--text-secondary);
  margin: 0.5rem 0;
  font-size: 0.9rem;
}

.role-meta,
.group-meta {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  margin-bottom: 1rem;
  color: var(--text-secondary);
  font-size: 0.875rem;
}

.role-actions,
.group-actions {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

/* Empty states for roles and groups */
.empty-roles,
.empty-groups {
  text-align: center;
  padding: 2rem;
  color: var(--text-secondary);
}

.empty-roles i,
.empty-groups i {
  font-size: 2rem;
  margin-bottom: 1rem;
  display: block;
  color: var(--text-secondary);
}

/* Textarea styles */
.textarea {
  width: 100%;
  padding: 0.5rem;
  border: 1px solid var(--card-border);
  border-radius: var(--border-radius-sm);
  background-color: var(--input-bg);
  color: var(--text-primary);
  font-size: 0.875rem;
  font-family: inherit;
  resize: vertical;
  min-height: 60px;
}

.textarea:focus {
  outline: none;
  border-color: var(--button-primary-bg);
  box-shadow: 0 0 0 1px var(--button-primary-bg);
}

/* Entity extension type */
.entity-extension-type,
.extension-type {
  color: var(--text-secondary);
  font-size: 0.875rem;
  font-style: italic;
}

/* User management */
.user-management {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 2rem;
}

.user-list-section h4 {
  margin: 0 0 1rem 0;
  color: var(--text-primary);
  font-size: 1rem;
  font-weight: 600;
}

.user-list {
  max-height: 300px;
  overflow-y: auto;
  border: 1px solid var(--card-border);
  border-radius: var(--border-radius-sm);
}

.user-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem;
  border-bottom: 1px solid var(--card-border);
}

.user-item:last-child {
  border-bottom: none;
}

.user-info {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.user-info strong {
  color: var(--text-primary);
  font-size: 0.9rem;
}

.user-info small {
  color: var(--text-secondary);
  font-size: 0.8rem;
}

@media (max-width: 768px) {
  .permission-form-grid {
    grid-template-columns: 1fr;
  }
  
  .user-management {
    grid-template-columns: 1fr;
  }
  
  .roles-grid,
  .groups-grid {
    grid-template-columns: 1fr;
  }
}
</style>