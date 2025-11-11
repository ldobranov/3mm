<template>
  <div class="pages-extension-view">
    <div class="view-header">
      <h1 class="view-title">Pages Management</h1>
      <button
        class="button button-primary"
        @click="openCreateModal"
      >
        <i class="bi bi-plus-circle" style="margin-right: 0.5rem;"></i>Create New Page
      </button>
    </div>

    <div v-if="isLoading" class="text-center" style="padding: 2rem 0;">
      <div class="spinner" role="status" aria-label="Loading"></div>
    </div>

    <div v-else class="grid">
      <div class="card" :style="{ backgroundColor: styleSettings.cardBg, color: styleSettings.textPrimary, borderColor: styleSettings.cardBorder }">
        <div style="padding: 1rem;">
          <h2>Existing Pages</h2>
          <div v-if="pages.length === 0" class="alert alert-info">
            <i class="bi bi-info-circle" style="margin-right: 0.5rem;"></i>
            No pages found.
          </div>
          <div v-else class="pages-grid">
            <div v-for="page in pages" :key="page.id" class="page-card card" :style="{ backgroundColor: styleSettings.cardBg, color: styleSettings.textPrimary, borderColor: styleSettings.cardBorder }">
              <h3>
                {{ page.title }}
                <span v-if="page.owner_id !== currentUserId && !isAdmin" class="text-sm" style="color: var(--text-secondary);">
                  (Shared with you)
                </span>
              </h3>
              <div class="meta">
                <span class="chip" :class="page.is_public ? 'chip-public' : 'chip-private'">
                  {{ page.is_public ? 'Public' : 'Private' }}
                </span>
              </div>
              <div class="page-slug" style="color: var(--text-muted);">Slug: /pages/{{ page.slug }}</div>
              <div class="actions">
                <button
                  class="button button-outline button-sm"
                  @click="openEditModal(page)"
                >
                  <i class="bi bi-pencil" style="margin-right: 0.25rem;"></i>Edit
                </button>
                <button
                  class="button button-outline button-sm"
                  style="--accent: var(--button-danger-bg); --accent-contrast: var(--button-danger-text); border-color: var(--button-danger-bg); color: var(--button-danger-bg);"
                  @click="confirmDelete(page)"
                  :disabled="isLoading"
                  v-if="page.owner_id === currentUserId || isAdmin"
                >
                  <i class="bi bi-trash" style="margin-right: 0.25rem;"></i>Delete
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <p v-if="errorMessage" class="error">{{ errorMessage }}</p>

    <!-- Create/Edit Page Modal -->
    <teleport to="body">
      <div v-if="showModal">
        <!-- backdrop -->
        <div
          class="modal-backdrop"
          @click="closeModal"
        ></div>

        <!-- dialog centered -->
        <div class="modal-container">
          <div
            class="modal-surface modal-lg"
            role="dialog"
            aria-modal="true"
            @click.stop
            :style="{ backgroundColor: styleSettings.cardBg, color: styleSettings.textPrimary, borderColor: styleSettings.cardBorder }"
          >
            <div class="flex items-center justify-between" style="padding-bottom: 0.5rem; border-bottom: 1px solid var(--card-border);">
              <div class="text-lg font-bold" style="color: var(--text-primary);">
                {{ editingPage ? 'Edit Page' : 'Create New Page' }}
              </div>
              <button
                class="button button-outline button-sm"
                type="button"
                @click.stop="closeModal"
              >
                ×
              </button>
            </div>

            <form @submit.prevent="editingPage ? updatePage() : createPage()" class="py-4 space-y-3">
              <div>
                <label for="page-title" class="block">
                  <span class="text-sm font-medium" style="color: var(--text-primary);">Title</span>
                  <input
                    id="page-title"
                    type="text"
                    class="input"
                    v-model="modalData.title"
                    placeholder="Page title"
                    required
                  />
                </label>
              </div>

              <div>
                <label for="page-slug" class="block">
                  <span class="text-sm font-medium" style="color: var(--text-primary);">Slug</span>
                  <input
                    id="page-slug"
                    type="text"
                    class="input"
                    v-model="modalData.slug"
                    placeholder="page-slug"
                  />
                  <p class="text-xs" style="color: var(--text-muted); margin-top: 0.25rem;">URL: /pages/{{ modalData.slug || generateSlug(modalData.title) }}</p>
                </label>
              </div>

              <div class="privacy-section">
                <label for="page-public" class="inline-flex items-center gap-2">
                  <input
                    id="page-public"
                    type="checkbox"
                    class="input"
                    v-model="modalData.isPublic"
                  />
                  <span style="color: var(--text-primary);">Make page public</span>
                </label>

                <div v-if="!modalData.isPublic" class="mt-2">
                  <p class="text-sm" style="color: var(--text-secondary);">
                    <i class="bi bi-info-circle me-1"></i>
                    This page will be private and only accessible to you.
                  </p>
                </div>
              </div>

              <div class="form-group">
                <label for="page-content" class="d-block mb-1" style="color: var(--text-primary); font-weight: 500; font-size: 0.875rem;">Content</label>
                <div class="editor-container card" style="padding: 0.75rem; margin-top: 0.25rem;" :style="{ backgroundColor: styleSettings.cardBg, borderColor: styleSettings.cardBorder }" @click="editor && editor.commands.focus('end')">
                  <EditorContent :editor="editor" />
                </div>
              </div>

              <div class="flex" style="justify-content: end; gap: 0.5rem; padding-top: 0.5rem; border-top: 1px solid var(--card-border);">
                <button
                  type="button"
                  class="button button-secondary"
                  @click.stop="closeModal"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  class="button button-primary"
                  :disabled="isLoading"
                >
                  <i class="bi bi-save" style="margin-right: 0.25rem;"></i>{{ isLoading ? 'Saving...' : (editingPage ? 'Update' : 'Create') }}
                </button>
              </div>
            </form>
          </div>
        </div>
      </div>
    </teleport>

    <!-- Delete Confirmation Modal -->
    <teleport to="body">
      <div v-if="showDeleteModal">
        <div
          class="modal-backdrop"
          @click="showDeleteModal = false"
        ></div>

        <div class="modal-container">
          <div
            class="modal-surface modal-sm"
            role="dialog"
            aria-modal="true"
            @click.stop
            :style="{ backgroundColor: styleSettings.cardBg, color: styleSettings.textPrimary, borderColor: styleSettings.cardBorder }"
          >
            <div class="text-lg font-bold mb-3" style="color: var(--text-primary);">Confirm Delete</div>
            <p class="mb-4" style="color: var(--text-primary); opacity: 0.9;">
              Are you sure you want to delete the page "{{ pageToDelete?.title }}"?
            </p>
            <div class="d-flex justify-content-end gap-2">
              <button
                class="button button-secondary"
                @click="showDeleteModal = false"
              >
                Cancel
              </button>
              <button
                class="button button-danger"
                @click="deletePage"
                :disabled="isLoading"
              >
                <i class="bi bi-trash" style="margin-right: 0.25rem;"></i>{{ isLoading ? 'Deleting...' : 'Delete' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </teleport>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, onMounted, onBeforeUnmount, computed, reactive, watch, nextTick } from 'vue';
import http from '@/utils/http';
import { Editor, EditorContent } from '@tiptap/vue-3';
import StarterKit from '@tiptap/starter-kit';
import { useThemeStore } from '@/stores/theme';
import { useSettingsStore } from '@/stores/settings';

export default defineComponent({
  components: { EditorContent },
  setup() {
    const themeStore = useThemeStore();
    const settingsStore = useSettingsStore();
    const isDark = computed(() => themeStore.isDark());
    const styleSettings = computed(() => settingsStore.styleSettings);

    interface Page {
      id: number;
      title: string;
      content: string;
      slug?: string;
      is_public?: boolean;
      owner_id?: number;
      owner_username?: string;
    }

    const pages = ref<Page[]>([]);
    const isLoading = ref(false);
    const errorMessage = ref('');
    const isAdmin = ref(localStorage.getItem('role') === 'admin');
    const currentUserId = ref(parseInt(localStorage.getItem('user_id') || '0'));

    // Modal states
    const showModal = ref(false);
    const showDeleteModal = ref(false);
    const editingPage = ref<Page | null>(null);
    const pageToDelete = ref<{ id: number; title: string } | null>(null);

    // Modal form data
    const modalData = reactive({
      title: '',
      slug: '',
      isPublic: true
    });

    const editor = new Editor({
      extensions: [StarterKit],
      content: '<p><br/></p>',
      autofocus: false,
      editable: true,
    });

    const fetchPages = async () => {
      try {
        isLoading.value = true;
        const response = await http.get('/api/pages/read');
        pages.value = response.data.items || [];
      } catch (error: any) {
        console.error('Failed to fetch pages:', error?.response || error);
        const status = error?.response?.status;
        errorMessage.value = status ? `Failed to fetch pages (HTTP ${status}).` : 'Failed to fetch pages.';
      } finally {
        isLoading.value = false;
      }
    };

    const generateSlug = (title: string) => {
      return title
        .toLowerCase()
        .replace(/\s+/g, '-')
        .replace(/[^a-z0-9-]/g, '');
    };

    const ensureHtml = (val?: string | null) => {
      const s = (val ?? '').trim();
      if (!s) return '<p><br/></p>';
      if (s.includes('<')) return s;
      const escaped = s
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
      return `<p>${escaped}</p>`;
    };

    // Modal functions
    const openCreateModal = async () => {
      editingPage.value = null;
      modalData.title = '';
      modalData.slug = '';
      modalData.isPublic = true;
      showModal.value = true;
      await nextTick();
      editor.commands.setContent(ensureHtml(''));
    };

    const openEditModal = async (page: { id: number; title: string; content: string; slug?: string; is_public?: boolean }) => {
      // Prime modal state
      editingPage.value = { ...page };
      modalData.title = page.title;
      modalData.slug = page.slug || '';
      modalData.isPublic = page.is_public ?? true;

      // Open modal first so layout exists
      showModal.value = true;
      await nextTick();

      // Default to any content we already have
      editor.commands.setContent(ensureHtml(page.content));

      // Load full content from backend by slug
      try {
        const slug = modalData.slug;
        if (slug) {
          const res = await http.get(`/api/pages/${slug}`);
          const content = res.data?.content ?? '';
          editor.commands.setContent(ensureHtml(content));
        }
      } catch (e) {
        // Keep whatever we set initially; do not break editing
        console.warn('Failed to load page content by slug, using existing content', e);
      }
    };

    const closeModal = () => {
      showModal.value = false;
      editingPage.value = null;
      errorMessage.value = '';
    };

    const confirmDelete = (page: { id: number; title: string }) => {
      pageToDelete.value = page;
      showDeleteModal.value = true;
    };

    const createPage = async () => {
      try {
        isLoading.value = true;
        const slug = modalData.slug || generateSlug(modalData.title);
        await http.post('/api/pages/create', {
          title: modalData.title,
          content: editor.getHTML(),
          slug: slug,
          is_public: modalData.isPublic
        });
        closeModal();
        fetchPages();
      } catch (error) {
        errorMessage.value = 'Failed to create page.';
      } finally {
        isLoading.value = false;
      }
    };

    const updatePage = async () => {
      try {
        isLoading.value = true;
        if (editingPage.value) {
          const slug = modalData.slug || generateSlug(modalData.title);
          await http.put(`/api/pages/${editingPage.value.id}`, {
            title: modalData.title,
            slug: slug,
            content: editor.getHTML(),
            is_public: modalData.isPublic
          });
          closeModal();
          fetchPages();
        }
      } catch (error) {
        errorMessage.value = 'Failed to update page.';
      } finally {
        isLoading.value = false;
      }
    };

    const deletePage = async () => {
      if (!pageToDelete.value) return;
      try {
        isLoading.value = true;
        await http.delete(`/api/pages/${pageToDelete.value.id}`);
        showDeleteModal.value = false;
        pageToDelete.value = null;
        fetchPages();
      } catch (error) {
        errorMessage.value = 'Failed to delete page.';
      } finally {
        isLoading.value = false;
      }
    };

    // Keyboard handlers
    const handleModalKeydown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (showModal.value) {
          e.stopPropagation();
          closeModal();
        } else if (showDeleteModal.value) {
          e.stopPropagation();
          showDeleteModal.value = false;
        }
      } else if (e.key === 'Enter' && !e.shiftKey) {
        if (showModal.value) {
          const target = e.target as HTMLElement;
          if (target.tagName !== 'TEXTAREA') {
            e.preventDefault();
            if (editingPage.value) {
              updatePage();
            } else {
              createPage();
            }
          }
        }
      }
    };

    onMounted(async () => {
      await fetchPages();
      window.addEventListener('keydown', handleModalKeydown);
    });

    onBeforeUnmount(() => {
      editor.destroy();
      window.removeEventListener('keydown', handleModalKeydown);
    });

    return {
      pages,
      editingPage,
      isLoading,
      errorMessage,
      isAdmin,
      currentUserId,
      showModal,
      showDeleteModal,
      pageToDelete,
      modalData,
      generateSlug,
      openCreateModal,
      openEditModal,
      closeModal,
      confirmDelete,
      createPage,
      updatePage,
      deletePage,
      editor,
      isDark,
      styleSettings,
    };
  },
});
</script>

<style scoped>
/* Pages-specific styles */

/* Modal styles */
.modal-backdrop {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: var(--color-overlay);
  z-index: 9998;
}

.modal-container {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  pointer-events: none;
}

.modal-surface {
  background-color: var(--modal-bg);
  color: var(--text-primary);
  border: 1px solid var(--modal-border);
  border-radius: var(--border-radius-md);
  box-shadow: 0 25px 50px -12px var(--card-shadow);
  padding: 1.25rem;
  width: min(90vw, 50rem);
  max-height: 90vh;
  overflow: auto;
  pointer-events: auto;
}

/* Pages grid */
.pages-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 1rem;
  margin-top: 1rem;
}

.page-card {
  padding: 1rem;
  border-radius: var(--border-radius-md);
  box-shadow: var(--card-shadow);
  transition: box-shadow 0.2s ease;
}

.page-card:hover {
  box-shadow: var(--card-hover-shadow);
}

.page-card h3 {
  margin: 0 0 0.5rem 0;
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--text-primary);
}

.page-card .meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.page-card .chip {
  padding: 0.25rem 0.5rem;
  border-radius: var(--border-radius-sm);
  font-size: 0.75rem;
  font-weight: 500;
  text-transform: uppercase;
}

.page-card .chip-public {
  background-color: var(--badge-success-bg);
  color: var(--badge-success-text);
}

.page-card .chip-private {
  background-color: var(--badge-warning-bg);
  color: var(--badge-warning-text);
}

.page-card .page-slug {
  font-size: 0.875rem;
  margin-bottom: 0.75rem;
}

.page-card .actions {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

/* Editor container */
.editor-container {
  min-height: 300px;
  max-height: 400px;
  overflow-y: auto;
  width: 100%;
  display: block;
  box-sizing: border-box;
}

/* TipTap editor styles */
.ProseMirror {
  min-height: 280px;
  outline: none;
  padding: 0.5rem 0;
  width: 100%;
  box-sizing: border-box;
}

.ProseMirror p {
  margin: 0.5rem 0;
}

.ProseMirror h1,
.ProseMirror h2,
.ProseMirror h3 {
  margin: 1rem 0 0.5rem 0;
}

.ProseMirror ul,
.ProseMirror ol {
  padding-left: 1.5rem;
}

.ProseMirror blockquote {
  border-left: 3px solid var(--card-border);
  padding-left: 1rem;
  margin: 1rem 0;
}
</style>