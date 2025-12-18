<template>
  <div class="modal-overlay" @click="$emit('cancel')">
    <div class="modal-content" @click.stop>
      <header class="modal-header">
        <h2>{{ editing ? t('store.admin.editCategory', 'Edit Category') : t('store.admin.addCategory', 'Add Category') }}</h2>
        <button @click="$emit('cancel')" class="close-btn">&times;</button>
      </header>

      <form @submit.prevent="save" class="category-form">
        <!-- Language Selector -->
        <div class="form-group">
          <label for="language">{{ t('store.language', 'Language') }}</label>
          <select
            id="language"
            v-model="selectedLanguage"
            class="language-selector"
          >
            <option
              v-for="lang in availableLanguages"
              :key="lang"
              :value="lang"
            >
              {{ getLanguageName(lang) }}
            </option>
          </select>
        </div>

        <!-- Multilingual Fields -->
        <div class="form-group">
          <label for="name">{{ t('store.name', 'Name') }} *</label>
          <input
            id="name"
            v-model="form.name"
            type="text"
            required
            :placeholder="t('store.categoryName', 'Category Name')"
          />
        </div>

        <div class="form-group">
          <label for="slug">{{ t('store.slug', 'Slug') }} *</label>
          <input
            id="slug"
            v-model="form.slug"
            type="text"
            required
            :placeholder="t('store.categorySlug', 'category-slug')"
            :disabled="selectedLanguage !== 'en'"
          />
        </div>

        <div class="form-group">
          <label for="description">{{ t('store.description', 'Description') }}</label>
          <textarea
            id="description"
            v-model="form.description"
            rows="3"
            :placeholder="t('store.categoryDescription', 'Category Description')"
          ></textarea>
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
import { ref, watch, computed, onMounted } from 'vue';
import { useI18n } from '@/utils/i18n';
import http from '@/utils/dynamic-http';

const { t, currentLanguage, setLanguage } = useI18n();

interface Props {
  category?: any;
  availableLanguages?: string[];
}

const props = defineProps<Props>();
const emit = defineEmits<{
  save: [data: any];
  cancel: [];
}>();

const loading = ref(false);
const editing = ref(!!props.category);
const selectedLanguage = ref('en');
const availableLanguages = ref<string[]>(props.availableLanguages || ['en', 'bg']);

const form = ref({
  name: '',
  slug: '',
  description: ''
});

const getLanguageName = (code: string) => {
  const languageNames: { [key: string]: string } = {
    'en': 'English',
    'bg': 'Bulgarian',
    'es': 'Spanish',
    'fr': 'French',
    'de': 'German'
  };
  return languageNames[code] || code.toUpperCase();
};

const loadCategoryData = async (categoryId: number, language: string) => {
  try {
    // Load base category data (always English)
    const baseResponse = await http.get(`/api/store/categories/${categoryId}`);
    const baseData = baseResponse.data;

    if (language === 'en') {
      // Use base data for English
      form.value = {
        name: baseData.name || '',
        slug: baseData.slug || '',
        description: baseData.description || ''
      };
    } else {
      // Load translation for selected language
      try {
        const translationResponse = await http.get(`/api/store/categories/${categoryId}/translations`);
        const translations = translationResponse.data.translations || [];
        const currentTranslation = translations.find((t: any) => t.language_code === language);

        if (currentTranslation && currentTranslation.data) {
          // Merge translation with base data
          form.value = {
            name: currentTranslation.data.name || baseData.name || '',
            slug: baseData.slug || '', // Slug stays in English
            description: currentTranslation.data.description || baseData.description || ''
          };
        } else {
          // No translation, use base data
          form.value = {
            name: baseData.name || '',
            slug: baseData.slug || '',
            description: baseData.description || ''
          };
        }
      } catch (translationError) {
        console.warn('Failed to load translation, using base data:', translationError);
        form.value = {
          name: baseData.name || '',
          slug: baseData.slug || '',
          description: baseData.description || ''
        };
      }
    }
  } catch (error) {
    console.error('Failed to load category data:', error);
  }
};

// Initialize form with category data if editing
watch(() => props.category, async (newCategory) => {
  if (newCategory) {
    editing.value = true;
    await loadCategoryData(newCategory.id, selectedLanguage.value);
  } else {
    // Reset form for new category
    form.value = {
      name: '',
      slug: '',
      description: ''
    };
    editing.value = false;
  }
}, { immediate: true });

// Watch for language changes and reload data
watch(selectedLanguage, async (newLanguage) => {
  if (props.category?.id) {
    await loadCategoryData(props.category.id, newLanguage);
  }
});

// Force reload translations on mount
onMounted(async () => {
  if (currentLanguage.value !== 'en') {
    console.log('CategoryForm: Forcing translation reload for', currentLanguage.value);
    await setLanguage(currentLanguage.value);
  }
});

// Auto-generate slug from name (only for English)
watch(() => form.value.name, (newName) => {
  if (newName && !editing.value && selectedLanguage.value === 'en') {
    form.value.slug = newName.toLowerCase()
      .replace(/[^a-z0-9\s-]/g, '')
      .replace(/\s+/g, '-')
      .replace(/-+/g, '-')
      .trim();
  }
});

const save = async () => {
  loading.value = true;
  try {
    if (selectedLanguage.value === 'en') {
      // Save base category data
      if (editing.value) {
        await http.put(`/api/store/categories/${props.category.id}`, form.value);
      } else {
        const response = await http.post('/api/store/categories', form.value);
        emit('save', response.data);
        return;
      }
    } else {
      // Save translation
      if (!props.category?.id) return;

      const translationData = {
        language_code: selectedLanguage.value,
        translations: {
          name: form.value.name,
          description: form.value.description
        }
      };

      await http.post(`/api/store/categories/${props.category.id}/translations`, translationData);
    }

    emit('save', form.value);
  } catch (error) {
    console.error('Error saving category:', error);
  } finally {
    loading.value = false;
  }
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
  max-width: 500px;
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

.category-form {
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
.form-group textarea {
  width: 100%;
  padding: 0.75rem;
  border: 1px solid var(--card-border, #e3e3e3);
  border-radius: var(--border-radius-md, 8px);
  font-size: 1rem;
  transition: border-color 0.2s ease;
}

.form-group input:focus,
.form-group textarea:focus {
  outline: none;
  border-color: var(--button-primary-bg, #007bff);
}

.form-group textarea {
  resize: vertical;
  min-height: 80px;
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

  .modal-header, .category-form {
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