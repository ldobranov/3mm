<template>
  <div class="advanced-image-upload">
    <!-- Main Tabs -->
    <div class="tabs">
      <button
        type="button"
        class="tab-button"
        :class="{ active: activeTab === 'upload' }"
        @click="activeTab = 'upload'"
      >
        {{ t('common.uploadNew', 'Upload New') }}
      </button>
      <button
        type="button"
        class="tab-button"
        :class="{ active: activeTab === 'library' }"
        @click="activeTab = 'library'; loadImageLibrary();"
      >
        {{ t('common.imageLibrary', 'Image Library') }}
      </button>
    </div>

    <!-- Upload Tab -->
    <div v-if="activeTab === 'upload'" class="upload-section">
      <div v-if="!selectedFile && !editingLibraryImage" class="upload-area" @click="triggerFileSelect" :class="{ 'disabled': disabled }">
        <input
          ref="fileInput"
          type="file"
          accept="image/*"
          @change="handleFileSelect"
          style="display: none"
          :disabled="disabled"
        />

        <div class="upload-icon">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/>
            <polyline points="14,2 14,8 20,8"/>
            <line x1="16" y1="13" x2="8" y2="13"/>
            <line x1="16" y1="17" x2="8" y2="17"/>
            <polyline points="10,9 9,9 8,9"/>
          </svg>
        </div>

        <p class="upload-text">
          {{ t('common.clickToUpload', 'Click to upload or drag and drop') }}
        </p>
        <p class="file-types" v-if="maxSize > 0">
          {{ t('common.maxSizeHint', 'Max {size}MB, Images only', { size: maxSize.toString() }) }}
        </p>
      </div>

      <!-- Image Preview and Editing -->
      <div v-if="selectedFile || editingLibraryImage" class="image-editor">
        <div class="editor-header">
           <h3>{{ editingLibraryImage ? t('common.editExistingImage', 'Edit Existing Image') : t('common.editImage', 'Edit Image') }}</h3>
           <div class="editor-actions">
             <button type="button" class="action-button" @click="cancelEdit" v-if="editingLibraryImage">
               <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                 <path d="M18 6L6 18"/>
                 <path d="M6 6l12 12"/>
               </svg>
               {{ t('common.cancel', 'Cancel') }}
             </button>
             <button type="button" class="action-button" @click="resetCrop">
               <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                 <polyline points="1,4 1,10 7,10"/>
                 <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/>
               </svg>
               {{ t('common.reset', 'Reset') }}
             </button>
             <button type="button" class="action-button primary" @click="applyCrop">
               <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                 <polyline points="9,11 12,14 22,4"/>
                 <path d="M21,12v7a2,2,0,0,1-2,2H5a2,2,0,0,1-2-2V5a2,2,0,0,1,2-2h14"/>
               </svg>
               {{ editingLibraryImage ? t('common.saveChanges', 'Save Changes') : t('common.apply', 'Apply') }}
             </button>
           </div>
         </div>

        <div class="cropper-container" ref="cropperContainer">
          <canvas
            ref="cropperCanvas"
            class="cropper-canvas"
            @mousedown="startCrop"
            @mousemove="updateCrop"
            @mouseup="endCrop"
            @touchstart="startCrop"
            @touchmove="updateCrop"
            @touchend="endCrop"
          ></canvas>
        </div>

        <div class="editor-controls">
          <div class="control-group">
            <label>{{ t('common.aspectRatio', 'Aspect Ratio') }}</label>
            <select v-model="aspectRatio" @change="updateAspectRatio">
              <option value="free">{{ t('common.free', 'Free') }}</option>
              <option value="1/1">{{ t('common.square', 'Square (1:1)') }}</option>
              <option value="4/3">{{ t('common.landscape', 'Landscape (4:3)') }}</option>
              <option value="3/4">{{ t('common.portrait', 'Portrait (3:4)') }}</option>
              <option value="16/9">{{ t('common.widescreen', 'Widescreen (16:9)') }}</option>
            </select>
          </div>

          <div class="control-group">
            <label>{{ t('common.zoom', 'Zoom') }}</label>
            <input
              type="range"
              min="0.1"
              max="3"
              step="0.1"
              v-model="zoomLevel"
              @input="updateZoom"
            />
          </div>
        </div>
      </div>
    </div>

    <!-- Image Library Tab -->
    <div v-if="activeTab === 'library'" class="library-section">
      <!-- Breadcrumb Navigation -->
      <div v-if="breadcrumb.length > 1" class="breadcrumb">
        <button
          type="button"
          class="back-button"
          @click="goBack"
          :title="t('common.goBack', 'Go Back')"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M19 12H5"/>
            <path d="M12 19l-7-7 7-7"/>
          </svg>
          {{ t('common.back', 'Back') }}
        </button>
        <button
          type="button"
          v-for="(crumb, index) in breadcrumb"
          :key="crumb.path"
          class="breadcrumb-item"
          :class="{ active: index === breadcrumb.length - 1 }"
          @click="navigateToFolder(crumb.path)"
        >
          {{ crumb.name }}
        </button>
      </div>

      <!-- Library Controls -->
      <div class="library-controls">
        <div class="search-container">
          <input
            type="text"
            v-model="searchQuery"
            @input="debouncedSearch"
            :placeholder="t('common.searchImages', 'Search images...')"
            class="search-input"
          />
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8"/>
            <path d="m21 21-4.35-4.35"/>
          </svg>
        </div>

        <div class="control-buttons">
           <button
             type="button"
             class="create-folder-btn"
             @click="showCreateFolderDialog = true"
             v-if="canCreateFolder"
           >
             <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
               <path d="M12 5v14"/>
               <path d="M5 12h14"/>
             </svg>
             {{ t('common.createFolder', 'Create Folder') }}
           </button>

           <!-- Multiple selection confirm button -->
           <button
             type="button"
             class="confirm-selection-btn"
             v-if="props.multiple && Array.isArray(selectedLibraryImage) && selectedLibraryImage.length > 0"
             @click="confirmImageSelection"
           >
             <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
               <polyline points="9,11 12,14 22,4"/>
               <path d="M21,12v7a2,2,0,0,1-2,2H5a2,2,0,0,1-2-2V5a2,2,0,0,1,2-2h14"/>
             </svg>
             {{ t('common.confirmSelection', 'Confirm Selection') }} ({{ selectedLibraryImage.length }})
           </button>

           <div class="view-controls">
             <button
               type="button"
               class="view-toggle"
               :class="{ active: viewMode === 'grid' }"
               @click="viewMode = 'grid'"
             >
               <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                 <rect width="7" height="7" x="3" y="3" rx="1"/>
                 <rect width="7" height="7" x="14" y="3" rx="1"/>
                 <rect width="7" height="7" x="14" y="14" rx="1"/>
                 <rect width="7" height="7" x="3" y="14" rx="1"/>
               </svg>
             </button>
             <button
               type="button"
               class="view-toggle"
               :class="{ active: viewMode === 'list' }"
               @click="viewMode = 'list'"
             >
               <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                 <line x1="8" x2="21" y1="6" y2="6"/>
                 <line x1="8" x2="21" y1="12" y2="12"/>
                 <line x1="8" x2="21" y1="18" y2="18"/>
                 <line x1="3" x2="3.01" y1="6" y2="6"/>
                 <line x1="3" x2="3.01" y1="12" y2="12"/>
                 <line x1="3" x2="3.01" y1="18" y2="18"/>
               </svg>
             </button>
           </div>
         </div>
      </div>

      <!-- Library Stats -->
      <div v-if="!loadingLibrary && filteredImages.length > 0" class="library-stats">
        <span>{{ t('common.showing', 'Showing') }} {{ displayedImages.length }} {{ t('common.of', 'of') }} {{ filteredImages.length }} {{ t('common.images', 'images') }}</span>
      </div>

      <!-- Loading State -->
      <div v-if="loadingLibrary" class="loading-indicator">
        <div class="spinner"></div>
        <p>{{ t('common.loadingImages', 'Loading images...') }}</p>
      </div>

      <!-- Empty State -->
      <div v-else-if="libraryImages.length === 0 && folders.length === 0" class="empty-library">
        <p>{{ t('common.noImagesFound', 'No images found in your library') }}</p>
        <button type="button" class="upload-button" @click="activeTab = 'upload'">
          {{ t('common.uploadFirstImage', 'Upload your first image') }}
        </button>
      </div>

      <!-- Image Library -->
      <div v-else class="image-library">
        <!-- Grid View -->
        <div v-if="viewMode === 'grid'" class="image-grid">
          <!-- Folders -->
          <div
            v-for="folder in folders"
            :key="`folder-${folder.path}`"
            class="folder-card"
            @click="selectFolder(folder)"
            @dragover.prevent
            @drop="handleFolderDrop($event, folder)"
            @dragenter="handleFolderDragEnter($event, folder)"
            @dragleave="handleFolderDragLeave($event, folder)"
            :class="{ 'drop-target': dropTargetFolder === folder.path }"
          >
            <div class="folder-preview">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z"/>
              </svg>
            </div>
            <div class="folder-info">
              <span class="folder-name" :title="folder.name">
                {{ folder.name }}
              </span>
              <span class="folder-count">{{ folder.image_count }} {{ t('common.images', 'images') }}</span>
            </div>
          </div>

          <!-- Images -->
          <div
            v-for="(image, index) in displayedImages"
            :key="image.url"
            class="image-card"
            :class="{
              selected: props.multiple
                ? (Array.isArray(selectedLibraryImage) && selectedLibraryImage.includes(image.url))
                : selectedLibraryImage === image.url
            }"
            draggable="true"
            @dragstart="handleImageDragStart($event, image)"
            @click="selectLibraryImage(image)"
          >
            <div class="image-preview">
              <img
                :src="getImageUrl(image.url)"
                :alt="image.name || 'Uploaded image'"
                loading="lazy"
              />
            </div>
            <div class="image-info">
              <span class="image-name" :title="image.name || t('common.untitled', 'Untitled')">
                {{ image.name || t('common.untitled', 'Untitled') }}
              </span>
              <span class="image-size">{{ formatFileSize(image.size || 0) }}</span>
            </div>
            <div class="image-actions">
               <button type="button" class="edit-button" @click.stop="editImage(image)" :title="t('common.edit', 'Edit')">
                 <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                   <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                   <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                 </svg>
               </button>
               <button type="button" class="rename-button" @click.stop="openRenameDialog(image)" v-if="canCreateFolder" :title="t('common.rename', 'Rename')">
                 <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                   <path d="M12 20h9"/>
                   <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>
                 </svg>
               </button>
               <button type="button" class="delete-button" @click.stop="openDeleteDialog(image)" v-if="canCreateFolder" :title="t('common.delete', 'Delete')">
                 <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                   <path d="M3 6h18"/>
                   <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/>
                   <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>
                 </svg>
               </button>
               <button type="button" class="select-button" @click.stop="selectLibraryImage(image)">
                 {{ (props.multiple
                     ? (Array.isArray(selectedLibraryImage) && selectedLibraryImage.includes(image.url))
                     : selectedLibraryImage === image.url)
                   ? t('common.selected', 'Selected') : t('common.select', 'Select') }}
               </button>
             </div>
          </div>
        </div>

        <!-- List View -->
        <div v-else class="image-list">
          <!-- Folders -->
          <div
            v-for="folder in folders"
            :key="`folder-${folder.path}`"
            class="folder-list-item"
            @click="selectFolder(folder)"
          >
            <div class="list-folder-preview">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z"/>
              </svg>
            </div>
            <div class="list-folder-info">
              <div class="list-folder-name">{{ folder.name }}</div>
              <div class="list-folder-meta">
                <span class="folder-count">{{ folder.image_count }} {{ t('common.images', 'images') }}</span>
              </div>
            </div>
            <button type="button" class="open-folder-button" @click.stop="selectFolder(folder)">
              {{ t('common.open', 'Open') }}
            </button>
          </div>

          <!-- Images -->
          <div
            v-for="(image, index) in displayedImages"
            :key="image.url"
            class="image-list-item"
            :class="{ selected: selectedLibraryImage === image.url }"
            @click="selectLibraryImage(image)"
          >
            <div class="list-image-preview">
              <img
                :src="getImageUrl(image.url)"
                :alt="image.name || 'Uploaded image'"
                loading="lazy"
              />
            </div>
            <div class="list-image-info">
              <div class="list-image-name">{{ image.name || t('common.untitled', 'Untitled') }}</div>
              <div class="list-image-meta">
                <span class="image-size">{{ formatFileSize(image.size || 0) }}</span>
                <span class="image-date" v-if="image.uploaded_at">
                  {{ formatDate(image.uploaded_at) }}
                </span>
              </div>
            </div>
            <button type="button" class="select-button" @click.stop="selectLibraryImage(image)">
              {{ selectedLibraryImage === image.url ? t('common.selected', 'Selected') : t('common.select', 'Select') }}
            </button>
          </div>
        </div>

        <!-- Pagination -->
        <div v-if="totalPages > 1" class="pagination">
          <button
            type="button"
            class="page-button"
            :disabled="currentPage === 1"
            @click="currentPage--"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="m15 18-6-6 6-6"/>
            </svg>
          </button>

          <span class="page-info">
            {{ t('common.page', 'Page') }} {{ currentPage }} {{ t('common.of', 'of') }} {{ totalPages }}
          </span>

          <button
            type="button"
            class="page-button"
            :disabled="currentPage === totalPages"
            @click="currentPage++"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="m9 18 6-6-6-6"/>
            </svg>
          </button>
        </div>

        <!-- Load More (Alternative to pagination) -->
        <div v-if="hasMoreImages && !showPagination" class="load-more">
          <button
            type="button"
            class="load-more-button"
            @click="loadMoreImages"
            :disabled="loadingMore"
          >
            {{ loadingMore ? t('common.loading', 'Loading...') : t('common.loadMore', 'Load More') }}
          </button>
        </div>
      </div>
    </div>

    <!-- Upload Progress -->
    <div v-if="uploading" class="upload-progress">
      <div class="progress-bar">
        <div class="progress-fill" :style="{ width: uploadProgress + '%' }"></div>
      </div>
      <span class="progress-text">{{ uploadProgress }}% - {{ t('common.uploading', 'Uploading...') }}</span>
    </div>

    <!-- Error Messages -->
    <div v-if="errorMessage" class="error-message">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10"/>
        <line x1="15" y1="9" x2="9" y2="15"/>
        <line x1="9" y1="9" x2="15" y2="15"/>
      </svg>
      {{ errorMessage }}
    </div>

    <!-- Confirmation Dialog -->
    <div v-if="showConfirmDialog" class="confirmation-dialog">
      <div class="dialog-content">
        <h3>{{ t('common.confirmSelection', 'Confirm Image Selection') }}</h3>
        <p>{{ t('common.confirmUseImage', 'Are you sure you want to use this image?') }}</p>
        <div class="dialog-actions">
           <button type="button" class="cancel-button" @click="showConfirmDialog = false">
             {{ t('common.cancel', 'Cancel') }}
           </button>
           <button type="button" class="confirm-button" @click="confirmImageSelection">
             {{ t('common.confirm', 'Confirm') }}
           </button>
         </div>
      </div>
    </div>

    <!-- Create Folder Dialog -->
    <div v-if="showCreateFolderDialog" class="confirmation-dialog">
      <div class="dialog-content">
        <h3>{{ t('common.createFolder', 'Create Folder') }}</h3>
        <div class="form-group">
          <label for="folder-name">{{ t('common.folderName', 'Folder Name') }}</label>
          <input
            id="folder-name"
            v-model="newFolderName"
            type="text"
            class="input"
            :placeholder="t('common.enterFolderName', 'Enter folder name')"
            @keyup.enter="createFolder"
          />
        </div>
        <div class="dialog-actions">
           <button type="button" class="cancel-button" @click="showCreateFolderDialog = false; newFolderName = ''">
             {{ t('common.cancel', 'Cancel') }}
           </button>
           <button type="button" class="confirm-button" @click="createFolder" :disabled="!newFolderName.trim()">
             {{ t('common.create', 'Create') }}
           </button>
         </div>
      </div>
    </div>

    <!-- Move Image Dialog -->
    <div v-if="showMoveDialog" class="confirmation-dialog">
      <div class="dialog-content">
        <h3>{{ t('common.moveImage', 'Move Image') }}</h3>
        <p v-if="imageToMove">{{ t('common.moveImageConfirm', 'Move "' + imageToMove.name + '" to:', {}) }}</p>
        <div class="form-group">
          <label for="move-destination">{{ t('common.destinationFolder', 'Destination Folder') }}</label>
          <input
            id="move-destination"
            v-model="moveDestination"
            type="text"
            class="input"
            :placeholder="t('common.enterDestinationFolder', 'Enter destination folder (e.g., store/folder1)')"
            @keyup.enter="moveImage"
          />
        </div>
        <div class="dialog-actions">
            <button type="button" class="cancel-button" @click="showMoveDialog = false; imageToMove = null; moveDestination = ''">
              {{ t('common.cancel', 'Cancel') }}
            </button>
            <button type="button" class="confirm-button" @click="moveImage" :disabled="!moveDestination.trim()">
              {{ t('common.move', 'Move') }}
            </button>
          </div>
      </div>
    </div>

    <!-- Delete Image Dialog -->
    <div v-if="showDeleteDialog" class="confirmation-dialog">
      <div class="dialog-content">
        <h3>{{ t('common.deleteImage', 'Delete Image') }}</h3>
        <p v-if="imageToDelete">{{ t('common.deleteImageConfirm', 'Are you sure you want to delete "' + imageToDelete.name + '"? This action cannot be undone.', {}) }}</p>
        <div class="dialog-actions">
            <button type="button" class="cancel-button" @click="showDeleteDialog = false; imageToDelete = null">
              {{ t('common.cancel', 'Cancel') }}
            </button>
            <button type="button" class="delete-confirm-button" @click="deleteImage">
              {{ t('common.delete', 'Delete') }}
            </button>
          </div>
      </div>
    </div>

    <!-- Rename Image Dialog -->
    <div v-if="showRenameDialog" class="confirmation-dialog">
      <div class="dialog-content">
        <h3>{{ t('common.renameImage', 'Rename Image') }}</h3>
        <div class="form-group">
          <label for="new-image-name">{{ t('common.newName', 'New Name') }}</label>
          <input
            id="new-image-name"
            v-model="newImageName"
            type="text"
            class="input"
            :placeholder="t('common.enterNewName', 'Enter new name')"
            @keyup.enter="renameImage"
          />
        </div>
        <div class="dialog-actions">
            <button type="button" class="cancel-button" @click="showRenameDialog = false; imageToRename = null; newImageName = ''">
              {{ t('common.cancel', 'Cancel') }}
            </button>
            <button type="button" class="confirm-button" @click="renameImage" :disabled="!newImageName.trim()">
              {{ t('common.rename', 'Rename') }}
            </button>
          </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
// Extension configuration mapping (outside setup for defineProps access)
const extensionConfig: Record<string, { displayName: string; description: string }> = {
  'store': { displayName: 'Store', description: 'Product images and media' },
  'settings': { displayName: 'Settings', description: 'Application settings and logos' },
  'blog': { displayName: 'Blog', description: 'Blog posts and articles' },
  'gallery': { displayName: 'Gallery', description: 'Photo gallery and media' }
};
</script>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue';
import { useI18n } from '@/utils/i18n';
import http from '@/utils/dynamic-http';

const { t } = useI18n();

// Props
interface Props {
  modelValue?: string | string[];
  uploadUrl?: string;
  maxSize?: number; // in MB
  disabled?: boolean;
  imageLibraryUrl?: string;
  uploadDirectory?: string;
  multiple?: boolean;
  extensionName?: string; // Extension identifier (e.g., 'store', 'blog', 'gallery')
  extensionDisplayName?: string; // Human-readable name (e.g., 'Store', 'Blog', 'Gallery')
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '',
  uploadUrl: '/api/upload',
  maxSize: 5,
  disabled: false,
  imageLibraryUrl: '/api/images/list',
  uploadDirectory: 'uploads',
  multiple: false,
  extensionName: 'store', // Default to store for backward compatibility
  extensionDisplayName: extensionConfig['store'].displayName // Use semantic display name
});

// Emits
const emit = defineEmits<{
  'update:modelValue': [value: string | string[]];
  'upload-success': [file: { url: string; filename: string; size: number }];
  'upload-error': [error: string];
  'image-selected': [image: { url: string; filename: string; size: number }];
  'images-selected': [images: Array<{ url: string; filename: string; size: number }> ];
}>();

// Reactive data
const fileInput = ref<HTMLInputElement>();
const cropperContainer = ref<HTMLDivElement>();
const cropperCanvas = ref<HTMLCanvasElement>();
const activeTab = ref<'upload' | 'library'>('upload');
const selectedFile = ref<File | null>(null);
const originalImage = ref<HTMLImageElement | null>(null);
const aspectRatio = ref<'free' | '1/1' | '4/3' | '3/4' | '16/9'>('free');
const zoomLevel = ref(1);
const uploading = ref(false);
const uploadProgress = ref(0);
const errorMessage = ref('');
const libraryImages = ref<Array<{ url: string; name: string; size: number; uploaded_at?: string }>>([]);
const loadingLibrary = ref(false);
const selectedLibraryImage = ref<string | string[] | null>(null);
const showConfirmDialog = ref(false);

// Canvas cropping state
const isCropping = ref(false);
const cropStartX = ref(0);
const cropStartY = ref(0);
const cropEndX = ref(0);
const cropEndY = ref(0);
const canvasOffsetX = ref(0);
const canvasOffsetY = ref(0);
const canvasScale = ref(1);

// Library browsing state
const searchQuery = ref('');
const viewMode = ref<'grid' | 'list'>('grid');
const currentPage = ref(1);
const itemsPerPage = ref(20);
const loadingMore = ref(false);
const showPagination = ref(true); // Can be toggled based on preference

// Folder navigation state
const currentDirectory = ref(props.extensionName);
const breadcrumb = ref<Array<{name: string, path: string}>>([{name: props.extensionDisplayName || extensionConfig[props.extensionName]?.displayName || props.extensionName, path: props.extensionName}]);
const folders = ref<Array<{name: string, path: string, type: string, image_count: number, modified: string, directory: string}>>([]);
const canCreateFolder = ref(false);
const showCreateFolderDialog = ref(false);
const newFolderName = ref('');
const showMoveDialog = ref(false);
const imageToMove = ref<{ url: string; name: string } | null>(null);
const moveDestination = ref('');
const showDeleteDialog = ref(false);
const imageToDelete = ref<{ url: string; name: string } | null>(null);
const showRenameDialog = ref(false);
const imageToRename = ref<{ url: string; name: string } | null>(null);
const newImageName = ref('');
const dropTargetFolder = ref<string | null>(null);
const draggedImage = ref<{ url: string; name: string } | null>(null);
const editingLibraryImage = ref<{ url: string; name: string } | null>(null);

// Computed
const maxSizeInBytes = props.maxSize * 1024 * 1024;

// Library computed properties
const filteredImages = computed(() => {
  if (!searchQuery.value) return libraryImages.value;

  const query = searchQuery.value.toLowerCase();
  return libraryImages.value.filter(image =>
    (image.name || '').toLowerCase().includes(query) ||
    image.url.toLowerCase().includes(query)
  );
});

const displayedImages = computed(() => {
  if (!showPagination.value) return filteredImages.value;

  const start = (currentPage.value - 1) * itemsPerPage.value;
  const end = start + itemsPerPage.value;
  return filteredImages.value.slice(start, end);
});

const totalPages = computed(() => {
  return Math.ceil(filteredImages.value.length / itemsPerPage.value);
});

const hasMoreImages = computed(() => {
  return displayedImages.value.length < filteredImages.value.length;
});

// Methods
const triggerFileSelect = () => {
  if (!props.disabled && fileInput.value) {
    fileInput.value.click();
  }
};

const handleFileSelect = (event: Event) => {
  const target = event.target as HTMLInputElement;
  const files = target.files;

  if (files && files.length > 0) {
    const file = files[0];

    // Validate file
    if (!validateFile(file)) {
      return;
    }

    selectedFile.value = file;

    // Load image and initialize canvas
    loadImageForCropping(file);
  }
};

const validateFile = (file: File): boolean => {
  // Check if it's an image
  if (!file.type.startsWith('image/')) {
    errorMessage.value = t('common.invalidImageType', 'Please select an image file');
    return false;
  }

  // Check file size
  if (file.size > maxSizeInBytes) {
    errorMessage.value = t('common.fileTooLarge', 'File is too large. Max {size}MB', { size: props.maxSize.toString() });
    return false;
  }

  errorMessage.value = '';
  return true;
};

const loadImageForCropping = (file: File) => {
  const img = new Image();
  const url = URL.createObjectURL(file);

  img.onload = () => {
    originalImage.value = img;
    initializeCanvas();
    URL.revokeObjectURL(url);
  };

  img.src = url;
};

const initializeCanvas = () => {
  if (!cropperCanvas.value || !originalImage.value || !cropperContainer.value) return;

  const canvas = cropperCanvas.value;
  const container = cropperContainer.value;
  const img = originalImage.value;

  // Set canvas size to container size
  const containerRect = container.getBoundingClientRect();
  canvas.width = containerRect.width;
  canvas.height = containerRect.height;

  // Calculate scale to fit image in canvas
  const scaleX = canvas.width / img.width;
  const scaleY = canvas.height / img.height;
  canvasScale.value = Math.min(scaleX, scaleY);

  // Center the image
  canvasOffsetX.value = (canvas.width - img.width * canvasScale.value) / 2;
  canvasOffsetY.value = (canvas.height - img.height * canvasScale.value) / 2;

  drawCanvas();
};

const drawCanvas = () => {
  if (!cropperCanvas.value || !originalImage.value) return;

  const canvas = cropperCanvas.value;
  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  const img = originalImage.value;

  // Clear canvas
  ctx.fillStyle = '#f5f5f5';
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  // Draw image
  ctx.drawImage(
    img,
    canvasOffsetX.value,
    canvasOffsetY.value,
    img.width * canvasScale.value,
    img.height * canvasScale.value
  );

  // Draw crop rectangle if cropping
  if (isCropping.value) {
    const startX = Math.min(cropStartX.value, cropEndX.value);
    const startY = Math.min(cropStartY.value, cropEndY.value);
    const width = Math.abs(cropEndX.value - cropStartX.value);
    const height = Math.abs(cropEndY.value - cropStartY.value);

    // Semi-transparent overlay
    ctx.fillStyle = 'rgba(0, 0, 0, 0.5)';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Clear crop area
    ctx.clearRect(startX, startY, width, height);
    ctx.drawImage(
      img,
      (startX - canvasOffsetX.value) / canvasScale.value,
      (startY - canvasOffsetY.value) / canvasScale.value,
      width / canvasScale.value,
      height / canvasScale.value,
      startX,
      startY,
      width,
      height
    );

    // Draw crop border
    ctx.strokeStyle = '#007bff';
    ctx.lineWidth = 2;
    ctx.strokeRect(startX, startY, width, height);
  }
};

const startCrop = (event: MouseEvent | TouchEvent) => {
  event.preventDefault();
  isCropping.value = true;

  const rect = cropperCanvas.value?.getBoundingClientRect();
  if (!rect) return;

  const clientX = 'touches' in event ? event.touches[0].clientX : event.clientX;
  const clientY = 'touches' in event ? event.touches[0].clientY : event.clientY;

  cropStartX.value = clientX - rect.left;
  cropStartY.value = clientY - rect.top;
  cropEndX.value = cropStartX.value;
  cropEndY.value = cropStartY.value;
};

const updateCrop = (event: MouseEvent | TouchEvent) => {
  if (!isCropping.value) return;

  event.preventDefault();

  const rect = cropperCanvas.value?.getBoundingClientRect();
  if (!rect) return;

  const clientX = 'touches' in event ? event.touches[0].clientX : event.clientX;
  const clientY = 'touches' in event ? event.touches[0].clientY : event.clientY;

  cropEndX.value = clientX - rect.left;
  cropEndY.value = clientY - rect.top;

  drawCanvas();
};

const endCrop = (event: MouseEvent | TouchEvent) => {
  event.preventDefault();
  isCropping.value = false;
};

const updateAspectRatio = () => {
  // Aspect ratio is enforced when drawing the crop rectangle
  drawCanvas();
};

const updateZoom = () => {
  if (!originalImage.value) return;

  const img = originalImage.value;
  const scaleX = cropperCanvas.value!.width / img.width;
  const scaleY = cropperCanvas.value!.height / img.height;
  canvasScale.value = Math.min(scaleX, scaleY) * zoomLevel.value;

  // Recenter
  canvasOffsetX.value = (cropperCanvas.value!.width - img.width * canvasScale.value) / 2;
  canvasOffsetY.value = (cropperCanvas.value!.height - img.height * canvasScale.value) / 2;

  drawCanvas();
};

const resetCrop = () => {
  isCropping.value = false;
  cropStartX.value = 0;
  cropStartY.value = 0;
  cropEndX.value = 0;
  cropEndY.value = 0;
  zoomLevel.value = 1;
  aspectRatio.value = 'free';

  if (originalImage.value) {
    initializeCanvas();
  }
};

const applyCrop = async () => {
  if ((!selectedFile.value && !editingLibraryImage.value) || !originalImage.value) {
    errorMessage.value = t('common.cropFailed', 'No image to crop');
    return;
  }

  try {
    console.log('Applying crop, isCropping:', isCropping.value);
    console.log('Crop coords:', {
      startX: cropStartX.value,
      startY: cropStartY.value,
      endX: cropEndX.value,
      endY: cropEndY.value,
      offsetX: canvasOffsetX.value,
      offsetY: canvasOffsetY.value,
      scale: canvasScale.value
    });

    // Check if there's a valid crop selection
    const hasValidCrop = cropStartX.value !== cropEndX.value && cropStartY.value !== cropEndY.value;
    const cropWidthPx = Math.abs(cropEndX.value - cropStartX.value);
    const cropHeightPx = Math.abs(cropEndY.value - cropStartY.value);

    let cropX = 0, cropY = 0, cropWidth = originalImage.value.width, cropHeight = originalImage.value.height;

    if (hasValidCrop && cropWidthPx >= 10 && cropHeightPx >= 10) {
      console.log('Using stored crop coordinates');

      // Calculate crop coordinates in original image space
      const startX = Math.min(cropStartX.value, cropEndX.value);
      const startY = Math.min(cropStartY.value, cropEndY.value);
      const width = cropWidthPx;
      const height = cropHeightPx;

      console.log('Raw crop rectangle:', { startX, startY, width, height });

      // Convert canvas coordinates to image coordinates
      cropX = Math.max(0, (startX - canvasOffsetX.value) / canvasScale.value);
      cropY = Math.max(0, (startY - canvasOffsetY.value) / canvasScale.value);
      cropWidth = Math.min(originalImage.value.width - cropX, width / canvasScale.value);
      cropHeight = Math.min(originalImage.value.height - cropY, height / canvasScale.value);

      console.log('Calculated crop in image space:', { cropX, cropY, cropWidth, cropHeight });
      console.log('Image dimensions:', originalImage.value.width, 'x', originalImage.value.height);

      // Apply aspect ratio if needed
      if (aspectRatio.value !== 'free') {
        const ratio = getAspectRatioValue();
        if (ratio && Math.abs(cropWidth / cropHeight - ratio) > 0.01) {
          console.log('Applying aspect ratio:', ratio);
          if (cropWidth / cropHeight > ratio) {
            cropWidth = cropHeight * ratio;
          } else {
            cropHeight = cropWidth / ratio;
          }
          console.log('Adjusted crop size:', cropWidth, 'x', cropHeight);
        }
      }
    } else {
      console.log('No valid crop selection, using full image');
    }

    // Create cropped canvas
    const croppedCanvas = document.createElement('canvas');
    const ctx = croppedCanvas.getContext('2d');
    if (!ctx) {
      errorMessage.value = t('common.cropFailed', 'Canvas not supported');
      return;
    }

    croppedCanvas.width = Math.max(1, Math.round(cropWidth));
    croppedCanvas.height = Math.max(1, Math.round(cropHeight));

    console.log('Creating cropped canvas:', croppedCanvas.width, 'x', croppedCanvas.height);

    // Draw the cropped image (transparent background)
    ctx.drawImage(
      originalImage.value,
      cropX, cropY, cropWidth, cropHeight,
      0, 0, croppedCanvas.width, croppedCanvas.height
    );

    console.log('Drew image to canvas');

    // Convert to blob
    const blob = await new Promise<Blob | null>((resolve) => {
      croppedCanvas.toBlob((blob: Blob | null) => {
        console.log('Blob created, size:', blob?.size);
        resolve(blob);
      }, 'image/png', 0.9);
    });

    if (!blob || blob.size === 0) {
      console.error('Failed to create blob');
      errorMessage.value = t('common.cropFailed', 'Failed to create image data');
      return;
    }

    console.log('Blob created successfully, size:', blob.size);

    // Create file and upload
    let fileName;
    if (editingLibraryImage.value) {
      // When editing existing image, use original filename
      const originalName = editingLibraryImage.value.url.split('/').pop()?.split('?')[0] || 'edited_image.png';
      fileName = isCropping.value
        ? originalName.replace(/\.[^/.]+$/, '') + '_cropped.png'
        : originalName;
    } else {
      // When uploading new file, use selectedFile name
      fileName = isCropping.value
        ? selectedFile.value!.name.replace(/\.[^/.]+$/, '') + '_cropped.png'
        : selectedFile.value!.name;
    }

    const croppedFile = new File([blob], fileName, {
      type: 'image/png',
      lastModified: Date.now()
    });

    console.log('Uploading file:', croppedFile.name, 'size:', croppedFile.size);

    await uploadFile(croppedFile);

  } catch (error) {
    console.error('Crop error:', error);
    errorMessage.value = t('common.cropFailed', 'Failed to apply crop');
  }
};

const getAspectRatioValue = (): number => {
  const ratios: Record<string, number> = {
    '1/1': 1,
    '4/3': 4/3,
    '3/4': 3/4,
    '16/9': 16/9
  };
  return ratios[aspectRatio.value] || 0;
};

const uploadFile = async (file: File) => {
  uploading.value = true;
  uploadProgress.value = 0;
  errorMessage.value = '';

  try {
    const formData = new FormData();
    // Use current directory when in library tab, otherwise use default upload directory
    const uploadDir = activeTab.value === 'library' ? currentDirectory.value : props.uploadDirectory;
    formData.append('file', file);
    formData.append('directory', uploadDir);

    // If editing an existing image, include the original filename for replacement
    if (editingLibraryImage.value) {
      const originalName = editingLibraryImage.value.url.split('/').pop()?.split('?')[0];
      if (originalName) {
        formData.append('replace_filename', originalName);
      }
    }

    const response = await http.post(`/api/${props.extensionName}/upload-image`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      },
      onUploadProgress: (progressEvent) => {
        if (progressEvent.total) {
          uploadProgress.value = Math.round(
            (progressEvent.loaded * 100) / progressEvent.total
          );
        }
      }
    });

    if (response.data?.url) {
      const cacheBustedUrl = response.data.url + '?t=' + Date.now();
      const result = {
        url: cacheBustedUrl,
        filename: file.name,
        size: file.size
      };

      emit('update:modelValue', cacheBustedUrl);
      emit('upload-success', result);
      showConfirmDialog.value = false;

      // If we were editing, refresh the library and clear edit state
      if (editingLibraryImage.value) {
        await loadImageLibrary();
        editingLibraryImage.value = null;
      }

      // Reset state
      selectedFile.value = null;
      originalImage.value = null;
      resetCrop();

      return result;
    } else {
      throw new Error('No URL returned from server');
    }

  } catch (error: any) {
    console.error('Upload error:', error);
    const errorMsg = error.response?.data?.message ||
                      error.message ||
                      t('common.uploadFailed', 'Upload failed');
    errorMessage.value = errorMsg;
    emit('upload-error', errorMsg);
    throw error;
  } finally {
    uploading.value = false;
  }
};

const loadImageLibrary = async (directory?: string) => {
  activeTab.value = 'library';
  loadingLibrary.value = true;
  errorMessage.value = '';

  const targetDirectory = directory || currentDirectory.value;

  try {
    const response = await http.get(`/api/${props.extensionName}/images/list`, {
      params: {
        directory: targetDirectory,
        search: searchQuery.value || undefined,
        limit: showPagination.value ? itemsPerPage.value : undefined,
        offset: showPagination.value ? (currentPage.value - 1) * itemsPerPage.value : undefined,
        t: Date.now() // Cache busting
      }
    });

    console.log('Image library response:', response.data);

    if (response.data) {
      // Handle folders
      folders.value = response.data.folders || [];

      // Handle images
      if (Array.isArray(response.data.images)) {
        libraryImages.value = response.data.images.map((item: any) => ({
          url: item.url + '?t=' + Date.now(), // Cache busting for images
          name: item.name || item.url.split('/').pop() || 'Untitled',
          size: item.size || 0,
          type: item.type || 'image'
        }));
      } else {
        libraryImages.value = [];
      }

      // Update breadcrumb
      breadcrumb.value = response.data.breadcrumb || [{name: props.extensionDisplayName, path: props.extensionName}];

      // Update current directory
      currentDirectory.value = response.data.directory || props.extensionName;

      // Update permissions
      canCreateFolder.value = response.data.can_create_folder || false;

    } else {
      console.log('No data found or invalid response format');
      libraryImages.value = [];
      folders.value = [];
      breadcrumb.value = [{name: props.extensionDisplayName || extensionConfig[props.extensionName]?.displayName || props.extensionName, path: props.extensionName}];
    }

  } catch (error: any) {
    console.error('Failed to load image library:', error);
    errorMessage.value = error.response?.data?.message ||
                          error.message ||
                          t('common.failedLoadLibrary', 'Failed to load image library');
    libraryImages.value = [];
    folders.value = [];
  } finally {
    loadingLibrary.value = false;
  }
};

const selectLibraryImage = (image: { url: string; name: string; size: number }) => {
  if (props.multiple) {
    // Multiple selection mode
    if (!selectedLibraryImage.value) {
      selectedLibraryImage.value = [];
    }
    const currentSelection = Array.isArray(selectedLibraryImage.value) ? selectedLibraryImage.value : [];

    if (currentSelection.includes(image.url)) {
      // Deselect if already selected
      selectedLibraryImage.value = currentSelection.filter(url => url !== image.url);
    } else {
      // Select if not selected
      selectedLibraryImage.value = [...currentSelection, image.url];
    }
  } else {
    // Single selection mode
    selectedLibraryImage.value = image.url;
    showConfirmDialog.value = true;
  }
};

const confirmImageSelection = () => {
  if (selectedLibraryImage.value) {
    if (props.multiple && Array.isArray(selectedLibraryImage.value)) {
      // Multiple images selected
      const selectedImages = libraryImages.value.filter(img => selectedLibraryImage.value!.includes(img.url));
      const processedImages = selectedImages.map(img => {
        const baseUrl = img.url.split('?')[0];
        const cacheBustedUrl = baseUrl + '?t=' + Date.now();
        return {
          url: cacheBustedUrl,
          filename: img.name,
          size: img.size
        };
      });

      emit('update:modelValue', processedImages.map(img => img.url));
      emit('images-selected', processedImages);
    } else {
      // Single image selected
      const selectedImage = libraryImages.value.find(img => img.url === selectedLibraryImage.value);
      if (selectedImage) {
        const baseUrl = selectedImage.url.split('?')[0];
        const cacheBustedUrl = baseUrl + '?t=' + Date.now();

        emit('update:modelValue', cacheBustedUrl);
        emit('image-selected', {
          url: cacheBustedUrl,
          filename: selectedImage.name,
          size: selectedImage.size
        });
      }
    }
    activeTab.value = 'upload';
  }
  showConfirmDialog.value = false;
  selectedLibraryImage.value = null;
};

const getImageUrl = (url: string): string => {
  // Ensure proper URL formatting
  if (url.startsWith('http')) {
    return url;
  }
  return `/${url.replace(/^\/+/, '')}`;
};

const formatFileSize = (bytes: number): string => {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
};

// Library browsing methods
let searchTimeout: number | null = null;

const debouncedSearch = () => {
  if (searchTimeout) {
    clearTimeout(searchTimeout);
  }
  searchTimeout = window.setTimeout(() => {
    currentPage.value = 1; // Reset to first page when searching
  }, 300);
};

const formatDate = (dateString: string): string => {
  if (!dateString) return '';
  try {
    const date = new Date(dateString);
    return date.toLocaleDateString();
  } catch {
    return '';
  }
};

const loadMoreImages = () => {
  if (loadingMore.value || !hasMoreImages.value) return;

  loadingMore.value = true;

  // Simulate loading more images (in real implementation, this would call API with pagination)
  setTimeout(() => {
    // For now, just show more items by increasing items per page
    itemsPerPage.value += 20;
    loadingMore.value = false;
  }, 500);
};

// Folder navigation methods
const navigateToFolder = async (folderPath: string) => {
  currentDirectory.value = folderPath;
  currentPage.value = 1; // Reset pagination
  await loadImageLibrary(folderPath);
};

const selectFolder = async (folder: any) => {
  await navigateToFolder(folder.path);
};

const goBack = async () => {
  // Navigate to parent directory
  const pathParts = currentDirectory.value.split('/');
  if (pathParts.length > 1) {
    pathParts.pop(); // Remove last part
    const parentPath = pathParts.join('/') || props.extensionName;
    await navigateToFolder(parentPath);
  } else {
    // If we're at root level, reset breadcrumb to use semantic display name
    breadcrumb.value = [{name: props.extensionDisplayName || extensionConfig[props.extensionName]?.displayName || props.extensionName, path: props.extensionName}];
  }
};

const cancelEdit = () => {
  // Cancel editing and return to library
  editingLibraryImage.value = null;
  originalImage.value = null;
  resetCrop();
  activeTab.value = 'library';
};

const createFolder = async () => {
  if (!newFolderName.value.trim()) {
    errorMessage.value = t('common.folderNameRequired', 'Folder name is required');
    return;
  }

  try {
    const response = await http.post(`/api/${props.extensionName}/images/folder`, {
      folder_name: newFolderName.value.trim(),
      directory: currentDirectory.value
    });

    if (response.data) {
      // Refresh the library to show the new folder
      await loadImageLibrary();
      newFolderName.value = '';
      showCreateFolderDialog.value = false;
      errorMessage.value = '';
    }
  } catch (error: any) {
    console.error('Failed to create folder:', error);
    errorMessage.value = error.response?.data?.message ||
                          error.message ||
                          t('common.failedCreateFolder', 'Failed to create folder');
  }
};

const openMoveDialog = (image: { url: string; name: string }) => {
  imageToMove.value = image;
  moveDestination.value = '';
  showMoveDialog.value = true;
};

const moveImage = async () => {
  if (!imageToMove.value || !moveDestination.value.trim()) {
    return;
  }

  try {
    // Extract image name from URL
    const imageName = imageToMove.value.url.split('/').pop()?.split('?')[0];
    if (!imageName) return;

    const response = await http.post(`/api/${props.extensionName}/images/move`, {
      image_name: imageName,
      from_directory: currentDirectory.value,
      to_directory: moveDestination.value.trim()
    });

    if (response.data) {
      // Refresh the library to show the moved image
      await loadImageLibrary();
      showMoveDialog.value = false;
      imageToMove.value = null;
      moveDestination.value = '';
      errorMessage.value = '';
    }
  } catch (error: any) {
    console.error('Failed to move image:', error);
    errorMessage.value = error.response?.data?.message ||
                          error.message ||
                          t('common.failedMoveImage', 'Failed to move image');
  }
};

// Drag and drop handlers for moving images between folders
const handleImageDragStart = (event: DragEvent, image: { url: string; name: string }) => {
  draggedImage.value = image;
  event.dataTransfer!.effectAllowed = 'move';
  event.dataTransfer!.setData('text/plain', image.url);
};

const handleFolderDragEnter = (event: DragEvent, folder: any) => {
  event.preventDefault();
  dropTargetFolder.value = folder.path;
};

const handleFolderDragLeave = (event: DragEvent, folder: any) => {
  event.preventDefault();
  // Only clear if we're actually leaving the folder (not entering a child element)
  const relatedTarget = event.relatedTarget as HTMLElement;
  const currentTarget = event.currentTarget as HTMLElement;
  if (!relatedTarget || !currentTarget.contains(relatedTarget)) {
    dropTargetFolder.value = null;
  }
};

const handleFolderDrop = async (event: DragEvent, folder: any) => {
  event.preventDefault();
  dropTargetFolder.value = null;

  if (!draggedImage.value) return;

  try {
    // Extract image name from URL
    const imageName = draggedImage.value.url.split('/').pop()?.split('?')[0];
    if (!imageName) return;

    const response = await http.post(`/api/${props.extensionName}/images/move`, {
      image_name: imageName,
      from_directory: currentDirectory.value,
      to_directory: folder.path
    });

    if (response.data) {
      // Refresh the library to show the moved image
      await loadImageLibrary();
      draggedImage.value = null;
      errorMessage.value = '';
    }
  } catch (error: any) {
    console.error('Failed to move image:', error);
    errorMessage.value = error.response?.data?.message ||
                          error.message ||
                          t('common.failedMoveImage', 'Failed to move image');
  }
};

// Delete image functionality
const openDeleteDialog = (image: { url: string; name: string }) => {
  imageToDelete.value = image;
  showDeleteDialog.value = true;
};

const deleteImage = async () => {
  if (!imageToDelete.value) return;

  try {
    // Extract image name from URL
    const imageName = imageToDelete.value.url.split('/').pop()?.split('?')[0];
    if (!imageName) return;

    const response = await http.delete(`/api/${props.extensionName}/images/delete`, {
      data: {
        image_name: imageName,
        directory: currentDirectory.value
      }
    });

    if (response.data) {
      // Refresh the library to remove the deleted image
      await loadImageLibrary();
      showDeleteDialog.value = false;
      imageToDelete.value = null;
      errorMessage.value = '';
    }
  } catch (error: any) {
    console.error('Failed to delete image:', error);
    errorMessage.value = error.response?.data?.message ||
                          error.message ||
                          t('common.failedDeleteImage', 'Failed to delete image');
  }
};

// Edit image functionality
const editImage = async (image: { url: string; name: string }) => {
  editingLibraryImage.value = image;

  try {
    // Reset crop state first
    resetCrop();

    // Load the image for editing
    const img = new Image();
    const imageUrl = getImageUrl(image.url.split('?')[0]); // Remove cache buster and ensure proper URL

    console.log('Loading image for editing:', imageUrl);

    img.onload = () => {
      console.log('Image loaded successfully for editing');
      originalImage.value = img;
      activeTab.value = 'upload'; // Switch to upload tab to show editor
      nextTick(() => {
        initializeCanvas();
      });
    };

    img.onerror = (error) => {
      console.error('Failed to load image for editing:', imageUrl, error);
      errorMessage.value = t('common.failedLoadImage', 'Failed to load image for editing');
    };

    img.src = imageUrl;
  } catch (error) {
    console.error('Failed to load image for editing:', error);
    errorMessage.value = t('common.failedLoadImage', 'Failed to load image for editing');
  }
};

// Rename image functionality
const openRenameDialog = (image: { url: string; name: string }) => {
  imageToRename.value = image;
  // Extract current name without extension
  const nameWithoutExt = image.name.split('.').slice(0, -1).join('.');
  newImageName.value = nameWithoutExt;
  showRenameDialog.value = true;
};

const renameImage = async () => {
  if (!imageToRename.value || !newImageName.value.trim()) return;

  try {
    // Extract current image name from URL
    const currentImageName = imageToRename.value.url.split('/').pop()?.split('?')[0];
    if (!currentImageName) return;

    // Get file extension
    const extension = currentImageName.split('.').pop();
    const newNameWithExt = newImageName.value.trim() + (extension ? '.' + extension : '');

    const response = await http.post(`/api/${props.extensionName}/images/rename`, {
      current_name: currentImageName,
      new_name: newNameWithExt,
      directory: currentDirectory.value
    });

    if (response.data) {
      // Refresh the library to show the renamed image
      await loadImageLibrary();
      showRenameDialog.value = false;
      imageToRename.value = null;
      newImageName.value = '';
      errorMessage.value = '';
    }
  } catch (error: any) {
    console.error('Failed to rename image:', error);
    errorMessage.value = error.response?.data?.message ||
                          error.message ||
                          t('common.failedRenameImage', 'Failed to rename image');
  }
};

// Window resize handler
const handleResize = () => {
  if (originalImage.value) {
    initializeCanvas();
  }
};

// Lifecycle
onMounted(() => {
  // Load library if starting on library tab
  if (activeTab.value === 'library') {
    loadImageLibrary();
  }

  // Add resize listener
  window.addEventListener('resize', handleResize);
});

onUnmounted(() => {
  cleanup();
});

// Cleanup
const cleanup = () => {
  window.removeEventListener('resize', handleResize);
  if (originalImage.value) {
    URL.revokeObjectURL(originalImage.value.src);
  }
};

watch(() => props.modelValue, (newVal) => {
  if (!newVal) {
    // Reset selection if model value is cleared
    selectedLibraryImage.value = null;
  }
});

watch(searchQuery, () => {
  currentPage.value = 1; // Reset to first page when search changes
});
</script>

<style scoped>
.advanced-image-upload {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  max-width: 100%;
}

.tabs {
  display: flex;
  gap: 0.5rem;
  border-bottom: 1px solid var(--card-border, #e3e3e3);
  padding-bottom: 0.5rem;
}

.tab-button {
  padding: 0.5rem 1rem;
  background: transparent;
  border: none;
  cursor: pointer;
  font-weight: 500;
  color: var(--text-secondary, #666666);
  border-radius: 4px 4px 0 0;
  transition: all 0.2s ease;
}

.tab-button:hover {
  background: var(--card-bg-hover, #f8f9fa);
}

.tab-button.active {
  color: var(--button-primary-bg, #007bff);
  border-bottom: 2px solid var(--button-primary-bg, #007bff);
}

.upload-section, .library-section {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.upload-area {
  border: 2px dashed var(--card-border, #e3e3e3);
  border-radius: var(--border-radius-md, 8px);
  padding: 2rem;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s ease;
  background: var(--card-bg, #ffffff);
}

.upload-area:hover:not(.disabled) {
  border-color: var(--button-primary-bg, #007bff);
  background: var(--card-bg-hover, #f8f9fa);
}

.upload-area.disabled {
  opacity: 0.5;
  cursor: not-allowed;
  pointer-events: none;
}

.upload-icon {
  color: var(--text-secondary, #666666);
  margin-bottom: 1rem;
}

.upload-text {
  font-weight: 500;
  color: var(--text-primary, #222222);
  margin: 0 0 0.5rem 0;
}

.file-types {
  font-size: 0.875rem;
  color: var(--text-secondary, #666666);
  margin: 0;
}

.image-editor {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  background: var(--card-bg, #ffffff);
  border: 1px solid var(--card-border, #e3e3e3);
  border-radius: var(--border-radius-md, 8px);
  padding: 1rem;
}

.editor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 1rem;
  border-bottom: 1px solid var(--card-border, #e3e3e3);
}

.editor-header h3 {
  margin: 0;
  font-size: 1.125rem;
  color: var(--text-primary, #222222);
}

.editor-actions {
  display: flex;
  gap: 0.5rem;
}

.action-button {
  padding: 0.5rem 1rem;
  background: var(--button-secondary-bg, #6c757d);
  color: var(--button-secondary-text, #ffffff);
  border: none;
  border-radius: var(--border-radius-sm, 4px);
  cursor: pointer;
  font-size: 0.875rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  transition: background 0.2s ease;
}

.action-button:hover:not(:disabled) {
  background: var(--button-secondary-hover, #545b62);
}

.action-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.action-button.primary {
  background: var(--button-primary-bg, #007bff);
}

.action-button.primary:hover:not(:disabled) {
  background: var(--button-primary-hover, #0069d9);
}

.cropper-container {
  position: relative;
  width: 100%;
  background: #f5f5f5;
  border-radius: var(--border-radius-sm, 4px);
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 300px;
}

.cropper-canvas {
  cursor: crosshair;
  max-width: 100%;
  max-height: 100%;
  display: block;
}

.editor-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 1.5rem;
  padding-top: 1rem;
  border-top: 1px solid var(--card-border, #e3e3e3);
}

.control-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  min-width: 150px;
}

.control-group label {
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--text-primary, #222222);
}

.control-group select,
.control-group input[type="range"] {
  padding: 0.5rem;
  border: 1px solid var(--card-border, #e3e3e3);
  border-radius: var(--border-radius-sm, 4px);
  background: var(--card-bg, #ffffff);
}

.rotate-buttons {
  display: flex;
  gap: 0.5rem;
}

.rotate-buttons button {
  padding: 0.5rem;
  background: var(--button-secondary-bg, #6c757d);
  color: white;
  border: none;
  border-radius: var(--border-radius-sm, 4px);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.library-section {
  min-height: 200px;
}

.library-controls {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1rem;
  padding: 1rem;
  background: var(--card-bg, #ffffff);
  border: 1px solid var(--card-border, #e3e3e3);
  border-radius: var(--border-radius-md, 8px);
}

.breadcrumb {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 1rem;
  padding: 0.75rem 1rem;
  background: var(--card-bg, #ffffff);
  border: 1px solid var(--card-border, #e3e3e3);
  border-radius: var(--border-radius-md, 8px);
  font-size: 0.875rem;
}

.breadcrumb-item {
  color: var(--text-secondary, #666666);
  cursor: pointer;
  padding: 0.5rem 0.75rem;
  border-radius: 6px;
  transition: all 0.2s ease;
  font-weight: 500;
  background: transparent;
  border: 1px solid transparent;
}

.breadcrumb-item:hover:not(.active) {
  background: var(--card-bg-hover, #f8f9fa);
  color: var(--text-primary, #222222);
  border-color: var(--card-border, #e3e3e3);
  transform: translateY(-1px);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.breadcrumb-item.active {
  color: var(--button-primary-bg, #007bff);
  font-weight: 600;
  background: var(--button-primary-bg-light, #e7f1ff);
  border-color: var(--button-primary-bg, #007bff);
}

.breadcrumb-item:not(:last-child)::after {
  content: "/";
  margin-left: 0.5rem;
  color: var(--text-muted, #999999);
}

.back-button {
  padding: 0.5rem 1rem;
  background: var(--button-secondary-bg, #6c757d);
  color: var(--button-secondary-text, #ffffff);
  border: none;
  border-radius: var(--border-radius-sm, 4px);
  cursor: pointer;
  font-size: 0.875rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-right: 1rem;
  transition: background 0.2s ease;
}

.back-button:hover {
  background: var(--button-secondary-hover, #545b62);
}

.back-button svg {
  width: 16px;
  height: 16px;
}

.control-buttons {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.search-container {
  position: relative;
  flex: 1;
  max-width: 400px;
}

.search-input {
  width: 100%;
  padding: 0.5rem 2.5rem 0.5rem 1rem;
  border: 1px solid var(--card-border, #e3e3e3);
  border-radius: var(--border-radius-sm, 4px);
  background: var(--card-bg, #ffffff);
  font-size: 0.875rem;
}

.search-container svg {
  position: absolute;
  right: 0.75rem;
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-secondary, #666666);
  pointer-events: none;
}

.view-controls {
  display: flex;
  gap: 0.5rem;
}

.view-toggle {
  padding: 0.5rem;
  background: var(--button-secondary-bg, #6c757d);
  color: var(--button-secondary-text, #ffffff);
  border: none;
  border-radius: var(--border-radius-sm, 4px);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.2s ease;
}

.view-toggle:hover:not(.active) {
  background: var(--button-secondary-hover, #545b62);
}

.view-toggle.active {
  background: var(--button-primary-bg, #007bff);
}

.create-folder-btn {
  padding: 0.5rem 1rem;
  background: var(--button-secondary-bg, #6c757d);
  color: var(--button-secondary-text, #ffffff);
  border: none;
  border-radius: var(--border-radius-sm, 4px);
  cursor: pointer;
  font-size: 0.875rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  transition: background 0.2s ease;
}

.create-folder-btn:hover {
  background: var(--button-secondary-hover, #545b62);
}

.confirm-selection-btn {
  padding: 0.5rem 1rem;
  background: var(--button-primary-bg, #007bff);
  color: var(--button-primary-text, #ffffff);
  border: none;
  border-radius: var(--border-radius-sm, 4px);
  cursor: pointer;
  font-size: 0.875rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  transition: background 0.2s ease;
}

.confirm-selection-btn:hover {
  background: var(--button-primary-hover, #0069d9);
}

.library-stats {
  text-align: center;
  padding: 0.5rem;
  color: var(--text-secondary, #666666);
  font-size: 0.875rem;
}

.image-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.folder-list-item {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1rem;
  background: var(--card-bg, #ffffff);
  border: 1px solid var(--card-border, #e3e3e3);
  border-radius: var(--border-radius-md, 8px);
  cursor: pointer;
  transition: all 0.2s ease;
}

.folder-list-item:hover {
  border-color: var(--button-primary-bg, #007bff);
  box-shadow: 0 2px 8px rgba(0, 123, 255, 0.1);
}

.list-folder-preview {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--button-primary-bg, #007bff);
  flex-shrink: 0;
}

.list-folder-info {
  flex: 1;
  min-width: 0;
}

.list-folder-name {
  font-weight: 500;
  color: var(--text-primary, #222222);
  margin-bottom: 0.25rem;
}

.list-folder-meta {
  font-size: 0.75rem;
  color: var(--text-secondary, #666666);
}

.open-folder-button {
  padding: 0.5rem 1rem;
  background: var(--button-primary-bg, #007bff);
  color: var(--button-primary-text, #ffffff);
  border: none;
  border-radius: var(--border-radius-sm, 4px);
  cursor: pointer;
  font-size: 0.75rem;
  font-weight: 500;
  transition: background 0.2s ease;
}

.open-folder-button:hover {
  background: var(--button-primary-hover, #0069d9);
}

.image-list-item {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1rem;
  background: var(--card-bg, #ffffff);
  border: 1px solid var(--card-border, #e3e3e3);
  border-radius: var(--border-radius-md, 8px);
  cursor: pointer;
  transition: all 0.2s ease;
}

.image-list-item:hover {
  border-color: var(--button-primary-bg, #007bff);
  box-shadow: 0 2px 8px rgba(0, 123, 255, 0.1);
}

.image-list-item.selected {
  border-color: var(--button-primary-bg, #007bff);
  background: var(--button-primary-bg-light, #e7f1ff);
}

.list-image-preview {
  width: 60px;
  height: 60px;
  flex-shrink: 0;
  overflow: hidden;
  border-radius: var(--border-radius-sm, 4px);
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f8f9fa;
}

.list-image-preview img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}

.list-image-info {
  flex: 1;
  min-width: 0;
}

.list-image-name {
  font-weight: 500;
  color: var(--text-primary, #222222);
  margin-bottom: 0.25rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.list-image-meta {
  display: flex;
  gap: 1rem;
  font-size: 0.75rem;
  color: var(--text-secondary, #666666);
}

.image-date {
  color: var(--text-muted, #999999);
}

.pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 1rem;
  margin-top: 2rem;
  padding: 1rem;
}

.page-button {
  padding: 0.5rem;
  background: var(--button-secondary-bg, #6c757d);
  color: var(--button-secondary-text, #ffffff);
  border: none;
  border-radius: var(--border-radius-sm, 4px);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.2s ease;
}

.page-button:hover:not(:disabled) {
  background: var(--button-secondary-hover, #545b62);
}

.page-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.page-info {
  font-size: 0.875rem;
  color: var(--text-secondary, #666666);
  font-weight: 500;
}

.load-more {
  display: flex;
  justify-content: center;
  margin-top: 2rem;
}

.load-more-button {
  padding: 0.75rem 1.5rem;
  background: var(--button-primary-bg, #007bff);
  color: var(--button-primary-text, #ffffff);
  border: none;
  border-radius: var(--border-radius-md, 8px);
  cursor: pointer;
  font-weight: 500;
  transition: background 0.2s ease;
}

.load-more-button:hover:not(:disabled) {
  background: var(--button-primary-hover, #0069d9);
}

.load-more-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.loading-indicator {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 2rem;
  gap: 1rem;
}

.spinner {
  width: 40px;
  height: 40px;
  border: 4px solid var(--card-border, #e3e3e3);
  border-top: 4px solid var(--button-primary-bg, #007bff);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.empty-library {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 2rem;
  text-align: center;
  gap: 1rem;
}

.empty-library p {
  color: var(--text-secondary, #666666);
  margin: 0;
}

.upload-button {
  padding: 0.75rem 1.5rem;
  background: var(--button-primary-bg, #007bff);
  color: var(--button-primary-text, #ffffff);
  border: none;
  border-radius: var(--border-radius-md, 8px);
  cursor: pointer;
  font-weight: 500;
}

.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 1rem;
  padding: 1rem 0;
}

.folder-card {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  border: 2px solid var(--card-border, #e3e3e3);
  border-radius: var(--border-radius-md, 8px);
  overflow: hidden;
  cursor: pointer;
  transition: all 0.2s ease;
  background: var(--card-bg, #ffffff);
  padding: 1rem;
  align-items: center;
  text-align: center;
}

.folder-card:hover {
  border-color: var(--button-primary-bg, #007bff);
  box-shadow: 0 2px 8px rgba(0, 123, 255, 0.1);
}

.folder-card.drop-target {
  border-color: var(--button-primary-bg, #007bff);
  background: var(--button-primary-bg-light, #e7f1ff);
  box-shadow: 0 4px 12px rgba(0, 123, 255, 0.3);
}

.folder-preview {
  width: 60px;
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--button-primary-bg, #007bff);
  margin-bottom: 0.5rem;
}

.folder-info {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  width: 100%;
}

.folder-name {
  font-weight: 500;
  color: var(--text-primary, #222222);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.folder-count {
  font-size: 0.75rem;
  color: var(--text-secondary, #666666);
}

.image-card {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  border: 2px solid var(--card-border, #e3e3e3);
  border-radius: var(--border-radius-md, 8px);
  overflow: hidden;
  cursor: pointer;
  transition: all 0.2s ease;
  position: relative;
}

.image-card:hover {
  border-color: var(--button-primary-bg, #007bff);
  box-shadow: 0 2px 8px rgba(0, 123, 255, 0.1);
}

.image-card.selected {
  border-color: var(--button-primary-bg, #007bff);
  background: var(--button-primary-bg-light, #e7f1ff);
}

.image-preview {
  width: 100%;
  height: 120px;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f8f9fa;
}

.image-preview img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}

.image-info {
  display: flex;
  justify-content: space-between;
  padding: 0 0.5rem;
  font-size: 0.75rem;
}

.image-actions {
  display: flex;
  gap: 0.25rem;
  padding: 0 0.5rem;
  margin-top: 0.5rem;
}

.move-button {
  padding: 0.25rem;
  background: var(--button-secondary-bg, #6c757d);
  color: var(--button-secondary-text, #ffffff);
  border: none;
  border-radius: var(--border-radius-sm, 4px);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.2s ease;
}

.move-button:hover {
  background: var(--button-secondary-hover, #545b62);
}

.delete-button {
  padding: 0.25rem;
  background: var(--error-bg, #dc3545);
  color: white;
  border: none;
  border-radius: var(--border-radius-sm, 4px);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.2s ease;
}

.delete-button:hover {
  background: var(--error-hover, #c82333);
}

.edit-button {
  padding: 0.25rem;
  background: var(--button-secondary-bg, #6c757d);
  color: white;
  border: none;
  border-radius: var(--border-radius-sm, 4px);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.2s ease;
}

.edit-button:hover {
  background: var(--button-secondary-hover, #545b62);
}

.rename-button {
  padding: 0.25rem;
  background: var(--button-secondary-bg, #6c757d);
  color: white;
  border: none;
  border-radius: var(--border-radius-sm, 4px);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.2s ease;
}

.rename-button:hover {
  background: var(--button-secondary-hover, #545b62);
}

.image-name {
  color: var(--text-primary, #222222);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100px;
}

.image-size {
  color: var(--text-secondary, #666666);
}

.select-button {
  width: 100%;
  padding: 0.5rem;
  background: var(--button-primary-bg, #007bff);
  color: var(--button-primary-text, #ffffff);
  border: none;
  border-radius: 0 0 var(--border-radius-md, 8px) var(--border-radius-md, 8px);
  cursor: pointer;
  font-size: 0.75rem;
  font-weight: 500;
}

.select-button:hover {
  background: var(--button-primary-hover, #0069d9);
}

.upload-progress {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.75rem;
  background: var(--card-bg, #ffffff);
  border: 1px solid var(--card-border, #e3e3e3);
  border-radius: var(--border-radius-md, 8px);
}

.progress-bar {
  flex: 1;
  height: 8px;
  background: var(--card-border, #e3e3e3);
  border-radius: 4px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--button-primary-bg, #007bff);
  transition: width 0.2s ease;
}

.progress-text {
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--text-primary, #222222);
}

.error-message {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem;
  background: var(--error-bg-light, #f8d7da);
  border: 1px solid var(--error-border, #f5c6cb);
  border-radius: var(--border-radius-md, 8px);
  color: var(--error-text, #721c24);
  font-size: 0.875rem;
}

.error-message svg {
  flex-shrink: 0;
}

.confirmation-dialog {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.dialog-content {
  background: var(--card-bg, #ffffff);
  padding: 1.5rem;
  border-radius: var(--border-radius-md, 8px);
  max-width: 400px;
  width: 100%;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
}

.dialog-content h3 {
  margin: 0 0 1rem 0;
  color: var(--text-primary, #222222);
}

.dialog-content p {
  margin: 0 0 1.5rem 0;
  color: var(--text-secondary, #666666);
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}

.cancel-button {
  padding: 0.5rem 1rem;
  background: var(--button-secondary-bg, #6c757d);
  color: var(--button-secondary-text, #ffffff);
  border: none;
  border-radius: var(--border-radius-sm, 4px);
  cursor: pointer;
}

.confirm-button {
  padding: 0.5rem 1rem;
  background: var(--button-primary-bg, #007bff);
  color: var(--button-primary-text, #ffffff);
  border: none;
  border-radius: var(--border-radius-sm, 4px);
  cursor: pointer;
}

.delete-confirm-button {
  padding: 0.5rem 1rem;
  background: var(--error-bg, #dc3545);
  color: white;
  border: none;
  border-radius: var(--border-radius-sm, 4px);
  cursor: pointer;
}

.delete-confirm-button:hover {
  background: var(--error-hover, #c82333);
}

/* Responsive Design */
@media (max-width: 768px) {
  .editor-controls {
    flex-direction: column;
    gap: 1rem;
  }

  .control-group {
    width: 100%;
  }

  .image-grid {
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  }
}

@media (max-width: 480px) {
  .tabs {
    flex-direction: column;
    align-items: stretch;
  }

  .image-grid {
    grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  }
}
</style>
