<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue';
import { useRouter } from 'vue-router';
import { useI18n, i18n } from '@/utils/i18n';
import http from '@/utils/dynamic-http';
import AdvancedImageUpload from '@/components/AdvancedImageUpload.vue';
import { useExtensionRelationships } from '@/utils/extension-relationships';

const { t, currentLanguage } = useI18n();
const router = useRouter();
const { getComponent, extensionProvides, loadComponentFromExtension, getProvidersOf, getContentEmbedders, refreshExtensions } = useExtensionRelationships();

interface Page {
  id: number;
  title: string;
  slug: string;
  is_public: boolean;
  owner_id: number;
}

interface ContentEmbedderConfig {
  extension: string;
  type: string;
  label: string;
  component: string;
  format_api: string;
  ui_translations_api: string;
  description: string;
}

const pages = ref<Page[]>([]);
const loading = ref(false);
const extensionEnabled = ref(false);
const showCreateModal = ref(false);
const showEditModal = ref(false);
const productSelectorProvider = ref<string | null>(null);

// Store settings (used for embedder currency)
const storeCurrency = ref('USD');
const storeCurrencyFormats = ref<Record<string, { label: string; position: 'prefix' | 'suffix' }>>({});

// Get available content embedders dynamically
const availableEmbedders = computed((): Record<string, ContentEmbedderConfig> => {
  return getContentEmbedders();
});

// Check if any content embedders are available
const hasContentEmbedders = computed(() => {
  return Object.keys(availableEmbedders.value).length > 0;
});

// Computed embedder labels for reactivity
const embedderLabels = computed(() => {
  // Depend on i18n version to ensure reactivity
  const _ = i18n.getVersion();
  const labels: Record<string, string> = {};
  for (const [key, config] of Object.entries(availableEmbedders.value)) {
    labels[key] = t(config.label, config.label);
  }
  return labels;
});


// Form data for creating pages
const newPageTitle = ref('');
const newPageContent = ref('');
const newPageIsPublic = ref(true);
const newPageSlug = ref('');
const creating = ref(false);

// Multilingual support for creating pages
const newPageContentLanguage = ref('en');
const newPageTranslations = ref<any>({});

// Form data for editing pages
const editingPage = ref<Page | null>(null);
const editPageTitle = ref('');
const editPageContent = ref('');
const editPageIsPublic = ref(true);
const editPageSlug = ref('');
const updating = ref(false);

// Store original English content for proper switching
const originalEnglishTitle = ref('');
const originalEnglishContent = ref('');

// Track current English content (updated when editing in English tab)
const currentEnglishTitle = ref('');
const currentEnglishContent = ref('');

// Multilingual support
const availableLanguages = ref<string[]>(['en']);
const contentLanguage = ref('en');
const pageTranslations = ref<any>({});
const loadingTranslations = ref(false);

// Image upload functionality
const showImageUpload = ref(false);
const selectedImages = ref<string[]>([]);
const showNewImageUpload = ref(false);
const selectedNewImages = ref<string[]>([]);

// Content embedding functionality - now supports multiple embedder types
const showProductSelector = ref(false);
const showNewProductSelector = ref(false);

// Dynamic UI translations from content embedders
const embedderTranslations = ref<Record<string, any>>({});
const activeEmbedder = ref<string | null>(null);

// Ensure embedder-related extension translations stay in sync with the UI language.
watch(currentLanguage, async (newLang) => {
  try {
    await i18n.loadExtensionTranslationsForExtension('PagesExtension', newLang);
  } catch (error) {
    console.warn('Failed to reload PagesExtension translations:', error);
  }

  try {
    // Load translations for all extensions that provide content embedders
    const embedderExts = new Set(Object.keys(availableEmbedders.value).map(k => k.split('.')[0]));
    for (const ext of embedderExts) {
      await i18n.loadExtensionTranslationsForExtension(ext, newLang);
    }
  } catch (error) {
    console.warn('Failed to reload embedder extension translations:', error);
  }
});

const checkExtensionStatus = async () => {
  try {
    const response = await http.get('/api/extensions');
    const extensions = response.data.items || [];
    const pagesExt = extensions.find((ext: any) => ext.name === 'PagesExtension' && ext.is_enabled);
    extensionEnabled.value = !!pagesExt;

    // Refresh extension relationships to reflect enabled/disabled status
    await refreshExtensions();
  } catch (error) {
    console.warn('Failed to check extension status:', error);
    extensionEnabled.value = false;
  }
};

const loadPages = async () => {
  if (!extensionEnabled.value) return;

  try {
    loading.value = true;
    const response = await http.get('/api/pages/read');
    pages.value = response.data.items || [];
  } catch (error) {
    console.error('Failed to load pages:', error);
  } finally {
    loading.value = false;
  }
};

const loadStoreSettings = async () => {
  try {
    const response = await http.get('/api/store/settings');
    storeCurrency.value = response.data.currency || 'USD';
    storeCurrencyFormats.value = response.data.currencies || {};
  } catch (error) {
    console.warn('Failed to load store settings for currency, falling back to USD:', error);
    storeCurrency.value = 'USD';
    storeCurrencyFormats.value = {};
  }
};

const createPage = () => {
  showCreateModal.value = true;
  newPageTitle.value = '';
  newPageContent.value = '';
  newPageIsPublic.value = true;
  newPageSlug.value = '';
  newPageContentLanguage.value = 'en';
  newPageTranslations.value = {};
};

const closeCreateModal = () => {
  showCreateModal.value = false;
  newPageContentLanguage.value = 'en';
  newPageTranslations.value = {};
};

const closeEditModal = () => {
  showEditModal.value = false;
  editingPage.value = null;
  pageTranslations.value = {};
  contentLanguage.value = 'en';
  originalEnglishTitle.value = '';
  originalEnglishContent.value = '';
  currentEnglishTitle.value = '';
  currentEnglishContent.value = '';
};

const submitCreatePage = async () => {
  // Get English content for base page creation (regardless of current language tab)
  const englishTranslation = newPageTranslations.value['en'];
  const englishTitle = englishTranslation ? englishTranslation.title : newPageTitle.value;
  const englishContent = englishTranslation ? englishTranslation.content : newPageContent.value;

  if (!englishTitle.trim()) {
    alert(t('extensions.pagesextension.pages.titleRequired') || 'Title is required');
    return;
  }

  try {
    creating.value = true;

    // Generate slug from English title
    const slug = newPageSlug.value.trim() ||
      englishTitle.toLowerCase().replace(/[^a-z0-9\s-]/g, '').replace(/\s+/g, '-');

    // Create page with English content
    const pageData = {
      title: englishTitle.trim(),
      content: englishContent,
      slug: slug,
      is_public: newPageIsPublic.value
    };

    // Send as FormData to handle HTML content properly
    const formData = new FormData();
    Object.keys(pageData).forEach(key => {
      const value = (pageData as any)[key];
      if (value !== undefined && value !== null) {
        formData.append(key, String(value));
      }
    });

    const response = await http.post('/api/pages/create', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    });

    if (response.data.id) {
      const pageId = response.data.id;

      // Save current form content to translations before saving
      newPageTranslations.value[newPageContentLanguage.value] = {
        title: newPageTitle.value,
        content: newPageContent.value
      };

      // Save translations for other languages
      await saveNewPageTranslations(pageId);

      alert(t('pages.pageCreated') || 'Page created successfully!');
      closeCreateModal();
      await loadPages();
    }
  } catch (error: any) {
    console.error('Failed to create page:', error);
    alert(error.response?.data?.detail || 'Failed to create page');
  } finally {
    creating.value = false;
  }
};

const saveNewPageTranslations = async (pageId: number) => {
  // Save translations for all non-English languages that have content
  for (const lang of availableLanguages.value.filter(l => l !== 'en')) {
    const translation = newPageTranslations.value[lang];
    if (translation && (translation.title || translation.content)) {
      try {
        const formData = new FormData();
        formData.append('language_code', lang);
        formData.append('translations', JSON.stringify({
          title: translation.title || undefined,
          content: translation.content || undefined
        }));

        await http.post(`/api/pages/${pageId}/translations`, formData, {
          headers: {
            'Content-Type': 'multipart/form-data'
          }
        });
        console.log(`Saved ${lang} translation for new page`);
      } catch (error: any) {
        console.warn(`Failed to save ${lang} translation (this is normal if translations table doesn't exist yet):`, error);
        // Don't show error to user - translations are optional
      }
    }
  }
};

const submitEditPage = async () => {
  if (!editingPage.value) return;

  try {
    updating.value = true;

    // Update current English content with any changes made in the current tab
    if (contentLanguage.value === 'en') {
      currentEnglishTitle.value = editPageTitle.value;
      currentEnglishContent.value = editPageContent.value;
    }

    // Always save base English content first (regardless of current language tab)
    // English content comes from the current English content (which may have been modified)
    const englishTitle = currentEnglishTitle.value;
    const englishContent = currentEnglishContent.value;

    if (!englishTitle.trim()) {
      alert(t('pages.titleRequired') || 'Title is required');
      return;
    }

    // Save base English content
    const pageData: any = {
      title: englishTitle.trim(),
      is_public: editPageIsPublic.value
    };

    if (englishContent) {
      pageData.content = englishContent;
    }

    if (editPageSlug.value.trim()) {
      pageData.slug = editPageSlug.value.trim();
    }

    // Send as FormData to handle HTML content properly
    const formData = new FormData();
    Object.keys(pageData).forEach(key => {
      const value = (pageData as any)[key];
      if (value !== undefined && value !== null) {
        formData.append(key, String(value));
      }
    });

    await http.put(`/api/pages/${editingPage.value.id}`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    });

    // Update current translation data with any changes made in the current tab
    if (contentLanguage.value !== 'en') {
      pageTranslations.value[contentLanguage.value] = {
        title: editPageTitle.value,
        content: editPageContent.value
      };
    }

    // Save all translations that have content
    for (const lang of availableLanguages.value.filter(l => l !== 'en')) {
      const translation = pageTranslations.value[lang];
      if (translation && (translation.title || translation.content)) {
        try {
          const formData = new FormData();
          formData.append('language_code', lang);
          formData.append('translations', JSON.stringify({
            title: translation.title || undefined,
            content: translation.content || undefined
          }));

          await http.post(`/api/pages/${editingPage.value.id}/translations`, formData, {
            headers: {
              'Content-Type': 'multipart/form-data'
            }
          });
        } catch (error: any) {
          console.warn(`Failed to save ${lang} translation:`, error);
          // Don't show error to user - translations are optional
        }
      }
    }

    alert(t('pages.pageUpdated') || 'Page updated successfully!');

    closeEditModal();
    await loadPages();
  } catch (error: any) {
    console.error('Failed to update page:', error);
    console.error('Error response:', error.response?.data);
    alert(error.response?.data?.detail || error.response?.data?.message || 'Failed to update page');
  } finally {
    updating.value = false;
  }
};

const editPage = async (page: Page) => {
  try {
    // Load full page data including content
    const response = await http.get(`/api/pages/${page.id}`);
    const pageData = response.data;

    editingPage.value = page;
    editPageTitle.value = pageData.title;
    editPageContent.value = pageData.content || '';
    editPageIsPublic.value = pageData.is_public;
    editPageSlug.value = pageData.slug;

    // Store original English content for proper switching
    originalEnglishTitle.value = pageData.title;
    originalEnglishContent.value = pageData.content || '';

    // Initialize current English content (can be modified during editing)
    currentEnglishTitle.value = pageData.title;
    currentEnglishContent.value = pageData.content || '';

    // Load translations for this page
    await loadPageTranslations(page.id);

    showEditModal.value = true;
  } catch (error) {
    console.error('Failed to load page for editing:', error);
    alert('Failed to load page content for editing');
  }
};

const loadPageTranslations = async (pageId: number) => {
  try {
    loadingTranslations.value = true;
    const response = await http.get(`/api/pages/${pageId}/translations`);
    const translations = response.data.translations || [];

    // Convert array to object for easier access
    pageTranslations.value = {};
    translations.forEach((t: any) => {
      pageTranslations.value[t.language_code] = t.data;
    });
  } catch (error: any) {
    console.warn('Failed to load page translations (this is normal if translations table doesn\'t exist yet):', error);
    pageTranslations.value = {};
    // Don't show error to user - just continue with empty translations
  } finally {
    loadingTranslations.value = false;
  }
};


const switchContentLanguage = (lang: string) => {
  // Save current language data before switching
  if (contentLanguage.value === 'en') {
    // Save current English content when switching away from English tab
    currentEnglishTitle.value = editPageTitle.value;
    currentEnglishContent.value = editPageContent.value;
  } else {
    // Save translation data when switching away from translation tab
    pageTranslations.value[contentLanguage.value] = {
      title: editPageTitle.value,
      content: editPageContent.value
    };
  }

  contentLanguage.value = lang;

  // Load data for new language
  if (lang === 'en') {
    // For English, load the current English content (which may have been modified)
    editPageTitle.value = currentEnglishTitle.value;
    editPageContent.value = currentEnglishContent.value;
  } else {
    // For other languages, load from translations
    const translation = pageTranslations.value[lang];
    if (translation) {
      editPageTitle.value = translation.title || '';
      editPageContent.value = translation.content || '';
    } else {
      // No translation exists yet, start with empty fields
      editPageTitle.value = '';
      editPageContent.value = '';
    }
  }
};

const switchNewContentLanguage = (lang: string) => {
  // Save current language data before switching
  newPageTranslations.value[newPageContentLanguage.value] = {
    title: newPageTitle.value,
    content: newPageContent.value
  };

  newPageContentLanguage.value = lang;

  // Load data for new language
  const translation = newPageTranslations.value[lang];
  if (translation) {
    newPageTitle.value = translation.title || '';
    newPageContent.value = translation.content || '';
  } else {
    // No translation exists yet, start with empty fields
    newPageTitle.value = '';
    newPageContent.value = '';
  }
};

const loadAvailableLanguages = async () => {
  try {
    const response = await http.get('/language/available');
    const languages = response.data.languages || ['en'];
    // Ensure 'en' is first
    availableLanguages.value = ['en', ...languages.filter((lang: string) => lang !== 'en')];
  } catch (error) {
    console.error('Failed to fetch available languages:', error);
    availableLanguages.value = ['en'];
  }
};

const getLanguageName = (code: string): string => {
  return t(`languages.${code}`, code.toUpperCase());
};

// Activate a specific content embedder
const activateEmbedder = async (embedderKey: string, isNewPage: boolean = false) => {
  const embedderConfig = availableEmbedders.value[embedderKey];
  if (!embedderConfig) return;

  activeEmbedder.value = embedderKey;
  const [extensionName] = embedderKey.split('.');

  try {
    // Load the component for this embedder
    const component = await getComponent(extensionName, embedderConfig.component);
    if (component) {
      ProductSelectorComponent.value = component;
    }

    // Load UI translations - use the extension's router prefix (lowercase without 'Extension')
    const extensionPrefix = extensionName.replace(/Extension$/i, '').toLowerCase();
    const response = await http.get(`/api/${extensionPrefix}/${embedderConfig.ui_translations_api}`, {
      params: { language: currentLanguage.value }
    });
    embedderTranslations.value = response.data;

    // Show the appropriate selector based on context
    if (isNewPage) {
      showNewProductSelector.value = true;
    } else {
      showProductSelector.value = true;
    }
  } catch (error) {
    console.error(`Failed to activate embedder ${embedderKey}:`, error);
  }
};

// Product embedding functionality - will be set asynchronously
const ProductSelectorComponent = ref<any>(null);


// Content insertion handlers - dynamically call the appropriate extension API
const insertProducts = async (products: any[]) => {
  if (!activeEmbedder.value) return;

  const embedderConfig = availableEmbedders.value[activeEmbedder.value];
  if (!embedderConfig) return;

  const [extensionName] = activeEmbedder.value.split('.');

  try {
    // Call the extension's format API dynamically
    const formData = new FormData();
    formData.append('products', JSON.stringify(products));
    formData.append('language', contentLanguage.value);
    formData.append('currency', storeCurrency.value);

    // Call the extension's format API dynamically
    const extensionPrefix = extensionName.replace(/Extension$/i, '').toLowerCase();
    const response = await http.post(`/api/${extensionPrefix}/${embedderConfig.format_api}`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    });

    const contentHtml = response.data.html;

    if (contentLanguage.value === 'en') {
      editPageContent.value += contentHtml;
    } else {
      if (!pageTranslations.value[contentLanguage.value]) {
        pageTranslations.value[contentLanguage.value] = { title: '', content: '' };
      }
      pageTranslations.value[contentLanguage.value].content += contentHtml;
      editPageContent.value = pageTranslations.value[contentLanguage.value].content;
    }
  } catch (error) {
    console.error('Failed to format content:', error);
    // Fallback to basic text if API fails
    const fallbackHtml = products.map(p => `<p>Product: ${p.name}</p>`).join('\n');
    if (contentLanguage.value === 'en') {
      editPageContent.value += fallbackHtml;
    } else {
      if (!pageTranslations.value[contentLanguage.value]) {
        pageTranslations.value[contentLanguage.value] = { title: '', content: '' };
      }
      pageTranslations.value[contentLanguage.value].content += fallbackHtml;
      editPageContent.value = pageTranslations.value[contentLanguage.value].content;
    }
  }
  showProductSelector.value = false;
};

const insertNewProducts = async (products: any[]) => {
  if (!activeEmbedder.value) return;

  const embedderConfig = availableEmbedders.value[activeEmbedder.value];
  if (!embedderConfig) return;

  const [extensionName] = activeEmbedder.value.split('.');

  try {
    // Call the extension's format API dynamically
    const formData = new FormData();
    formData.append('products', JSON.stringify(products));
    formData.append('language', newPageContentLanguage.value);
    formData.append('currency', storeCurrency.value);

    // Call the extension's format API dynamically
    const extensionPrefix = extensionName.replace(/Extension$/i, '').toLowerCase();
    const response = await http.post(`/api/${extensionPrefix}/${embedderConfig.format_api}`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    });

    const contentHtml = response.data.html;

    if (newPageContentLanguage.value === 'en') {
      newPageContent.value += contentHtml;
    } else {
      if (!newPageTranslations.value[newPageContentLanguage.value]) {
        newPageTranslations.value[newPageContentLanguage.value] = { title: '', content: '' };
      }
      newPageTranslations.value[newPageContentLanguage.value].content += contentHtml;
      newPageContent.value = newPageTranslations.value[newPageContentLanguage.value].content;
    }
  } catch (error) {
    console.error('Failed to format content:', error);
    // Fallback to basic text if API fails
    const fallbackHtml = products.map(p => `<p>Product: ${p.name}</p>`).join('\n');
    if (newPageContentLanguage.value === 'en') {
      newPageContent.value += fallbackHtml;
    } else {
      if (!newPageTranslations.value[newPageContentLanguage.value]) {
        newPageTranslations.value[newPageContentLanguage.value] = { title: '', content: '' };
      }
      newPageTranslations.value[newPageContentLanguage.value].content += fallbackHtml;
      newPageContent.value = newPageTranslations.value[newPageContentLanguage.value].content;
    }
  }
  showNewProductSelector.value = false;
};

const viewPage = (page: Page) => {
  router.push(`/pages/${page.slug}`);
};

const deletePage = async (page: Page) => {
  if (confirm(t('pages.confirmDelete'))) {
    try {
      await http.delete(`/api/pages/${page.id}`);
      await loadPages();
      alert(t('pages.pageDeleted'));
    } catch (error) {
      console.error('Failed to delete page:', error);
    }
  }
};

// Image insertion methods
const insertImage = (image: { url: string; filename: string; size: number }) => {
  const imageHtml = `<img src="${image.url}" alt="${image.filename}" style="max-width: 100%; height: auto;" />`;
  if (contentLanguage.value === 'en') {
    editPageContent.value += imageHtml;
  } else {
    // For translations, we need to update the translation data
    if (!pageTranslations.value[contentLanguage.value]) {
      pageTranslations.value[contentLanguage.value] = { title: '', content: '' };
    }
    pageTranslations.value[contentLanguage.value].content += imageHtml;
    // Update the current form field
    editPageContent.value = pageTranslations.value[contentLanguage.value].content;
  }
  showImageUpload.value = false;
};

const insertImages = (images: Array<{ url: string; filename: string; size: number }>) => {
  const imagesHtml = images.map(image =>
    `<img src="${image.url}" alt="${image.filename}" style="max-width: 100%; height: auto;" />`
  ).join('\n');

  if (contentLanguage.value === 'en') {
    editPageContent.value += imagesHtml;
  } else {
    // For translations, we need to update the translation data
    if (!pageTranslations.value[contentLanguage.value]) {
      pageTranslations.value[contentLanguage.value] = { title: '', content: '' };
    }
    pageTranslations.value[contentLanguage.value].content += imagesHtml;
    // Update the current form field
    editPageContent.value = pageTranslations.value[contentLanguage.value].content;
  }
  showImageUpload.value = false;
};

// Image insertion methods for create modal
const insertNewImage = (image: { url: string; filename: string; size: number }) => {
  const imageHtml = `<img src="${image.url}" alt="${image.filename}" style="max-width: 100%; height: auto;" />`;
  if (newPageContentLanguage.value === 'en') {
    newPageContent.value += imageHtml;
  } else {
    // For translations, we need to update the translation data
    if (!newPageTranslations.value[newPageContentLanguage.value]) {
      newPageTranslations.value[newPageContentLanguage.value] = { title: '', content: '' };
    }
    newPageTranslations.value[newPageContentLanguage.value].content += imageHtml;
    // Update the current form field
    newPageContent.value = newPageTranslations.value[newPageContentLanguage.value].content;
  }
  showNewImageUpload.value = false;
};

const insertNewImages = (images: Array<{ url: string; filename: string; size: number }>) => {
  const imagesHtml = images.map(image =>
    `<img src="${image.url}" alt="${image.filename}" style="max-width: 100%; height: auto;" />`
  ).join('\n');

  if (newPageContentLanguage.value === 'en') {
    newPageContent.value += imagesHtml;
  } else {
    // For translations, we need to update the translation data
    if (!newPageTranslations.value[newPageContentLanguage.value]) {
      newPageTranslations.value[newPageContentLanguage.value] = { title: '', content: '' };
    }
    newPageTranslations.value[newPageContentLanguage.value].content += imagesHtml;
    // Update the current form field
    newPageContent.value = newPageTranslations.value[newPageContentLanguage.value].content;
  }
  showNewImageUpload.value = false;
};

onMounted(async () => {
  await checkExtensionStatus();
  await loadAvailableLanguages();
  await loadStoreSettings();

  // Load PagesExtension translations for current language
  try {
    console.log('Loading PagesExtension translations');
    const currentLang = i18n.getCurrentLanguage();
    await i18n.loadExtensionTranslationsForExtension('PagesExtension', currentLang);
    console.log('PagesExtension translations loaded');
  } catch (error) {
    console.error('Failed to load PagesExtension translations:', error);
  }

  // Load StoreExtension translations if available (for embedder labels)
  try {
    console.log('Loading StoreExtension translations for embedder labels');
    const currentLang = i18n.getCurrentLanguage();
    await i18n.loadExtensionTranslationsForExtension('StoreExtension', currentLang);
    console.log('StoreExtension translations loaded');
  } catch (error) {
    console.error('Failed to load StoreExtension translations:', error);
  }

  // Discover and load all available content embedders
  const embedders = availableEmbedders.value;
  for (const [embedderKey, embedderConfig] of Object.entries(embedders) as [string, ContentEmbedderConfig][]) {
    const [extensionName, embedderType] = embedderKey.split('.');
    try {
      // Load the component for this embedder
      const component = await getComponent(extensionName, embedderConfig.component);
      if (component) {
        // Store component reference (we'll need to handle multiple components)
        if (!ProductSelectorComponent.value) {
          ProductSelectorComponent.value = component; // For now, use first available
          activeEmbedder.value = embedderKey;
        }

        // Load UI translations from this extension
        try {
          const extensionPrefix = extensionName.replace(/Extension$/i, '').toLowerCase();
          const response = await http.get(`/api/${extensionPrefix}/${embedderConfig.ui_translations_api}`, {
            params: { language: currentLanguage.value }
          });
          embedderTranslations.value = { ...embedderTranslations.value, ...response.data };
        } catch (error) {
          console.warn(`Failed to load UI translations for ${extensionName}:`, error);
        }
      }
    } catch (error) {
      console.error(`Failed to load component for ${embedderKey}:`, error);
    }
  }

  await loadPages();
});
</script>

<template>
  <div class="pages-extension">
    <!-- Extension not enabled message -->
    <div v-if="!extensionEnabled" class="extension-disabled">
      <div class="disabled-message">
        <h2>{{ t('extensionNotEnabled') || 'Pages Extension Not Enabled' }}</h2>
        <p>{{ t('enableExtensionMessage') || 'Please enable the Pages extension in the Extensions panel to manage pages.' }}</p>
      </div>
    </div>

    <!-- Extension enabled content -->
    <div v-else>
      <div class="header">
        <h2>{{ t('pages.title') }}</h2>
        <button @click="createPage" class="btn-primary">
          {{ t('pages.createNew') }}
        </button>
      </div>

      <div v-if="loading" class="loading">
        {{ t('pages.loading') }}
      </div>

      <div v-else-if="pages.length === 0" class="empty-state">
        {{ t('pages.noPages') }}
      </div>

      <div v-else class="pages-list">
        <div
          v-for="page in pages"
          :key="page.id"
          class="page-item"
        >
          <div class="page-info">
            <h3>{{ page.title }}</h3>
            <span class="page-slug">/{{ page.slug }}</span>
            <span v-if="!page.is_public" class="private-badge">Private</span>
          </div>
          <div class="page-actions">
            <button @click="viewPage(page)" class="btn-primary">
              {{ t('pages.view') || 'View' }}
            </button>
            <button @click="editPage(page)" class="btn-secondary">
              {{ t('pages.edit') }}
            </button>
            <button @click="deletePage(page)" class="btn-danger">
              {{ t('pages.delete') }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Edit Page Modal -->
    <div v-if="showEditModal" class="modal-overlay" @click="closeEditModal">
      <div class="modal-content" @click.stop>
        <div class="modal-header">
          <h3>{{ t('pages.editPage') || 'Edit Page' }}</h3>
          <button @click="closeEditModal" class="close-btn">&times;</button>
        </div>

        <!-- Language Selector -->
        <div class="language-selector">
          <div class="language-tabs">
            <button
              v-for="lang in availableLanguages"
              :key="lang"
              :class="{ active: contentLanguage === lang }"
              @click="switchContentLanguage(lang)"
            >
              {{ getLanguageName(lang) }}
            </button>
          </div>
          <div v-if="loadingTranslations" class="loading-translations">
            {{ t('pages.loading') || 'Loading translations...' }}
          </div>
        </div>

        <form @submit.prevent="submitEditPage" class="modal-body">
          <!-- Only show slug and public settings for English (base language) -->
          <template v-if="contentLanguage === 'en'">
            <div class="form-group">
              <label class="form-label">{{ t('pages.titleLabel') || 'Title' }} ({{ getLanguageName(contentLanguage) }}) *</label>
              <input
                type="text"
                v-model="editPageTitle"
                class="input"
                required
                :placeholder="t('pages.titlePlaceholder') || 'Enter page title'"
              />
            </div>

            <div class="form-group">
              <label class="form-label">{{ t('pages.slug') || 'Slug' }} (optional)</label>
              <input
                type="text"
                v-model="editPageSlug"
                class="input"
                :placeholder="t('pages.slugPlaceholder') || 'auto-generated-from-title'"
              />
            </div>

            <div class="form-group">
              <label class="form-label">{{ t('pages.content') || 'Content' }} ({{ getLanguageName(contentLanguage) }})</label>
              <div class="content-editor">
                <div class="editor-toolbar">
                  <button type="button" @click="showImageUpload = !showImageUpload" class="toolbar-btn" :title="t('pages.insertImage') || 'Insert Image'">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <rect width="18" height="18" x="3" y="3" rx="2" ry="2"/>
                      <circle cx="9" cy="9" r="2"/>
                      <path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/>
                    </svg>
                    {{ t('pages.insertImage') || 'Image' }}
                  </button>
                  <!-- Dynamic content embedder buttons -->
                  <button
                    v-for="(embedderConfig, embedderKey) in availableEmbedders"
                    :key="embedderKey"
                    type="button"
                    @click="activateEmbedder(embedderKey, false)"
                    class="toolbar-btn"
                    :title="embedderLabels[embedderKey]"
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/>
                      <line x1="7" y1="7" x2="7" y2="7"/>
                    </svg>
                    {{ embedderLabels[embedderKey] }}
                  </button>
                </div>
                <textarea
                  v-model="editPageContent"
                  class="textarea"
                  rows="8"
                  :placeholder="t('pages.contentPlaceholder') || 'Enter page content (HTML supported)'"
                ></textarea>
                <AdvancedImageUpload
                  v-if="showImageUpload"
                  v-model="selectedImages"
                  :extension-name="'pages'"
                  :multiple="true"
                  @image-selected="insertImage"
                  @images-selected="insertImages"
                  class="content-image-upload"
                />

                <component
                  v-if="showProductSelector && ProductSelectorComponent"
                  :is="ProductSelectorComponent"
                  :multiple="true as boolean"
                  :language="contentLanguage"
                  :currency="storeCurrency"
                  :currency-formats="storeCurrencyFormats"
                  @products-selected="insertProducts"
                  class="content-product-selector"
                />
              </div>
            </div>

            <div class="form-group">
              <label class="checkbox-label">
                <input type="checkbox" v-model="editPageIsPublic" />
                {{ t('pages.isPublic') || 'Make page public' }}
              </label>
            </div>
          </template>

          <!-- For translations, show title and content with image support -->
          <template v-else>
            <div class="form-group">
              <label class="form-label">{{ t('pages.titleLabel') || 'Title' }} ({{ getLanguageName(contentLanguage) }}) *</label>
              <input
                type="text"
                v-model="editPageTitle"
                class="input"
                :placeholder="`${t('pages.titlePlaceholder') || 'Enter page title'} (${getLanguageName(contentLanguage)})`"
              />
            </div>

            <div class="form-group">
              <label class="form-label">{{ t('pages.content') || 'Content' }} ({{ getLanguageName(contentLanguage) }})</label>
              <div class="content-editor">
                <div class="editor-toolbar">
                  <button type="button" @click="showImageUpload = !showImageUpload" class="toolbar-btn" :title="t('pages.insertImage') || 'Insert Image'">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <rect width="18" height="18" x="3" y="3" rx="2" ry="2"/>
                      <circle cx="9" cy="9" r="2"/>
                      <path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/>
                    </svg>
                    {{ t('pages.insertImage') || 'Image' }}
                  </button>
                  <!-- Dynamic content embedder buttons -->
                  <button
                    v-for="(embedderConfig, embedderKey) in availableEmbedders"
                    :key="embedderKey"
                    type="button"
                    @click="activateEmbedder(embedderKey, false)"
                    class="toolbar-btn"
                    :title="embedderLabels[embedderKey]"
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/>
                      <line x1="7" y1="7" x2="7" y2="7"/>
                    </svg>
                    {{ embedderLabels[embedderKey] }}
                  </button>
                </div>
                <textarea
                  v-model="editPageContent"
                  class="textarea"
                  rows="8"
                  :placeholder="`${t('pages.contentPlaceholder') || 'Enter page content (HTML supported)'} (${getLanguageName(contentLanguage)})`"
                ></textarea>
                <AdvancedImageUpload
                  v-if="showImageUpload"
                  v-model="selectedImages"
                  :extension-name="'pages'"
                  :multiple="true"
                  @image-selected="insertImage"
                  @images-selected="insertImages"
                  class="content-image-upload"
                />

                <component
                  v-if="showProductSelector && ProductSelectorComponent"
                  :is="ProductSelectorComponent"
                  :multiple="true as boolean"
                  :language="contentLanguage"
                  :currency="storeCurrency"
                  :currency-formats="storeCurrencyFormats"
                  @products-selected="insertProducts"
                  class="content-product-selector"
                />
              </div>
            </div>
          </template>
        </form>

        <div class="modal-footer">
          <button @click="closeEditModal" class="btn-secondary" type="button">
            {{ t('pages.cancel') || 'Cancel' }}
          </button>
          <button @click="submitEditPage" class="btn-primary" :disabled="updating" type="button">
            {{ updating ? (t('pages.updating') || 'Updating...') : (t('pages.update') || 'Update Page') }}
          </button>
        </div>
      </div>
    </div>

    <!-- Create Page Modal -->
    <div v-if="showCreateModal" class="modal-overlay" @click="closeCreateModal">
      <div class="modal-content" @click.stop>
        <div class="modal-header">
          <h3>{{ t('pages.createNew') || 'Create New Page' }}</h3>
          <button @click="closeCreateModal" class="close-btn">&times;</button>
        </div>

        <!-- Language Selector for Create Modal -->
        <div v-if="availableLanguages.length > 1" class="language-selector">
          <div class="language-tabs">
            <button
              v-for="lang in availableLanguages"
              :key="lang"
              :class="{ active: newPageContentLanguage === lang }"
              @click="switchNewContentLanguage(lang)"
            >
              {{ getLanguageName(lang) }}
            </button>
          </div>
        </div>

        <form @submit.prevent="submitCreatePage" class="modal-body">
          <!-- Only show slug and public settings for English (base language) -->
          <template v-if="newPageContentLanguage === 'en'">
            <div class="form-group">
              <label class="form-label">{{ t('pages.titleLabel') || 'Title' }} ({{ getLanguageName(newPageContentLanguage) }}) *</label>
              <input
                type="text"
                v-model="newPageTitle"
                class="input"
                required
                :placeholder="t('pages.titlePlaceholder') || 'Enter page title'"
              />
            </div>

            <div class="form-group">
              <label class="form-label">{{ t('pages.slug') || 'Slug' }} (optional)</label>
              <input
                type="text"
                v-model="newPageSlug"
                class="input"
                :placeholder="t('pages.slugPlaceholder') || 'auto-generated-from-title'"
              />
            </div>

            <div class="form-group">
              <label class="form-label">{{ t('pages.content') || 'Content' }} ({{ getLanguageName(newPageContentLanguage) }})</label>
              <div class="content-editor">
                <div class="editor-toolbar">
                  <button type="button" @click="showNewImageUpload = !showNewImageUpload" class="toolbar-btn" :title="t('pages.insertImage') || 'Insert Image'">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <rect width="18" height="18" x="3" y="3" rx="2" ry="2"/>
                      <circle cx="9" cy="9" r="2"/>
                      <path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/>
                    </svg>
                    {{ t('pages.insertImage') || 'Image' }}
                  </button>
                  <!-- Dynamic content embedder buttons -->
                  <button
                    v-for="(embedderConfig, embedderKey) in availableEmbedders"
                    :key="embedderKey"
                    type="button"
                    @click="activateEmbedder(embedderKey, true)"
                    class="toolbar-btn"
                    :title="embedderLabels[embedderKey]"
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/>
                      <line x1="7" y1="7" x2="7" y2="7"/>
                    </svg>
                    {{ embedderLabels[embedderKey] }}
                  </button>
                </div>
                <textarea
                  v-model="newPageContent"
                  class="textarea"
                  rows="8"
                  :placeholder="t('pages.contentPlaceholder') || 'Enter page content (HTML supported)'"
                ></textarea>
                <AdvancedImageUpload
                  v-if="showNewImageUpload"
                  v-model="selectedNewImages"
                  :extension-name="'pages'"
                  :multiple="true"
                  @image-selected="insertNewImage"
                  @images-selected="insertNewImages"
                  class="content-image-upload"
                />

                <component
                  v-if="showNewProductSelector && ProductSelectorComponent"
                  :is="ProductSelectorComponent"
                  :multiple="true as boolean"
                  :language="newPageContentLanguage"
                  :currency="storeCurrency"
                  :currency-formats="storeCurrencyFormats"
                  @products-selected="insertNewProducts"
                  class="content-product-selector"
                />
              </div>
            </div>

            <div class="form-group">
              <label class="checkbox-label">
                <input type="checkbox" v-model="newPageIsPublic" />
                {{ t('pages.isPublic') || 'Make page public' }}
              </label>
            </div>
          </template>

          <!-- For translations, show title and content with image support -->
          <template v-else>
            <div class="form-group">
              <label class="form-label">{{ t('pages.titleLabel') || 'Title' }} ({{ getLanguageName(newPageContentLanguage) }}) *</label>
              <input
                type="text"
                v-model="newPageTitle"
                class="input"
                :placeholder="`${t('pages.titlePlaceholder') || 'Enter page title'} (${getLanguageName(newPageContentLanguage)})`"
              />
            </div>

            <div class="form-group">
              <label class="form-label">{{ t('pages.content') || 'Content' }} ({{ getLanguageName(newPageContentLanguage) }})</label>
              <div class="content-editor">
                <div class="editor-toolbar">
                  <button type="button" @click="showNewImageUpload = !showNewImageUpload" class="toolbar-btn" :title="t('pages.insertImage') || 'Insert Image'">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <rect width="18" height="18" x="3" y="3" rx="2" ry="2"/>
                      <circle cx="9" cy="9" r="2"/>
                      <path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/>
                    </svg>
                    {{ t('pages.insertImage') || 'Image' }}
                  </button>
                  <!-- Dynamic content embedder buttons -->
                  <button
                    v-for="(embedderConfig, embedderKey) in availableEmbedders"
                    :key="embedderKey"
                    type="button"
                    @click="activateEmbedder(embedderKey, true)"
                    class="toolbar-btn"
                    :title="t(embedderConfig.label, embedderConfig.label)"
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/>
                      <line x1="7" y1="7" x2="7" y2="7"/>
                    </svg>
                    {{ t(embedderConfig.label, embedderConfig.label) }}
                  </button>
                </div>
                <textarea
                  v-model="newPageContent"
                  class="textarea"
                  rows="8"
                  :placeholder="`${t('pages.contentPlaceholder') || 'Enter page content (HTML supported)'} (${getLanguageName(newPageContentLanguage)})`"
                ></textarea>
                <AdvancedImageUpload
                  v-if="showNewImageUpload"
                  v-model="selectedNewImages"
                  :extension-name="'pages'"
                  :multiple="true"
                  @image-selected="insertNewImage"
                  @images-selected="insertNewImages"
                  class="content-image-upload"
                />

                <component
                  v-if="showNewProductSelector && ProductSelectorComponent"
                  :is="ProductSelectorComponent"
                  :multiple="true as boolean"
                  :language="newPageContentLanguage"
                  :currency="storeCurrency"
                  :currency-formats="storeCurrencyFormats"
                  @products-selected="insertNewProducts"
                  class="content-product-selector"
                />
              </div>
            </div>
          </template>
        </form>

        <div class="modal-footer">
          <button @click="closeCreateModal" class="btn-secondary" type="button">
            {{ t('pages.cancel') || 'Cancel' }}
          </button>
          <button @click="submitCreatePage" class="btn-primary" :disabled="creating" type="button">
            {{ creating ? (t('pages.creating') || 'Creating...') : (t('pages.create') || 'Create Page') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.pages-extension {
  padding: 1rem;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2rem;
}

.header h2 {
  margin: 0;
  color: var(--text-primary);
}

.btn-primary {
  padding: 0.5rem 1rem;
  background: var(--button-primary-bg);
  color: var(--button-primary-text);
  border: none;
  border-radius: var(--border-radius-sm);
  cursor: pointer;
  font-weight: 500;
}

.btn-secondary {
  padding: 0.25rem 0.5rem;
  background: var(--button-secondary-bg);
  color: var(--button-secondary-text);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-sm);
  cursor: pointer;
  font-size: 0.875rem;
}

.btn-danger {
  padding: 0.25rem 0.5rem;
  background: var(--button-danger-bg, #dc3545);
  color: var(--button-danger-text, #ffffff);
  border: 1px solid var(--button-danger-bg, #dc3545);
  border-radius: var(--border-radius-sm);
  cursor: pointer;
  font-size: 0.875rem;
}

.btn-danger:hover {
  background: var(--button-danger-hover, #c82333);
  border-color: var(--button-danger-hover, #c82333);
}

.loading, .empty-state {
  text-align: center;
  padding: 2rem;
  color: var(--text-secondary);
}

.pages-list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.page-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-md);
  background: var(--bg-primary);
}

.page-info h3 {
  margin: 0 0 0.25rem 0;
  color: var(--text-primary);
}

.page-slug {
  color: var(--text-secondary);
  font-size: 0.875rem;
}

.private-badge {
  display: inline-block;
  padding: 0.125rem 0.25rem;
  background: var(--warning-bg, rgba(245, 158, 11, 0.15));
  color: var(--warning-text, #92400e);
  border-radius: var(--border-radius-sm, 4px);
  font-size: 0.75rem;
  margin-left: 0.5rem;
}

.page-actions {
  display: flex;
  gap: 0.5rem;
}

/* Modal Styles */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: var(--modal-backdrop, rgba(0, 0, 0, 0.7));
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: var(--modal-bg, var(--card-bg, #ffffff));
  border-radius: var(--border-radius-lg);
  box-shadow: 0 4px 20px var(--card-shadow, rgba(0, 0, 0, 0.3));
  max-width: 600px;
  width: 90%;
  max-height: 90vh;
  overflow-y: auto;
  border: 1px solid var(--modal-border, var(--card-border, #e3e3e3));
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.5rem;
  border-bottom: 1px solid var(--border-color);
}

.modal-header h3 {
  margin: 0;
  color: var(--text-primary);
  font-size: 1.25rem;
}

.close-btn {
  background: none;
  border: none;
  font-size: 1.5rem;
  cursor: pointer;
  color: var(--text-secondary);
  padding: 0;
  width: 2rem;
  height: 2rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--border-radius-sm);
}

.close-btn:hover {
  background: var(--bg-secondary, #f8f9fa);
  color: var(--text-primary, #222222);
}

.modal-body {
  padding: 1.5rem;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  padding: 1.5rem;
  border-top: 1px solid var(--border-color);
}

.textarea {
  width: 100%;
  padding: 0.75rem;
  border: 1px solid var(--input-border);
  border-radius: var(--border-radius-sm);
  background-color: var(--input-bg);
  color: var(--text-primary);
  font-family: inherit;
  font-size: 0.875rem;
  resize: vertical;
  min-height: 120px;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.textarea:focus {
  outline: none;
  border-color: var(--input-focus-border);
  box-shadow: 0 0 0 2px rgba(var(--button-primary-bg), 0.2);
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--text-primary);
}

.checkbox-label input[type="checkbox"] {
  width: auto;
  margin: 0;
}

/* Content editor styles */
.content-editor {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.editor-toolbar {
  display: flex;
  gap: 0.5rem;
  padding: 0.5rem;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-sm);
}

.toolbar-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  background: var(--button-secondary-bg);
  color: var(--button-secondary-text);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-sm);
  cursor: pointer;
  font-size: 0.875rem;
  transition: all 0.2s ease;
}

.toolbar-btn:hover {
  background: var(--button-secondary-hover, #545b62);
  border-color: var(--button-primary-bg, #007bff);
}

.content-image-upload {
  margin-top: 1rem;
}

/* Language selector styles */
.language-selector {
  padding: 1rem 1.5rem;
  border-bottom: 1px solid var(--border-color, #e3e3e3);
  background: var(--bg-secondary, #f8f9fa);
  margin: -1.5rem -1.5rem 1.5rem -1.5rem;
}

.language-tabs {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
  align-items: center;
}

.language-tabs button {
  padding: 0.5rem 1rem;
  border: 1px solid var(--button-secondary-bg, #6c757d);
  background: var(--button-secondary-bg, #6c757d);
  color: var(--button-secondary-text, #ffffff);
  border-radius: var(--border-radius-sm, 4px);
  cursor: pointer;
  font-size: 0.875rem;
  transition: all 0.2s ease;
  font-weight: 500;
}

.language-tabs button:hover {
  background: var(--button-secondary-hover, #545b62);
  border-color: var(--button-primary-bg, #007bff);
}

.language-tabs button.active {
  background: var(--button-primary-bg, #007bff);
  color: var(--button-primary-text, #ffffff);
  border-color: var(--button-primary-bg, #007bff);
  box-shadow: 0 2px 8px rgba(0, 123, 255, 0.3);
  transform: translateY(-1px);
}

.loading-translations {
  font-size: 0.875rem;
  color: var(--text-secondary, #666666);
  text-align: center;
}

/* Extension disabled styles */
.extension-disabled {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 300px;
}

.disabled-message {
  text-align: center;
  max-width: 400px;
  padding: 2rem;
  background: var(--card-bg, #ffffff);
  border: 1px solid var(--card-border, #e3e3e3);
  border-radius: var(--border-radius-md, 8px);
  box-shadow: 0 2px 4px var(--card-shadow, rgba(0, 0, 0, 0.1));
}

.disabled-message h2 {
  color: var(--text-secondary, #666666);
  margin-bottom: 1rem;
  font-size: 1.25rem;
}

.disabled-message p {
  color: var(--text-secondary, #666666);
  line-height: 1.5;
}

/* Dark mode overrides for PagesExtension */
.dark-mode .language-tabs button {
  background: var(--button-secondary-bg, #4a5568);
  color: var(--button-secondary-text, #ffffff);
  border-color: var(--button-secondary-bg, #4a5568);
}

.dark-mode .language-tabs button:hover {
  background: var(--button-secondary-hover, #2d3748);
  border-color: var(--button-primary-bg, #63b3ed);
}

.dark-mode .language-tabs button.active {
  background: var(--button-primary-bg, #3182ce);
  color: var(--button-primary-text, #ffffff);
  border-color: var(--button-primary-bg, #3182ce);
}

.dark-mode .language-selector {
  background: var(--bg-secondary, #2d3748);
  border-color: var(--border-color, #4a5568);
}

.dark-mode .close-btn {
  color: var(--text-secondary, #a0aec0);
}

.dark-mode .close-btn:hover {
  background: var(--bg-secondary, #4a5568);
  color: var(--text-primary, #e2e8f0);
}

/* Hide scrollbars on modal content while maintaining scroll functionality */
.modal-content {
  scrollbar-width: none; /* Firefox */
  -ms-overflow-style: none; /* IE and Edge */
}

.modal-content::-webkit-scrollbar {
  display: none; /* Chrome, Safari, and Opera */
}
</style>
