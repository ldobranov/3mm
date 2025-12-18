<script setup lang="ts">
import { ref, onMounted, computed, defineAsyncComponent, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useI18n, i18n } from '@/utils/i18n';
import http from '@/utils/dynamic-http';
import { useExtensionRelationships, extensionRelationships } from '@/utils/extension-relationships';

console.log('🔍 PageEditor component loading...');

const route = useRoute();
const router = useRouter();
const { t, currentLanguage } = useI18n();
const { extensionProvides, getManifest } = useExtensionRelationships();

interface Page {
  id?: number;
  title: string;
  slug: string;
  content: string;
  is_public: boolean;
}

const page = ref<Page>({
  title: '',
  slug: '',
  content: '',
  is_public: false
});

const loading = ref(false);
const saving = ref(false);
const showProductSelector = ref(false);
const isNew = computed(() => !route.params.id);
const productSelectorAvailable = ref(false);
const productSelectorProvider = ref<string | null>(null);
const currency = ref('USD');
const currencyFormats = ref<Record<string, { label: string; position: 'prefix' | 'suffix' }>>({});

// Currency formatting helper (use store settings currency code)
const formatCurrency = (amount: any, currencyCode: string = 'USD') => {
  const code = (currencyCode || 'USD').toString().trim().toUpperCase();
  const fmt = currencyFormats.value?.[code];

  const defaultSymbols: Record<string, string> = {
    USD: '$',
    EUR: '€',
    GBP: '£',
    BGN: 'лв',
    JPY: '¥',
    CAD: 'C$',
    AUD: 'A$'
  };

  const label = (fmt?.label || defaultSymbols[code] || code).toString();
  const position = (fmt?.position || (code === 'BGN' ? 'suffix' : 'prefix')) as 'prefix' | 'suffix';

  // Normalize amount to string without trailing .0 when possible
  let amountStr = String(amount ?? '');
  const num = Number(amount);
  if (!Number.isNaN(num) && amountStr !== '') {
    amountStr = `${num % 1 === 0 ? Math.trunc(num) : num}`;
  }

  if (position === 'suffix') return `${amountStr} ${label}`.trim();
  return `${label}${amountStr}`.trim();
};

// Get translated embedder labels (handled directly in template for reactivity)


// Check extension relationships asynchronously
const checkExtensionRelationships = async () => {
  console.log('🔍 Checking extension relationships...');

  try {
    // Wait for extension relationships to be initialized
    await new Promise(resolve => {
      const checkInitialized = () => {
        if (extensionRelationships.getDiscoveredExtensions().length > 0) {
          resolve(void 0);
        } else {
          // Wait a bit and check again
          setTimeout(checkInitialized, 100);
        }
      };
      checkInitialized();
    });

    console.log('🔍 Extension relationships initialized, discovered extensions:', extensionRelationships.getDiscoveredExtensions());

    // Check our own manifest for relationships
    const ourManifest = getManifest('PagesExtension');
    console.log('🔍 PagesExtension manifest:', ourManifest);

    // Debug: Check all cached manifests
    try {
      const allManifests: Record<string, any> = {};
      ['PagesExtension', 'StoreExtension', 'BulgarianLanguagePack', 'ClockWidget', 'MultilingualClockWidget'].forEach(ext => {
        allManifests[ext] = getManifest(ext);
      });
      console.log('🔍 All cached manifests:', allManifests);
    } catch (error) {
      console.log('🔍 Could not inspect all manifests:', error);
    }

    if (ourManifest?.consumes) {
      console.log('🔍 PagesExtension consumes:', ourManifest.consumes);
      for (const [providerName, resources] of Object.entries(ourManifest.consumes)) {
        const typedResources = resources as Record<string, string[]>;
        console.log(`🔍 Checking provider ${providerName}, resources:`, typedResources);
        if (typedResources.components?.includes('product_selector')) {
          console.log(`✅ PagesExtension has relationship with ${providerName} for product_selector`);
          productSelectorProvider.value = providerName;

          // Check if the provider extension actually provides the component
          console.log(`🔍 PageEditor calling extensionProvides with: ${providerName}, components, product_selector`);
          const provides = await extensionProvides(providerName, 'components', 'product_selector');
          console.log(`🔍 Relationship check result for ${providerName} providing product_selector:`, provides);
          productSelectorAvailable.value = provides;
          return;
        }
      }
    }

    console.log('❌ No relationship found for product_selector');
    productSelectorProvider.value = null;
    productSelectorAvailable.value = false;
  } catch (error) {
    console.error('❌ Error checking extension relationships:', error);
    productSelectorProvider.value = null;
    productSelectorAvailable.value = false;
  }
};

// Dynamically load ProductSelector component when needed
const ProductSelectorComponent = ref<any>(null);

const loadProductSelector = async () => {
  if (productSelectorAvailable.value && !ProductSelectorComponent.value) {
    const provider = productSelectorProvider.value;
    if (!provider) return;

    try {
      console.log(`Loading ProductSelector component from ${provider} using extension relationships...`);

      // Ensure StoreExtension translations are loaded before loading component
      console.log('Loading StoreExtension translations for language:', currentLanguage.value);
      await i18n.loadExtensionTranslationsForExtension(provider, currentLanguage.value);
      console.log('StoreExtension translations loaded successfully');


      ProductSelectorComponent.value = await extensionRelationships.getComponent(provider, 'ProductSelector');

      console.log('ProductSelector component loaded successfully');
    } catch (error) {
      console.error('Failed to load ProductSelector component:', error);
    }
  }
};

const openProductSelector = async () => {
  await loadProductSelector();
  showProductSelector.value = true;
};

const loadPage = async () => {
  if (isNew.value) return;

  try {
    loading.value = true;
    const response = await http.get(`/api/pages/${route.params.id}`);
    page.value = response.data;
  } catch (error) {
    console.error('Error loading page:', error);
    // Redirect to pages list if page not found
    router.push('/pages');
  } finally {
    loading.value = false;
  }
};

const loadStoreSettings = async () => {
  try {
    const response = await http.get('/api/store/settings');
    currency.value = response.data.currency || 'USD';
    currencyFormats.value = response.data.currencies || {};
  } catch (error) {
    console.error('Error loading store settings:', error);
    currency.value = 'USD';
    currencyFormats.value = {};
  }
};

const generateSlug = (title: string) => {
  return title
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .trim();
};

const updateSlug = () => {
  if (!page.value.slug || page.value.slug === generateSlug(page.value.title)) {
    page.value.slug = generateSlug(page.value.title);
  }
};

const savePage = async () => {
  try {
    saving.value = true;

    console.log('🔍 Saving page, current page data:', page.value);

    // Send as FormData to handle HTML content properly
    const formData = new FormData();
    formData.append('title', page.value.title || '');
    formData.append('slug', page.value.slug || '');
    formData.append('content', page.value.content || '');
    formData.append('is_public', String(page.value.is_public));

    console.log('🔍 FormData contents:');
    for (const [key, value] of formData.entries()) {
      console.log(`  ${key}: ${value} (type: ${typeof value})`);
    }

    if (isNew.value) {
      console.log('🔍 Creating new page...');
      const response = await http.post('/api/pages/create', formData, {
        headers: {
          'Content-Type': 'multipart/form-data'
        }
      });
      console.log('✅ Page created successfully:', response.data);
      router.push('/pages');
    } else {
      console.log(`🔍 Updating existing page ${page.value.id}...`);
      const response = await http.put(`/api/pages/${page.value.id}`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data'
        }
      });
      console.log('✅ Page updated successfully:', response.data);
      router.push('/pages');
    }
  } catch (error) {
    console.error('❌ Error saving page:', error);
    alert('Error saving page. Please try again.');
  } finally {
    saving.value = false;
  }
};

const insertProduct = (product: any) => {
  // Insert product display HTML into content
  const formattedPrice = formatCurrency(product.sale_price || product.price, currency.value)
  const productHtml = `
    <div class="product-display" data-product-id="${product.id}">
      <h3>${product.name}</h3>
      <p>${product.description || ''}</p>
      <p><strong>${t('store.price', 'Price')}: ${formattedPrice}</strong></p>
      ${product.images && product.images.length > 0 ? `<img src="${product.images[0]}" alt="${product.name}" style="max-width: 200px;">` : ''}
    </div>
  `;

  // Insert at cursor position or append
  const textarea = document.querySelector('textarea') as HTMLTextAreaElement;
  if (textarea) {
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const text = textarea.value;
    textarea.value = text.substring(0, start) + productHtml + text.substring(end);
    page.value.content = textarea.value;
  } else {
    page.value.content += productHtml;
  }

  showProductSelector.value = false;
};

const insertProducts = (products: any[]) => {
  const productsHtml = products.map(product => {
    const imageHtml = product.images?.[0] ?
      `<img src="${product.images[0]}" alt="${product.name}" style="max-width: 100%; height: auto; margin-bottom: 0.5rem;" />` : '';

    // Use translations for the embedded product display
    const skuLabel = t('store.sku', 'SKU');
    const formattedPrice = formatCurrency(product.sale_price || product.price, currency.value)

    return `
      <div class="embedded-product" data-product-id="${product.id}" style="border: 1px solid #e3e3e3; border-radius: 8px; padding: 1rem; margin: 1rem 0; background: #f8f9fa;">
        ${imageHtml}
        <h3 style="margin: 0 0 0.5rem 0; color: #222;">${product.name}</h3>
        <p style="margin: 0 0 0.5rem 0; font-weight: 600; color: #007bff;">${formattedPrice}</p>
        ${product.sku ? `<p style="margin: 0; font-size: 0.875rem; color: #666;">${skuLabel}: ${product.sku}</p>` : ''}
        <p style="margin: 0.5rem 0 0 0; color: #666;">${product.description || ''}</p>
      </div>
    `;
  }).join('\n');

  page.value.content += productsHtml;
  showProductSelector.value = false;
};

const cancel = () => {
  router.push('/pages');
};


// Watch for language changes and reload components
watch(currentLanguage, async (newLang) => {
  console.log('PageEditor language changed to:', newLang);

  // Load StoreExtension translations for the new language
  if (productSelectorProvider.value) {
    try {
      console.log('Loading StoreExtension translations for new language:', newLang);
      await i18n.loadExtensionTranslationsForExtension(productSelectorProvider.value, newLang);
      console.log('StoreExtension translations loaded for new language');
    } catch (error) {
      console.error('Failed to load StoreExtension translations for new language:', error);
    }
  }

  // Force complete reload of ProductSelector when language changes
  ProductSelectorComponent.value = null
  showProductSelector.value = false // Close modal first
  if (productSelectorAvailable.value) {
    await loadProductSelector()
  }
})

onMounted(async () => {
  await checkExtensionRelationships();

  // Load store settings for currency
  await loadStoreSettings();

  // Load StoreExtension translations if available
  if (productSelectorProvider.value) {
    try {
      console.log('Loading StoreExtension translations for PageEditor');
      await i18n.loadExtensionTranslationsForExtension(productSelectorProvider.value, currentLanguage.value);
      console.log('StoreExtension translations loaded for PageEditor');
    } catch (error) {
      console.error('Failed to load StoreExtension translations:', error);
    }
  }

  loadPage();
});
</script>

<template>
  <div class="page-editor">
    <div class="editor-header">
      <h1>{{ isNew ? t('pages.createNew', 'Create New Page') : t('pages.editPage', 'Edit Page') }}</h1>
      <div class="actions">
        <button @click="cancel" class="btn-secondary">
          {{ t('pages.cancel', 'Cancel') }}
        </button>
        <button @click="savePage" :disabled="saving" class="btn-primary">
          {{ saving ? t('pages.saving', 'Saving...') : t('pages.save', 'Save') }}
        </button>
      </div>
    </div>

    <div v-if="loading" class="loading">
      {{ t('pages.loading', 'Loading...') }}
    </div>

    <div v-else class="editor-content">
      <div class="form-group">
        <label>{{ t('pages.title', 'Title') }}</label>
        <input
          v-model="page.title"
          @input="updateSlug"
          type="text"
          class="input"
          :placeholder="t('pages.titlePlaceholder', 'Enter page title')"
        />
      </div>

      <div class="form-group">
        <label>{{ t('pages.slug', 'Slug') }}</label>
        <input
          v-model="page.slug"
          type="text"
          class="input"
          :placeholder="t('pages.slugPlaceholder', 'page-url-slug')"
        />
      </div>

      <div class="form-group">
        <label class="checkbox-label">
          <input v-model="page.is_public" type="checkbox" />
          {{ t('pages.isPublic', 'Public') }}
        </label>
      </div>

      <div class="content-editor">
        <div class="editor-toolbar">
          <button
            v-if="productSelectorAvailable"
            @click="openProductSelector"
            type="button"
            class="btn-secondary"
          >
            {{ t('store.productSelector.title', 'Add Product') }}
          </button>
        </div>

        <div class="form-group">
          <label>{{ t('pages.content', 'Content (HTML)') }}</label>
          <textarea
            v-model="page.content"
            class="textarea"
            :placeholder="t('pages.contentPlaceholder', 'Enter page content (HTML allowed)')"
            rows="20"
          ></textarea>
        </div>
      </div>
    </div>

    <!-- Product Selector Modal -->
    <div v-if="showProductSelector" class="modal-overlay" @click="showProductSelector = false">
      <div class="modal-content" @click.stop>
        <div class="modal-header">
          <h3>{{ t('store.productSelector.title', 'Select Product') }}</h3>
          <button @click="showProductSelector = false" class="close-btn">&times;</button>
        </div>
        <div class="modal-body">
          <component
            v-if="ProductSelectorComponent"
            :is="ProductSelectorComponent"
            :key="`product-selector-${currentLanguage}-${currency}`"
            :multiple="true"
            :language="currentLanguage"
            :currency="currency"
            :currency-formats="currencyFormats"
            @products-selected="insertProducts"
          />
          <div v-else class="error">
            {{ t('pages.storeExtensionNotAvailable', 'StoreExtension is not available') }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-editor {
  max-width: 1000px;
  margin: 0 auto;
  padding: 2rem;
}

.editor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid var(--border-color);
}

.editor-header h1 {
  margin: 0;
  color: var(--text-primary);
}

.actions {
  display: flex;
  gap: 1rem;
}

.form-group {
  margin-bottom: 1.5rem;
}

.form-group label {
  display: block;
  margin-bottom: 0.5rem;
  font-weight: 500;
  color: var(--text-primary);
}

.input, .textarea {
  width: 100%;
  padding: 0.75rem;
  border: 1px solid var(--input-border);
  border-radius: var(--border-radius);
  background-color: var(--input-bg);
  color: var(--text-primary);
  font-size: 1rem;
}

.input:focus, .textarea:focus {
  outline: none;
  border-color: var(--input-focus-border);
  box-shadow: 0 0 0 2px rgba(var(--button-primary-bg), 0.2);
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  font-weight: normal;
}

.content-editor {
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius);
  padding: 1rem;
  background-color: var(--bg-secondary);
}

.editor-toolbar {
  margin-bottom: 1rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid var(--border-color);
}

.btn-primary {
  background-color: var(--button-primary-bg);
  color: var(--button-primary-text);
  border: none;
  padding: 0.75rem 1.5rem;
  border-radius: var(--border-radius);
  cursor: pointer;
  font-weight: 500;
  transition: background-color 0.2s;
}

.btn-primary:hover:not(:disabled) {
  background-color: var(--button-primary-hover);
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary {
  background-color: var(--button-secondary-bg);
  color: var(--button-secondary-text);
  border: 1px solid var(--button-secondary-border);
  padding: 0.75rem 1.5rem;
  border-radius: var(--border-radius);
  cursor: pointer;
  font-weight: 500;
  transition: background-color 0.2s;
}

.btn-secondary:hover {
  background-color: var(--button-secondary-hover);
}

.loading {
  text-align: center;
  padding: 2rem;
  color: var(--text-secondary);
}

/* Modal Styles */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
}

.modal-content {
  background-color: var(--bg-primary);
  border-radius: var(--border-radius);
  width: 90%;
  max-width: 800px;
  max-height: 80vh;
  overflow-y: auto;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  border-bottom: 1px solid var(--border-color);
}

.modal-header h3 {
  margin: 0;
  color: var(--text-primary);
}

.close-btn {
  background: none;
  border: none;
  font-size: 1.5rem;
  cursor: pointer;
  color: var(--text-secondary);
  padding: 0;
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.close-btn:hover {
  color: var(--text-primary);
}

.modal-body {
  padding: 1rem;
}
</style>
