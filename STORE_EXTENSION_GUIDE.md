# Store Extension Development Guide

## Overview

This guide provides specific instructions for creating e-commerce/store extensions similar to OpenCart, WooCommerce, or Magento. Store extensions are complex extensions that manage products, categories, orders, customers, and provide shopping cart functionality.

## Store Extension Architecture

A typical store extension includes:

### Core Features
- **Product Management**: CRUD operations for products with variants, images, descriptions
- **Category Management**: Hierarchical product categories
- **Order Management**: Order processing, status tracking, payment integration
- **Customer Management**: Customer accounts, addresses, order history
- **Shopping Cart**: Add to cart, checkout process, cart persistence
- **Payment Integration**: Payment gateway support
- **Shipping**: Shipping methods, rates, calculations
- **Inventory Management**: Stock tracking, low stock alerts
- **Admin Dashboard**: Sales reports, analytics, order management

### Database Schema Structure

```json
{
  "tables": {
    "store_products": {
      "columns": {
        "id": {"type": "integer", "primary": true, "auto_increment": true},
        "sku": {"type": "text", "nullable": false, "unique": true},
        "name": {"type": "text", "nullable": false},
        "description": {"type": "text"},
        "short_description": {"type": "text"},
        "price": {"type": "float", "nullable": false},
        "sale_price": {"type": "float"},
        "cost_price": {"type": "float"},
        "stock_quantity": {"type": "integer", "default": 0},
        "stock_status": {"type": "text", "default": "in_stock"},
        "weight": {"type": "float"},
        "dimensions": {"type": "json"},
        "images": {"type": "json"},
        "categories": {"type": "json"},
        "tags": {"type": "json"},
        "attributes": {"type": "json"},
        "variants": {"type": "json"},
        "is_active": {"type": "boolean", "default": true},
        "is_featured": {"type": "boolean", "default": false},
        "created_at": {"type": "timestamp", "default": "CURRENT_TIMESTAMP"},
        "updated_at": {"type": "timestamp", "default": "CURRENT_TIMESTAMP"}
      }
    },
    "store_categories": {
      "columns": {
        "id": {"type": "integer", "primary": true, "auto_increment": true},
        "name": {"type": "text", "nullable": false},
        "slug": {"type": "text", "nullable": false, "unique": true},
        "description": {"type": "text"},
        "parent_id": {"type": "integer"},
        "image": {"type": "text"},
        "sort_order": {"type": "integer", "default": 0},
        "is_active": {"type": "boolean", "default": true}
      }
    },
    "store_orders": {
      "columns": {
        "id": {"type": "integer", "primary": true, "auto_increment": true},
        "order_number": {"type": "text", "nullable": false, "unique": true},
        "customer_id": {"type": "integer"},
        "status": {"type": "text", "default": "pending"},
        "subtotal": {"type": "float", "nullable": false},
        "tax_amount": {"type": "float", "default": 0},
        "shipping_amount": {"type": "float", "default": 0},
        "discount_amount": {"type": "float", "default": 0},
        "total_amount": {"type": "float", "nullable": false},
        "currency": {"type": "text", "default": "USD"},
        "billing_address": {"type": "json"},
        "shipping_address": {"type": "json"},
        "payment_method": {"type": "text"},
        "shipping_method": {"type": "text"},
        "notes": {"type": "text"},
        "created_at": {"type": "timestamp", "default": "CURRENT_TIMESTAMP"},
        "updated_at": {"type": "timestamp", "default": "CURRENT_TIMESTAMP"}
      }
    },
    "store_order_items": {
      "columns": {
        "id": {"type": "integer", "primary": true, "auto_increment": true},
        "order_id": {"type": "integer", "nullable": false},
        "product_id": {"type": "integer", "nullable": false},
        "product_name": {"type": "text", "nullable": false},
        "product_sku": {"type": "text"},
        "quantity": {"type": "integer", "nullable": false},
        "unit_price": {"type": "float", "nullable": false},
        "total_price": {"type": "float", "nullable": false},
        "variant_data": {"type": "json"}
      }
    },
    "store_customers": {
      "columns": {
        "id": {"type": "integer", "primary": true, "auto_increment": true},
        "user_id": {"type": "integer"},
        "email": {"type": "text", "nullable": false},
        "first_name": {"type": "text"},
        "last_name": {"type": "text"},
        "phone": {"type": "text"},
        "billing_address": {"type": "json"},
        "shipping_address": {"type": "json"},
        "is_active": {"type": "boolean", "default": true},
        "created_at": {"type": "timestamp", "default": "CURRENT_TIMESTAMP"}
      }
    },
    "store_cart": {
      "columns": {
        "id": {"type": "integer", "primary": true, "auto_increment": true},
        "session_id": {"type": "text", "nullable": false},
        "user_id": {"type": "integer"},
        "items": {"type": "json"},
        "created_at": {"type": "timestamp", "default": "CURRENT_TIMESTAMP"},
        "updated_at": {"type": "timestamp", "default": "CURRENT_TIMESTAMP"}
      }
    }
  }
}
```

## Manifest Configuration

```json
{
  "name": "StoreExtension",
  "version": "1.0.0",
  "type": "extension",
  "description": "Full-featured e-commerce store with products, orders, and payments",
  "author": "Your Name",
  "backend_entry": "store_extension.py",
  "frontend_entry": "StoreFront.vue",
  "frontend_editor": "StoreAdmin.vue",
  "frontend_components": [
    "ProductCard.vue",
    "CartWidget.vue",
    "CheckoutForm.vue",
    "OrderHistory.vue"
  ],
  "frontend_routes": [
    {
      "path": "/store",
      "component": "StoreFront.vue",
      "name": "Store",
      "meta": {"requiresAuth": false}
    },
    {
      "path": "/store/product/:slug",
      "component": "ProductDetail.vue",
      "name": "ProductDetail",
      "props": true
    },
    {
      "path": "/store/cart",
      "component": "ShoppingCart.vue",
      "name": "Cart",
      "meta": {"requiresAuth": false}
    },
    {
      "path": "/store/checkout",
      "component": "CheckoutForm.vue",
      "name": "Checkout",
      "meta": {"requiresAuth": true}
    },
    {
      "path": "/store/admin",
      "component": "StoreAdmin.vue",
      "name": "StoreAdmin",
      "meta": {"requiresAuth": true, "requiresRole": "admin"}
    }
  ],
  "locales": {
    "supported": ["en", "bg", "es"],
    "default": "en",
    "directory": "locales/"
  },
  "multilingual": {
    "content_fields": ["name", "description", "short_description"],
    "fallback_language": "en"
  },
  "permissions": ["database_read", "database_write", "file_upload"],
  "config_schema": {
    "type": "object",
    "properties": {
      "storeName": {
        "type": "string",
        "title": "Store Name",
        "default": "My Store"
      },
      "currency": {
        "type": "string",
        "title": "Currency Code",
        "default": "USD"
      },
      "taxRate": {
        "type": "number",
        "title": "Tax Rate (%)",
        "default": 0
      },
      "shippingEnabled": {
        "type": "boolean",
        "title": "Enable Shipping",
        "default": true
      },
      "paymentMethods": {
        "type": "array",
        "title": "Payment Methods",
        "items": {
          "type": "string",
          "enum": ["stripe", "paypal", "bank_transfer"]
        },
        "default": ["stripe"]
      }
    }
  }
}
```

## Backend Implementation

### Critical: Database Transaction Issues

**Major Issue Discovered**: The extension database context has transaction commit problems. INSERT RETURNING queries don't commit properly, causing data to be "inserted" but not visible in subsequent SELECT queries.

**Solution**: Use a custom `execute_main_db_query` function that always commits:

```python
def execute_main_db_query(query: str, params: dict = None):
    """Execute query using main database session with proper commits"""
    db = next(get_db())
    try:
        result = db.execute(text(query), params or {})
        rows = []
        if result.returns_rows:
            for row in result.fetchall():
                rows.append(dict(row))
        db.commit()  # Always commit after execution
        return rows
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()
```

**Use this function for all CRUD operations** instead of `context.execute_query` to ensure data persistence.

### PostgreSQL-Specific Issues

**Table Name Quoting**: Always quote table names in queries:
```python
# Wrong:
f"SELECT * FROM {table_name}"

# Correct:
f'SELECT * FROM "{table_name}"'
```

**Column Auto-increment**: Use `SERIAL` for PostgreSQL:
```sql
-- Correct for PostgreSQL:
id SERIAL PRIMARY KEY
```

### Core Store Backend Structure

```python
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from backend.utils.auth_dep import require_user
from backend.db.base import get_db
from typing import List, Optional
import json
from datetime import datetime

def initialize_extension(context):
    """Initialize the store extension"""
    try:
        # Table names
        products_table = "ext_StoreExtension_products"
        categories_table = "ext_StoreExtension_categories"
        orders_table = "ext_StoreExtension_orders"
        order_items_table = "ext_StoreExtension_order_items"
        customers_table = "ext_StoreExtension_customers"
        cart_table = "ext_StoreExtension_cart"

        router = APIRouter(prefix="/api/store")

        # Product Management
        @router.get("/products")
        def get_products(
            category: Optional[str] = None,
            search: Optional[str] = None,
            limit: int = 20,
            offset: int = 0
        ):
            """Get products with filtering"""
            query = f"SELECT * FROM {products_table} WHERE is_active = true"
            params = {}

            if category:
                query += " AND categories::text LIKE :category"
                params["category"] = f"%{category}%"

            if search:
                query += " AND (name ILIKE :search OR description ILIKE :search)"
                params["search"] = f"%{search}%"

            query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
            params.update({"limit": limit, "offset": offset})

            result = context.execute_query(query, params)
            return {"items": result, "total": len(result)}

        @router.get("/products/{product_id}")
        def get_product(product_id: int):
            """Get single product"""
            result = context.execute_query(
                f"SELECT * FROM {products_table} WHERE id = :id AND is_active = true",
                {"id": product_id}
            )
            if not result:
                raise HTTPException(status_code=404, detail="Product not found")
            return result[0]

        @router.post("/products")
        def create_product(product: dict, claims: dict = Depends(require_user)):
            """Create new product"""
            # Validate required fields
            if not product.get("name") or not product.get("price"):
                raise HTTPException(status_code=400, detail="Name and price are required")

            result = context.execute_query(f"""
                INSERT INTO {products_table}
                (sku, name, description, short_description, price, sale_price, stock_quantity, categories, images)
                VALUES (:sku, :name, :description, :short_description, :price, :sale_price, :stock_quantity, :categories, :images)
                RETURNING id
            """, {
                "sku": product.get("sku", ""),
                "name": product["name"],
                "description": product.get("description", ""),
                "short_description": product.get("short_description", ""),
                "price": product["price"],
                "sale_price": product.get("sale_price"),
                "stock_quantity": product.get("stock_quantity", 0),
                "categories": json.dumps(product.get("categories", [])),
                "images": json.dumps(product.get("images", []))
            })

            return {"id": result[0]["id"], "message": "Product created successfully"}

        # Cart Management
        @router.get("/cart")
        def get_cart(session_id: str):
            """Get cart contents"""
            result = context.execute_query(
                f"SELECT items FROM {cart_table} WHERE session_id = :session_id",
                {"session_id": session_id}
            )
            return {"items": result[0]["items"] if result else []}

        @router.post("/cart/add")
        def add_to_cart(item: dict, session_id: str):
            """Add item to cart"""
            # Get existing cart or create new one
            cart_result = context.execute_query(
                f"SELECT id, items FROM {cart_table} WHERE session_id = :session_id",
                {"session_id": session_id}
            )

            if cart_result:
                cart_id = cart_result[0]["id"]
                current_items = cart_result[0]["items"] or []
            else:
                # Create new cart
                cart_insert = context.execute_query(f"""
                    INSERT INTO {cart_table} (session_id, items)
                    VALUES (:session_id, :items)
                    RETURNING id
                """, {"session_id": session_id, "items": []})
                cart_id = cart_insert[0]["id"]
                current_items = []

            # Add/update item in cart
            item_found = False
            for cart_item in current_items:
                if (cart_item["product_id"] == item["product_id"] and
                    cart_item.get("variant_data") == item.get("variant_data")):
                    cart_item["quantity"] += item["quantity"]
                    item_found = True
                    break

            if not item_found:
                current_items.append(item)

            # Update cart
            context.execute_query(f"""
                UPDATE {cart_table}
                SET items = :items, updated_at = CURRENT_TIMESTAMP
                WHERE id = :cart_id
            """, {"items": current_items, "cart_id": cart_id})

            return {"message": "Item added to cart", "cart_count": len(current_items)}

        # Order Management
        @router.post("/orders")
        def create_order(order_data: dict, claims: dict = Depends(require_user)):
            """Create new order"""
            user_id = claims.get("user_id")

            # Generate order number
            order_number = f"ORD-{datetime.now().strftime('%Y%m%d')}-{user_id}"

            # Calculate totals
            subtotal = order_data["subtotal"]
            tax_amount = subtotal * 0.1  # 10% tax
            shipping_amount = order_data.get("shipping_amount", 0)
            total_amount = subtotal + tax_amount + shipping_amount

            # Create order
            order_result = context.execute_query(f"""
                INSERT INTO {orders_table}
                (order_number, customer_id, subtotal, tax_amount, shipping_amount, total_amount,
                 billing_address, shipping_address, payment_method, shipping_method)
                VALUES (:order_number, :customer_id, :subtotal, :tax_amount, :shipping_amount, :total_amount,
                        :billing_address, :shipping_address, :payment_method, :shipping_method)
                RETURNING id
            """, {
                "order_number": order_number,
                "customer_id": user_id,
                "subtotal": subtotal,
                "tax_amount": tax_amount,
                "shipping_amount": shipping_amount,
                "total_amount": total_amount,
                "billing_address": json.dumps(order_data["billing_address"]),
                "shipping_address": json.dumps(order_data["shipping_address"]),
                "payment_method": order_data["payment_method"],
                "shipping_method": order_data.get("shipping_method", "standard")
            })

            order_id = order_result[0]["id"]

            # Create order items
            for item in order_data["items"]:
                context.execute_query(f"""
                    INSERT INTO {order_items_table}
                    (order_id, product_id, product_name, product_sku, quantity, unit_price, total_price, variant_data)
                    VALUES (:order_id, :product_id, :product_name, :product_sku, :quantity, :unit_price, :total_price, :variant_data)
                """, {
                    "order_id": order_id,
                    "product_id": item["product_id"],
                    "product_name": item["name"],
                    "product_sku": item.get("sku", ""),
                    "quantity": item["quantity"],
                    "unit_price": item["price"],
                    "total_price": item["quantity"] * item["price"],
                    "variant_data": json.dumps(item.get("variant_data", {}))
                })

                # Update product stock
                context.execute_query(f"""
                    UPDATE {products_table}
                    SET stock_quantity = stock_quantity - :quantity
                    WHERE id = :product_id
                """, {"quantity": item["quantity"], "product_id": item["product_id"]})

            # Clear cart
            context.execute_query(
                f"DELETE FROM {cart_table} WHERE session_id = :session_id",
                {"session_id": order_data.get("session_id")}
            )

            return {
                "order_id": order_id,
                "order_number": order_number,
                "total_amount": total_amount,
                "message": "Order created successfully"
            }

        context.register_router(router)

        return {
            "routes_registered": 6,
            "tables_created": 6,
            "status": "initialized"
        }

    except Exception as e:
        print(f"Store extension initialization error: {e}")
        return {"status": "error", "error": str(e)}
```

## Frontend Components

### Store Front Component

```vue
<template>
  <div class="store-container">
    <header class="store-header">
      <h1>{{ storeSettings.storeName || t('store.title', 'Store') }}</h1>
      <div class="cart-widget">
        <router-link to="/store/cart" class="cart-link">
          🛒 {{ cartCount }} items
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
          @add-to-cart="addToCart"
        />
      </div>

      <div v-if="loading" class="loading">
        {{ t('store.loading', 'Loading products...') }}
      </div>

      <div v-if="!loading && products.length === 0" class="no-products">
        {{ t('store.noProducts', 'No products found') }}
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import { useRoute } from 'vue-router';
import { useI18n } from '@/utils/i18n';
import http from '@/utils/dynamic-http';
import ProductCard from './ProductCard.vue';

const { t } = useI18n();
const route = useRoute();

const products = ref([]);
const categories = ref([]);
const loading = ref(false);
const cartCount = ref(0);

const storeSettings = computed(() => {
  // Get store settings from settings store
  return {}; // Implement settings loading
});

const loadProducts = async () => {
  loading.value = true;
  try {
    const params = {};
    if (route.query.category) params.category = route.query.category;
    if (route.query.search) params.search = route.query.search;

    const response = await http.get('/api/store/products', { params });
    products.value = response.data.items;
  } catch (error) {
    console.error('Failed to load products:', error);
  } finally {
    loading.value = false;
  }
};

const addToCart = async (product: any) => {
  try {
    await http.post('/api/store/cart/add', {
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

onMounted(() => {
  loadProducts();
  // Load cart count
});
</script>
```

### Product Card Component

```vue
<template>
  <div class="product-card">
    <div class="product-image">
      <img
        :src="product.images?.[0] || '/placeholder-product.jpg'"
        :alt="product.name"
        @error="handleImageError"
      />
      <div v-if="product.sale_price" class="sale-badge">SALE</div>
    </div>

    <div class="product-info">
      <h3 class="product-name">{{ product.name }}</h3>
      <p class="product-price">
        <span v-if="product.sale_price" class="original-price">${{ product.price }}</span>
        <span class="current-price">${{ product.sale_price || product.price }}</span>
      </p>

      <div class="product-actions">
        <button @click="$emit('add-to-cart', product)" class="add-to-cart-btn">
          {{ t('store.addToCart', 'Add to Cart') }}
        </button>
        <router-link :to="`/store/product/${product.slug || product.id}`" class="view-details-btn">
          {{ t('store.viewDetails', 'View Details') }}
        </router-link>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from '@/utils/i18n';

const { t } = useI18n();

defineProps<{
  product: {
    id: number;
    name: string;
    price: number;
    sale_price?: number;
    images?: string[];
    slug?: string;
  };
}>();

defineEmits<{
  'add-to-cart': [product: any];
}>();

const handleImageError = (event: Event) => {
  const img = event.target as HTMLImageElement;
  img.src = '/placeholder-product.jpg';
};
</script>
```

## Key Features Implementation

### 1. Product Variants
```json
{
  "variants": [
    {
      "id": "size-m-color-blue",
      "attributes": {"size": "M", "color": "Blue"},
      "price_modifier": 0,
      "stock_quantity": 10,
      "sku": "TSHIRT-M-BLUE"
    }
  ]
}
```

### 2. Payment Integration
```python
@router.post("/payment/process")
def process_payment(payment_data: dict, claims: dict = Depends(require_user)):
    """Process payment through integrated gateway"""
    # Implement payment gateway integration
    # (Stripe, PayPal, etc.)
    pass
```

### 3. Shipping Calculation
```python
def calculate_shipping(weight: float, destination: str) -> float:
    """Calculate shipping cost based on weight and destination"""
    base_rate = 5.99
    weight_rate = weight * 0.5
    return base_rate + weight_rate
```

### 4. Inventory Management
```python
@router.put("/products/{product_id}/stock")
def update_stock(product_id: int, new_stock: int, claims: dict = Depends(require_user)):
    """Update product stock"""
    context.execute_query(
        "UPDATE products SET stock_quantity = :stock WHERE id = :id",
        {"stock": new_stock, "id": product_id}
    )
    return {"message": "Stock updated"}
```

## Admin Dashboard Features

### Sales Analytics
- Total revenue, orders, customers
- Popular products, categories
- Sales trends over time
- Geographic sales distribution

### Order Management
- View all orders with filtering
- Update order status
- Process refunds
- Generate invoices

### Product Management
- Bulk product operations
- Category management
- Inventory alerts
- Product import/export

## Security Considerations

### Store-Specific Security
- PCI compliance for payment processing
- Secure storage of payment information
- CSRF protection for forms
- Rate limiting for API endpoints
- Input validation and sanitization

### Data Protection
- Customer data encryption
- GDPR compliance features
- Order data retention policies
- Secure password handling

## Performance Optimization

### Database Optimization
- Proper indexing on frequently queried columns
- Query optimization for product searches
- Caching for category trees and product data
- Database connection pooling

### Frontend Optimization
- Lazy loading of product images
- Infinite scroll for product listings
- Service worker for offline cart functionality
- CDN for static assets

## Troubleshooting Common Issues

### Data Not Persisting After Create/Update Operations

**Symptoms**: API returns success (200 OK) but data doesn't appear in subsequent GET requests.

**Root Cause**: Extension database context doesn't commit transactions for INSERT RETURNING queries.

**Solution**: Use `execute_main_db_query` function instead of `context.execute_query` for all database operations.

### 405 Method Not Allowed Errors

**Symptoms**: POST/PUT/DELETE requests return 405 errors.

**Root Cause**: Backend server not restarted after extension code changes, or routes not registered.

**Solution**: Restart the backend server with `uvicorn backend.main:app --reload --host 0.0.0.0 --port 8887`

### Table Not Found Errors

**Symptoms**: `relation "table_name" does not exist` errors.

**Root Cause**: Table names not quoted in queries, causing PostgreSQL case-sensitivity issues.

**Solution**: Always quote table names: `f'SELECT * FROM "{table_name}"'`

### Extension Not Loading

**Symptoms**: Extension appears in list but routes don't work.

**Root Cause**: Extension code errors preventing initialization.

**Solution**: Check backend logs for initialization errors and fix syntax/import issues.

## Extension Lifecycle

### Installation
1. Create database tables
2. Set up default categories
3. Configure payment gateways
4. Create admin user permissions

### Updates
1. Database migrations for schema changes
2. Backward compatibility checks
3. Data migration scripts
4. Feature flag management

### Uninstallation
1. Option to export data
2. Clean removal of tables and data
3. Removal of uploaded files
4. Cleanup of user permissions

This guide provides a comprehensive foundation for building a full-featured e-commerce extension with professional-grade functionality.