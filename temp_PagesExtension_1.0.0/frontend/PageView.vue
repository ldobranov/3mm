<template>
  <div class="page-view-container" v-if="!isLoading">
    <div class="page-content card" v-if="page" :style="{ backgroundColor: styleSettings.cardBg, color: styleSettings.textPrimary, borderColor: styleSettings.cardBorder }">
      <div class="page-header">
        <h1 class="page-title">{{ page.title }}</h1>
        <div class="page-meta">
          <span class="chip" :class="page.is_public ? 'chip-public' : 'chip-private'">
            {{ page.is_public ? 'Public' : 'Private' }}
          </span>
          <span v-if="page.owner_username" class="page-owner">
            by {{ page.owner_username }}
          </span>
        </div>
      </div>
      
      <div 
        class="page-body" 
        v-html="page.content"
        @click="handleContentClick"
      ></div>
    </div>

    <div v-else class="not-found text-center" style="padding: 2rem 0;">
      <h2>Page Not Found</h2>
      <p>The page you're looking for doesn't exist or you don't have access to view it.</p>
      <button 
        class="button button-primary" 
        @click="$router.push('/pages')"
      >
        Back to Pages
      </button>
    </div>

    <div v-if="errorMessage" class="error-alert" style="padding: 1rem; margin: 1rem 0; border: 1px solid var(--danger); background-color: var(--danger-bg); color: var(--danger-text); border-radius: var(--border-radius-sm);">
      {{ errorMessage }}
    </div>
  </div>

  <div v-else class="text-center" style="padding: 2rem 0;">
    <div class="spinner" role="status" aria-label="Loading"></div>
    <p>Loading page...</p>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, onMounted, computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import http from '@/utils/http';
import { useThemeStore } from '@/stores/theme';
import { useSettingsStore } from '@/stores/settings';

interface Page {
  title: string;
  content: string;
  is_public?: boolean;
  owner_username?: string;
}

export default defineComponent({
  setup() {
    const route = useRoute();
    const router = useRouter();
    const themeStore = useThemeStore();
    const settingsStore = useSettingsStore();
    
    const isDark = computed(() => themeStore.isDark());
    const styleSettings = computed(() => settingsStore.styleSettings);
    
    const page = ref<Page | null>(null);
    const isLoading = ref(true);
    const errorMessage = ref('');
    
    const fetchPage = async () => {
      const slug = route.params.slug as string;
      if (!slug) {
        errorMessage.value = 'Invalid page slug';
        isLoading.value = false;
        return;
      }

      try {
        isLoading.value = true;
        errorMessage.value = '';
        
        const response = await http.get(`/api/pages/${slug}`);
        page.value = response.data;
        
      } catch (error: any) {
        console.error('Failed to fetch page:', error);
        const status = error?.response?.status;
        
        if (status === 404) {
          page.value = null; // Page not found
        } else if (status === 401) {
          errorMessage.value = 'You need to be logged in to view this page.';
        } else if (status === 403) {
          errorMessage.value = 'You do not have permission to view this page.';
        } else {
          errorMessage.value = 'Failed to load page. Please try again later.';
        }
      } finally {
        isLoading.value = false;
      }
    };

    const handleContentClick = (event: MouseEvent) => {
      // Handle any custom click events in the content if needed
      // For example, external links, etc.
      const target = event.target as HTMLElement;
      if (target.tagName === 'A') {
        const link = target as HTMLAnchorElement;
        if (link.href?.startsWith('http')) {
          // Open external links in new tab
          window.open(link.href, '_blank');
          event.preventDefault();
        }
      }
    };

    onMounted(() => {
      fetchPage();
    });

    return {
      page,
      isLoading,
      errorMessage,
      styleSettings,
      handleContentClick,
      isDark,
    };
  },
});
</script>

<style scoped>
.page-view-container {
  max-width: 800px;
  margin: 0 auto;
  padding: 1rem;
}

.page-content {
  padding: 2rem;
  border-radius: var(--border-radius-md);
  box-shadow: var(--card-shadow);
}

.page-header {
  margin-bottom: 2rem;
  border-bottom: 1px solid var(--card-border);
  padding-bottom: 1rem;
}

.page-title {
  margin: 0 0 0.5rem 0;
  font-size: 2rem;
  font-weight: 700;
  color: var(--text-primary);
}

.page-meta {
  display: flex;
  align-items: center;
  gap: 1rem;
  color: var(--text-secondary);
}

.chip {
  padding: 0.25rem 0.5rem;
  border-radius: var(--border-radius-sm);
  font-size: 0.75rem;
  font-weight: 500;
  text-transform: uppercase;
}

.chip-public {
  background-color: var(--badge-success-bg);
  color: var(--badge-success-text);
}

.chip-private {
  background-color: var(--badge-warning-bg);
  color: var(--badge-warning-text);
}

.page-owner {
  font-size: 0.875rem;
}

.page-body {
  color: var(--text-primary);
  line-height: 1.6;
}

/* Content styling for the page body */
.page-body :deep(h1) {
  font-size: 1.5rem;
  margin: 1.5rem 0 1rem 0;
  color: var(--text-primary);
}

.page-body :deep(h2) {
  font-size: 1.25rem;
  margin: 1.25rem 0 0.75rem 0;
  color: var(--text-primary);
}

.page-body :deep(h3) {
  font-size: 1.125rem;
  margin: 1rem 0 0.5rem 0;
  color: var(--text-primary);
}

.page-body :deep(p) {
  margin: 1rem 0;
  color: var(--text-primary);
}

.page-body :deep(ul),
.page-body :deep(ol) {
  margin: 1rem 0;
  padding-left: 1.5rem;
  color: var(--text-primary);
}

.page-body :deep(li) {
  margin: 0.25rem 0;
}

.page-body :deep(blockquote) {
  border-left: 3px solid var(--card-border);
  padding-left: 1rem;
  margin: 1rem 0;
  font-style: italic;
  color: var(--text-secondary);
}

.page-body :deep(code) {
  background-color: var(--code-bg);
  color: var(--code-text);
  padding: 0.125rem 0.25rem;
  border-radius: var(--border-radius-sm);
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 0.875em;
}

.page-body :deep(pre) {
  background-color: var(--code-bg);
  color: var(--code-text);
  padding: 1rem;
  border-radius: var(--border-radius-sm);
  overflow-x: auto;
  margin: 1rem 0;
}

.page-body :deep(pre code) {
  background: none;
  padding: 0;
}

.page-body :deep(a) {
  color: var(--link-color);
  text-decoration: none;
}

.page-body :deep(a:hover) {
  color: var(--link-hover-color);
  text-decoration: underline;
}

.not-found {
  text-align: center;
  color: var(--text-primary);
}

.not-found h2 {
  color: var(--text-primary);
  margin-bottom: 1rem;
}

.not-found p {
  color: var(--text-secondary);
  margin-bottom: 2rem;
}

.error-alert {
  background-color: var(--danger-bg);
  color: var(--danger-text);
  border: 1px solid var(--danger);
  border-radius: var(--border-radius-sm);
}

@media (max-width: 768px) {
  .page-view-container {
    padding: 0.5rem;
  }
  
  .page-content {
    padding: 1.5rem;
  }
  
  .page-title {
    font-size: 1.5rem;
  }
}
</style>