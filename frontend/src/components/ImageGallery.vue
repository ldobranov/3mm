<template>
  <div class="image-gallery">
    <!-- Gallery Header -->
    <div v-if="title" class="gallery-header">
      <h4>{{ title }}</h4>
      <span v-if="images.length > 0" class="image-count">
        {{ t('common.imageCount', '{count} images', { count: images.length.toString() }) }}
      </span>
    </div>

    <!-- Images Grid -->
    <div v-if="images.length > 0" class="images-grid" :class="gridClass">
      <div
        v-for="(image, index) in images"
        :key="getImageKey(image, index)"
        class="image-item"
        :class="{ 'removable': removable }"
      >
        <!-- Image -->
        <div class="image-container">
          <img
            :src="getImageUrl(image)"
            :alt="getImageAlt(image)"
            class="image-preview"
            @error="(event) => handleImageError(event, index)"
            @load="() => handleImageLoad(index)"
          />

          <!-- Loading placeholder -->
          <div v-if="loadingStates[index]" class="image-loading">
            <div class="loading-spinner"></div>
          </div>

          <!-- Remove button -->
          <button
            v-if="removable"
            type="button"
            class="remove-btn"
            @click="removeImage(index)"
            :title="t('common.removeImage', 'Remove image')"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"/>
              <line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>

        <!-- Image info -->
        <div v-if="showInfo" class="image-info">
          <div class="image-name" :title="getImageName(image)">
            {{ getImageName(image) }}
          </div>
          <div v-if="showSize" class="image-size">
            {{ getImageSize(image) }}
          </div>
        </div>
      </div>
    </div>

    <!-- Empty state -->
    <div v-else-if="showEmptyState" class="empty-state">
      <div class="empty-icon">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1">
          <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
          <circle cx="9" cy="9" r="2"/>
          <path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/>
        </svg>
      </div>
      <p class="empty-text">{{ emptyText || t('common.noImages', 'No images uploaded yet') }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useI18n } from '@/utils/i18n';
import http from '@/utils/dynamic-http';

const { t } = useI18n();

// Props
interface ImageData {
  url?: string;
  filename?: string;
  name?: string;
  size?: number;
  [key: string]: any;
}

interface Props {
  images?: ImageData[];
  title?: string;
  removable?: boolean;
  showInfo?: boolean;
  showSize?: boolean;
  showEmptyState?: boolean;
  emptyText?: string;
  gridColumns?: number;
  maxHeight?: string;
}

const props = withDefaults(defineProps<Props>(), {
  images: () => [],
  removable: true,
  showInfo: true,
  showSize: true,
  showEmptyState: true,
  gridColumns: 4,
  maxHeight: '400px'
});

// Emits
const emit = defineEmits<{
  'remove': [index: number, image: ImageData];
}>();

// Reactive data
const loadingStates = ref<Record<number, boolean>>({});

// Computed properties
const gridClass = computed(() => {
  return `grid-${Math.min(props.gridColumns, 6)}`;
});

// Reactive data
const backendUrl = ref('');

// Methods
const getImageKey = (image: ImageData, index: number): string => {
  return image.url || image.filename || `image-${index}`;
};

const getImageUrl = (image: ImageData): string => {
  let url = image.url || '';

  // Convert relative URLs to full URLs
  if (url.startsWith('/uploads')) {
    // Use dynamic backend URL instead of hardcoded localhost
    if (backendUrl.value) {
      url = `${backendUrl.value}${url}`;
    } else {
      // Fallback to localhost if backend URL not yet determined
      url = `http://localhost:8887${url}`;
    }
  }

  return url;
};

// Load backend URL on component mount
const loadBackendUrl = async () => {
  try {
    backendUrl.value = await http.getCurrentBackendUrl();
  } catch (error) {
    console.warn('Could not load backend URL, using fallback:', error);
    // Will use localhost fallback
  }
};

const getImageAlt = (image: ImageData): string => {
  return image.filename || image.name || 'Image';
};

const getImageName = (image: ImageData): string => {
  return image.filename || image.name || 'Unnamed image';
};

const getImageSize = (image: ImageData): string => {
  if (!image.size) return '';

  const bytes = image.size;
  if (bytes === 0) return '0 B';

  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));

  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
};

const removeImage = (index: number) => {
  const image = props.images[index];
  emit('remove', index, image);
};

const handleImageLoad = (index: number) => {
  loadingStates.value[index] = false;
};

const handleImageError = (event: Event, index: number) => {
  loadingStates.value[index] = false;
  const img = event.target as HTMLImageElement;
  img.src = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjQiIGhlaWdodD0iMjQiIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPHJlY3QgeD0iMyIgeT0iMyIgd2lkdGg9IjE4IiBoZWlnaHQ9IjE4IiByeD0iMiIgcnk9IjIiIHN0cm9rZT0iI2NjYyIgc3Ryb2tlLXdpZHRoPSIyIi8+CjxsaW5lIHgxPSIxNSIgeTE9IjkiIHgyPSI5IiB5Mj0iMTUiIHN0cm9rZT0iI2NjYyIgc3Ryb2tlLXdpZHRoPSIyIi8+CjxsaW5lIHgxPSI5IiB5MT0iOSIgeDI9IjE1IiB5Mj0iMTUiIHN0cm9rZT0iI2NjYyIgc3Ryb2tlLXdpZHRoPSIyIi8+Cjwvc3ZnPgo=';
};

// Load backend URL when component is mounted
onMounted(() => {
  loadBackendUrl();
});
</script>

<style scoped>
.image-gallery {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.gallery-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid var(--card-border, #e3e3e3);
}

.gallery-header h4 {
  margin: 0;
  color: var(--text-primary, #222222);
  font-size: 1rem;
  font-weight: 500;
}

.image-count {
  font-size: 0.875rem;
  color: var(--text-secondary, #666666);
}

.images-grid {
  display: grid;
  gap: 1rem;
  max-height: v-bind(maxHeight);
  overflow-y: auto;
}

.images-grid.grid-1 { grid-template-columns: 1fr; }
.images-grid.grid-2 { grid-template-columns: repeat(2, 1fr); }
.images-grid.grid-3 { grid-template-columns: repeat(3, 1fr); }
.images-grid.grid-4 { grid-template-columns: repeat(4, 1fr); }
.images-grid.grid-5 { grid-template-columns: repeat(5, 1fr); }
.images-grid.grid-6 { grid-template-columns: repeat(6, 1fr); }

.image-item {
  position: relative;
  display: flex;
  flex-direction: column;
  border-radius: var(--border-radius-md, 8px);
  overflow: hidden;
  background: var(--card-bg, #ffffff);
  border: 1px solid var(--card-border, #e3e3e3);
  transition: all 0.2s ease;
}

.image-item:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.image-item.removable:hover .remove-btn {
  opacity: 1;
}

.image-container {
  position: relative;
  width: 100%;
  height: 120px;
  overflow: hidden;
}

.image-preview {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.2s ease;
}

.image-item:hover .image-preview {
  transform: scale(1.05);
}

.image-loading {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.8);
}

.loading-spinner {
  width: 24px;
  height: 24px;
  border: 2px solid var(--card-border, #e3e3e3);
  border-top: 2px solid var(--button-primary-bg, #007bff);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.remove-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--error-bg, #dc3545);
  color: white;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: all 0.2s ease;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
}

.remove-btn:hover {
  background: var(--error-hover, #c82333);
  transform: scale(1.1);
}

.image-info {
  padding: 0.75rem;
  background: var(--card-bg, #ffffff);
}

.image-name {
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--text-primary, #222222);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 0.25rem;
}

.image-size {
  font-size: 0.75rem;
  color: var(--text-secondary, #666666);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem 1rem;
  text-align: center;
  color: var(--text-secondary, #666666);
}

.empty-icon {
  margin-bottom: 1rem;
  opacity: 0.5;
}

.empty-text {
  margin: 0;
  font-size: 0.875rem;
}

/* Responsive Design */
@media (max-width: 768px) {
  .images-grid.grid-4,
  .images-grid.grid-5,
  .images-grid.grid-6 {
    grid-template-columns: repeat(3, 1fr);
  }

  .images-grid.grid-3 {
    grid-template-columns: repeat(2, 1fr);
  }

  .gallery-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 0.5rem;
  }

  .image-container {
    height: 100px;
  }
}

@media (max-width: 480px) {
  .images-grid {
    grid-template-columns: 1fr !important;
  }

  .image-container {
    height: 120px;
  }
}
</style>