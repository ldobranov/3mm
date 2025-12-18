<template>
  <div class="product-detail" v-if="product">
    <nav class="breadcrumb">
      <router-link to="/store">{{ t('store.home', 'Home') }}</router-link>
      <span class="separator">></span>
      <router-link to="/store">{{ t('store.store', 'Store') }}</router-link>
      <span class="separator">></span>
      <span class="current">{{ product.name }}</span>
    </nav>

    <div class="product-content">
      <div class="product-gallery">
        <div class="main-image">
          <img
            :src="selectedImage || '/placeholder-product.jpg'"
            :alt="product.name"
            @error="handleImageError"
          />
        </div>
        <div v-if="product.images && product.images.length > 1" class="thumbnail-gallery">
          <img
            v-for="(image, index) in product.images"
            :key="index"
            :src="image"
            :alt="`${product.name} ${index + 1}`"
            :class="{ active: selectedImage === image }"
            @click="selectedImage = image"
            @error="handleImageError"
          />
        </div>
      </div>

      <div class="product-info">
        <h1 class="product-title">{{ product.name }}</h1>

         <div class="product-price">
            <span v-if="product.sale_price" class="original-price">{{ formatCurrency(product.price, storeSettings.currency, storeSettings.currencies) }}</span>
            <span class="current-price">{{ formatCurrency(product.sale_price || product.price, storeSettings.currency, storeSettings.currencies) }}</span>
            <span v-if="product.sale_price" class="savings">
              {{ t('store.save', 'Save') }} {{ formatCurrency(product.price - product.sale_price, storeSettings.currency, storeSettings.currencies) }}
            </span>
          </div>

        <div v-if="product.sku" class="product-sku">
          <strong>{{ t('store.sku', 'SKU') }}:</strong> {{ product.sku }}
        </div>

        <div class="product-rating" v-if="product.rating">
          <div class="stars">
            <span
              v-for="star in 5"
              :key="star"
              :class="{ filled: star <= Math.floor(product.rating) }"
            >
              ★
            </span>
          </div>
          <span class="rating-text">
            {{ product.rating }} ({{ product.review_count || 0 }} {{ t('store.reviews', 'reviews') }})
          </span>
        </div>

        <!-- Product Description Section -->
        <div class="product-description-section">
          <h3 class="section-title">{{ t('store.description', 'Description') }}</h3>
          <div class="product-description-content">
            <div v-if="product?.description && product.description.trim()" class="description-block">
              <p class="description-text">{{ product.description }}</p>
            </div>
            <div v-else-if="product?.short_description" class="description-block">
              <p class="short-description-text">{{ product.short_description }}</p>
            </div>
            <div v-else class="no-description">
              <p>{{ t('store.noDescription', 'No description available for this product.') }}</p>
            </div>
          </div>
        </div>

        <!-- Product Reviews Section -->
        <div class="product-reviews-section">
          <h3 class="section-title">{{ t('store.reviews', 'Reviews') }}</h3>

          <!-- Reviews content will go here -->
          <div class="reviews-placeholder">
            <p class="placeholder-text">Reviews functionality coming soon...</p>
          </div>
        </div>

        <div class="product-stock">
          <span v-if="product.stock_quantity > 10" class="in-stock">
            ✓ {{ t('store.inStock', 'In Stock') }}
          </span>
          <span v-else-if="product.stock_quantity > 0" class="low-stock">
            ⚠ {{ t('store.onlyXLeft', 'Only {count} left in stock', { count: product.stock_quantity }) }}
          </span>
          <span v-else class="out-of-stock">
            ✗ {{ t('store.outOfStock', 'Out of Stock') }}
          </span>
        </div>


        <div class="add-to-cart-section">
           <div class="quantity-selector">
             <label for="quantity" class="quantity-label">{{ t('store.quantity', 'Quantity') }}</label>
            <div class="quantity-controls">
              <button @click="decrementQuantity" class="quantity-btn">-</button>
              <input
                id="quantity"
                v-model.number="quantity"
                type="number"
                min="1"
                :max="product.stock_quantity || 999"
                class="quantity-input"
              />
              <button @click="incrementQuantity" class="quantity-btn">+</button>
            </div>
          </div>

          <button
            @click="addToCart"
            class="add-to-cart-btn"
            :disabled="!canAddToCart"
          >
            {{ t('store.addToCart', 'Add to Cart') }}
          </button>
        </div>

        <div class="product-meta">
           <div v-if="product.categories && product.categories.length" class="product-categories">
             <strong class="meta-label">{{ t('store.categories', 'Categories') }}:</strong>
            <span
              v-for="category in product.categories"
              :key="category"
              class="category-tag"
            >
              {{ category }}
            </span>
          </div>

          <div v-if="product.tags && product.tags.length" class="product-tags">
            <strong>{{ t('store.tags', 'Tags') }}:</strong>
            <span
              v-for="tag in product.tags"
              :key="tag"
              class="tag"
            >
              {{ tag }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <div v-if="relatedProducts.length" class="related-products">
      <h2>{{ t('store.relatedProducts', 'Related Products') }}</h2>
      <div class="related-grid">
        <div
          v-for="relatedProduct in relatedProducts"
          :key="relatedProduct.id"
          class="related-product-card"
          @click="goToProduct(relatedProduct)"
        >
          <img
            :src="parseImages(relatedProduct.images)[0] || '/placeholder-product.jpg'"
            :alt="relatedProduct.name"
            @error="handleImageError"
          />
          <h4>{{ relatedProduct.name }}</h4>
          <p class="price">{{ formatCurrency(relatedProduct.sale_price || relatedProduct.price, storeSettings.currency, storeSettings.currencies) }}</p>
        </div>
      </div>
    </div>
  </div>

  <div v-else-if="loading" class="loading">
    {{ t('store.loading', 'Loading...') }}
  </div>

  <div v-else class="product-not-found">
    <h1>{{ t('store.productNotFound', 'Product Not Found') }}</h1>
    <p>{{ t('store.productNotFoundMessage', 'The product you are looking for does not exist.') }}</p>
    <router-link to="/store" class="back-to-store-btn">
      {{ t('store.backToStore', 'Back to Store') }}
    </router-link>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useI18n } from '@/utils/i18n';
import http from '@/utils/dynamic-http';
import { formatCurrency } from './utils/currency';

const { t, currentLanguage } = useI18n();
const route = useRoute();
const router = useRouter();

const product = ref<any>(null);
const selectedImage = ref<string>('');
const quantity = ref(1);
const loading = ref(false);
const relatedProducts = ref<any[]>([]);

type CurrencyPosition = 'prefix' | 'suffix';
type CurrencyFormat = { label: string; position: CurrencyPosition };
type StoreSettings = {
  storeName: string;
  currency: string;
  currencies: Record<string, CurrencyFormat>;
  taxRate: number;
  shippingEnabled: boolean;
  paymentMethods: string[];
};

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

// Reviews related reactive data
const activeTab = ref('description');
const showReviewForm = ref(false);
const submittingReview = ref(false);
const reviewsData = ref<any>({
  reviews: [],
  total: 0,
  average_rating: 0,
  rating_distribution: {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
});
const newReview = ref({
  rating: 0,
  title: '',
  customer_name: '',
  customer_email: '',
  comment: ''
});

// Product tabs
const tabs = computed(() => [
  { id: 'description', label: t('store.description', 'Description') },
  { id: 'reviews', label: t('store.reviews', 'Reviews') }
]);

// Generate session ID for cart
const sessionId = computed(() => {
  return localStorage.getItem('cart_session') || generateSessionId();
});

const canAddToCart = computed(() => {
  return product.value &&
         product.value.stock_quantity > 0 &&
         quantity.value > 0 &&
         quantity.value <= (product.value.stock_quantity || 999);
});

const loadStoreSettings = async () => {
  try {
    const response = await http.get('/api/store/settings');
    storeSettings.value = { ...storeSettings.value, ...response.data };
  } catch (error) {
    console.error('Failed to load store settings:', error);
  }
};

const generateSessionId = () => {
  const id = 'cart_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
  localStorage.setItem('cart_session', id);
  return id;
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

const loadProduct = async () => {
  loading.value = true;
  try {
    const productId = route.params.slug;

    // Load base product (always in English)
    const productResponse = await http.get(`/api/store/products/${productId}`);
    let productData = productResponse.data;

    // Load translations for current language
    if (currentLanguage.value !== 'en') {
      try {
        const translationsResponse = await http.get(`/api/store/products/${productId}/translations`);
        const translations = translationsResponse.data.translations || [];

        // Find translation for current language
        const currentTranslation = translations.find((t: any) => t.language_code === currentLanguage.value);
        if (currentTranslation && currentTranslation.data) {
          // Merge translation with base product
          productData = { ...productData, ...currentTranslation.data };
        }
      } catch (translationError) {
        console.warn('Failed to load translations:', translationError);
        // Continue with base product
      }
    }

    product.value = productData;

    // Parse images from JSON string if needed
    if (product.value) {
      product.value.images = parseImages(product.value.images);
    }

    if (product.value.images && product.value.images.length > 0) {
      selectedImage.value = product.value.images[0];
    }

    // Load related products (same category)
    if (product.value.categories && product.value.categories.length > 0) {
      loadRelatedProducts();
    }

    // Load reviews for this product
    await loadReviews();
  } catch (error) {
    console.error('Failed to load product:', error);
    product.value = null;
  } finally {
    loading.value = false;
  }
};

const loadRelatedProducts = async () => {
  try {
    const category = product.value.categories[0];
    const response = await http.get('/api/store/products', {
      params: { category, limit: 4 }
    });
    relatedProducts.value = response.data.items.filter((p: any) => p.id !== product.value.id);
  } catch (error) {
    console.error('Failed to load related products:', error);
  }
};

const incrementQuantity = () => {
  if (quantity.value < (product.value.stock_quantity || 999)) {
    quantity.value++;
  }
};

const decrementQuantity = () => {
  if (quantity.value > 1) {
    quantity.value--;
  }
};

const addToCart = async () => {
  if (!canAddToCart.value) return;

  try {
    await http.post('/api/store/cart/add', {
      session_id: sessionId.value,
      product_id: product.value.id,
      name: product.value.name,
      price: product.value.sale_price || product.value.price,
      quantity: quantity.value,
      sku: product.value.sku,
      image: selectedImage.value
    });

    // Show success message (you could add a toast notification here)
    alert(t('store.addedToCart', 'Added to cart successfully!'));

    // Reset quantity
    quantity.value = 1;
  } catch (error) {
    console.error('Failed to add to cart:', error);
    alert(t('store.addToCartError', 'Failed to add to cart. Please try again.'));
  }
};

const goToProduct = (relatedProduct: any) => {
  router.push(`/store/product/${relatedProduct.slug || relatedProduct.id}`);
};

const handleImageError = (event: Event) => {
  const img = event.target as HTMLImageElement;
  img.src = '/placeholder-product.jpg';
};

// Reviews methods
const loadReviews = async () => {
  if (!product.value) return;

  try {
    const response = await http.get(`/api/store/products/${product.value.id}/reviews`);
    reviewsData.value = response.data;
  } catch (error) {
    console.error('Failed to load reviews:', error);
  }
};

const getRatingPercentage = (rating: number): number => {
  const total = reviewsData.value.total || 0;
  if (total === 0) return 0;
  const count = reviewsData.value.rating_distribution?.[rating] || 0;
  return (count / total) * 100;
};

const submitReview = async () => {
  if (!newReview.value.rating || !newReview.value.customer_name || !newReview.value.comment) {
    alert(t('store.ratingRequired', 'Please select a rating'));
    return;
  }

  submittingReview.value = true;

  try {
    await http.post(`/api/store/products/${product.value.id}/reviews`, newReview.value);

    // Reset form
    newReview.value = {
      rating: 0,
      title: '',
      customer_name: '',
      customer_email: '',
      comment: ''
    };
    showReviewForm.value = false;

    // Reload reviews
    await loadReviews();

    alert(t('store.reviewPendingApproval', 'Your review has been submitted and is pending approval.'));
  } catch (error) {
    console.error('Failed to submit review:', error);
    alert(t('store.reviewSubmitted', 'Failed to submit review. Please try again.'));
  } finally {
    submittingReview.value = false;
  }
};

const formatDate = (dateString: string): string => {
  const date = new Date(dateString);
  return date.toLocaleDateString(currentLanguage.value || 'en', {
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  });
};

// Watch for route changes (when navigating between products)
watch(() => route.params.slug, () => {
  loadProduct();
});

// Watch for language changes and reload product
watch(() => currentLanguage.value, () => {
  loadProduct();
});

onMounted(() => {
  loadProduct();
  loadStoreSettings();
});
</script>

<style scoped>
.product-detail {
  max-width: 1200px;
  margin: 0 auto;
  padding: 2rem 1rem;
}

.breadcrumb {
  margin-bottom: 2rem;
  font-size: 0.9rem;
  color: var(--text-secondary, #666666);
}

.breadcrumb a {
  color: var(--link-color, #007bff);
  text-decoration: none;
}

.breadcrumb a:hover {
  text-decoration: underline;
}

.separator {
  margin: 0 0.5rem;
}

.current {
  color: var(--text-primary, #222222);
  font-weight: 500;
}

.product-content {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 3rem;
  margin-bottom: 3rem;
}

.product-gallery {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.main-image img {
  width: 100%;
  max-width: 500px;
  height: 500px;
  object-fit: cover;
  border-radius: var(--border-radius-md, 8px);
  border: 1px solid var(--card-border, #e3e3e3);
}

.thumbnail-gallery {
  display: flex;
  gap: 0.5rem;
  overflow-x: auto;
  padding-bottom: 0.5rem;
}

.thumbnail-gallery img {
  width: 80px;
  height: 80px;
  object-fit: cover;
  border-radius: var(--border-radius-sm, 4px);
  border: 2px solid transparent;
  cursor: pointer;
  transition: border-color 0.2s ease;
}

.thumbnail-gallery img:hover,
.thumbnail-gallery img.active {
  border-color: var(--button-primary-bg, #007bff);
}

.product-info {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.product-title {
  font-size: 2rem;
  color: var(--text-primary, #222222);
  margin: 0;
}

.product-price {
  display: flex;
  align-items: center;
  gap: 1rem;
  font-size: 1.5rem;
}

.original-price {
  text-decoration: line-through;
  color: var(--text-secondary, #666666);
  font-size: 1.2rem;
}

.current-price {
  font-weight: bold;
  color: var(--success-color, #28a745);
}

.savings {
  font-size: 1rem;
  color: var(--success-color, #28a745);
  font-weight: 500;
}

.product-sku {
  color: var(--text-secondary, #666666);
}

.product-rating {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.stars {
  color: var(--warning-color, #ffc107);
  font-size: 1.2rem;
}

.rating-text {
  color: var(--text-secondary, #666666);
  font-size: 0.9rem;
}

.product-description-section,
.product-reviews-section {
  margin-top: 2rem;
  margin-bottom: 2rem;
  padding: 1.5rem;
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: var(--border-radius-lg);
}

.section-title {
  color: var(--text-primary);
  margin-bottom: 1rem;
  border-bottom: 2px solid var(--button-primary-bg);
  padding-bottom: 0.5rem;
}

.product-description-content {
  line-height: 1.6;
}

.description-block {
  margin-bottom: 1rem;
}

.description-text {
  font-size: 16px;
  color: var(--text-primary);
}

.short-description-text {
  font-size: 14px;
  color: var(--text-secondary);
  font-style: italic;
}

.no-description {
  color: var(--text-secondary);
  font-style: italic;
}

.placeholder-text {
  color: var(--text-secondary);
  text-align: center;
  font-style: italic;
}

.product-stock {
  font-weight: 500;
}

.in-stock {
  color: var(--success-color, #28a745);
}

.low-stock {
  color: var(--warning-color, #ffc107);
}

.out-of-stock {
  color: var(--error-color, #dc3545);
}

.add-to-cart-section {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  padding: 1.5rem;
  background: var(--card-bg, #ffffff);
  border: 1px solid var(--card-border, #e3e3e3);
  border-radius: var(--border-radius-lg, 12px);
}

.quantity-selector {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.quantity-label {
  color: var(--text-primary);
  font-weight: 500;
}

.quantity-controls {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.quantity-btn {
  width: 40px;
  height: 40px;
  border: 1px solid var(--card-border, #e3e3e3);
  background: var(--card-bg, #ffffff);
  border-radius: var(--border-radius-sm, 4px);
  cursor: pointer;
  font-size: 1.2rem;
  font-weight: bold;
  display: flex;
  align-items: center;
  justify-content: center;
}

.quantity-btn:hover {
  background: var(--hover-bg, #f8f9fa);
}

.quantity-input {
  width: 80px;
  height: 40px;
  text-align: center;
  border: 1px solid var(--card-border, #e3e3e3);
  border-radius: var(--border-radius-sm, 4px);
  font-size: 1rem;
}

.add-to-cart-btn {
  padding: 1rem 2rem;
  background: var(--button-primary-bg, #007bff);
  color: var(--button-primary-text, #ffffff);
  border: none;
  border-radius: var(--border-radius-md, 8px);
  font-size: 1.1rem;
  font-weight: 600;
  cursor: pointer;
  transition: background-color 0.2s ease;
}

.add-to-cart-btn:hover:not(:disabled) {
  background: var(--button-primary-hover, #0056b3);
}

.add-to-cart-btn:disabled {
  background: var(--text-secondary, #666666);
  cursor: not-allowed;
}

.additional-actions {
  display: flex;
  gap: 1rem;
}

.product-meta {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.product-categories,
.product-tags {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.meta-label {
  color: var(--text-primary);
  font-weight: 600;
}

.category-tag,
.tag {
  padding: 0.25rem 0.75rem;
  background: var(--tag-bg, #f8f9fa);
  color: var(--tag-text, #495057);
  border-radius: var(--border-radius-sm, 4px);
  font-size: 0.9rem;
}

.related-products {
  margin-top: 3rem;
  padding-top: 2rem;
  border-top: 1px solid var(--card-border, #e3e3e3);
}

.related-products h2 {
  color: var(--text-primary, #222222);
  margin-bottom: 2rem;
}

.related-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 1.5rem;
}

.related-product-card {
  border: 1px solid var(--card-border, #e3e3e3);
  border-radius: var(--border-radius-md, 8px);
  padding: 1rem;
  cursor: pointer;
  transition: box-shadow 0.2s ease;
}

.related-product-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.related-product-card img {
  width: 100%;
  height: 200px;
  object-fit: cover;
  border-radius: var(--border-radius-sm, 4px);
  margin-bottom: 1rem;
}

.related-product-card h4 {
  margin: 0 0 0.5rem 0;
  color: var(--text-primary, #222222);
  font-size: 1.1rem;
}

.related-product-card .price {
  margin: 0;
  font-weight: bold;
  color: var(--text-primary, #222222);
}

.loading,
.product-not-found {
  text-align: center;
  padding: 4rem 2rem;
}

.product-not-found h1 {
  color: var(--text-primary, #222222);
  margin-bottom: 1rem;
}

.product-not-found p {
  color: var(--text-secondary, #666666);
  margin-bottom: 2rem;
}

.back-to-store-btn {
  display: inline-block;
  padding: 0.75rem 1.5rem;
  background: var(--button-primary-bg, #007bff);
  color: var(--button-primary-text, #ffffff);
  text-decoration: none;
  border-radius: var(--border-radius-md, 8px);
  font-weight: 500;
  transition: background-color 0.2s ease;
}

.back-to-store-btn:hover {
  background: var(--button-primary-hover, #0056b3);
}

/* Product Tabs */
.product-tabs {
  margin-bottom: 2rem;
}

.tab-buttons {
  display: flex;
  border-bottom: 1px solid var(--card-border, #e3e3e3);
  margin-bottom: 2rem;
}

.tab-button {
  padding: 1rem 2rem;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  font-weight: 500;
  color: var(--text-secondary, #666666);
  transition: all 0.2s ease;
}

.tab-button:hover {
  color: var(--text-primary, #222222);
}

.tab-button.active {
  color: var(--button-primary-bg, #007bff);
  border-bottom-color: var(--button-primary-bg, #007bff);
}

.tab-content {
  min-height: 300px;
}

/* Reviews Section */
.reviews-section {
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.reviews-summary {
  background: var(--card-bg, #ffffff);
  border: 1px solid var(--card-border, #e3e3e3);
  border-radius: var(--border-radius-lg, 12px);
  padding: 2rem;
}

.rating-overview {
  display: grid;
  grid-template-columns: 1fr 2fr;
  gap: 2rem;
  align-items: start;
}

.average-rating {
  text-align: center;
  padding: 1rem;
  background: var(--hover-bg, #f8f9fa);
  border-radius: var(--border-radius-md, 8px);
}

.rating-number {
  font-size: 3rem;
  font-weight: bold;
  color: var(--text-primary, #222222);
  margin-bottom: 0.5rem;
}

.average-rating .stars {
  font-size: 1.5rem;
  margin-bottom: 0.5rem;
}

.review-count {
  color: var(--text-secondary, #666666);
  font-size: 0.9rem;
}

.rating-distribution h4 {
  margin-bottom: 1rem;
  color: var(--text-primary, #222222);
}

.rating-bar {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.5rem;
}

.rating-label {
  min-width: 60px;
  font-size: 0.9rem;
  color: var(--text-secondary, #666666);
}

.bar-container {
  flex: 1;
  height: 8px;
  background: var(--hover-bg, #f8f9fa);
  border-radius: 4px;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  background: var(--warning-color, #ffc107);
  border-radius: 4px;
  transition: width 0.3s ease;
}

.rating-count {
  min-width: 30px;
  text-align: right;
  font-size: 0.9rem;
  color: var(--text-secondary, #666666);
}

.write-review-section {
  text-align: center;
}

.write-review-btn {
  padding: 1rem 2rem;
  background: var(--button-primary-bg, #007bff);
  color: var(--button-primary-text, #ffffff);
  border: none;
  border-radius: var(--border-radius-md, 8px);
  font-weight: 600;
  cursor: pointer;
  transition: background-color 0.2s ease;
}

.write-review-btn:hover {
  background: var(--button-primary-hover, #0056b3);
}

/* Review Form */
.review-form {
  background: var(--card-bg, #ffffff);
  border: 1px solid var(--card-border, #e3e3e3);
  border-radius: var(--border-radius-lg, 12px);
  padding: 2rem;
}

.review-form h3 {
  margin-top: 0;
  margin-bottom: 1.5rem;
  color: var(--text-primary, #222222);
}

.form-group {
  margin-bottom: 1.5rem;
}

.form-group label {
  display: block;
  margin-bottom: 0.5rem;
  font-weight: 500;
  color: var(--text-primary, #222222);
}

.form-control {
  width: 100%;
  padding: 0.75rem;
  border: 1px solid var(--card-border, #e3e3e3);
  border-radius: var(--border-radius-md, 8px);
  font-size: 1rem;
  transition: border-color 0.2s ease;
}

.form-control:focus {
  outline: none;
  border-color: var(--button-primary-bg, #007bff);
}

.rating-input {
  display: flex;
  gap: 0.5rem;
}

.star-select {
  font-size: 2rem;
  color: var(--text-secondary, #cccccc);
  cursor: pointer;
  transition: color 0.2s ease;
}

.star-select.selected,
.star-select:hover {
  color: var(--warning-color, #ffc107);
}

.form-actions {
  display: flex;
  gap: 1rem;
  justify-content: flex-end;
  margin-top: 2rem;
}

.submit-btn,
.cancel-btn {
  padding: 0.75rem 1.5rem;
  border: none;
  border-radius: var(--border-radius-md, 8px);
  font-weight: 500;
  cursor: pointer;
  transition: background-color 0.2s ease;
}

.submit-btn {
  background: var(--button-primary-bg, #007bff);
  color: var(--button-primary-text, #ffffff);
}

.submit-btn:hover:not(:disabled) {
  background: var(--button-primary-hover, #0056b3);
}

.submit-btn:disabled {
  background: var(--text-secondary, #666666);
  cursor: not-allowed;
}

.cancel-btn {
  background: var(--button-secondary-bg, #6c757d);
  color: var(--button-secondary-text, #ffffff);
}

.cancel-btn:hover {
  background: var(--button-secondary-hover, #545b62);
}

/* Reviews List */
.reviews-list h3 {
  margin-bottom: 2rem;
  color: var(--text-primary, #222222);
}

.reviews-container {
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.review-item {
  border: 1px solid var(--card-border, #e3e3e3);
  border-radius: var(--border-radius-lg, 12px);
  padding: 1.5rem;
  background: var(--card-bg, #ffffff);
}

.review-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.review-rating .stars {
  color: var(--warning-color, #ffc107);
  font-size: 1.2rem;
}

.review-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.25rem;
}

.review-author {
  font-weight: 600;
  color: var(--text-primary, #222222);
}

.review-date {
  font-size: 0.9rem;
  color: var(--text-secondary, #666666);
}

.review-title {
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--text-primary, #222222);
  margin-bottom: 0.5rem;
}

.review-comment {
  line-height: 1.6;
  color: var(--text-primary, #222222);
}

.no-reviews {
  text-align: center;
  padding: 3rem 2rem;
  color: var(--text-secondary, #666666);
}

.no-reviews p {
  margin-bottom: 1rem;
}

/* Responsive Design */
@media (max-width: 768px) {
  .product-content {
    grid-template-columns: 1fr;
    gap: 2rem;
  }

  .product-gallery {
    order: -1;
  }

  .product-title {
    font-size: 1.5rem;
  }

  .add-to-cart-section {
    padding: 1rem;
  }

  .quantity-controls {
    justify-content: center;
  }

  .additional-actions {
    flex-direction: column;
  }

  .related-grid {
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 1rem;
  }

  /* Reviews responsive */
  .rating-overview {
    grid-template-columns: 1fr;
    gap: 1.5rem;
  }

  .average-rating {
    padding: 1.5rem;
  }

  .rating-number {
    font-size: 2.5rem;
  }

  .review-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 0.5rem;
  }

  .review-meta {
    align-items: flex-start;
  }

  .form-actions {
    flex-direction: column;
  }

  .submit-btn,
  .cancel-btn {
    width: 100%;
  }

  .tab-buttons {
    overflow-x: auto;
  }

  .tab-button {
    white-space: nowrap;
    padding: 0.75rem 1rem;
  }
}
</style>
