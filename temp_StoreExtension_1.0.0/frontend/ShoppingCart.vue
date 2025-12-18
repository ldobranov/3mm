<template>
  <div class="shopping-cart">
    <header class="cart-header">
      <h1>{{ t('store.shoppingCart', 'Shopping Cart') }}</h1>
      <div class="cart-info">
        <span>{{ cartItems.length }} {{ t('store.items', 'items') }}</span>
      </div>
    </header>

    <div v-if="cartItems.length === 0" class="empty-cart">
      <div class="empty-cart-content">
        <div class="empty-cart-icon">🛒</div>
        <h2>{{ t('store.cartEmpty', 'Your cart is empty') }}</h2>
        <p>{{ t('store.cartEmptyMessage', 'Add some products to get started!') }}</p>
        <router-link to="/store" class="continue-shopping-btn">
          {{ t('store.continueShopping', 'Continue Shopping') }}
        </router-link>
      </div>
    </div>

    <div v-else class="cart-content">
      <div class="cart-items">
        <div
          v-for="(item, index) in cartItems"
          :key="`${item.product_id}-${item.variant_data || ''}`"
          class="cart-item"
        >
          <div class="item-image">
            <img
              :src="item.image || '/placeholder-product.jpg'"
              :alt="item.name"
              @error="handleImageError"
            />
          </div>

          <div class="item-details">
            <h3 class="item-name">{{ item.name }}</h3>
            <p v-if="item.sku" class="item-sku">{{ t('store.sku', 'SKU') }}: {{ item.sku }}</p>
            <div v-if="item.variant_data" class="item-variants">
              <span
                v-for="(value, key) in item.variant_data"
                :key="key"
                class="variant-tag"
              >
                {{ key }}: {{ value }}
              </span>
            </div>
            <div class="item-price">
              <span class="price">{{ formatCurrency(item.price, storeSettings.currency, storeSettings.currencies) }}</span>
            </div>
          </div>

          <div class="item-quantity">
            <button @click="updateQuantity(index, item.quantity - 1)" class="quantity-btn">-</button>
            <span class="quantity">{{ item.quantity }}</span>
            <button @click="updateQuantity(index, item.quantity + 1)" class="quantity-btn">+</button>
          </div>

          <div class="item-total">
            <span class="total">{{ formatCurrency((item.price * item.quantity).toFixed(2), storeSettings.currency, storeSettings.currencies) }}</span>
          </div>

          <div class="item-actions">
            <button @click="removeItem(index)" class="remove-btn">
              {{ t('store.remove', 'Remove') }}
            </button>
          </div>
        </div>
      </div>

      <div class="cart-summary">
        <div class="summary-row">
          <span class="summary-label">{{ t('store.subtotal', 'Subtotal') }}</span>
          <span class="summary-value">{{ formatCurrency(subtotal.toFixed(2), storeSettings.currency, storeSettings.currencies) }}</span>
        </div>
        <div class="summary-row">
          <span class="summary-label">{{ t('store.shipping', 'Shipping') }}</span>
          <span class="summary-value">{{ formatCurrency(shipping.toFixed(2), storeSettings.currency, storeSettings.currencies) }}</span>
        </div>
        <div class="summary-row">
          <span class="summary-label">{{ t('store.tax', 'Tax') }}</span>
          <span class="summary-value">{{ formatCurrency(tax.toFixed(2), storeSettings.currency, storeSettings.currencies) }}</span>
        </div>
        <div class="summary-row total-row">
          <span class="summary-label">{{ t('store.total', 'Total') }}</span>
          <span class="summary-value">{{ formatCurrency(total.toFixed(2), storeSettings.currency, storeSettings.currencies) }}</span>
        </div>

        <div class="cart-actions">
          <router-link to="/store" class="continue-shopping-btn">
            {{ t('store.continueShopping', 'Continue Shopping') }}
          </router-link>
          <button @click="proceedToCheckout" class="checkout-btn" :disabled="!canCheckout">
            {{ t('store.proceedToCheckout', 'Proceed to Checkout') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { useI18n } from '@/utils/i18n';
import http from '@/utils/dynamic-http';
import { formatCurrency } from './utils/currency';

const { t } = useI18n();
const router = useRouter();

const cartItems = ref<any[]>([]);
const loading = ref(false);

type CurrencyPosition = 'prefix' | 'suffix';
type CurrencyFormat = { label: string; position: CurrencyPosition };

const storeSettings = ref<{ currency: string; currencies: Record<string, CurrencyFormat> }>({
  currency: 'USD',
  currencies: {
    USD: { label: '$', position: 'prefix' },
    EUR: { label: '€', position: 'prefix' },
    GBP: { label: '£', position: 'prefix' },
    BGN: { label: 'лв', position: 'suffix' },
    JPY: { label: '¥', position: 'prefix' },
    CAD: { label: 'C$', position: 'prefix' },
    AUD: { label: 'A$', position: 'prefix' }
  }
});

// Generate session ID (in production, this would come from user session)
const sessionId = computed(() => {
  return localStorage.getItem('cart_session') || generateSessionId();
});

const subtotal = computed(() => {
  return cartItems.value.reduce((sum, item) => sum + (item.price * item.quantity), 0);
});

const shipping = computed(() => {
  // Simple shipping calculation - in production, this would be more complex
  return subtotal.value > 50 ? 0 : 9.99;
});

const tax = computed(() => {
  // Simple tax calculation - 8.5% tax rate
  return (subtotal.value + shipping.value) * 0.085;
});

const total = computed(() => {
  return subtotal.value + shipping.value + tax.value;
});

const canCheckout = computed(() => {
  return cartItems.value.length > 0 && !loading.value;
});

const generateSessionId = () => {
  const id = 'cart_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
  localStorage.setItem('cart_session', id);
  return id;
};

const loadCart = async () => {
  try {
    const response = await http.get('/api/store/cart', {
      params: { session_id: sessionId.value }
    });
    cartItems.value = response.data.items || [];
  } catch (error) {
    console.error('Failed to load cart:', error);
    cartItems.value = [];
  }
};

const loadStoreSettings = async () => {
  try {
    const response = await http.get('/api/store/settings');
    storeSettings.value = { ...storeSettings.value, ...response.data };
  } catch (error) {
    console.warn('Failed to load store settings for currency formatting:', error);
  }
};

const updateQuantity = async (index: number, newQuantity: number) => {
  if (newQuantity < 1) return;

  const item = cartItems.value[index];
  const quantityDiff = newQuantity - item.quantity;

  try {
    // Update cart on server
    await http.post('/api/store/cart/add', {
      session_id: sessionId.value,
      product_id: item.product_id,
      name: item.name,
      price: item.price,
      quantity: quantityDiff,
      variant_data: item.variant_data
    });

    // Update local cart
    item.quantity = newQuantity;
  } catch (error) {
    console.error('Failed to update quantity:', error);
  }
};

const removeItem = async (index: number) => {
  const item = cartItems.value[index];

  try {
    // For removal, we need to add negative quantity
    await http.post('/api/store/cart/add', {
      session_id: sessionId.value,
      product_id: item.product_id,
      quantity: -item.quantity,
      variant_data: item.variant_data
    });

    // Remove from local cart
    cartItems.value.splice(index, 1);
  } catch (error) {
    console.error('Failed to remove item:', error);
  }
};

const proceedToCheckout = () => {
  if (canCheckout.value) {
    router.push('/store/checkout');
  }
};

const handleImageError = (event: Event) => {
  const img = event.target as HTMLImageElement;
  img.src = '/placeholder-product.jpg';
};

onMounted(() => {
  loadCart();
  loadStoreSettings();
});
</script>

<style scoped>
.shopping-cart {
  max-width: 1200px;
  margin: 0 auto;
  padding: 2rem 1rem;
}

.cart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid var(--card-border, #e3e3e3);
}

.cart-header h1 {
  color: var(--text-primary, #222222);
  margin: 0;
}

.cart-info {
  color: var(--text-secondary, #666666);
  font-size: 1.1rem;
}

.empty-cart {
  text-align: center;
  padding: 4rem 2rem;
}

.empty-cart-content {
  max-width: 400px;
  margin: 0 auto;
}

.empty-cart-icon {
  font-size: 4rem;
  margin-bottom: 1rem;
}

.empty-cart h2 {
  color: var(--text-primary, #222222);
  margin-bottom: 1rem;
}

.empty-cart p {
  color: var(--text-secondary, #666666);
  margin-bottom: 2rem;
}

.continue-shopping-btn, .checkout-btn {
  display: inline-block;
  padding: 0.75rem 1.5rem;
  border-radius: var(--border-radius-md, 8px);
  text-decoration: none;
  font-weight: 500;
  transition: all 0.2s ease;
  cursor: pointer;
  border: none;
}

.continue-shopping-btn {
  background: var(--button-secondary-bg, #6c757d);
  color: var(--button-secondary-text, #ffffff);
}

.continue-shopping-btn:hover {
  background: var(--button-secondary-hover, #545b62);
}

.checkout-btn {
  background: var(--button-primary-bg, #007bff);
  color: var(--button-primary-text, #ffffff);
}

.checkout-btn:hover:not(:disabled) {
  background: var(--button-primary-hover, #0056b3);
}

.checkout-btn:disabled {
  background: var(--text-secondary, #666666);
  cursor: not-allowed;
}

.cart-content {
  display: grid;
  grid-template-columns: 1fr 300px;
  gap: 2rem;
}

.cart-items {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.cart-item {
  display: grid;
  grid-template-columns: 80px minmax(200px, 1fr) 120px 100px 80px;
  gap: 1rem;
  align-items: center;
  padding: 1rem;
  border: 1px solid var(--card-border, #e3e3e3);
  border-radius: var(--border-radius-md, 8px);
  background: var(--card-bg, #ffffff);
}

.item-image img {
  width: 60px;
  height: 60px;
  object-fit: cover;
  border-radius: var(--border-radius-sm, 4px);
}

.item-details {
  min-width: 0;
}

.item-name {
  margin: 0 0 0.5rem 0;
  font-size: 1.1rem;
  color: var(--text-primary, #222222);
}

.item-sku {
  margin: 0 0 0.5rem 0;
  font-size: 0.9rem;
  color: var(--text-secondary, #666666);
}

.item-variants {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
  margin-bottom: 0.5rem;
}

.variant-tag {
  font-size: 0.8rem;
  background: var(--tag-bg, #f8f9fa);
  color: var(--tag-text, #495057);
  padding: 0.25rem 0.5rem;
  border-radius: var(--border-radius-sm, 4px);
}

.item-price {
  font-weight: 600;
  color: var(--text-primary, #222222);
}

.item-quantity {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.quantity-btn {
  width: 30px;
  height: 30px;
  border: 1px solid var(--card-border, #e3e3e3);
  background: var(--card-bg, #ffffff);
  border-radius: var(--border-radius-sm, 4px);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: bold;
}

.quantity-btn:hover {
  background: var(--hover-bg, #f8f9fa);
}

.quantity {
  font-weight: 600;
  min-width: 30px;
  text-align: center;
}

.item-total {
  font-weight: 600;
  color: var(--text-primary, #222222);
  text-align: right;
}

.item-actions {
  display: flex;
  justify-content: flex-end;
}

.remove-btn {
  padding: 0.5rem;
  background: var(--error-bg, #dc3545);
  color: var(--error-text, #ffffff);
  border: none;
  border-radius: var(--border-radius-sm, 4px);
  cursor: pointer;
  font-size: 0.9rem;
}

.remove-btn:hover {
  background: var(--error-hover, #c82333);
}

.cart-summary {
  background: var(--card-bg, #ffffff);
  border: 1px solid var(--card-border, #e3e3e3);
  border-radius: var(--border-radius-lg, 12px);
  padding: 1.5rem;
  height: fit-content;
}

.summary-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.75rem;
}

.summary-row:last-child {
  margin-bottom: 1.5rem;
}

.summary-label {
  color: var(--text-primary, #222222);
}

.summary-value {
  font-weight: 600;
  color: var(--text-primary, #222222);
}

.total-row {
  border-top: 2px solid var(--card-border, #e3e3e3);
  padding-top: 1rem;
  margin-top: 1rem;
  font-size: 1.2rem;
  font-weight: bold;
}

.cart-actions {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

/* Responsive Design */
@media (max-width: 768px) {
  .cart-content {
    grid-template-columns: 1fr;
    gap: 1rem;
  }

  .cart-item {
    grid-template-columns: 60px 1fr;
    grid-template-rows: auto auto;
    gap: 0.5rem;
  }

  .item-quantity, .item-total, .item-actions {
    grid-column: 2;
  }

  .item-quantity {
    justify-self: start;
  }

  .item-total, .item-actions {
    justify-self: end;
  }

  .cart-summary {
    order: -1;
  }

  .cart-actions {
    flex-direction: column;
  }

  .continue-shopping-btn, .checkout-btn {
    width: 100%;
    text-align: center;
  }
}

</style>
