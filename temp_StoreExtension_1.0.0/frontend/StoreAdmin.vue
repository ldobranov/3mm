<template>
  <div class="store-admin">
    <header class="admin-header">
      <h1>{{ t('store.admin.title', 'Store Administration') }}</h1>
      <nav class="admin-nav">
        <button
          @click="activeTab = 'products'"
          :class="{ active: activeTab === 'products' }"
        >
          {{ t('store.admin.products', 'Products') }}
        </button>
        <button
          @click="activeTab = 'categories'"
          :class="{ active: activeTab === 'categories' }"
        >
          {{ t('store.admin.categories', 'Categories') }}
        </button>
        <button
          @click="activeTab = 'orders'"
          :class="{ active: activeTab === 'orders' }"
        >
          {{ t('store.admin.orders', 'Orders') }}
        </button>
        <button
          @click="activeTab = 'settings'"
          :class="{ active: activeTab === 'settings' }"
        >
          {{ t('store.admin.settings', 'Settings') }}
        </button>
      </nav>
    </header>

    <main class="admin-content">
      <!-- Products Tab -->
      <div v-if="activeTab === 'products'" class="admin-section">
        <div class="section-header">
          <h2>{{ t('store.admin.products', 'Products') }}</h2>
          <button @click="showProductForm = true" class="add-btn">
            {{ t('store.admin.addProduct', 'Add Product') }}
          </button>
        </div>
        <div class="products-list">
          <div
            v-for="product in products"
            :key="product.id"
            class="product-item"
          >
            <div class="product-info">
              <h3>{{ product.name }}</h3>
              <p>{{ product.price }}</p>
              <span :class="{ 'out-of-stock': product.stock_quantity === 0 }">
                {{ product.stock_quantity }} {{ t('store.inStock', 'in stock') }}
              </span>
            </div>
            <div class="product-actions">
              <button @click="editProduct(product)" class="edit-btn">
                {{ t('store.edit', 'Edit') }}
              </button>
              <button @click="deleteProduct(product.id)" class="delete-btn">
                {{ t('store.delete', 'Delete') }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Categories Tab -->
      <div v-if="activeTab === 'categories'" class="admin-section">
        <div class="section-header">
          <h2>{{ t('store.admin.categories', 'Categories') }}</h2>
          <button @click="showCategoryForm = true" class="add-btn">
            {{ t('store.admin.addCategory', 'Add Category') }}
          </button>
        </div>
        <div class="categories-list">
          <div
            v-for="category in categories"
            :key="category.id"
            class="category-item"
          >
            <div class="category-info">
              <h3>{{ category.name }}</h3>
              <p>{{ category.description }}</p>
            </div>
            <div class="category-actions">
              <button @click="editCategory(category)" class="edit-btn">
                {{ t('store.edit', 'Edit') }}
              </button>
              <button @click="deleteCategory(category.id)" class="delete-btn">
                {{ t('store.delete', 'Delete') }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Orders Tab -->
      <div v-if="activeTab === 'orders'" class="admin-section">
        <div class="section-header">
          <h2>{{ t('store.admin.orders', 'Orders') }}</h2>
        </div>
        <div class="orders-list">
          <div
            v-for="order in orders"
            :key="order.id"
            class="order-item"
          >
            <div class="order-info">
              <h3>{{ order.order_number }}</h3>
              <p>{{ order.total_amount }}</p>
              <span :class="order.status">{{ order.status }}</span>
            </div>
            <div class="order-actions">
              <button @click="viewOrder(order.id)" class="view-btn">
                {{ t('store.view', 'View') }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Settings Tab -->
      <div v-if="activeTab === 'settings'" class="admin-section">
        <div class="section-header">
          <h2>{{ t('store.admin.settings', 'Settings') }}</h2>
        </div>

        <!-- Language Selector for Settings -->
        <div class="settings-grid">
          <div class="settings-card">
            <h3>{{ t('store.language', 'Language') }}</h3>
            <div class="form-field">
              <select v-model="selectedSettingsLanguage" @change="loadSettingsForLanguage" class="form-control">
                <option value="en">English</option>
                <option v-for="lang in availableLanguages.filter(l => l !== 'en')" :key="lang" :value="lang">
                  {{ getLanguageName(lang) }}
                </option>
              </select>
              <small class="help-text">{{ t('store.settings.languageHelp', 'Select language for store settings') }}</small>
            </div>
          </div>
        </div>

        <form @submit.prevent="saveSettings" class="settings-form">
          <div class="settings-grid">
            <!-- Store Information Section -->
            <div class="settings-card">
              <h3>{{ t('store.settings.storeInfo', 'Store Information') }}</h3>

              <div class="form-field">
                <label for="storeName" class="form-label">{{ t('store.settings.storeName', 'Store Name') }}</label>
                <input
                  id="storeName"
                  v-model="settings.storeName"
                  type="text"
                  class="form-control"
                  :placeholder="t('store.settings.storeName', 'Store Name')"
                  required
                />
              </div>

              <div class="form-field">
                <label for="currency" class="form-label">{{ t('store.settings.currency', 'Currency Code') }}</label>
                <select id="currency" v-model="settings.currency" class="form-control">
                  <option
                    v-for="code in Object.keys(settings.currencies || {}).sort()"
                    :key="code"
                    :value="code"
                  >
                    {{ code }} (
                    {{ (settings.currencies?.[code]?.label || code) }}
                    {{ (settings.currencies?.[code]?.position || 'prefix') === 'suffix'
                      ? t('store.settings.currencySuffix', 'Suffix')
                      : t('store.settings.currencyPrefix', 'Prefix') }}
                    )
                  </option>
                </select>

                <button type="button" class="btn-secondary" style="margin-top: 0.75rem;" @click="showCurrencyModal = true">
                  {{ t('store.settings.manageCurrencies', 'Manage Currencies') }}
                </button>

                <button type="button" class="btn-secondary" style="margin-top: 0.5rem;" @click="showLocationsModal = true">
                  {{ t('store.settings.manageLocations', 'Manage Locations') }}
                </button>
              </div>
            </div>

            <!-- Pricing & Tax Section -->
            <div class="settings-card">
              <h3>{{ t('store.settings.pricing', 'Pricing & Tax') }}</h3>

              <div class="form-field">
                <label for="taxRate" class="form-label">{{ t('store.settings.taxRate', 'Tax Rate (%)') }}</label>
                <input
                  id="taxRate"
                  v-model.number="settings.taxRate"
                  type="number"
                  min="0"
                  max="100"
                  step="0.01"
                  class="form-control"
                  :placeholder="t('store.settings.taxRate', 'Tax Rate (%)')"
                />
                <small class="help-text">{{ t('store.settings.taxRateHelp', 'Tax rate applied to all orders (0-100%)') }}</small>
              </div>
            </div>

            <!-- Shipping & Fulfillment Section -->
            <div class="settings-card">
              <h3>{{ t('store.settings.shipping', 'Shipping & Fulfillment') }}</h3>

              <div class="form-field">
                <label class="checkbox-label">
                  <input
                    id="shippingEnabled"
                    v-model="settings.shippingEnabled"
                    type="checkbox"
                  />
                  <span>{{ t('store.settings.shippingEnabled', 'Enable Shipping') }}</span>
                </label>
                <small class="help-text">{{ t('store.settings.shippingHelp', 'Allow customers to select shipping options during checkout') }}</small>
              </div>
            </div>

            <!-- Payment Methods Section -->
            <div class="settings-card">
              <h3>{{ t('store.settings.payments', 'Payment Methods') }}</h3>

              <div class="form-field">
                <label class="form-label">{{ t('store.settings.paymentMethods', 'Accepted Payment Methods') }}</label>
                <div class="checkbox-group">
                  <label class="checkbox-label">
                    <input
                      v-model="settings.paymentMethods"
                      type="checkbox"
                      value="stripe"
                    />
                    <span>Stripe</span>
                  </label>
                  <label class="checkbox-label">
                    <input
                      v-model="settings.paymentMethods"
                      type="checkbox"
                      value="paypal"
                    />
                    <span>PayPal</span>
                  </label>
                  <label class="checkbox-label">
                    <input
                      v-model="settings.paymentMethods"
                      type="checkbox"
                      value="bank_transfer"
                    />
                    <span>{{ t('store.settings.bankTransfer', 'Bank Transfer') }}</span>
                  </label>
                </div>
                <small class="help-text">{{ t('store.settings.paymentHelp', 'Select which payment methods to accept') }}</small>
              </div>
            </div>
          </div>

          <!-- Save Button -->
          <div class="form-actions" style="margin-top: 2rem; text-align: center;">
            <button type="submit" class="button button-primary" :disabled="saving" style="padding: 0.75rem 2rem; font-size: 1rem;">
              {{ saving ? t('store.saving', 'Saving...') : t('store.save', 'Save Settings') }}
            </button>
          </div>
        </form>
      </div>
    </main>

    <!-- Product Form Modal -->
    <ProductForm
      v-if="showProductForm"
      :product="editingProduct"
      :available-languages="availableLanguages"
      @save="saveProduct"
      @cancel="cancelProductForm"
    />

    <!-- Category Form Modal -->
    <CategoryForm
      v-if="showCategoryForm"
      :category="editingCategory"
      :available-languages="availableLanguages"
      @save="saveCategory"
      @cancel="cancelCategoryForm"
    />

    <!-- Currency Editor Modal -->
    <div v-if="showCurrencyModal" class="modal-overlay" @click="showCurrencyModal = false">
      <div class="modal-content" @click.stop>
        <div class="modal-header">
          <h3>{{ t('store.settings.currencies', 'Currencies') }}</h3>
          <button type="button" class="close-btn" @click="showCurrencyModal = false">&times;</button>
        </div>

        <div class="modal-body">
          <p class="help-text" style="margin-top: 0;">
            {{ t('store.settings.currenciesHelp', 'Manage currency label and whether it is shown before (prefix) or after (suffix) the amount.') }}
          </p>

          <div class="currency-list">
            <div
              v-for="code in Object.keys(settings.currencies || {}).sort()"
              :key="code"
              class="currency-row"
            >
              <div class="currency-code">{{ code }}</div>

              <div class="form-field" style="margin: 0;">
                <label class="form-label">{{ t('store.settings.currencyLabel', 'Label') }}</label>
                <input
                  v-model="settings.currencies[code].label"
                  type="text"
                  class="form-control"
                  :placeholder="t('store.settings.currencyLabel', 'Label')"
                />
              </div>

              <div class="form-field" style="margin: 0;">
                <label class="form-label">{{ t('store.settings.currencyPosition', 'Position') }}</label>
                <select v-model="settings.currencies[code].position" class="form-control">
                  <option value="prefix">{{ t('store.settings.currencyPrefix', 'Prefix') }}</option>
                  <option value="suffix">{{ t('store.settings.currencySuffix', 'Suffix') }}</option>
                </select>
              </div>

              <button
                type="button"
                class="delete-btn"
                style="height: 40px; align-self: end;"
                :disabled="Object.keys(settings.currencies || {}).length <= 1"
                @click="removeCurrency(code)"
              >
                {{ t('store.delete', 'Delete') }}
              </button>
            </div>
          </div>

          <div class="currency-add">
            <h4 style="margin: 1rem 0 0.5rem 0;">{{ t('store.settings.addCurrency', 'Add Currency') }}</h4>
            <div class="currency-row">
              <div class="form-field" style="margin: 0;">
                <label class="form-label">{{ t('store.settings.currencyCode', 'Code') }}</label>
                <input v-model="newCurrencyCode" type="text" class="form-control" placeholder="USD" />
              </div>
              <div class="form-field" style="margin: 0;">
                <label class="form-label">{{ t('store.settings.currencyLabel', 'Label') }}</label>
                <input v-model="newCurrencyLabel" type="text" class="form-control" placeholder="$" />
              </div>
              <div class="form-field" style="margin: 0;">
                <label class="form-label">{{ t('store.settings.currencyPosition', 'Position') }}</label>
                <select v-model="newCurrencyPosition" class="form-control">
                  <option value="prefix">{{ t('store.settings.currencyPrefix', 'Prefix') }}</option>
                  <option value="suffix">{{ t('store.settings.currencySuffix', 'Suffix') }}</option>
                </select>
              </div>
              <button type="button" class="add-btn" style="height: 40px; align-self: end;" @click="addCurrency">
                {{ t('store.add', 'Add') }}
              </button>
            </div>
          </div>
        </div>

        <div class="modal-footer">
          <button type="button" class="add-btn" :disabled="saving" @click="saveSettings">
            {{ saving ? t('store.saving', 'Saving...') : t('store.save', 'Save Settings') }}
          </button>
          <button type="button" class="btn-secondary" @click="showCurrencyModal = false">
            {{ t('store.done', 'Done') }}
          </button>
        </div>
      </div>
    </div>

    <!-- Store Locations Modal -->
    <div v-if="showLocationsModal" class="modal-overlay" @click="showLocationsModal = false">
      <div class="modal-content" @click.stop>
        <div class="modal-header">
          <h3>{{ t('store.settings.locations', 'Store Locations') }}</h3>
          <button type="button" class="close-btn" @click="showLocationsModal = false">&times;</button>
        </div>

        <div class="modal-body">
          <p class="help-text" style="margin-top: 0;">
            {{ t('store.settings.locationsHelp', 'Add your physical store locations for contact purposes. You can reorder them.') }}
          </p>

          <div v-if="(settings.locations || []).length === 0" class="empty-state" style="padding: 0.75rem;">
            {{ t('store.settings.noLocations', 'No locations yet.') }}
          </div>

           <div class="locations-list">
             <div v-for="(loc, idx) in settings.locations" :key="loc.id || idx" class="location-card">
                <div class="location-card-header">
                  <strong>{{ getLocationField(loc, 'name') || t('store.settings.unnamedLocation', 'Unnamed location') }}</strong>
                  <div class="location-actions">
                    <button type="button" class="btn-secondary" @click="moveLocation(idx, -1)" :disabled="selectedSettingsLanguage !== 'en' || idx === 0">
                      {{ t('store.up', 'Up') }}
                    </button>
                    <button type="button" class="btn-secondary" @click="moveLocation(idx, 1)" :disabled="selectedSettingsLanguage !== 'en' || idx === settings.locations.length - 1">
                      {{ t('store.down', 'Down') }}
                    </button>
                    <button type="button" class="btn-danger" @click="removeLocation(idx)" :disabled="selectedSettingsLanguage !== 'en'">
                      {{ t('store.delete', 'Delete') }}
                    </button>
                  </div>
                </div>

               <div class="location-grid">
                 <div class="form-field" style="margin: 0;">
                   <label class="form-label">{{ t('store.settings.locationName', 'Name') }}</label>
                   <input
                     type="text"
                     class="form-control"
                     :value="getLocationField(loc, 'name')"
                     @input="setLocationField(loc, 'name', getEventValue($event))"
                   />
                 </div>

                 <div class="form-field" style="margin: 0;">
                   <label class="form-label">{{ t('store.settings.locationAddress', 'Address') }}</label>
                   <input
                     type="text"
                     class="form-control"
                     :value="getLocationField(loc, 'address')"
                     @input="setLocationField(loc, 'address', getEventValue($event))"
                   />
                 </div>

                 <div class="form-field" style="margin: 0;">
                   <label class="form-label">{{ t('store.settings.locationPhone', 'Phone') }}</label>
                   <input
                     type="text"
                     class="form-control"
                     :value="getLocationField(loc, 'phone')"
                     @input="setLocationField(loc, 'phone', getEventValue($event))"
                   />
                 </div>

                 <div class="form-field" style="margin: 0;">
                   <label class="form-label">{{ t('store.settings.locationEmail', 'Email') }}</label>
                   <input
                     type="email"
                     class="form-control"
                     :value="getLocationField(loc, 'email')"
                     @input="setLocationField(loc, 'email', getEventValue($event))"
                   />
                 </div>

                 <div class="form-field" style="margin: 0; grid-column: 1 / -1;">
                   <label class="form-label">{{ t('store.settings.locationNotes', 'Notes') }}</label>
                   <textarea
                     class="form-control"
                     rows="2"
                     :value="getLocationField(loc, 'notes')"
                     @input="setLocationField(loc, 'notes', getEventValue($event))"
                   ></textarea>
                 </div>
               </div>
             </div>
           </div>

          <button type="button" class="add-btn" style="margin-top: 1rem;" @click="addLocation" :disabled="selectedSettingsLanguage !== 'en'">
            {{ t('store.settings.addLocation', 'Add Location') }}
          </button>
          <p v-if="selectedSettingsLanguage !== 'en'" class="help-text" style="margin-top: 0.75rem;">
            {{ t('store.settings.locationsTranslateHint', 'To add/remove/reorder locations, switch language to English. Other languages edit translations only.') }}
          </p>
        </div>

        <div class="modal-footer">
          <button type="button" class="add-btn" :disabled="saving" @click="saveSettings">
            {{ saving ? t('store.saving', 'Saving...') : t('store.save', 'Save Settings') }}
          </button>
          <button type="button" class="btn-secondary" @click="showLocationsModal = false">
            {{ t('store.done', 'Done') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue';
import { useI18n, i18n } from '@/utils/i18n';
import http from '@/utils/dynamic-http';
import ProductForm from './ProductForm.vue';
import CategoryForm from './CategoryForm.vue';

const { t, currentLanguage } = useI18n();

const activeTab = ref('products');
const products = ref<any[]>([]);
const categories = ref<any[]>([]);
const orders = ref<any[]>([]);
const availableLanguages = ref<string[]>(['en']);
const showProductForm = ref(false);
const showCategoryForm = ref(false);
const editingProduct = ref<any>(null);
const editingCategory = ref<any>(null);

// Settings
type CurrencyPosition = 'prefix' | 'suffix';
type CurrencyFormat = { label: string; position: CurrencyPosition };

const settings = ref<{ 
  storeName: string;
  currency: string;
  currencies: Record<string, CurrencyFormat>;
  locations: Array<{ id: string; name: string; address: string; phone?: string; email?: string; notes?: string }>;
  taxRate: number;
  shippingEnabled: boolean;
  paymentMethods: string[];
}>({
  storeName: 'My Store',
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
  locations: [],
  taxRate: 0,
  shippingEnabled: true,
  paymentMethods: ['stripe']
});

const newCurrencyCode = ref('');
const newCurrencyLabel = ref('');
const newCurrencyPosition = ref<CurrencyPosition>('prefix');
const showCurrencyModal = ref(false);
const showLocationsModal = ref(false);

const addLocation = () => {
  if (!Array.isArray(settings.value.locations)) settings.value.locations = [] as any;
  settings.value.locations.push({
    id: `loc_${Date.now()}_${Math.random().toString(36).slice(2)}`,
    name: '',
    address: '',
    phone: '',
    email: '',
    notes: ''
  });
};

const removeLocation = (index: number) => {
  if (!Array.isArray(settings.value.locations)) return;
  settings.value.locations.splice(index, 1);
};

const moveLocation = (index: number, direction: -1 | 1) => {
  const arr = settings.value.locations;
  if (!Array.isArray(arr)) return;
  const newIndex = index + direction;
  if (newIndex < 0 || newIndex >= arr.length) return;
  const next = [...arr];
  const tmp = next[index];
  next[index] = next[newIndex];
  next[newIndex] = tmp;
  settings.value.locations = next as any;
};

const normalizeCurrencyCode = (code: string) => code.trim().toUpperCase();

const addCurrency = () => {
  const code = normalizeCurrencyCode(newCurrencyCode.value);
  if (!code) return;
  if (!settings.value.currencies) settings.value.currencies = {} as any;
  if (settings.value.currencies[code]) {
    alert(t('store.settings.currencyExists', 'Currency already exists'));
    return;
  }
  const label = (newCurrencyLabel.value || code).trim();
  const position = newCurrencyPosition.value;

  settings.value.currencies = {
    ...settings.value.currencies,
    [code]: { label, position }
  };

  if (!settings.value.currency) settings.value.currency = code;
  newCurrencyCode.value = '';
  newCurrencyLabel.value = '';
  newCurrencyPosition.value = 'prefix';
};

const removeCurrency = (code: string) => {
  if (!settings.value.currencies || !settings.value.currencies[code]) return;
  const keys = Object.keys(settings.value.currencies);
  if (keys.length <= 1) return;

  const next = { ...settings.value.currencies };
  delete next[code];
  settings.value.currencies = next;

  if (settings.value.currency === code) {
    settings.value.currency = Object.keys(settings.value.currencies).sort()[0] || 'USD';
  }
};
const saving = ref(false);
const selectedSettingsLanguage = ref('en');
const settingsTranslations = ref<any[]>([]);

// Per-language overrides for store locations.
// Stored inside settings translations payload as { locationTranslations: { [locationId]: {field: value} } }
const locationTranslations = ref<Record<string, Record<string, any>>>({});

const getLocationField = (loc: any, field: string): string => {
  if (!loc) return ''
  if (selectedSettingsLanguage.value === 'en') return String(loc[field] ?? '')
  const id = String(loc.id || '')
  if (!id) return String(loc[field] ?? '')
  const tr = locationTranslations.value?.[id]?.[field]
  return String(tr ?? loc[field] ?? '')
}

const setLocationField = (loc: any, field: string, value: string) => {
  if (!loc) return
  if (selectedSettingsLanguage.value === 'en') {
    loc[field] = value
    return
  }
  const id = String(loc.id || '')
  if (!id) return
  const current = locationTranslations.value[id] || {}
  locationTranslations.value = {
    ...locationTranslations.value,
    [id]: {
      ...current,
      [field]: value
    }
  }
}

const getEventValue = (event: Event): string => {
  const target = event?.target as (HTMLInputElement | HTMLTextAreaElement | null)
  return (target?.value ?? '').toString()
}


const loadProducts = async () => {
  try {
    const response = await http.get('/api/store/products');
    products.value = response.data.items;
  } catch (error) {
    console.error('Failed to load products:', error);
  }
};

const loadCategories = async () => {
  try {
    const response = await http.get('/api/store/categories');
    categories.value = response.data.items;
  } catch (error) {
    console.error('Failed to load categories:', error);
  }
};

const loadOrders = async () => {
  try {
    const response = await http.get('/api/store/orders');
    orders.value = response.data.items;
  } catch (error) {
    console.error('Failed to load orders:', error);
  }
};

const loadAvailableLanguages = async () => {
  try {
    const response = await http.get('/language/available');
    const languages = response.data.languages || ['en', 'bg'];
    // Ensure 'en' is first
    availableLanguages.value = ['en', ...languages.filter((lang: string) => lang !== 'en')];
  } catch (error) {
    console.error('Failed to fetch available languages:', error);
    availableLanguages.value = ['en', 'bg'];
  }
};

const editProduct = (product: any) => {
  editingProduct.value = product;
  showProductForm.value = true;
};

const saveProduct = async (data: any) => {
  try {
    const { productData, translationsData } = data;
    let savedProduct;

    if (editingProduct.value) {
      // Update existing product
      await http.put(`/api/store/products/${editingProduct.value.id}`, productData);
      savedProduct = { id: editingProduct.value.id, ...productData };
    } else {
      // Create new product
      const response = await http.post('/api/store/products', productData);
      savedProduct = response.data;
    }

    // Save translations for the product
    await saveProductTranslations(savedProduct.id, translationsData);

    await loadProducts();
    showProductForm.value = false;
    editingProduct.value = null;
  } catch (error) {
    console.error('Failed to save product:', error);
  }
};

const saveProductTranslations = async (productId: number, translationsData: any[]) => {
  for (const translation of translationsData) {
    try {
      await http.post(`/api/store/products/${productId}/translations`, {
        language_code: translation.language_code,
        translations: translation.translations
      });
      console.log(`Saved translations for ${translation.language_code}`);
    } catch (error) {
      console.error(`Failed to save translations for ${translation.language_code}:`, error);
    }
  }
};

const deleteProduct = async (productId: number) => {
  if (confirm(t('store.confirmDelete', 'Are you sure you want to delete this product?'))) {
    try {
      await http.delete(`/api/store/products/${productId}`);
      await loadProducts();
    } catch (error) {
      console.error('Failed to delete product:', error);
    }
  }
};

const editCategory = (category: any) => {
  editingCategory.value = category;
  showCategoryForm.value = true;
};

const saveCategory = async (categoryData: any) => {
  try {
    await loadCategories();
    showCategoryForm.value = false;
    editingCategory.value = null;
  } catch (error) {
    console.error('Failed to save category:', error);
  }
};

const deleteCategory = async (categoryId: number) => {
  if (confirm(t('store.confirmDelete', 'Are you sure you want to delete this category?'))) {
    try {
      await http.delete(`/api/store/categories/${categoryId}`);
      await loadCategories();
    } catch (error) {
      console.error('Failed to delete category:', error);
    }
  }
};

const cancelProductForm = () => {
  showProductForm.value = false;
  editingProduct.value = null;
};

const cancelCategoryForm = () => {
  showCategoryForm.value = false;
  editingCategory.value = null;
};

const viewOrder = (orderId: number) => {
  // Navigate to order details
  console.log('View order:', orderId);
};

const loadSettings = async () => {
  await loadSettingsForLanguage();
};

  const loadSettingsForLanguage = async () => {
  try {
    // Load base settings
    const response = await http.get('/api/store/settings');
    let settingsData = { ...settings.value, ...response.data };

     // Reset per-language location overrides by default
     if (selectedSettingsLanguage.value === 'en') {
       locationTranslations.value = {};
     }

    // Ensure currencies exist (backwards compat)
    if (!settingsData.currencies || typeof settingsData.currencies !== 'object') {
      settingsData.currencies = settings.value.currencies;
    }

    // Ensure locations exist (backwards compat)
    if (!Array.isArray((settingsData as any).locations)) {
      (settingsData as any).locations = [];
    }

    // If current language is not English, load translations
    if (selectedSettingsLanguage.value !== 'en') {
      try {
        const translationsResponse = await http.get('/api/store/settings/translations');
        const translations = translationsResponse.data.translations || [];

        // Find translation for selected language
        const currentTranslation = translations.find((t: any) => t.language_code === selectedSettingsLanguage.value);
        if (currentTranslation && currentTranslation.data) {
          // Merge translation with base settings
          settingsData = { ...settingsData, ...currentTranslation.data };

           // Load per-location overrides (do NOT overwrite base locations array)
           locationTranslations.value = currentTranslation.data.locationTranslations || {};
        }
      } catch (translationError) {
        console.warn('Failed to load store settings translations:', translationError);
        // Continue with base settings
        locationTranslations.value = {};
      }
    }

    settings.value = settingsData;
  } catch (error) {
    console.error('Failed to load settings for language:', error);
  }
};

const getLanguageName = (langCode: string) => {
  const uiLang = currentLanguage.value || 'en'
  const languageNamesByUi: Record<string, Record<string, string>> = {
    en: {
      en: 'English',
      bg: 'Bulgarian',
      es: 'Spanish',
      fr: 'French',
      de: 'German',
      it: 'Italian',
      pt: 'Portuguese',
      ru: 'Russian',
      zh: 'Chinese',
      ja: 'Japanese',
      ko: 'Korean'
    },
    bg: {
      en: 'Английски',
      bg: 'Български',
      es: 'Испански',
      fr: 'Френски',
      de: 'Немски',
      it: 'Италиански',
      pt: 'Португалски',
      ru: 'Руски',
      zh: 'Китайски',
      ja: 'Японски',
      ko: 'Корейски'
    }
  }
  return (languageNamesByUi[uiLang]?.[langCode] || languageNamesByUi.en[langCode] || langCode.toUpperCase())
};

const saveSettings = async () => {
  try {
    saving.value = true;
    console.log('Saving settings:', settings.value);

    if (selectedSettingsLanguage.value === 'en') {
      // Save base settings
      const response = await http.put('/api/store/settings', settings.value);
      console.log('Settings saved successfully:', response.data);
    } else {
      // Save translations for non-English languages
      const translations = {
        storeName: settings.value.storeName,
        // per-location translated fields
        locationTranslations: locationTranslations.value
      };

      const response = await http.post('/api/store/settings/translations', {
        language_code: selectedSettingsLanguage.value,
        translations: translations
      });
      console.log('Settings translations saved successfully:', response.data);
    }

    // Also save base settings if they changed (for currency, tax, etc.)
    if (selectedSettingsLanguage.value === 'en') {
      // Already saved above
    } else {
      // Save base settings too (currency, tax, etc. are not translatable)
      const baseSettings = {
        currency: settings.value.currency,
        currencies: settings.value.currencies,
        locations: settings.value.locations,
        taxRate: settings.value.taxRate,
        shippingEnabled: settings.value.shippingEnabled,
        paymentMethods: settings.value.paymentMethods
      };
      await http.put('/api/store/settings', baseSettings);
    }

    // Show success message using a more visible method
    const successMessage = t('store.admin.settingsSaved', 'Settings saved successfully!');
    console.log('Success message:', successMessage);

    // For now, use alert but also log to console
    alert(successMessage);

    // Reload settings to confirm they were saved
    await loadSettingsForLanguage();

  } catch (error: any) {
    console.error('Failed to save settings:', error);
    console.error('Error response:', error.response?.data);
    console.error('Error status:', error.response?.status);

    let errorMessage = t('store.admin.settingsSaveError', 'Failed to save settings. Please try again.');
    if (error.response?.data?.detail) {
      errorMessage += `\n\nDetails: ${error.response.data.detail}`;
    }

    alert(errorMessage);
  } finally {
    saving.value = false;
  }
};

onMounted(async () => {
  await loadAvailableLanguages();

  // Force reload translations to ensure extension translations are loaded
  if (currentLanguage.value !== 'en') {
    console.log('StoreAdmin: Forcing translation reload for', currentLanguage.value);
    await i18n.setLanguage(currentLanguage.value);

    // Debug: Check what translations are available
    setTimeout(() => {
      console.log('StoreAdmin Debug:');
      console.log('store.admin.title:', t('store.admin.title', 'DEFAULT'));
      console.log('store.admin.addCategory:', t('store.admin.addCategory', 'DEFAULT'));
      console.log('store.admin.products:', t('store.admin.products', 'DEFAULT'));
    }, 100);
  }

  loadProducts();
  loadCategories();
  loadOrders();
  loadSettings();
});

// Watch for language changes - translations should be handled by the i18n system
watch(currentLanguage, async (newLanguage) => {
  // The i18n system should automatically load translations when language changes
  console.log('Language changed to:', newLanguage);
});
</script>

<style scoped>
.store-admin {
  max-width: 1200px;
  margin: 0 auto;
  padding: 2rem 1rem;
}

.admin-header {
  margin-bottom: 2rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid var(--card-border, #e3e3e3);
}

.admin-header h1 {
  color: var(--text-primary, #222222);
  margin: 0 0 1rem 0;
}

.admin-nav {
  display: flex;
  gap: 1rem;
}

.admin-nav button {
  padding: 0.5rem 1rem;
  border: 1px solid var(--card-border, #e3e3e3);
  background: var(--card-bg, #ffffff);
  color: var(--text-primary, #222222);
  border-radius: var(--border-radius-md, 8px);
  cursor: pointer;
  transition: all 0.2s ease;
}

.admin-nav button.active,
.admin-nav button:hover {
  background: var(--button-primary-bg, #007bff);
  color: var(--button-primary-text, #ffffff);
  border-color: var(--button-primary-bg, #007bff);
}

.admin-content {
  background: var(--card-bg, #ffffff);
  border: 1px solid var(--card-border, #e3e3e3);
  border-radius: var(--border-radius-lg, 12px);
  padding: 2rem;
}

.admin-section {
  min-height: 400px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2rem;
}

.section-header h2 {
  color: var(--text-primary, #222222);
  margin: 0;
}

.add-btn {
  padding: 0.75rem 1.5rem;
  background: var(--button-primary-bg, #007bff);
  color: var(--button-primary-text, #ffffff);
  border: none;
  border-radius: var(--border-radius-md, 8px);
  font-weight: 500;
  cursor: pointer;
  transition: background-color 0.2s ease;
}

.add-btn:hover {
  background: var(--button-primary-hover, #0056b3);
}

.products-list, .categories-list, .orders-list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.product-item, .category-item, .order-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  border: 1px solid var(--card-border, #e3e3e3);
  border-radius: var(--border-radius-md, 8px);
  background: var(--card-bg, #ffffff);
}

.product-info, .category-info, .order-info {
  flex: 1;
}

.product-info h3, .category-info h3, .order-info h3 {
  margin: 0 0 0.5rem 0;
  color: var(--text-primary, #222222);
}

.product-info p, .category-info p, .order-info p {
  margin: 0 0 0.5rem 0;
  color: var(--text-secondary, #666666);
}

.product-actions, .category-actions, .order-actions {
  display: flex;
  gap: 0.5rem;
}

.edit-btn, .delete-btn, .view-btn {
  padding: 0.5rem 1rem;
  border: none;
  border-radius: var(--border-radius-sm, 4px);
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.edit-btn {
  background: var(--button-secondary-bg, #6c757d);
  color: var(--button-secondary-text, #ffffff);
}

.edit-btn:hover {
  background: var(--button-secondary-hover, #545b62);
}

.delete-btn {
  background: var(--error-bg, #dc3545);
  color: var(--error-text, #ffffff);
}

.delete-btn:hover {
  background: var(--error-hover, #c82333);
}

.view-btn {
  background: var(--link-color, #007bff);
  color: var(--button-primary-text, #ffffff);
}

.view-btn:hover {
  background: var(--button-primary-hover, #0056b3);
}

.out-of-stock {
  color: var(--error-bg, #dc3545);
  font-weight: 600;
}

/* Settings specific styles */
.settings-form {
  margin-top: 1rem;
}

/* Reusable buttons (theme-aware) */
.btn-secondary {
  padding: 0.5rem 1rem;
  background: var(--button-secondary-bg, #6c757d);
  color: var(--button-secondary-text, #ffffff);
  border: 1px solid var(--button-secondary-bg, #6c757d);
  border-radius: var(--border-radius-md, 8px);
  cursor: pointer;
  font-weight: 500;
  transition: all 0.2s ease;
}

.btn-secondary:hover {
  background: var(--button-secondary-hover, #545b62);
}

.btn-secondary:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.btn-danger {
  padding: 0.5rem 1rem;
  background: var(--button-danger-bg, #dc3545);
  color: var(--button-danger-text, #ffffff);
  border: 1px solid var(--button-danger-bg, #dc3545);
  border-radius: var(--border-radius-md, 8px);
  cursor: pointer;
  font-weight: 500;
  transition: all 0.2s ease;
}

.btn-danger:hover {
  background: var(--button-danger-hover, #c82333);
  border-color: var(--button-danger-hover, #c82333);
}

/* Generic modal (used for currency editor) */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: var(--modal-backdrop, rgba(0, 0, 0, 0.6));
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
}

.modal-content {
  background: var(--bg-primary, var(--card-bg, #ffffff));
  border-radius: var(--border-radius-lg, 12px);
  width: 90%;
  max-width: 900px;
  max-height: 90vh;
  overflow: auto;
  border: 1px solid var(--border-color, var(--card-border, #e3e3e3));
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.25);
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--border-color, var(--card-border, #e3e3e3));
}

.modal-header h3 {
  margin: 0;
}

.modal-body {
  padding: 1rem 1.25rem;
}

.modal-footer {
  padding: 1rem 1.25rem;
  border-top: 1px solid var(--border-color, var(--card-border, #e3e3e3));
  display: flex;
  justify-content: flex-end;
}

.close-btn {
  background: none;
  border: none;
  font-size: 1.75rem;
  line-height: 1;
  cursor: pointer;
  color: var(--text-secondary, #666666);
}

.close-btn:hover {
  color: var(--text-primary, #222222);
}

.currency-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin-top: 1rem;
}

.empty-state {
  border: 1px dashed var(--border-color, #e3e3e3);
  border-radius: var(--border-radius-md, 8px);
  color: var(--text-secondary, #666666);
  background: var(--bg-secondary, rgba(0, 0, 0, 0.03));
}

.locations-list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.location-card {
  border: 1px solid var(--border-color, #e3e3e3);
  border-radius: var(--border-radius-lg, 12px);
  background: var(--bg-secondary, rgba(0, 0, 0, 0.02));
  padding: 1rem;
}

.location-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 0.75rem;
  color: var(--text-primary, #222222);
}

.location-actions {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.location-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
}

.currency-row {
  display: grid;
  grid-template-columns: 80px 1fr 1fr auto;
  gap: 0.75rem;
  align-items: end;
  padding: 0.75rem;
  border: 1px solid var(--card-border, #e3e3e3);
  border-radius: var(--border-radius-md, 8px);
  background: var(--bg-secondary, rgba(0, 0, 0, 0.02));
}

.currency-code {
  font-weight: 700;
  color: var(--text-primary, #222222);
  align-self: center;
}

.currency-add .currency-row {
  background: transparent;
}

.checkbox-group {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  font-weight: normal;
}

.checkbox-label input[type="checkbox"] {
  width: 16px;
  height: 16px;
  margin: 0;
  accent-color: var(--button-primary-bg, #007bff);
  cursor: pointer;
}

.checkbox-label span {
  color: var(--text-primary, #222222);
}

/* Form actions */
.form-actions {
  display: flex;
  justify-content: center;
  gap: 1rem;
  margin-top: 2rem;
}

/* Responsive Design */
@media (max-width: 768px) {
  .store-admin {
    padding: 1rem 0.5rem;
  }

  .admin-nav {
    flex-wrap: wrap;
  }

  .section-header {
    flex-direction: column;
    gap: 1rem;
    text-align: center;
  }

  .product-item, .category-item, .order-item {
    flex-direction: column;
    gap: 1rem;
    text-align: center;
  }

  .product-actions, .category-actions, .order-actions {
    justify-content: center;
  }

  .settings-grid {
    grid-template-columns: 1fr;
    gap: 1rem;
  }

  .currency-row {
    grid-template-columns: 1fr;
  }

  .location-grid {
    grid-template-columns: 1fr;
  }

  .form-actions {
    flex-direction: column;
  }

  .checkbox-group {
    gap: 1rem;
  }
}
</style>
