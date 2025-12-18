<template>
  <div class="product-selector">
    <div class="selector-header">
      <h4>{{ titleTranslation }}<!-- {{ translationVersion }} --></h4>
      <button @click="showSelector = !showSelector" type="button" class="toggle-btn">
        {{ showSelector ? hideTranslation : showTranslation }}
      </button>
    </div>

    <div v-if="showSelector" class="selector-content">
      <!-- Search and Filter -->
      <div class="selector-controls">
        <div class="search-box">
          <input
            type="text"
            v-model="searchQuery"
            :placeholder="searchPlaceholderTranslation"
            class="search-input"
            @input="debouncedSearch"
          />
        </div>

        <div class="filter-controls">
          <select v-model="selectedCategory" @change="loadProducts" class="category-select">
            <option value="">{{ allCategoriesTranslation }}</option>
            <option v-for="category in categories" :key="category.id" :value="category.slug">
              {{ category.name }}
            </option>
          </select>
        </div>
      </div>

      <!-- Product Grid -->
      <div class="products-grid">
        <div
          v-for="product in filteredProducts"
          :key="product.id"
          class="product-item"
          :class="{ selected: isSelected(product.id) }"
          @click="toggleProduct(product)"
        >
          <div class="product-image">
            <img
              :src="getImageUrl(product.images?.[0])"
              :alt="product.name"
              @error="handleImageError"
            />
          </div>

          <div class="product-info">
            <h5 class="product-name">{{ product.name }}</h5>
            <div class="product-price">
              <span v-if="product.sale_price" class="original-price">{{ formatCurrency(product.price, props.currency, props.currencyFormats) }}</span>
              <span class="current-price">{{ formatCurrency(product.sale_price || product.price, props.currency, props.currencyFormats) }}</span>
            </div>
            <div class="product-sku" v-if="product.sku">SKU: {{ product.sku }}</div>
          </div>

          <div class="selection-indicator">
            <div v-if="isSelected(product.id)" class="selected-badge">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="20,6 9,17 4,12"/>
              </svg>
            </div>
          </div>
        </div>
      </div>

      <!-- Loading and Empty States -->
      <div v-if="loading" class="loading-state">
        {{ t('store.productSelector.loading', 'Loading products...') }}
      </div>

      <div v-if="!loading && filteredProducts.length === 0" class="empty-state">
        {{ noProductsTranslation }}
      </div>

      <!-- Selected Products Summary -->
      <div v-if="selectedProducts.length > 0" class="selected-summary">
        <h5>{{ selectedProductsTranslation }} ({{ selectedProducts.length }})</h5>
        <div class="selected-list">
          <div v-for="product in selectedProducts" :key="product.id" class="selected-item">
            <span>{{ product.name }}</span>
            <button @click.stop="removeProduct(product.id)" type="button" class="remove-btn">×</button>
          </div>
        </div>

        <div class="action-buttons">
          <button @click="clearSelection" type="button" class="clear-btn">
            {{ clearAllTranslation }}
          </button>
          <button @click="confirmSelection" type="button" class="confirm-btn">
            {{ multiple ? addSelectedTranslation : selectProductTranslation }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, getCurrentInstance } from 'vue'
import { useI18n, i18n } from '@/utils/i18n'
import http from '@/utils/dynamic-http'
import { registerComponent, registerRelationship } from '@/utils/extension-relationships'
import { formatCurrency } from './utils/currency'

const { t, currentLanguage } = useI18n()

// Force reactivity when translations change
const translationVersion = computed(() => {
  const version = i18n.getVersion()
  console.log('ProductSelector translationVersion computed:', version, 'current language:', currentLanguage.value)
  return version
})

interface Product {
  id: number
  name: string
  sku?: string
  price: number
  sale_price?: number
  images?: string[]
  categories?: string[]
}

interface Category {
  id: number
  name: string
  slug: string
}

interface Props {
  multiple?: boolean
  selectedProducts?: Product[]
  /**
   * Language for store content (product names/descriptions/categories) fetched from the Store API.
   * This should follow the Pages "content language" tabs (EN/BG), NOT the app UI language.
   */
  language?: string
  maxSelection?: number
  currency?: string
  currencyFormats?: Record<string, { label: string; position: 'prefix' | 'suffix' }>
}

const props = withDefaults(defineProps<Props>(), {
  multiple: true,
  selectedProducts: () => [],
  language: 'en',
  maxSelection: 50,
  currency: 'USD',
  currencyFormats: undefined
})

const emit = defineEmits<{
  'product-selected': [product: Product]
  'products-selected': [products: Product[]]
}>()

// Component state
const showSelector = ref(false)
const loading = ref(false)
const products = ref<Product[]>([])
const categories = ref<Category[]>([])
const searchQuery = ref('')
const selectedCategory = ref('')
const selectedProductIds = ref<Set<number>>(new Set())

// Initialize selected products from props
watch(() => props.selectedProducts, (newSelected) => {
  selectedProductIds.value = new Set(newSelected.map(p => p.id))
}, { immediate: true })

// Computed properties
const filteredProducts = computed(() => {
  let filtered = products.value

  // Apply search filter
  if (searchQuery.value.trim()) {
    const query = searchQuery.value.toLowerCase()
    filtered = filtered.filter(product =>
      product.name.toLowerCase().includes(query) ||
      (product.sku && product.sku.toLowerCase().includes(query))
    )
  }

  return filtered
})

const selectedProducts = computed(() => {
  return products.value.filter(product => selectedProductIds.value.has(product.id))
})

/**
 * UI translations MUST follow the app UI language (header language selector).
 * Content language (product names/descriptions) is controlled separately via `props.language`.
 */
const titleTranslation = computed(() => t('store.productSelector.title', 'Select Products'))
const searchPlaceholderTranslation = computed(() => t('store.productSelector.searchPlaceholder', 'Search products...'))
const allCategoriesTranslation = computed(() => t('store.productSelector.allCategories', 'All Categories'))
const hideTranslation = computed(() => t('store.productSelector.hide', 'Hide'))
const showTranslation = computed(() => t('store.productSelector.show', 'Show'))
const noProductsTranslation = computed(() => t('store.productSelector.noProducts', 'No products found'))
const selectedProductsTranslation = computed(() => t('store.productSelector.selectedProducts', 'Selected Products'))
const clearAllTranslation = computed(() => t('store.productSelector.clearAll', 'Clear All'))
const addSelectedTranslation = computed(() => t('store.productSelector.addSelected', 'Add Selected'))
const selectProductTranslation = computed(() => t('store.productSelector.selectProduct', 'Select Product'))

// Methods
const loadProducts = async () => {
  try {
    loading.value = true
    const params: any = {
      limit: 100,
      language: props.language
    }

    if (selectedCategory.value) {
      params.category = selectedCategory.value
    }

    const response = await http.get('/api/store/products', { params })
    products.value = response.data.items || []
  } catch (error) {
    console.error('Failed to load products:', error)
    products.value = []
  } finally {
    loading.value = false
  }
}

const loadCategories = async () => {
  try {
    const response = await http.get('/api/store/categories', {
      params: { language: props.language }
    })
    categories.value = response.data.items || []
  } catch (error) {
    console.error('Failed to load categories:', error)
    categories.value = []
  }
}

const isSelected = (productId: number): boolean => {
  return selectedProductIds.value.has(productId)
}

const toggleProduct = (product: Product) => {
  const productId = product.id

  if (props.multiple) {
    if (selectedProductIds.value.has(productId)) {
      selectedProductIds.value.delete(productId)
    } else {
      if (selectedProductIds.value.size < props.maxSelection) {
        selectedProductIds.value.add(productId)
      }
    }
  } else {
    // Single selection mode
    selectedProductIds.value.clear()
    selectedProductIds.value.add(productId)
  }
}

const removeProduct = (productId: number) => {
  selectedProductIds.value.delete(productId)
}

const clearSelection = () => {
  selectedProductIds.value.clear()
}

const confirmSelection = () => {
  const selected = selectedProducts.value

  if (props.multiple) {
    emit('products-selected', selected)
  } else if (selected.length > 0) {
    emit('product-selected', selected[0])
  }

  showSelector.value = false
}

const getImageUrl = (imagePath: string | string[] | undefined): string => {
  if (!imagePath) return '/placeholder-product.jpg'

  // If it's an array, get the first element
  let path: string | undefined
  if (Array.isArray(imagePath)) {
    path = imagePath[0]
  } else if (typeof imagePath === 'string') {
    // Try to parse as JSON array if it looks like one
    if (imagePath.startsWith('[') && imagePath.endsWith(']')) {
      try {
        const parsed = JSON.parse(imagePath)
        path = Array.isArray(parsed) ? parsed[0] : imagePath
      } catch {
        path = imagePath
      }
    } else {
      path = imagePath
    }
  }

  if (!path) return '/placeholder-product.jpg'

  // If it's already a full URL, return as is
  if (path.startsWith('http://') || path.startsWith('https://')) {
    return path
  }

  // If it starts with /uploads, it's already a full path
  if (path.startsWith('/uploads/')) {
    return path
  }

  // Otherwise, prefix with /uploads/
  return `/uploads/${path}`
}

const handleImageError = (event: Event) => {
  const img = event.target as HTMLImageElement
  img.src = '/placeholder-product.jpg'
}

// Debounced search
let searchTimeout: number | null = null
const debouncedSearch = () => {
  if (searchTimeout) {
    clearTimeout(searchTimeout)
  }
  searchTimeout = setTimeout(() => {
    // Search is applied through computed property
  }, 300)
}

// Initialize component
onMounted(async () => {
  console.log('ProductSelector onMounted - props:', {
    language: props.language
  });

  // Register the component in the extension relationships system
  const instance = getCurrentInstance()
  if (instance) {
    console.log('Registering ProductSelector component');
    registerComponent('StoreExtension', 'ProductSelector', instance.proxy?.$options || {})
    console.log('ProductSelector registration complete');

    // Register the relationship so other extensions can find this component
    console.log('Registering StoreExtension -> PagesExtension relationship');
    registerRelationship('StoreExtension', 'PagesExtension', 'component', 'product_selector')
    console.log('Relationship registered');
  } else {
    console.error('Could not get current instance for registration');
  }

  // UI translations come from global i18n; content language is props.language.
  console.log('ProductSelector UI language:', currentLanguage.value, 'content language:', props.language);

  // Load products and categories
  try {
    console.log('Loading products and categories');
    await Promise.all([loadProducts(), loadCategories()])
    console.log('Products loaded:', products.value.length);
    console.log('Categories loaded:', categories.value.length);
  } catch (error) {
    console.error('Failed to load products/categories:', error);
  }
})

// Watch for language changes
watch(() => props.language, async (newLang, oldLang) => {
  if (newLang && newLang !== oldLang) {
    console.log('ProductSelector language changed from', oldLang, 'to', newLang);

    // UI translations follow global i18n; on content language change, reload data
    console.log('ProductSelector reloading data for new language:', newLang);

    await Promise.all([loadProducts(), loadCategories()])
  }
})
</script>

<style scoped>
.product-selector {
  border: 1px solid var(--border-color, #e3e3e3);
  border-radius: var(--border-radius-md, 8px);
  background: var(--card-bg, #ffffff);
  overflow: hidden;
}

.selector-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  border-bottom: 1px solid var(--border-color, #e3e3e3);
  background: var(--bg-secondary, #f8f9fa);
}

.selector-header h4 {
  margin: 0;
  color: var(--text-primary, #222222);
  font-size: 1.1rem;
}

.toggle-btn {
  padding: 0.5rem 1rem;
  background: var(--button-secondary-bg, #6c757d);
  color: var(--button-secondary-text, #ffffff);
  border: 1px solid var(--button-secondary-bg, #6c757d);
  border-radius: var(--border-radius-sm, 4px);
  cursor: pointer;
  font-size: 0.875rem;
  transition: all 0.2s ease;
}

.toggle-btn:hover {
  background: var(--button-secondary-hover, #545b62);
}

.selector-content {
  padding: 1rem;
}

.selector-controls {
  display: flex;
  gap: 1rem;
  margin-bottom: 1rem;
  flex-wrap: wrap;
}

.search-input, .category-select {
  padding: 0.5rem;
  border: 1px solid var(--input-border, #d1d5db);
  border-radius: var(--border-radius-sm, 4px);
  background: var(--input-bg, #ffffff);
  color: var(--text-primary, #222222);
  font-size: 0.875rem;
}

.search-input {
  flex: 1;
  min-width: 200px;
}

.category-select {
  min-width: 150px;
}

.products-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 1rem;
  margin-bottom: 1rem;
  max-height: 400px;
  overflow-y: auto;
}

.product-item {
  border: 1px solid var(--border-color, #e3e3e3);
  border-radius: var(--border-radius-sm, 4px);
  padding: 0.75rem;
  cursor: pointer;
  transition: all 0.2s ease;
  background: var(--card-bg, #ffffff);
}

.product-item:hover {
  border-color: var(--button-primary-bg, #007bff);
  box-shadow: 0 2px 4px rgba(0, 123, 255, 0.1);
}

.product-item.selected {
  border-color: var(--button-primary-bg, #007bff);
  background: rgba(0, 123, 255, 0.05);
}

.product-image {
  width: 100%;
  height: 120px;
  margin-bottom: 0.5rem;
  overflow: hidden;
  border-radius: var(--border-radius-sm, 4px);
}

.product-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.product-info {
  text-align: center;
}

.product-name {
  margin: 0 0 0.5rem 0;
  font-size: 0.9rem;
  font-weight: 500;
  color: var(--text-primary, #222222);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  line-clamp: 2;
  overflow: hidden;
}

.product-price {
  margin-bottom: 0.25rem;
}

.original-price {
  text-decoration: line-through;
  color: var(--text-secondary, #666666);
  font-size: 0.8rem;
  margin-right: 0.5rem;
}

.current-price {
  font-weight: 600;
  color: var(--text-primary, #222222);
}

.product-sku {
  font-size: 0.75rem;
  color: var(--text-secondary, #666666);
}

.selection-indicator {
  display: flex;
  justify-content: center;
  margin-top: 0.5rem;
}

.selected-badge {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--button-primary-bg, #007bff);
  color: var(--button-primary-text, #ffffff);
  display: flex;
  align-items: center;
  justify-content: center;
}

.selected-summary {
  border-top: 1px solid var(--border-color, #e3e3e3);
  padding-top: 1rem;
  margin-top: 1rem;
}

.selected-summary h5 {
  margin: 0 0 0.5rem 0;
  color: var(--text-primary, #222222);
}

.selected-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 1rem;
}

.selected-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.25rem 0.5rem;
  background: var(--bg-secondary, #f8f9fa);
  border-radius: var(--border-radius-sm, 4px);
  font-size: 0.875rem;
}

.remove-btn {
  background: none;
  border: none;
  color: var(--text-secondary, #666666);
  cursor: pointer;
  font-size: 1.2rem;
  line-height: 1;
  padding: 0;
  width: 16px;
  height: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.remove-btn:hover {
  color: var(--danger-color, #dc3545);
}

.action-buttons {
  display: flex;
  gap: 0.75rem;
  justify-content: flex-end;
}

.clear-btn, .confirm-btn {
  padding: 0.5rem 1rem;
  border: none;
  border-radius: var(--border-radius-sm, 4px);
  cursor: pointer;
  font-size: 0.875rem;
  font-weight: 500;
  transition: all 0.2s ease;
}

.clear-btn {
  background: var(--button-secondary-bg, #6c757d);
  color: var(--button-secondary-text, #ffffff);
}

.clear-btn:hover {
  background: var(--button-secondary-hover, #545b62);
}

.confirm-btn {
  background: var(--button-primary-bg, #007bff);
  color: var(--button-primary-text, #ffffff);
}

.confirm-btn:hover {
  background: var(--button-primary-hover, #0056b3);
}

.loading-state, .empty-state {
  text-align: center;
  padding: 2rem;
  color: var(--text-secondary, #666666);
}

/* Dark mode overrides */
.dark-mode .product-item {
  background: var(--card-bg, #2d3748);
  border-color: var(--border-color, #4a5568);
}

.dark-mode .product-name,
.dark-mode .current-price {
  color: var(--text-primary, #e2e8f0);
}

.dark-mode .original-price,
.dark-mode .product-sku {
  color: var(--text-secondary, #a0aec0);
}

.dark-mode .selected-item {
  background: var(--bg-secondary, #4a5568);
}
</style>
