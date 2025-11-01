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

    <!-- Permissions Tab (Admin Only) -->
    <div v-if="activeTab === 'permissions' && isAdmin">
      <div class="card security-card" :style="{ backgroundColor: styleSettings.cardBg, color: styleSettings.textPrimary, borderColor: styleSettings.cardBorder }">
        <div class="card-header">
          <h3 class="card-title">Manage Permissions</h3>
        </div>
        <div class="card-content">
          <p class="permissions-description">
            Grant or revoke access to specific pages, dashboards, and widgets for users.
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
                <option value="page">Page</option>
                <option value="dashboard">Dashboard</option>
              </select>
            </div>
            <div class="form-group">
              <label class="form-label">
                {{ newPermission.entity_type === 'page' ? 'Page' :
                   newPermission.entity_type === 'dashboard' ? 'Dashboard' :
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
                  {{ newPermission.entity_type === 'page' ? entity.title : entity.name }}
                  {{ entity.slug ? `(/${entity.slug})` : '' }}
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
            {{ newPermission.entity_type === 'page' ? selectedEntity.title : selectedEntity.name }}
            <span v-if="selectedEntity.slug" class="entity-slug">
              (Slug: {{ selectedEntity.slug }})
            </span>
            <span v-if="selectedEntity.description" class="entity-description">
              - {{ selectedEntity.description }}
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
</template>

<script lang="ts">
import { defineComponent, ref, onMounted, computed } from 'vue';
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
    const auditStats = ref<any>(null);
    
    const loadingSessions = ref(false);
    const loadingAudit = ref(false);
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
    
    const canGrantPermission = computed(() => {
      return newPermission.value.entity_type && 
             newPermission.value.entity_id && 
             newPermission.value.user_id;
    });
    
    // Get available entities based on type
    const availableEntities = computed(() => {
      if (newPermission.value.entity_type === 'page') {
        return pages.value;
      } else if (newPermission.value.entity_type === 'dashboard') {
        return dashboards.value;
      }
      return [];
    });
    
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
      }
    };
    
    const loadPages = async () => {
      try {
        const response = await http.get('/pages/read?limit=100');
        pages.value = response.data.items || [];
      } catch (error) {
        console.error('Failed to load pages:', error);
      }
    };
    
    const loadDashboards = async () => {
      try {
        const response = await http.get('/display/read?limit=100');
        dashboards.value = response.data.items || [];
      } catch (error) {
        console.error('Failed to load dashboards:', error);
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
      if (newPermission.value.entity_type === 'page') {
        const page = pages.value.find(p => p.id === entityId);
        if (page) {
          newPermission.value.entity_id = page.id;
          newPermission.value.entity_name = page.title;
          selectedEntity.value = page;
        }
      } else if (newPermission.value.entity_type === 'dashboard') {
        const dashboard = dashboards.value.find(d => d.id === entityId);
        if (dashboard) {
          newPermission.value.entity_id = dashboard.id;
          newPermission.value.entity_name = dashboard.name;
          selectedEntity.value = dashboard;
        }
      }
    };
    
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
      auditStats,
      selectedEntity,
      availableEntities,
      loadingSessions,
      loadingAudit,
      hasMoreAuditLogs,
      successMessage,
      errorMessage,
      isAdmin,
      auditFilters,
      newPermission,
      canGrantPermission,
      styleSettings,
      loadSessions,
      loadAuditLogs,
      loadMoreAuditLogs,
      logoutAllSessions,
      revokeSession,
      grantPermission,
      revokePermission,
      loadPermissions,
      onEntityTypeChange,
      onEntitySelect,
      formatDate,
      getActionBadgeBg,
      getActionBadgeColor,
      getPermissionBadgeBg,
      getPermissionBadgeColor,
      getUserName
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
}

.tab-button.active {
  color: var(--button-primary-text);
  border-bottom-color: var(--button-primary-bg);
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
}

.audit-table th,
.audit-table td {
  padding: 0.75rem;
  text-align: left;
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
}

.permissions-table th,
.permissions-table td {
  padding: 0.75rem;
  text-align: left;
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
</style>