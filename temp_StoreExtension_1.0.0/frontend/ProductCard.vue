<template>
  <div class="product-card">
    <div class="product-image">
      <img
        :src="parsedImages[0] || '/placeholder-product.jpg'"
        :alt="product.name"
        @error="handleImageError"
      />
      <div v-if="product.sale_price" class="sale-badge">{{ t('store.sale', 'Sale') }}</div>
      <div v-if="product.stock_quantity === 0" class="out-of-stock-badge">
        {{ t('store.outOfStock', 'Out of Stock') }}
      </div>
    </div>

    <div class="product-info">
      <h3 class="product-name">{{ product.name }}</h3>
      <p class="product-price">
        <span v-if="product.sale_price" class="original-price">{{ formatCurrency(product.price, props.currency, props.currencyFormats) }}</span>
        <span class="current-price">{{ formatCurrency(product.sale_price || product.price, props.currency, props.currencyFormats) }}</span>
      </p>

      <div class="product-actions">
        <button
          @click="$emit('add-to-cart', product)"
          :disabled="product.stock_quantity === 0"
          class="add-to-cart-btn"
          :class="{ disabled: product.stock_quantity === 0 }"
        >
          {{ product.stock_quantity === 0 ? t('store.outOfStock', 'Out of Stock') : t('store.addToCart', 'Add to Cart') }}
        </button>
        <router-link :to="`/store/product/${product.slug || product.id}`" class="view-details-btn">
          {{ t('store.viewDetails', 'View Details') }}
        </router-link>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, watch, onMounted } from 'vue';
import { useI18n } from '@/utils/i18n';
import { formatCurrency } from './utils/currency';

const { t, currentLanguage } = useI18n();

// Debug logging for component initialization
onMounted(() => {
  console.log('ProductCard mounted with language:', currentLanguage.value);
  console.log('Initial translations:', {
    addToCart: t('store.addToCart', 'Add to Cart'),
    viewDetails: t('store.viewDetails', 'View Details'),
    sale: t('store.sale', 'Sale')
  });
});

// Debug logging for language changes
watch(currentLanguage, (newLang) => {
  console.log('ProductCard language changed to:', newLang);
  console.log('Updated translations:', {
    addToCart: t('store.addToCart', 'Add to Cart'),
    viewDetails: t('store.viewDetails', 'View Details'),
    sale: t('store.sale', 'Sale')
  });
});

const props = defineProps<{
  product: {
    id: number;
    name: string;
    price: number;
    sale_price?: number;
    stock_quantity: number;
    images?: string | string[];
    slug?: string;
  };
  currency?: string;
  currencyFormats?: Record<string, { label: string; position: 'prefix' | 'suffix' }>;
}>();

defineEmits<{
  'add-to-cart': [product: any];
}>();

// Parse images from JSON string or return as array
const parsedImages = computed(() => {
  if (!props.product.images) return [];

  let images: string[] = [];
  if (Array.isArray(props.product.images)) {
    images = props.product.images;
  } else {
    // Try to parse JSON string
    try {
      const parsed = JSON.parse(props.product.images);
      images = Array.isArray(parsed) ? parsed : [];
    } catch {
      images = [];
    }
  }

  // Convert relative URLs to full URLs
  return images.map(url => {
    if (url.startsWith('/uploads')) {
      return `http://localhost:8887${url}`;
    }
    return url;
  });
});

const handleImageError = (event: Event) => {
  const img = event.target as HTMLImageElement;
  img.src = '/placeholder-product.jpg';
};

</script>

<style scoped>
.product-card {
  background: var(--card-bg, #ffffff);
  border: 1px solid var(--card-border, #e3e3e3);
  border-radius: var(--border-radius-lg, 12px);
  box-shadow: 0 2px 8px var(--card-shadow, rgba(0, 0, 0, 0.1));
  overflow: hidden;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.product-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 16px var(--card-shadow, rgba(0, 0, 0, 0.15));
}

.product-image {
  position: relative;
  width: 100%;
  height: 200px;
  overflow: hidden;
}

.product-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.2s ease;
}

.product-card:hover .product-image img {
  transform: scale(1.05);
}

.sale-badge, .out-of-stock-badge {
  position: absolute;
  top: 10px;
  right: 10px;
  padding: 0.25rem 0.5rem;
  border-radius: var(--border-radius-sm, 4px);
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
}

.sale-badge {
  background: var(--error-bg, #dc3545);
  color: var(--error-text, #ffffff);
}

.out-of-stock-badge {
  background: var(--text-secondary, #666666);
  color: var(--card-bg, #ffffff);
}

.product-info {
  padding: 1rem;
}

.product-name {
  color: var(--text-primary, #222222);
  margin: 0 0 0.5rem 0;
  font-size: 1.1rem;
  font-weight: 600;
  line-height: 1.3;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  line-clamp: 2;
}

.product-price {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 1rem;
}

.original-price {
  color: var(--text-secondary, #666666);
  text-decoration: line-through;
  font-size: 0.9rem;
}

.current-price {
  color: var(--text-primary, #222222);
  font-size: 1.1rem;
  font-weight: 600;
}

.product-actions {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.add-to-cart-btn, .view-details-btn {
  padding: 0.5rem 1rem;
  border: none;
  border-radius: var(--border-radius-md, 8px);
  font-weight: 500;
  text-align: center;
  text-decoration: none;
  transition: all 0.2s ease;
  cursor: pointer;
}

.add-to-cart-btn {
  background: var(--button-primary-bg, #007bff);
  color: var(--button-primary-text, #ffffff);
}

.add-to-cart-btn:hover:not(.disabled) {
  background: var(--button-primary-hover, #0056b3);
}

.add-to-cart-btn.disabled {
  background: var(--text-secondary, #666666);
  cursor: not-allowed;
  opacity: 0.6;
}

.view-details-btn {
  background: transparent;
  color: var(--link-color, #007bff);
  border: 1px solid var(--link-color, #007bff);
}

.view-details-btn:hover {
  background: var(--link-color, #007bff);
  color: var(--button-primary-text, #ffffff);
}

/* Responsive Design */
@media (max-width: 768px) {
  .product-image {
    height: 150px;
  }

  .product-info {
    padding: 0.75rem;
  }

  .product-name {
    font-size: 1rem;
  }

  .current-price {
    font-size: 1rem;
  }

  .add-to-cart-btn, .view-details-btn {
    padding: 0.4rem 0.8rem;
    font-size: 0.9rem;
  }
}
</style>
