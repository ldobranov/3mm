<template>
  <div class="image-upload-container">
    <!-- Upload Area -->
    <div
      class="upload-area"
      :class="{ 'drag-over': isDragOver, 'disabled': disabled || (maxFiles > 0 && totalImages >= maxFiles) }"
      @dragover.prevent="handleDragOver"
      @dragleave.prevent="handleDragLeave"
      @drop.prevent="handleDrop"
      @click="triggerFileSelect"
    >
      <input
        ref="fileInput"
        type="file"
        :multiple="multiple"
        :accept="accept"
        @change="handleFileSelect"
        style="display: none"
      />

      <div class="upload-content">
        <div class="upload-icon">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/>
            <polyline points="14,2 14,8 20,8"/>
            <line x1="16" y1="13" x2="8" y2="13"/>
            <line x1="16" y1="17" x2="8" y2="17"/>
            <polyline points="10,9 9,9 8,9"/>
          </svg>
        </div>

        <div class="upload-text">
          <p class="primary-text">
            {{ buttonText || t('common.dropFilesHere', 'Drop files here or click to browse') }}
          </p>
          <p class="secondary-text" v-if="fileTypesText || maxSizeText">
            {{ [fileTypesText, maxSizeText].filter(Boolean).join(' • ') }}
          </p>
          <p class="secondary-text" v-if="maxFiles > 0">
            {{ t('common.maxFiles', 'Maximum {count} files', { count: maxFiles.toString() }) }}
          </p>
        </div>

        <button
          type="button"
          class="upload-btn"
          :disabled="disabled || uploading || (maxFiles > 0 && totalImages >= maxFiles)"
        >
          {{ uploading ? t('common.uploading', 'Uploading...') : t('common.selectFiles', 'Select Files') }}
        </button>
      </div>
    </div>

    <!-- Upload Progress -->
    <div v-if="uploading && uploadProgress.length > 0" class="upload-progress">
      <div
        v-for="(progress, index) in uploadProgress"
        :key="index"
        class="progress-item"
      >
        <div class="progress-info">
          <span class="file-name">{{ progress.fileName }}</span>
          <span class="file-size">{{ formatFileSize(progress.fileSize) }}</span>
        </div>
        <div class="progress-bar">
          <div
            class="progress-fill"
            :style="{ width: `${progress.progress}%` }"
          ></div>
        </div>
        <span class="progress-text">{{ progress.progress }}%</span>
      </div>
    </div>

    <!-- Error Messages -->
    <div v-if="errors.length > 0" class="upload-errors">
      <div
        v-for="(error, index) in errors"
        :key="index"
        class="error-message"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10"/>
          <line x1="15" y1="9" x2="9" y2="15"/>
          <line x1="9" y1="9" x2="15" y2="15"/>
        </svg>
        {{ error }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useI18n } from '@/utils/i18n';
import http from '@/utils/dynamic-http';

const { t } = useI18n();

// Props
interface Props {
  modelValue?: string[];
  uploadUrl?: string;
  multiple?: boolean;
  accept?: string;
  maxSize?: number; // in MB
  maxFiles?: number;
  disabled?: boolean;
  buttonText?: string;
  existingImages?: string[];
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: () => [],
  uploadUrl: '/api/upload',
  multiple: true,
  accept: 'image/*',
  maxSize: 5,
  maxFiles: 0, // 0 = unlimited
  disabled: false,
  existingImages: () => []
});

// Emits
const emit = defineEmits<{
  'update:modelValue': [value: string[]];
  'upload-success': [files: any[]];
  'upload-error': [error: string];
  'file-removed': [index: number];
}>();

// Reactive data
const fileInput = ref<HTMLInputElement>();
const isDragOver = ref(false);
const uploading = ref(false);
const uploadProgress = ref<any[]>([]);
const errors = ref<string[]>([]);

// Computed properties
const totalImages = computed(() => {
  return (props.modelValue?.length || 0) + (props.existingImages?.length || 0);
});

const fileTypesText = computed(() => {
  if (props.accept === 'image/*') {
    return t('common.imageFiles', 'Image files');
  } else if (props.accept === '*/*') {
    return t('common.allFiles', 'All files');
  } else {
    return props.accept.replace('/*', '').toUpperCase() + ' files';
  }
});

const maxSizeText = computed(() => {
  if (props.maxSize > 0) {
    return t('common.maxSize', 'Max {size}MB', { size: props.maxSize.toString() });
  }
  return '';
});

// Methods
const triggerFileSelect = () => {
  if (!props.disabled && fileInput.value) {
    fileInput.value.click();
  }
};

const handleDragOver = () => {
  if (!props.disabled) {
    isDragOver.value = true;
  }
};

const handleDragLeave = () => {
  isDragOver.value = false;
};

const handleDrop = (event: DragEvent) => {
  isDragOver.value = false;
  if (props.disabled) return;

  const files = event.dataTransfer?.files;
  if (files) {
    handleFiles(Array.from(files));
  }
};

const handleFileSelect = (event: Event) => {
  const target = event.target as HTMLInputElement;
  const files = target.files;
  if (files) {
    handleFiles(Array.from(files));
  }
  // Clear input
  if (target) target.value = '';
};

const handleFiles = async (files: File[]) => {
  if (props.disabled) return;

  // Validate file count
  if (props.maxFiles > 0 && totalImages.value + files.length > props.maxFiles) {
    errors.value.push(t('common.tooManyFiles', 'Too many files selected'));
    return;
  }

  // Validate each file
  const validFiles: File[] = [];
  for (const file of files) {
    if (validateFile(file)) {
      validFiles.push(file);
    }
  }

  if (validFiles.length === 0) return;

  // Upload files
  await uploadFiles(validFiles);
};

const validateFile = (file: File): boolean => {
  // Check file type
  if (props.accept !== '*/*') {
    const acceptTypes = props.accept.split(',').map(type => type.trim());
    const isAccepted = acceptTypes.some(type => {
      if (type.endsWith('/*')) {
        return file.type.startsWith(type.slice(0, -1));
      } else {
        return file.type === type;
      }
    });

    if (!isAccepted) {
      errors.value.push(t('common.invalidFileType', '{file} has invalid file type', { file: file.name }));
      return false;
    }
  }

  // Check file size
  if (props.maxSize > 0 && file.size > props.maxSize * 1024 * 1024) {
    errors.value.push(t('common.fileTooLarge', '{file} is too large (max {size}MB)', {
      file: file.name,
      size: props.maxSize.toString()
    }));
    return false;
  }

  return true;
};

const uploadFiles = async (files: File[]) => {
  uploading.value = true;
  errors.value.splice(0); // Clear previous errors

  uploadProgress.value = files.map(file => ({
    fileName: file.name,
    fileSize: file.size,
    progress: 0
  }));

  const uploadedUrls: string[] = [];

  try {
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const formData = new FormData();
      formData.append('file', file);

      // Simulate progress (in a real implementation, you'd use XMLHttpRequest for progress tracking)
      const progressInterval = setInterval(() => {
        if (uploadProgress.value[i].progress < 90) {
          uploadProgress.value[i].progress += Math.random() * 20;
        }
      }, 200);

      const response = await http.post(props.uploadUrl, formData, {
        headers: {
          'Content-Type': 'multipart/form-data'
        },
        onUploadProgress: (progressEvent) => {
          if (progressEvent.total) {
            uploadProgress.value[i].progress = Math.round(
              (progressEvent.loaded * 100) / progressEvent.total
            );
          }
        }
      });

      clearInterval(progressInterval);
      uploadProgress.value[i].progress = 100;

      if (response.data?.url) {
        uploadedUrls.push(response.data.url);
      }
    }

    // Update model value
    const newValue = [...(props.modelValue || []), ...uploadedUrls];
    emit('update:modelValue', newValue);
    emit('upload-success', uploadedUrls.map((url, index) => ({
      url,
      filename: files[index].name
    })));

  } catch (error: any) {
    console.error('Upload error:', error);
    const errorMessage = error.response?.data?.message ||
                        error.message ||
                        t('common.uploadFailed', 'Upload failed');
    errors.value.push(errorMessage);
    emit('upload-error', errorMessage);
  } finally {
    uploading.value = false;
    uploadProgress.value.splice(0);
  }
};

const formatFileSize = (bytes: number): string => {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
};

// Watch for external changes to clear errors
watch(() => props.modelValue, () => {
  errors.value.splice(0);
});
</script>

<style scoped>
.image-upload-container {
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

.upload-area.drag-over {
  border-color: var(--success-bg, #28a745);
  background: var(--success-bg-light, #d4edda);
}

.upload-area.disabled {
  opacity: 0.5;
  cursor: not-allowed;
  pointer-events: none;
}

.upload-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
}

.upload-icon {
  color: var(--text-secondary, #666666);
}

.upload-text {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.primary-text {
  font-weight: 500;
  color: var(--text-primary, #222222);
  margin: 0;
}

.secondary-text {
  font-size: 0.875rem;
  color: var(--text-secondary, #666666);
  margin: 0;
}

.upload-btn {
  padding: 0.75rem 1.5rem;
  background: var(--button-secondary-bg, #6c757d);
  color: var(--button-secondary-text, #ffffff);
  border: none;
  border-radius: var(--border-radius-md, 8px);
  cursor: pointer;
  font-weight: 500;
  transition: background 0.2s ease;
}

.upload-btn:hover:not(:disabled) {
  background: var(--button-secondary-hover, #545b62);
}

.upload-btn:disabled {
  background: var(--text-secondary, #666666);
  cursor: not-allowed;
}

.upload-progress {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.progress-item {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.75rem;
  background: var(--card-bg, #ffffff);
  border: 1px solid var(--card-border, #e3e3e3);
  border-radius: var(--border-radius-md, 8px);
}

.progress-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.file-name {
  font-weight: 500;
  color: var(--text-primary, #222222);
}

.file-size {
  font-size: 0.875rem;
  color: var(--text-secondary, #666666);
}

.progress-bar {
  flex: 2;
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
  min-width: 3rem;
  text-align: right;
}

.upload-errors {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
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

/* Responsive Design */
@media (max-width: 768px) {
  .upload-area {
    padding: 1.5rem;
  }

  .progress-item {
    flex-direction: column;
    align-items: stretch;
    gap: 0.75rem;
  }

  .progress-bar {
    flex: none;
  }

  .progress-text {
    text-align: center;
  }
}
</style>