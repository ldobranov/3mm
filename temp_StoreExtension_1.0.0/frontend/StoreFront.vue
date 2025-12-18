<template>
  <div class="store-container">
    <header class="store-header">
      <div class="header-left">
        <h1>{{ storeSettings.storeName || t('store.title', 'Store') }}</h1>
      </div>
      <div class="cart-widget">
        <router-link to="/store/cart" class="cart-link">
          🛒 {{ cartCount }} {{ t('store.items', 'items') }}
        </router-link>
      </div>
    </header>

    <nav class="store-nav">
      <router-link to="/store" class="nav-link">{{ t('store.allProducts', 'All Products') }}</router-link>
      <router-link
        v-for="category in categories"
        :key="category.id"
        :to="`/store?category=${category.slug}`"
        class="nav-link"
      >
        {{ category.name }}
      </router-link>
    </nav>

    <main class="store-content">
      <div class="products-grid">
        <ProductCard
          v-for="product in products"
          :key="product.id"
          :product="product"
          :currency="storeSettings.currency"
          :currency-formats="storeSettings.currencies"
          @add-to-cart="addToCart"
        />
      </div>

      <div v-if="loading" class="loading">
        <div class="spinner"></div>
        <p>{{ t('store.loading', 'Loading products...') }}</p>
      </div>

      <div v-if="!loading && products.length === 0" class="no-products">
        {{ t('store.noProducts', 'No products found') }}
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue';
import { useRoute } from 'vue-router';
import { useI18n } from '@/utils/i18n';
import http from '@/utils/dynamic-http';
import ProductCard from './ProductCard.vue';

const { t, currentLanguage, availableLanguages, setLanguage } = useI18n();

// Type definitions
interface Product {
  id: number;
  name: string;
  price: number;
  sale_price?: number;
  stock_quantity: number;
  images?: string | string[];
  slug?: string;
  description?: string;
  short_description?: string;
  categories?: string[];
}

interface Category {
  id: number;
  name: string;
  slug: string;
}

interface StoreSettings {
  storeName?: string;
  currency?: string;
  currencies?: Record<string, { label: string; position: 'prefix' | 'suffix' }>;
  taxRate?: number;
  shippingEnabled?: boolean;
  paymentMethods?: string[];
}
const route = useRoute();

const products = ref<Product[]>([]);
const categories = ref<Category[]>([]);
const loading = ref(false);
const cartCount = ref(0);
const storeSettings = ref<StoreSettings>({
  storeName: 'Store',
  currency: 'USD',
  currencies: {
    USD: { label: '$', position: 'prefix' },
    EUR: { label: '€', position: 'prefix' },
    GBP: { label: '£', position: 'prefix' },
    BGN: { label: 'лв', position: 'suffix' },
    JPY: { label: '¥', position: 'prefix' },
    CAD: { label: 'C$', position: 'prefix' },
    AUD: { label: 'A$', position: 'prefix' }
  },
  taxRate: 0,
  shippingEnabled: true,
  paymentMethods: ['stripe']
});

// Generate session ID for cart
const sessionId = computed(() => {
  return localStorage.getItem('cart_session') || generateSessionId();
});

const generateSessionId = () => {
  const id = 'cart_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
  localStorage.setItem('cart_session', id);
  return id;
};

const loadStoreSettings = async () => {
  try {
    // Load base settings
    const response = await http.get('/api/store/settings');
    let settingsData = { ...storeSettings.value, ...response.data };

    // If current language is not English, load translations
    if (currentLanguage.value !== 'en') {
      try {
        const translationsResponse = await http.get('/api/store/settings/translations');
        const translations = translationsResponse.data.translations || [];

        // Find translation for current language
        const currentTranslation = translations.find((t: any) => t.language_code === currentLanguage.value);
        if (currentTranslation && currentTranslation.data) {
          // Merge translation with base settings
          settingsData = { ...settingsData, ...currentTranslation.data };
        }
      } catch (translationError) {
        console.warn('Failed to load store settings translations:', translationError);
        // Continue with base settings
      }
    }

    storeSettings.value = settingsData;
  } catch (error) {
    console.error('Failed to load store settings:', error);
  }
};

const loadProducts = async () => {
  loading.value = true;
  try {
    const params: { category?: string; search?: string } = {};
    const query = route.query as { category?: string; search?: string };
    if (query.category) params.category = query.category;
    if (query.search) params.search = query.search;

    // Load base products (always in English)
    const response = await http.get('/api/store/products', {
      params: {
        ...params,
        language: 'en'  // Always load English base
      }
    });

    let productsData = response.data.items;

    // If current language is not English, load translations for each product
    if (currentLanguage.value !== 'en') {
      const translatedProducts = [];

      for (const product of productsData) {
        try {
          const translationResponse = await http.get(`/api/store/products/${product.id}/translations`);
          const translations = translationResponse.data.translations || [];
          
          // Find translation for current language
          const currentTranslation = translations.find((t: any) => t.language_code === currentLanguage.value);
          if (currentTranslation && currentTranslation.data) {
            // Merge translation with base product
            translatedProducts.push({ ...product, ...currentTranslation.data });
          } else {
            console.log(`No ${currentLanguage.value} translation for product ${product.id}, using base`);
            // No translation available, use base product
            translatedProducts.push(product);
          }
        } catch (translationError) {
          console.error(`Failed to load translation for product ${product.id}:`, translationError);
          // Use base product if translation fails
          console.log(`Using base product ${product.id} due to translation error`);
          translatedProducts.push(product);
        }
      }
      productsData = translatedProducts;
    } else {
      console.log('Using English (base language), no translation loading needed');
    }
    
    products.value = productsData;
  } catch (error) {
    console.error('Failed to load products:', error);
  } finally {
    loading.value = false;
  }
};

const loadCartCount = async () => {
  try {
    const response = await http.get('/api/store/cart', {
      params: { session_id: sessionId.value }
    });
    cartCount.value = response.data.items?.length || 0;
  } catch (error) {
    console.error('Failed to load cart count:', error);
    cartCount.value = 0;
  }
};

const addToCart = async (product: any) => {
  try {
    await http.post('/api/store/cart/add', {
      session_id: sessionId.value,
      product_id: product.id,
      name: product.name,
      price: product.price,
      quantity: 1,
      sku: product.sku
    });
    cartCount.value++;
  } catch (error) {
    console.error('Failed to add to cart:', error);
  }
};

const loadCategories = async () => {
  try {
    
    // Load base categories (always in English)
    const response = await http.get('/api/store/categories');
    let categoriesData = response.data.items;

    // If current language is not English, load translations for each category
    if (currentLanguage.value !== 'en') {
      const translatedCategories = [];

      for (const category of categoriesData) {
        try {
          const translationResponse = await http.get(`/api/store/categories/${category.id}/translations`);
          const translations = translationResponse.data.translations || [];

          // Find translation for current language
          const currentTranslation = translations.find((t: any) => t.language_code === currentLanguage.value);
          if (currentTranslation && currentTranslation.data) {
            // Merge translation with base category
            translatedCategories.push({ ...category, ...currentTranslation.data });
          } else {
            // No translation available, use base category
            translatedCategories.push(category);
          }
        } catch (translationError) {
          console.warn(`Failed to load translation for category ${category.id}:`, translationError);
          // Use base category if translation fails
          translatedCategories.push(category);
        }
      }

      categoriesData = translatedCategories;
    }
    
    categories.value = categoriesData;
  } catch (error) {
    console.error('Failed to load categories:', error);
  }
};

onMounted(() => {
  loadProducts();
  loadCategories();
  loadCartCount();
  loadStoreSettings();
});

// Watch for language changes and reload products and categories
watch(() => currentLanguage.value, () => {
  loadProducts();
  loadCategories();
});

// Watch for route query changes (category filtering)
watch(() => route.query.category, () => {
  loadProducts();
});

watch(() => route.query.search, () => {
  loadProducts();
});

// Watch for potential settings changes (when returning from admin)
watch(() => route.path, (newPath) => {
  if (newPath === '/store' || newPath.startsWith('/store/')) {
    loadStoreSettings();
  }
});
</script>

<style scoped>
.store-container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 2rem 1rem;
}

.store-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid var(--card-border, #e3e3e3);
}

.header-left {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  align-items: flex-start;
}

.store-header h1 {
  color: var(--text-primary, #222222);
  margin: 0;
  font-size: 2.5rem;
}

.cart-widget {
  display: flex;
  align-items: center;
}

.cart-link {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  background: var(--button-primary-bg, #007bff);
  color: var(--button-primary-text, #ffffff);
  text-decoration: none;
  border-radius: var(--border-radius-md, 8px);
  font-weight: 500;
  transition: background-color 0.2s ease;
}

.cart-link:hover {
  background: var(--button-primary-hover, #0056b3);
}

.store-nav {
  display: flex;
  gap: 1rem;
  margin-bottom: 2rem;
  flex-wrap: wrap;
}

.nav-link {
  padding: 0.5rem 1rem;
  background: var(--card-bg, #ffffff);
  color: var(--text-primary, #222222);
  text-decoration: none;
  border: 1px solid var(--card-border, #e3e3e3);
  border-radius: var(--border-radius-md, 8px);
  transition: all 0.2s ease;
}

.nav-link:hover,
.nav-link.router-link-active {
  background: var(--button-primary-bg, #007bff);
  color: var(--button-primary-text, #ffffff);
  border-color: var(--button-primary-bg, #007bff);
}

.products-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 2rem;
  margin-bottom: 2rem;
}

.loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 4rem 2rem;
  text-align: center;
}

.spinner {
  width: 40px;
  height: 40px;
  border: 4px solid var(--card-border, #e3e3e3);
  border-top: 4px solid var(--button-primary-bg, #007bff);
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 1rem;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.no-products {
  text-align: center;
  padding: 4rem 2rem;
  color: var(--text-secondary, #666666);
  font-size: 1.1rem;
}

/* Responsive Design */
@media (max-width: 768px) {
  .store-container {
    padding: 1rem 0.5rem;
  }

  .store-header {
    flex-direction: column;
    gap: 1rem;
  }

  .header-left {
    align-items: center;
    text-align: center;
  }

  .store-header h1 {
    font-size: 2rem;
  }

  .store-nav {
    justify-content: center;
  }

  .products-grid {
    grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
    gap: 1rem;
  }
}
</style>
