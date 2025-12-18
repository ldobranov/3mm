<template>
  <div v-if="show" class="image-editor-modal-overlay" @click="closeModal">
    <div class="image-editor-modal" @click.stop>
      <div class="modal-header">
        <h3>{{ editingImage ? t('common.editExistingImage', 'Edit Existing Image') : t('common.editImage', 'Edit Image') }}</h3>
        <button type="button" class="close-button" @click="closeModal">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"/>
            <line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>

      <div class="modal-body">
        <!-- Upload Tab -->
        <div v-if="activeTab === 'upload'" class="upload-section">
          <div class="upload-area" @click="triggerFileSelect" :class="{ 'disabled': disabled }">
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
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue';
import { useI18n } from '@/utils/i18n';
import http from '@/utils/dynamic-http';

const { t } = useI18n();

// Props
interface Props {
  show: boolean;
  modelValue?: string;
  uploadUrl?: string;
  maxSize?: number;
  disabled?: boolean;
  imageLibraryUrl?: string;
  uploadDirectory?: string;
  extensionName?: string;
  editingImage?: { url: string; name: string } | null;
}

const props = withDefaults(defineProps<Props>(), {
  show: false,
  modelValue: '',
  uploadUrl: '/api/upload',
  maxSize: 5,
  disabled: false,
  imageLibraryUrl: '/api/images/list',
  uploadDirectory: 'uploads',
  extensionName: 'store',
  editingImage: null
});

// Emits
const emit = defineEmits<{
  'update:show': [value: boolean];
  'update:modelValue': [value: string];
  'upload-success': [file: { url: string; filename: string; size: number }];
  'upload-error': [error: string];
  'close': [];
}>();

// Reactive data
const fileInput = ref<HTMLInputElement>();
const cropperContainer = ref<HTMLDivElement>();
const cropperCanvas = ref<HTMLCanvasElement>();
const activeTab = ref<'upload'>('upload');
const selectedFile = ref<File | null>(null);
const originalImage = ref<HTMLImageElement | null>(null);
const aspectRatio = ref<'free' | '1/1' | '4/3' | '3/4' | '16/9'>('free');
const zoomLevel = ref(1);
const uploading = ref(false);
const uploadProgress = ref(0);
const errorMessage = ref('');

// Canvas cropping state
const isCropping = ref(false);
const cropStartX = ref(0);
const cropStartY = ref(0);
const cropEndX = ref(0);
const cropEndY = ref(0);
const canvasOffsetX = ref(0);
const canvasOffsetY = ref(0);
const canvasScale = ref(1);

// Computed
const maxSizeInBytes = props.maxSize * 1024 * 1024;
const editingLibraryImage = computed(() => props.editingImage);

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
    formData.append('file', file);
    formData.append('directory', props.uploadDirectory);

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
      closeModal();

      // If we were editing, refresh the library and clear edit state
      if (editingLibraryImage.value) {
        // Could emit an event to refresh library if needed
        // Note: editingLibraryImage is a computed prop, so we don't set it directly
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

const cancelEdit = () => {
  // Cancel editing and close modal
  closeModal();
};

const closeModal = () => {
  emit('update:show', false);
  emit('close');

  // Reset state
  selectedFile.value = null;
  originalImage.value = null;
  resetCrop();
  errorMessage.value = '';
  uploading.value = false;
  uploadProgress.value = 0;
};

// Watch for editing image changes
watch(() => props.editingImage, (newImage) => {
  if (newImage && props.show) {
    // Load the image for editing
    loadEditingImage(newImage);
  }
});

const loadEditingImage = async (image: { url: string; name: string }) => {
  try {
    // Reset crop state first
    resetCrop();

    // Load the image for editing
    const img = new Image();
    const imageUrl = image.url.split('?')[0]; // Remove cache buster

    console.log('Loading image for editing:', imageUrl);

    img.onload = () => {
      console.log('Image loaded successfully for editing');
      originalImage.value = img;
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

// Window resize handler
const handleResize = () => {
  if (originalImage.value) {
    initializeCanvas();
  }
};

// Lifecycle
onMounted(() => {
  // Add resize listener
  window.addEventListener('resize', handleResize);

  // If we have an editing image when mounted, load it
  if (props.editingImage && props.show) {
    loadEditingImage(props.editingImage);
  }
});

onUnmounted(() => {
  window.removeEventListener('resize', handleResize);
  if (originalImage.value) {
    URL.revokeObjectURL(originalImage.value.src);
  }
});
</script>

<style scoped>
.image-editor-modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.75);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10000;
  padding: 2rem;
}

.image-editor-modal {
  background: var(--card-bg, #ffffff);
  border-radius: var(--border-radius-lg, 12px);
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  max-width: 90vw;
  max-height: 90vh;
  width: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.5rem;
  border-bottom: 1px solid var(--card-border, #e3e3e3);
}

.modal-header h3 {
  margin: 0;
  color: var(--text-primary, #222222);
  font-size: 1.25rem;
  font-weight: 600;
}

.close-button {
  background: none;
  border: none;
  cursor: pointer;
  padding: 0.5rem;
  border-radius: 4px;
  color: var(--text-secondary, #666666);
  transition: background 0.2s ease;
}

.close-button:hover {
  background: var(--card-bg-hover, #f8f9fa);
  color: var(--text-primary, #222222);
}

.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 1.5rem;
}

.upload-section {
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
  justify-content: flex-end;
  align-items: center;
  padding-bottom: 1rem;
  border-bottom: 1px solid var(--card-border, #e3e3e3);
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
  min-height: 400px;
  max-height: 60vh;
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

.upload-progress {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.75rem;
  background: var(--card-bg, #ffffff);
  border: 1px solid var(--card-border, #e3e3e3);
  border-radius: var(--border-radius-md, 8px);
  margin-top: 1rem;
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
  margin-top: 1rem;
}

.error-message svg {
  flex-shrink: 0;
}

@media (max-width: 768px) {
  .image-editor-modal-overlay {
    padding: 1rem;
  }

  .image-editor-modal {
    max-width: 95vw;
    max-height: 95vh;
  }

  .modal-header,
  .modal-body {
    padding: 1rem;
  }

  .editor-controls {
    flex-direction: column;
    gap: 1rem;
  }

  .control-group {
    width: 100%;
  }

  .cropper-container {
    min-height: 300px;
    max-height: 50vh;
  }
}
</style>