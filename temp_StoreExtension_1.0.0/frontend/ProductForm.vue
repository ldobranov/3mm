<template>
  <div class="modal-overlay" @click="$emit('cancel')">
    <div class="modal-content" @click.stop>
      <header class="modal-header">
        <h2>{{ editing ? t('store.admin.editProduct', 'Edit Product') : t('store.admin.addProduct', 'Add Product') }}</h2>
        <button @click="$emit('cancel')" class="close-btn">&times;</button>
      </header>

      <form @submit.prevent="save" class="product-form">
        <!-- Language Selector for Multilingual Content -->
        <div v-if="canAddTranslations" class="form-group">
          <label for="content-language">{{ t('store.contentLanguage', 'Content Language') }}</label>
          <select
            id="content-language"
            v-model="contentLanguage"
            class="select"
            @change="handleLanguageChange"
          >
            <option
              v-for="lang in availableLanguages"
              :key="lang"
              :value="lang"
            >
              {{ getLanguageName(lang) }} ({{ lang.toUpperCase() }})
            </option>
          </select>
        </div>

        <div class="form-group">
          <label for="name">{{ t('store.name', 'Name') }} *</label>
          <input
            id="name"
            v-model="currentName"
            type="text"
            required
            :placeholder="`${t('store.productName', 'Product Name')} (${contentLanguage.toUpperCase()})`"
          />
        </div>

        <div class="form-group">
          <label for="sku">{{ t('store.sku', 'SKU') }}</label>
          <input
            id="sku"
            v-model="form.sku"
            type="text"
            :placeholder="t('store.productSku', 'Product SKU')"
          />
        </div>

        <div class="form-group">
          <label for="price">{{ t('store.price', 'Price') }} *</label>
          <input
            id="price"
            v-model="form.price"
            type="number"
            step="0.01"
            required
            :placeholder="t('store.productPrice', 'Product Price')"
          />
        </div>

        <div class="form-group">
          <label for="sale_price">{{ t('store.salePrice', 'Sale Price') }}</label>
          <input
            id="sale_price"
            v-model="form.sale_price"
            type="number"
            step="0.01"
            :placeholder="t('store.productSalePrice', 'Sale Price (optional)')"
          />
        </div>

        <div class="form-group">
          <label for="stock_quantity">{{ t('store.stockQuantity', 'Stock Quantity') }}</label>
          <input
            id="stock_quantity"
            v-model.number="form.stock_quantity"
            type="number"
            min="0"
            :placeholder="t('store.productStock', 'Stock Quantity')"
          />
        </div>

        <div class="form-group">
          <label for="description">{{ t('store.description', 'Description') }}</label>
          <textarea
            id="description"
            v-model="currentDescription"
            rows="4"
            :placeholder="`${t('store.productDescription', 'Product Description')} (${contentLanguage.toUpperCase()})`"
          ></textarea>
        </div>

        <div class="form-group">
          <label for="short_description">{{ t('store.shortDescription', 'Short Description') }}</label>
          <textarea
            id="short_description"
            v-model="currentShortDescription"
            rows="2"
            :placeholder="`${t('store.productShortDescription', 'Short Description')} (${contentLanguage.toUpperCase()})`"
          ></textarea>
        </div>

        <div class="form-group">
          <label for="categories">{{ t('store.categories', 'Categories') }}</label>
          <select
            id="categories"
            v-model="selectedCategories"
            multiple
            class="categories-select"
            :placeholder="t('store.selectCategories', 'Select categories')"
          >
            <option
              v-for="category in availableCategories"
              :key="category.id"
              :value="category.id"
            >
              {{ category.name }}
            </option>
          </select>
          <small class="form-help">{{ t('store.categoriesHelp', 'Hold Ctrl/Cmd to select multiple categories') }}</small>
        </div>

        <div class="form-group">
          <label for="images">{{ t('store.images', 'Images') }}</label>

          <!-- Currently Selected Images Display -->
          <div v-if="allImagesForDisplay.length > 0" class="selected-images-section">
            <h4>{{ t('store.currentlySelectedImages', 'Currently Selected Images') }}</h4>
            <div class="selected-images-grid">
              <div
                v-for="(image, index) in allImagesForDisplay"
                :key="image.url"
                class="selected-image-item"
                draggable="true"
                @dragstart="handleDragStart($event, index)"
                @dragover="handleDragOver($event, index)"
                @drop="handleDrop($event, index)"
                @dragenter="handleDragEnter($event, index)"
                @dragleave="handleDragLeave($event, index)"
                :class="{ 'dragging': draggingIndex === index }"
              >
                <img :src="image.url" :alt="image.url.split('/').pop()" />
                <div class="drag-indicator">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="9" cy="12" r="1"/>
                    <circle cx="9" cy="5" r="1"/>
                    <circle cx="9" cy="19" r="1"/>
                    <circle cx="15" cy="12" r="1"/>
                    <circle cx="15" cy="5" r="1"/>
                    <circle cx="15" cy="19" r="1"/>
                  </svg>
                </div>
                <button
                  type="button"
                  @click="removeImage(index, image)"
                  class="remove-image-btn"
                  :title="t('store.removeImage', 'Remove image')"
                >
                  ×
                </button>
              </div>
            </div>
          </div>

          <!-- Advanced Image Upload Component with multiple selection -->
          <AdvancedImageUpload
            v-model="selectedImageUrls"
            :upload-url="'/api/store/upload-image'"
            :max-size="5"
            upload-directory="store"
            image-library-url="/api/store/images/list"
            :multiple="true"
            @upload-success="handleUploadSuccess"
            @upload-error="handleUploadError"
            @images-selected="handleImagesSelected"
          />
        </div>


        <div class="form-actions">
          <button type="button" @click="$emit('cancel')" class="cancel-btn">
            {{ t('store.cancel', 'Cancel') }}
          </button>
          <button type="submit" :disabled="loading" class="save-btn">
            {{ loading ? t('store.saving', 'Saving...') : t('store.save', 'Save') }}
          </button>
        </div>
      </form>
    </div>
  </div>

</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { useI18n } from '@/utils/i18n';
import http from '@/utils/dynamic-http';
import AdvancedImageUpload from '@/components/AdvancedImageUpload.vue';

const { t, currentLanguage, setLanguage } = useI18n();

interface Props {
  product?: any;
  availableLanguages?: string[];
}

const props = defineProps<Props>();
const emit = defineEmits<{
  save: [product: any];
  cancel: [];
}>();

// Reactive data
const loading = ref(false);
const editing = computed(() => !!props.product);
const availableCategories = ref<any[]>([]);
const selectedImageUrls = ref<string[]>([]); // For AdvancedImageUpload v-model (multiple)
const collectedImageUrls = ref<string[]>([]); // All collected images
const isAdmin = ref(true); // Assume admin for now - TODO: Get from user context
const contentLanguage = ref('en'); // Default to English
const draggingIndex = ref<number | null>(null); // For drag and drop reordering

const form = ref({
  name: '',
  sku: '',
  price: '',
  sale_price: '',
  stock_quantity: 0,
  description: '',
  short_description: '',
  categories: [] as number[],
  images: [] as string[]
} as Record<string, any>);

const selectedCategories = computed({
  get: () => form.value.categories,
  set: (value: number[]) => {
    form.value.categories = value;
  }
});

const availableLanguages = computed(() => props.availableLanguages || ['en']);
const canAddTranslations = computed(() => availableLanguages.value.length > 1); // > 1 because 'en' is always available

// Computed property for existing images in gallery format
const existingImages = computed(() => {
  return form.value.images.map((url: string) => ({ url }));
});

// Computed property for all images (existing + newly collected) for display
const allImagesForDisplay = computed(() => {
  const existing = form.value.images.map((url: string) => ({ url, isExisting: true }));
  const collected = collectedImageUrls.value.map((url: string) => ({ url, isExisting: false }));
  return [...existing, ...collected];
});

// Computed properties for multilingual content
const currentName = computed({
  get: () => getProductField('name', contentLanguage.value),
  set: (value) => setProductField('name', contentLanguage.value, value)
});

const currentDescription = computed({
  get: () => getProductField('description', contentLanguage.value),
  set: (value) => setProductField('description', contentLanguage.value, value)
});

const currentShortDescription = computed({
  get: () => getProductField('short_description', contentLanguage.value),
  set: (value) => setProductField('short_description', contentLanguage.value, value)
});

// Load available categories
const loadCategories = async () => {
  try {
    const response = await http.get('/api/store/categories');
    availableCategories.value = response.data.items || [];
  } catch (error) {
    console.error('Failed to load categories:', error);
  }
};

// Remove image from combined gallery (existing or newly collected)
const removeImage = (index: number, image: any) => {
  if (image.isExisting) {
    // Remove from existing images
    const existingIndex = form.value.images.findIndex((url: string) => url === image.url);
    if (existingIndex !== -1) {
      form.value.images.splice(existingIndex, 1);
    }
  } else {
    // Remove from newly collected images
    const collectedIndex = collectedImageUrls.value.findIndex((url: string) => url === image.url);
    if (collectedIndex !== -1) {
      collectedImageUrls.value.splice(collectedIndex, 1);
    }
  }
};

// Parse images from JSON string or return as array
const parseImages = (images: any): string[] => {
  if (!images) return [];
  let imageArray: string[] = [];
  if (Array.isArray(images)) {
    imageArray = images;
  } else {
    try {
      const parsed = JSON.parse(images);
      imageArray = Array.isArray(parsed) ? parsed : [];
    } catch {
      imageArray = [];
    }
  }

  // Convert relative URLs to full URLs
  return imageArray.map(url => {
    if (url.startsWith('/uploads')) {
      return `http://localhost:8887${url}`;
    }
    return url;
  });
};

// Load translations for editing product
const loadTranslations = async (productId: number) => {
  try {
    const response = await http.get(`/api/store/products/${productId}/translations`);
    const translations = response.data.translations || [];

    // Populate form with translation data
    translations.forEach((translation: any) => {
      const lang = translation.language_code;
      const data = translation.data || {};

      if (data.name) setProductField('name', lang, data.name);
      if (data.description) setProductField('description', lang, data.description);
      if (data.short_description) setProductField('short_description', lang, data.short_description);
    });
  } catch (error) {
    console.error('Failed to load translations:', error);
  }
};

// Initialize form with product data if editing
watch(() => props.product, async (newProduct) => {
  if (newProduct) {
    // Initialize multilingual fields
    const nameObj = typeof newProduct.name === 'string' ? { en: newProduct.name } : (newProduct.name || { en: '' });
    const descriptionObj = typeof newProduct.description === 'string' ? { en: newProduct.description } : (newProduct.description || { en: '' });
    const shortDescriptionObj = typeof newProduct.short_description === 'string' ? { en: newProduct.short_description } : (newProduct.short_description || { en: '' });

    // Parse categories from JSON string or array
    let categoriesArray: number[] = [];
    if (newProduct.categories) {
      if (Array.isArray(newProduct.categories)) {
        categoriesArray = newProduct.categories;
      } else if (typeof newProduct.categories === 'string') {
        try {
          const parsed = JSON.parse(newProduct.categories);
          categoriesArray = Array.isArray(parsed) ? parsed : [];
        } catch {
          categoriesArray = [];
        }
      }
    }

    form.value = {
      name: nameObj,
      sku: newProduct.sku || '',
      price: newProduct.price || '',
      sale_price: newProduct.sale_price || '',
      stock_quantity: newProduct.stock_quantity || 0,
      description: descriptionObj,
      short_description: shortDescriptionObj,
      categories: categoriesArray,
      images: parseImages(newProduct.images)
    };
    collectedImageUrls.value = []; // Reset collected images when editing
    selectedImageUrls.value = parseImages(newProduct.images); // Initialize with existing images

    // Load existing translations
    await loadTranslations(newProduct.id);
  } else {
    // Reset form for new product
    form.value = {
      name: { en: '' },
      sku: '',
      price: '',
      sale_price: '',
      stock_quantity: 0,
      description: { en: '' },
      short_description: { en: '' },
      categories: [],
      images: []
    };
    collectedImageUrls.value = [];
    selectedImageUrls.value = [];
  }
}, { immediate: true });

// Initialize content language to English (default) for editing
// Users can switch to other languages to add translations
watch(() => availableLanguages.value, (newLanguages) => {
  if (newLanguages && newLanguages.length > 1) {
    // Keep English as default, user can switch to other languages
    if (!contentLanguage.value || contentLanguage.value === 'en') {
      contentLanguage.value = 'en';
    }
  } else {
    // Only English available
    contentLanguage.value = 'en';
  }
}, { immediate: true });

// Get language display name
const getLanguageName = (code: string): string => {
  const names: Record<string, string> = {
    'bg': 'Български',
    'es': 'Español',
    'fr': 'Français',
    'de': 'Deutsch'
  };
  return names[code] || code.toUpperCase();
};

// Helper functions for multilingual content
const getProductField = (field: string, language: string): string => {
  if (!form.value[field] || typeof form.value[field] === 'string') {
    // Convert string to object if needed
    if (typeof form.value[field] === 'string') {
      form.value[field] = { en: form.value[field] };
    } else {
      form.value[field] = { en: '' };
    }
  }
  return form.value[field][language] || form.value[field]['en'] || '';
};

const setProductField = (field: string, language: string, value: string) => {
  if (!form.value[field] || typeof form.value[field] === 'string') {
    // Convert string to object if needed
    const currentValue = typeof form.value[field] === 'string' ? form.value[field] : '';
    form.value[field] = { en: currentValue };
  }
  form.value[field][language] = value;
};

const handleLanguageChange = () => {
  console.log('Language changed to:', contentLanguage.value);
  // Language changed, form fields will automatically update via computed properties
};

// Event handlers for AdvancedImageUpload component
const handleUploadSuccess = (file: { url: string; filename: string; size: number }) => {
  console.log('Upload success:', file);
  // Add uploaded image to collected images (prevent duplicates)
  if (!collectedImageUrls.value.includes(file.url) && !form.value.images.includes(file.url)) {
    collectedImageUrls.value.push(file.url);
  }
};

const handleUploadError = (error: string) => {
  console.error('Upload error:', error);
  alert(t('store.uploadError', 'Upload failed'));
};

const handleImageSelected = (image: { url: string; filename: string; size: number }) => {
  console.log('Image selected from library:', image);
  // Add selected image to collected images (prevent duplicates)
  if (!collectedImageUrls.value.includes(image.url) && !form.value.images.includes(image.url)) {
    collectedImageUrls.value.push(image.url);
  }
};

const handleImagesSelected = (images: Array<{ url: string; filename: string; size: number }>) => {
  console.log('Multiple images selected from library:', images);
  // Add all selected images to collected images (prevent duplicates)
  images.forEach(image => {
    if (!collectedImageUrls.value.includes(image.url) && !form.value.images.includes(image.url)) {
      collectedImageUrls.value.push(image.url);
    }
  });
};

// Drag and drop handlers for reordering images
const handleDragStart = (event: DragEvent, index: number) => {
  console.log('Drag start:', index);
  draggingIndex.value = index;
  console.log('Set draggingIndex to:', draggingIndex.value);
  event.dataTransfer!.effectAllowed = 'move';
  event.dataTransfer!.setData('text/plain', index.toString());
};

const handleDragOver = (event: DragEvent, index: number) => {
  event.preventDefault();
  event.dataTransfer!.dropEffect = 'move';
};

const handleDragEnter = (event: DragEvent, index: number) => {
  event.preventDefault();
  if (draggingIndex.value !== null && draggingIndex.value !== index) {
    // Visual feedback for drop target
    const target = event.currentTarget as HTMLElement;
    target.classList.add('drag-over');
  }
};

const handleDragLeave = (event: DragEvent, index: number) => {
  event.preventDefault();
  const target = event.currentTarget as HTMLElement;
  target.classList.remove('drag-over');
};

const handleDrop = (event: DragEvent, dropIndex: number) => {
  console.log('Drop:', dropIndex, 'from:', draggingIndex.value);
  event.preventDefault();
  const target = event.currentTarget as HTMLElement;
  target.classList.remove('drag-over');

  const dragIndex = draggingIndex.value;
  if (dragIndex === null || dragIndex === dropIndex) {
    console.log('No reorder needed');
    draggingIndex.value = null;
    return;
  }

  // Reorder the images array
  const images = [...allImagesForDisplay.value];
  const draggedItem = images[dragIndex];

  // Remove dragged item
  images.splice(dragIndex, 1);
  // Insert at new position
  images.splice(dropIndex, 0, draggedItem);

  // Update the underlying arrays based on the reordered display
  const existingImages: string[] = [];
  const collectedImages: string[] = [];

  images.forEach(image => {
    if (image.isExisting) {
      existingImages.push(image.url);
    } else {
      collectedImages.push(image.url);
    }
  });

  form.value.images = existingImages;
  collectedImageUrls.value = collectedImages;

  draggingIndex.value = null;
};

// Load categories on mount
onMounted(async () => {
  // Force reload translations to ensure extension translations are loaded
  if (currentLanguage.value !== 'en') {
    console.log('ProductForm: Forcing translation reload for', currentLanguage.value);
    await setLanguage(currentLanguage.value);
  }

  loadCategories();
});

const save = async () => {
  loading.value = true;
  try {
    // Combine existing images with newly collected ones
    const allImages = [
      ...form.value.images,
      ...collectedImageUrls.value
    ];

    // Extract default (English) values for base product fields
    const productData = {
      sku: form.value.sku,
      price: form.value.price,
      sale_price: form.value.sale_price,
      stock_quantity: form.value.stock_quantity,
      categories: form.value.categories,
      images: allImages,
      name: getProductField('name', 'en'),
      description: getProductField('description', 'en'),
      short_description: getProductField('short_description', 'en')
    };

    // Prepare translations data for all non-English languages
    const translationsData = prepareTranslationsData();

    // Emit both product data and translations to parent
    emit('save', { productData, translationsData });
  } catch (error) {
    console.error('Error preparing product data:', error);
  } finally {
    loading.value = false;
  }
};

const prepareTranslationsData = () => {
  const translations = [];

  // Get all available languages except English
  const translationLanguages = availableLanguages.value.filter(lang => lang !== 'en');

  for (const language of translationLanguages) {
    const name = getProductField('name', language);
    const description = getProductField('description', language);
    const shortDescription = getProductField('short_description', language);

    // Only include if there's actual content for this language
    if (name || description || shortDescription) {
      const translationData = {
        language_code: language,
        translations: {
          name: name || undefined,
          description: description || undefined,
          short_description: shortDescription || undefined
        }
      };

      // Filter out undefined values
      const filteredTranslations: any = {};
      if (translationData.translations.name) filteredTranslations.name = translationData.translations.name;
      if (translationData.translations.description) filteredTranslations.description = translationData.translations.description;
      if (translationData.translations.short_description) filteredTranslations.short_description = translationData.translations.short_description;

      if (Object.keys(filteredTranslations).length > 0) {
        translations.push({
          language_code: language,
          translations: filteredTranslations
        });
      }
    }
  }

  return translations;
};

</script>

<style scoped>
.modal-overlay {
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

.modal-content {
  background: var(--card-bg, #ffffff);
  border-radius: var(--border-radius-lg, 12px);
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
  max-width: 600px;
  width: 90%;
  max-height: 90vh;
  overflow-y: auto;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.5rem;
  border-bottom: 1px solid var(--card-border, #e3e3e3);
}

.modal-header h2 {
  margin: 0;
  color: var(--text-primary, #222222);
}

.close-btn {
  background: none;
  border: none;
  font-size: 2rem;
  color: var(--text-secondary, #666666);
  cursor: pointer;
  padding: 0;
  width: 2rem;
  height: 2rem;
  display: flex;
  align-items: center;
  justify-content: center;
}

.close-btn:hover {
  color: var(--text-primary, #222222);
}

.product-form {
  padding: 1.5rem;
}

.form-group {
  margin-bottom: 1.5rem;
}

.form-group label {
  display: block;
  margin-bottom: 0.5rem;
  color: var(--text-primary, #222222);
  font-weight: 500;
}

.form-group input,
.form-group textarea,
.form-group select {
  width: 100%;
  padding: 0.75rem;
  border: 1px solid var(--card-border, #e3e3e3);
  border-radius: var(--border-radius-md, 8px);
  font-size: 1rem;
  transition: border-color 0.2s ease;
}

.form-group input:focus,
.form-group textarea:focus,
.form-group select:focus {
  outline: none;
  border-color: var(--button-primary-bg, #007bff);
}

.form-group textarea {
  resize: vertical;
  min-height: 80px;
}

.categories-select {
  width: 100%;
  padding: 0.75rem;
  border: 1px solid var(--card-border, #e3e3e3);
  border-radius: var(--border-radius-md, 8px);
  font-size: 1rem;
  min-height: 120px;
  background: var(--card-bg, #ffffff);
}

.categories-select:focus {
  outline: none;
  border-color: var(--button-primary-bg, #007bff);
}

.form-help {
  display: block;
  margin-top: 0.25rem;
  color: var(--text-secondary, #666666);
  font-size: 0.875rem;
}

.image-upload-section {
  display: flex;
  flex-direction: column;
  gap: 1rem;
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
  align-self: flex-start;
}

.upload-btn:hover:not(:disabled) {
  background: var(--button-secondary-hover, #545b62);
}

.upload-btn:disabled {
  background: var(--text-secondary, #666666);
  cursor: not-allowed;
}

.selected-images-section {
  margin-bottom: 1.5rem;
  padding: 1rem;
  background: var(--card-bg, #f8f9fa);
  border: 1px solid var(--card-border, #e3e3e3);
  border-radius: var(--border-radius-md, 8px);
}

.selected-images-section h4 {
  margin: 0 0 1rem 0;
  color: var(--text-primary, #222222);
  font-size: 1rem;
  font-weight: 500;
}

.selected-images-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
  gap: 1rem;
}

.selected-image-item {
  position: relative;
  display: inline-block;
  cursor: grab;
  transition: all 0.2s ease;
}

.selected-image-item:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
}

.selected-image-item.dragging {
  opacity: 0.5;
  transform: rotate(5deg);
  cursor: grabbing;
}

.selected-image-item.drag-over {
  border-color: var(--button-primary-bg, #007bff);
  box-shadow: 0 0 8px rgba(0, 123, 255, 0.3);
}

.selected-image-item img {
  width: 100%;
  height: 80px;
  object-fit: cover;
  border-radius: var(--border-radius-md, 8px);
  border: 1px solid var(--card-border, #e3e3e3);
}

.drag-indicator {
  position: absolute;
  bottom: 4px;
  right: 4px;
  width: 24px;
  height: 24px;
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid rgba(0, 0, 0, 0.1);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
  transition: all 0.2s ease;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.remove-image-btn {
  position: absolute;
  top: -8px;
  right: -8px;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--error-bg, #dc3545);
  color: white;
  border: none;
  cursor: pointer;
  font-size: 16px;
  font-weight: bold;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.2s ease;
  z-index: 10;
}

.remove-image-btn:hover {
  background: var(--error-hover, #c82333);
}

.uploaded-images, .existing-images {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
}

.existing-images h4 {
  width: 100%;
  margin: 0 0 0.5rem 0;
  color: var(--text-primary, #222222);
  font-size: 1rem;
  font-weight: 500;
}

.image-item {
  position: relative;
  display: inline-block;
}

.image-preview {
  width: 100px;
  height: 100px;
  object-fit: cover;
  border-radius: var(--border-radius-md, 8px);
  border: 1px solid var(--card-border, #e3e3e3);
}

.remove-image-btn {
  position: absolute;
  top: -8px;
  right: -8px;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--error-bg, #dc3545);
  color: white;
  border: none;
  cursor: pointer;
  font-size: 16px;
  font-weight: bold;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.2s ease;
}

.remove-image-btn:hover {
  background: var(--error-hover, #c82333);
}

.form-section {
  margin-top: 2rem;
  padding-top: 1.5rem;
  border-top: 1px solid var(--card-border, #e3e3e3);
}


.form-actions {
  display: flex;
  gap: 1rem;
  justify-content: flex-end;
  margin-top: 2rem;
  padding-top: 1rem;
  border-top: 1px solid var(--card-border, #e3e3e3);
}

.cancel-btn, .save-btn {
  padding: 0.75rem 1.5rem;
  border: none;
  border-radius: var(--border-radius-md, 8px);
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.cancel-btn {
  background: var(--button-secondary-bg, #6c757d);
  color: var(--button-secondary-text, #ffffff);
}

.cancel-btn:hover {
  background: var(--button-secondary-hover, #545b62);
}

.save-btn {
  background: var(--button-primary-bg, #007bff);
  color: var(--button-primary-text, #ffffff);
}

.save-btn:hover:not(:disabled) {
  background: var(--button-primary-hover, #0056b3);
}

.save-btn:disabled {
  background: var(--text-secondary, #666666);
  cursor: not-allowed;
}

/* Responsive Design */
@media (max-width: 768px) {
  .modal-content {
    width: 95%;
    margin: 1rem;
  }

  .modal-header, .product-form {
    padding: 1rem;
  }

  .form-actions {
    flex-direction: column;
  }

  .cancel-btn, .save-btn {
    width: 100%;
  }
}

</style>