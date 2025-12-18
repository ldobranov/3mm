<script setup lang="ts">
import { ref, onMounted, watch, computed, defineAsyncComponent } from 'vue';
import { useRoute } from 'vue-router';
import { useI18n } from '@/utils/i18n';
import http from '@/utils/dynamic-http';
import { extensionRelationships } from '@/utils/extension-relationships';

// Dynamically load ProductCard from StoreExtension using extension relationships
const ProductCard = ref(null);

const loadProductCard = async () => {
  if (!ProductCard.value) {
    ProductCard.value = await extensionRelationships.getComponent('StoreExtension', 'ProductCard');
    console.log('ProductCard component loaded for PageView');
  }
};

const route = useRoute();
const { currentLanguage } = useI18n();

// Store settings (used for product card currency)
const storeCurrency = ref('USD');
const storeCurrencyFormats = ref<Record<string, { label: string; position: 'prefix' | 'suffix' }>>({});

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

interface Page {
  title: string;
  content: string;
}

interface ContentBlock {
  type: 'html' | 'product' | 'embedded_product';
  content: string;
  productId?: string | null;
  productData?: any;
}

const page = ref<Page | null>(null);
const loading = ref(true);
const error = ref<string | null>(null);

// Prevent races when language switches during initial load (or rapid toggles)
let loadPageRequestId = 0;

const loadPage = async () => {
  try {
    loading.value = true;
    error.value = null;

    const requestId = ++loadPageRequestId;
    const language = currentLanguage.value;

    const slug = route.params.slug as string;
    // Use the new endpoint that supports translations
    const response = await http.get(`/api/pages/by-slug/${slug}`, {
      params: { language }
    });

    // Ignore stale responses
    if (requestId !== loadPageRequestId) return;

    page.value = response.data;

    // Load product data for any embedded products
    await loadProductData(language);
  } catch (err: any) {
    error.value = err.response?.data?.detail || 'Page not found';
  } finally {
    loading.value = false;
  }
};

// Parse content to separate HTML and product components
const parsedContent = computed(() => {
  if (!page.value?.content) return [];

  const blocks: ContentBlock[] = [];
  let content = page.value.content;

  // Fix double /uploads/store/ paths in the content
  content = content.replace(/\/uploads\/store\/\/uploads\/store\//g, '/uploads/store/');

  // Parse embedded product HTML
  const productRegex = /<div class="embedded-product"[^>]*>([\s\S]*?)<\/div>/g;
  let lastIndex = 0;
  let match;

  while ((match = productRegex.exec(content)) !== null) {
    // Add HTML before the product
    if (match.index > lastIndex) {
      const htmlContent = content.substring(lastIndex, match.index);
      if (htmlContent.trim()) {
        blocks.push({
          type: 'html',
          content: htmlContent
        });
      }
    }

    // Extract product info from the embedded HTML
    const productHtml = match[0]; // Full match including the div tag
    const productIdMatch = productHtml.match(/data-product-id="([^"]+)"/);

    if (productIdMatch) {
      // Product ID found in data attribute - use it directly
      const productId = productIdMatch[1];

      blocks.push({
        type: 'embedded_product',
        content: match[0], // Keep original HTML as fallback
        productId: productId,
        productData: {
          id: productId,
          // Mark as needing translation - will be populated by loadProductData
          needsTranslation: true
        }
      });
    } else {
      // Fallback for old embedded products without data-product-id
      const titleMatch = productHtml.match(/<h3[^>]*>([^<]+)<\/h3>/);
      // Extract the first <p> after </h3> as price (supports any currency prefix/suffix)
      const priceTextMatch = productHtml.match(/<\/h3>\s*<p[^>]*>([^<]+)<\/p>/);
      const skuMatch = productHtml.match(/SKU:\s*([^<]+)/);
      const descMatch = productHtml.match(/<p[^>]*>([^<]+)<\/p>\s*$/);
      const imgMatch = productHtml.match(/<img[^>]+src="([^"]+)"/);

      if (titleMatch) {
        // Try to find product by name/SKU to get the actual product ID
        const productName = titleMatch[1].trim();
        const sku = skuMatch ? skuMatch[1].trim() : '';

        // Create a block that will be populated with real product data
        blocks.push({
          type: 'embedded_product',
          content: match[0], // Keep original HTML as fallback
          productId: null,
          productData: {
            id: Date.now() + Math.random(), // Temporary ID
            name: productName,
            price: (() => {
              const priceText = priceTextMatch ? priceTextMatch[1] : '';
              const numeric = priceText.match(/([0-9]+(?:[\.,][0-9]{1,2})?)/);
              if (!numeric) return 0;
              return parseFloat(numeric[1].replace(',', '.'));
            })(),
            stock_quantity: 1,
            images: imgMatch ? [imgMatch[1]] : [],
            sku: sku,
            description: descMatch ? descMatch[1] : '',
            // Mark as needing translation
            needsTranslation: true
          }
        });
      }
    }

    lastIndex = match.index + match[0].length;
  }

  // Add remaining HTML
  if (lastIndex < content.length) {
    const remainingContent = content.substring(lastIndex);
    if (remainingContent.trim()) {
      blocks.push({
        type: 'html',
        content: remainingContent
      });
    }
  }

  return blocks;
});

// Load product data for all product blocks
const loadProductData = async (language: string = currentLanguage.value) => {
  const embeddedProductBlocks = parsedContent.value.filter(block => block.type === 'embedded_product');
  if (embeddedProductBlocks.length === 0) return;

  // Load product data for each embedded product block
  const loadPromises = embeddedProductBlocks.map(async (block) => {
    if (block.productData?.needsTranslation) {
      try {
        let matchedProduct = null;

        // If we have a product ID from the data attribute, use it directly
        if (block.productId) {
          try {
            const productResponse = await http.get(`/api/store/products/${block.productId}`, {
              params: { language }
            });
            block.productData = productResponse.data;
            console.log(`Loaded translated product by ID: ${block.productData.name} (${language})`);
            console.log('Product data:', block.productData);
            return;
          } catch (error) {
            console.warn(`Could not load product by ID ${block.productId}, falling back to matching:`, error);
          }
        }

        // Fallback: Get all products and find the best match (for legacy embedded products)
        const allProductsResponse = await http.get('/api/store/products', {
          params: {
            limit: 100, // Get more products to find matches
            language
          }
        });

        const allProducts = allProductsResponse.data.items || [];

        // Try different matching strategies
        if (block.productData.sku) {
          // Exact SKU match (most reliable)
          matchedProduct = allProducts.find((p: any) => p.sku === block.productData.sku);
        }

        if (!matchedProduct && block.productData.name) {
          // Name match - try exact match first
          matchedProduct = allProducts.find((p: any) =>
            p.name.toLowerCase() === block.productData.name.toLowerCase()
          );

          // If no exact match, try partial match
          if (!matchedProduct) {
            matchedProduct = allProducts.find((p: any) =>
              p.name.toLowerCase().includes(block.productData.name.toLowerCase()) ||
              block.productData.name.toLowerCase().includes(p.name.toLowerCase())
            );
          }
        }

        if (matchedProduct) {
          // Get full product details with translations
          const productResponse = await http.get(`/api/store/products/${matchedProduct.id}`, {
            params: { language }
          });
          block.productData = productResponse.data;
          console.log(`Loaded translated product by matching: ${block.productData.name} (${language})`);
          console.log('Product data:', block.productData);
        } else {
          console.warn(`Could not find matching product for: ${block.productData.name} (SKU: ${block.productData.sku})`);
          // Keep the extracted data but mark as untranslated
          delete block.productData.needsTranslation;
        }
      } catch (error) {
        console.error(`Error loading product data for ${block.productData?.name}:`, error);
        // Keep the extracted data
        delete block.productData.needsTranslation;
      }
    }
  });

  await Promise.all(loadPromises);
};

const handleAddToCart = (product: any) => {
  // Handle add to cart functionality
  console.log('Add to cart:', product);
  // You could emit an event or call a cart API here
};

onMounted(async () => {
  await loadProductCard();
  await loadStoreSettings();
  loadPage();
});

// Watch for language changes and reload page with new language
watch(currentLanguage, async () => {
  await loadPage();
});
</script>

<template>
  <div class="page-view">
    <div v-if="loading" class="loading">
      Loading page...
    </div>

    <div v-else-if="error" class="error">
      {{ error }}
    </div>

    <div v-else-if="page" class="page-content">
      <h1>{{ page.title }}</h1>
      <div class="content">
        <template v-for="(block, index) in parsedContent" :key="index">
          <div v-if="block.type === 'html'" v-html="block.content"></div>
          <component
             v-else-if="block.type === 'embedded_product' && block.productData && ProductCard"
             :is="ProductCard"
             :product="block.productData"
             :currency="storeCurrency"
             :currency-formats="storeCurrencyFormats"
             @add-to-cart="handleAddToCart"
             :key="`${block.productData.id}-${currentLanguage}`"
           />
        </template>
      </div>
    </div>

    <div v-else class="not-found">
      Page not found
    </div>
  </div>
</template>

<style scoped>
.page-view {
  max-width: 800px;
  margin: 0 auto;
  padding: 2rem;
}

.loading, .error, .not-found {
  text-align: center;
  padding: 2rem;
  color: var(--text-secondary);
}

.error {
  color: var(--error-text);
}

.page-content h1 {
  color: var(--text-primary);
  margin-bottom: 1rem;
  font-size: 2rem;
}

.content {
  color: var(--text-primary);
  line-height: 1.6;
}

.content :deep(p) {
  margin-bottom: 1rem;
}

.content :deep(h2) {
  color: var(--text-primary);
  margin: 1.5rem 0 0.5rem 0;
  font-size: 1.5rem;
}

.content :deep(h3) {
  color: var(--text-primary);
  margin: 1.25rem 0 0.5rem 0;
  font-size: 1.25rem;
}

.content :deep(ul), .content :deep(ol) {
  margin-bottom: 1rem;
  padding-left: 2rem;
}

.content :deep(li) {
  margin-bottom: 0.25rem;
}

.content :deep(a) {
  color: var(--link-color);
  text-decoration: none;
}

.content :deep(a:hover) {
  text-decoration: underline;
}
</style>
