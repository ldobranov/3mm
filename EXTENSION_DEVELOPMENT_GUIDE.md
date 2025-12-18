\# Extension Development Guide

This is a practical, repo-specific guide for building extensions in **this codebase** (FastAPI backend + Vue 3 frontend + custom i18n + extension relationship system).

---

## 0. TL;DR: Create a new extension (checklist)

1. **Pick an extension name + version**: `MyExtension` + `1.0.0`.
2. Create backend folder: `backend/extensions/MyExtension_1.0.0/`.
3. Create frontend folder: `frontend/src/extensions/MyExtension_1.0.0/`.
4. Add `manifest.json` + `locales/` + backend entry file + frontend entry `.vue`.
5. Implement `initialize_extension(context)` + register `APIRouter(prefix="/api/<prefix>")`.
6. Use **namespaced translation keys** + provide `locales/en.json` and `locales/bg.json`.
7. Enable and test via Extensions UI; verify routes and translations load.

---

## 1. How extensions are structured in this repo

There are two “sides” to most extensions:

### Backend (installed extensions)

```
backend/extensions/MyExtension_1.0.0/
├── manifest.json
├── database_schema.json                 # Optional; depends on extension
├── my_extension.py                      # The backend_entry (FastAPI router + init/cleanup)
└── locales/
    ├── en.json                          # Backend-side translations (if used)
    └── bg.json
```

### Frontend (extension UI)

```
frontend/src/extensions/MyExtension_1.0.0/
├── manifest.json                        # Frontend reads this for routing/relationships
├── MyExtension.vue                      # frontend_entry
├── MyExtensionEditor.vue                # frontend_editor (optional)
├── components/...                       # Optional
└── locales/
    ├── en.json
    └── bg.json
```

> Notes:
> - The frontend i18n loader scans `frontend/src/extensions/**/locales/<lang>.json`.
> - The backend also has an extension manifest and routes; keep **name/version** consistent.

---

## 2. `manifest.json`: the contract for install, routes, permissions, i18n, and relationships

### 2.1 Minimal extension manifest (recommended starting point)

```json
{
  "name": "MyExtension",
  "version": "1.0.0",
  "type": "extension",
  "description": "One-line description.",
  "author": "Your Name",
  "backend_entry": "my_extension.py",
  "frontend_entry": "MyExtension.vue",
  "frontend_components": ["MyExtensionEditor.vue"],
  "frontend_routes": [
    {
      "path": "/my",
      "component": "MyExtension.vue",
      "name": "MyExtension",
      "meta": { "requiresAuth": true }
    }
  ],
  "locales": {
    "supported": ["en", "bg"],
    "default": "en",
    "directory": "locales/"
  },
  "permissions": ["database_read", "database_write"],
  "public_endpoints": [],
  "dependencies": {}
}
```

### 2.2 Naming + routing rules that prevent bugs

- **Extension folder name**: must match `Name_Version`, e.g. `StoreExtension_1.0.0`.
- **API prefix**: keep stable across versions.
  - Recommended: `/api/<extensionPrefix>` where `extensionPrefix = name.replace(/Extension$/i, '').toLowerCase()`.
  - Example: `StoreExtension` → `/api/store`.
- **Frontend route paths**: treat as stable public API of your extension UI.

---

## 3. Backend: `initialize_extension(context)` patterns that work reliably

### 3.1 Minimal backend skeleton

```python
from fastapi import APIRouter, Depends, HTTPException
from backend.utils.auth_dep import require_user

def initialize_extension(context):
    router = APIRouter(prefix="/api/my")

    @router.get("/health")
    def health():
        return {"ok": True}

    @router.get("/private")
    def private_endpoint(claims: dict = Depends(require_user)):
        return {"user_id": claims.get("user_id")}

    context.register_router(router)
    return {"routes_registered": 2, "status": "initialized"}

def cleanup_extension(context):
    return {"status": "cleaned_up"}
```

### 3.2 PostgreSQL table naming (do this from day 1)

- Use **lowercase** table names.
- Prefer a **stable base name** (no version in table name), for smoother upgrades:

```python
base = "myextension"  # or context.extension_id.split('_')[0].lower()
items_table = f"ext_{base}_items"  # ext_myextension_items
```

### 3.3 Critical transaction note (RETURNING + commits)

In this codebase, `context.execute_query` can be tricky with writes that use `RETURNING`. When correctness matters, use a helper that commits.

Recommended pattern: use an `execute_main_db_query()` helper (see StoreExtension for a working implementation).

---

## 4. Frontend: Vue 3 + i18n that stays reactive

### 4.1 Use the app i18n everywhere

```ts
import { useI18n } from '@/utils/i18n'

const { t, currentLanguage } = useI18n()
```

Best practice:
- Always call `t('some.key', 'English fallback')`.
- Prefer **namespaced keys**:
  - `my.title`, `my.actions.save`, `my.settings.currencyCode`
  - or `myExtension.*` if you want to avoid collisions.

### 4.2 Locale file structure (what actually works)

Create `frontend/src/extensions/MyExtension_1.0.0/locales/en.json` and `.../bg.json`.

Example:

```json
{
  "my": {
    "title": "My Extension",
    "actions": {
      "save": "Save",
      "cancel": "Cancel"
    }
  }
}
```

Avoid this common bug:
- Using keys like `store.settings.storeInfo` in code but only defining `settings.storeInfo` in JSON.
  - The key path must match exactly.

---

## 5. Multilingual *content* vs multilingual *UI*

You typically have **two** language concepts:

1. **UI language**: controlled by the app header language selector; affects labels/buttons.
2. **Content language**: the language of the content you are creating/editing (pages, products).

Best practice:
- Keep UI strings on the global i18n.
- Pass content language explicitly in props and backend API params.

Example pattern (used in Store ↔ Pages embedding):
- UI labels use `t('store.productSelector.title')` (UI language).
- Product data fetch uses `params: { language: contentLanguage }`.

---

## 6. Cross-extension integration (relationships + embedders)

This repo supports inter-extension integration via manifest-driven relationships.

### 6.1 Content embedders (recommended pattern)

Provider extension declares:

```json
"provides": {
  "content_embedders": {
    "product": {
      "label": "store.productSelector.title",
      "component": "ProductSelector",
      "format_api": "format_product_html",
      "ui_translations_api": "get_ui_translations",
      "description": "Embed products from the store"
    }
  }
}
```

Consumer extension can discover embedders via the frontend relationship system.

### 6.2 Translation loading for shared components

When dynamically loading a component from another extension, also load its locales for the current UI language.

Pattern:

```ts
import { i18n } from '@/utils/i18n'

await i18n.loadExtensionTranslationsForExtension('StoreExtension', currentLanguage.value)
```

---

## 7. Settings + translations: avoid “record_id collisions”

If you build a translations table like:

```
(record_id, language_code) UNIQUE
```

Then you must not reuse the same `record_id` for multiple unrelated translation “domains”.

**Recommended approach**:
- Use **separate tables** per entity (products, categories, settings).
- Or introduce a discriminator like `record_type`.
- If you must overload `record_id`, reserve values:
  - `0` for settings
  - `-1` for UI strings

This prevents settings translations from overwriting UI translations.

---

## 8. Testing workflow (fast)

### Frontend

- `cd frontend && npm run dev`
- Verify:
  - your route renders
  - `t()` keys resolve
  - language switch updates the UI

### Backend

- Start backend (see repo scripts).
- Verify:
  - `/api/<prefix>/health` responds
  - protected endpoints require auth
  - public endpoints work without auth if listed in `public_endpoints`

---

## 9. Troubleshooting (most common)

### 9.1 “I see untranslated English strings or raw keys”

- Check the key path matches the JSON structure.
- Confirm the locale file exists at `frontend/src/extensions/<Ext>_1.0.0/locales/<lang>.json`.
- If the component is dynamically loaded from another extension, ensure you call:
  - `i18n.loadExtensionTranslationsForExtension('<Ext>', currentLanguage.value)`.

### 9.2 “The UI shows prefix/suffix raw”

- Never render raw enum values directly.
- Map to translations like `t('...currencyPrefix')` / `t('...currencySuffix')`.

### 9.3 “Writes succeed but later reads don’t show data”

- Suspect missing commits.
- Prefer `execute_main_db_query()` (commits) for write operations.

---

## 10. Reference implementations in this repo

- Store extension: backend + frontend + translations + content embedders.
- Pages extension: multilingual content + consuming an embedder.

Use these as a pattern library, not as a copy/paste target.

### Universal Image Components

The application provides comprehensive universal image components for consistent image handling across all extensions:

#### AdvancedImageUpload Component

The `AdvancedImageUpload` component provides a comprehensive image management system with enterprise-grade features:

**Core Features:**
- ✅ **Dual-tab interface**: Upload new images or browse existing library
- ✅ **Advanced image editing**: Built-in canvas-based image editor with cropping, zooming, and aspect ratio control
- ✅ **Folder organization**: Create, navigate, and manage hierarchical image folders
- ✅ **Drag-and-drop operations**: Visual drag-and-drop for moving images between folders
- ✅ **Bulk operations**: Select multiple images, batch operations with confirmation dialogs
- ✅ **Search and pagination**: Real-time search with configurable pagination
- ✅ **Multilingual support**: Built-in i18n for all interface text (English/Bulgarian)
- ✅ **Responsive design**: Optimized for all screen sizes and devices
- ✅ **Accessibility**: Full keyboard navigation and screen reader support

**Advanced Features:**
- ✅ **Multiple image selection**: Single or multiple image selection modes
- ✅ **Image editing**: Edit existing images with crop, resize, and save changes
- ✅ **Rename functionality**: Rename images with inline editing
- ✅ **Delete with confirmation**: Safe deletion with confirmation dialogs
- ✅ **Semantic configuration**: Dynamic extension names from configuration mapping
- ✅ **Progress tracking**: Real-time upload progress with visual indicators
- ✅ **Error handling**: Comprehensive error messages and recovery mechanisms
- ✅ **Cache busting**: Automatic cache invalidation for updated images

**Import:** `import AdvancedImageUpload from '@/components/AdvancedImageUpload.vue'`

**Basic Usage:**
```vue
<template>
  <AdvancedImageUpload
    v-model="selectedImages"
    :extension-name="'myextension'"
    :extension-display-name="'My Extension'"
    :multiple="true"
    @upload-success="handleUploadSuccess"
    @image-selected="handleImageSelected"
  />
</template>

<script setup lang="ts">
import { ref } from 'vue'
import AdvancedImageUpload from '@/components/AdvancedImageUpload.vue'

const selectedImages = ref<string[]>([])

const handleUploadSuccess = (response: any) => {
  console.log('Image uploaded:', response)
}

const handleImageSelected = (image: any) => {
  console.log('Image selected:', image)
}
</script>
```

**Component Props:**
| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `modelValue` | `string \| string[]` | `''` | Selected image URLs (single or array) |
| `extensionName` | `string` | `'store'` | Extension identifier for API endpoints |
| `extensionDisplayName` | `string` | `'Store'` | Human-readable extension name (auto-configured) |
| `uploadUrl` | `string` | `'/api/upload'` | Upload endpoint (auto-configured) |
| `imageLibraryUrl` | `string` | `'/api/images/list'` | Library endpoint (auto-configured) |
| `uploadDirectory` | `string` | `'uploads'` | Base upload directory |
| `maxSize` | `number` | `5` | Max file size in MB |
| `multiple` | `boolean` | `false` | Allow multiple image selection |
| `disabled` | `boolean` | `false` | Disable component |

**Semantic Extension Configuration:**
The component uses a built-in configuration mapping for semantic extension names:

```javascript
const extensionConfig = {
  'store': { displayName: 'Store', description: 'Product images and media' },
  'settings': { displayName: 'Settings', description: 'Application settings and logos' },
  'blog': { displayName: 'Blog', description: 'Blog posts and articles' },
  'gallery': { displayName: 'Gallery', description: 'Photo gallery and media' }
};
```

This ensures consistent naming and allows easy addition of new extensions.

**Component Events:**
| Event | Payload | Description |
|-------|---------|-------------|
| `update:modelValue` | `string \| string[]` | Model value updated (single URL or array) |
| `upload-success` | `{ url, filename, size }` | Upload completed successfully |
| `upload-error` | `Error` | Upload failed with error details |
| `image-selected` | `{ url, filename, size }` | Single image selected from library |
| `images-selected` | `Array<{ url, filename, size }>` | Multiple images selected (when `multiple="true"`) |

**Required Backend Endpoints:**
Extensions must implement these API endpoints (replace `myextension` with your extension name):

```python
# In your extension's backend
@router.post("/upload-image")
def upload_image(
    file: UploadFile = File(...),
    directory: str = "myextension",
    replace_filename: str = None,
    claims: dict = Depends(require_user)
):
    # Handle file upload to uploads/myextension/ directory
    # Support replacing existing images with replace_filename parameter

@router.get("/images/list")
def list_images(
    directory: str = "myextension",
    search: str = None,
    limit: int = 100,
    offset: int = 0
):
    # Return images and folders in uploads/myextension/ directory
    # Include breadcrumb navigation and permissions

@router.post("/images/folder")
def create_folder(data: dict, claims: dict = Depends(require_user)):
    # Create new folder: data = {"folder_name": "name", "directory": "path"}

@router.post("/images/move")
def move_image(data: dict, claims: dict = Depends(require_user)):
    # Move image: data = {"image_name": "file.jpg", "from_directory": "src", "to_directory": "dest"}

@router.delete("/images/delete")
def delete_image(data: dict, claims: dict = Depends(require_user)):
    # Delete image: data = {"image_name": "file.jpg", "directory": "path"}

@router.post("/images/rename")
def rename_image(data: dict, claims: dict = Depends(require_user)):
    # Rename image: data = {"current_name": "old.jpg", "new_name": "new.jpg", "directory": "path"}
```

**Complete Extension Implementation:**
```python
def initialize_extension(context):
    router = APIRouter(prefix="/api/gallery")

    @router.post("/upload-image")
    def upload_image(
        file: UploadFile = File(...),
        directory: str = "gallery",
        replace_filename: str = None,
        claims: dict = Depends(require_user)
    ):
        # Handle file upload with optional replacement
        # Save to uploads/gallery/ directory
        # If replace_filename provided, replace existing file
        return {
            "filename": "image.jpg",
            "url": f"/uploads/gallery/image.jpg",
            "message": "Image uploaded successfully"
        }

    @router.get("/images/list")
    def list_images(directory: str = "gallery", search: str = None, limit: int = 100, offset: int = 0):
        # Return comprehensive folder and image listing
        return {
            "folders": [
                {"name": "Events", "path": "gallery/Events", "image_count": 5, "type": "folder"}
            ],
            "images": [
                {"url": "/uploads/gallery/image1.jpg", "name": "image1.jpg", "size": 1024000, "type": "image"}
            ],
            "breadcrumb": [
                {"name": "Gallery", "path": "gallery"}
            ],
            "can_create_folder": True,
            "directory": directory
        }

    @router.post("/images/folder")
    def create_folder(data: dict, claims: dict = Depends(require_user)):
        folder_name = data.get("folder_name")
        directory = data.get("directory", "gallery")
        # Create folder and return success
        return {
            "message": "Folder created successfully",
            "folder": {
                "name": folder_name,
                "path": f"{directory}/{folder_name}",
                "type": "folder",
                "image_count": 0
            }
        }

    @router.post("/images/move")
    def move_image(data: dict, claims: dict = Depends(require_user)):
        # Move image between directories
        return {"message": "Image moved successfully"}

    @router.delete("/images/delete")
    def delete_image(data: dict, claims: dict = Depends(require_user)):
        # Delete image file
        return {"message": "Image deleted successfully"}

    @router.post("/images/rename")
    def rename_image(data: dict, claims: dict = Depends(require_user)):
        # Rename image file
        return {"message": "Image renamed successfully"}

    context.register_router(router)
```

**Advanced Frontend Integration:**
```vue
<!-- In your extension's main component -->
<template>
  <div class="gallery-extension">
    <h2>Photo Gallery</h2>

    <!-- Single image selection -->
    <AdvancedImageUpload
      v-model="featuredImage"
      :extension-name="'gallery'"
      :multiple="false"
      :max-size="10"
      @image-selected="handleFeaturedImage"
    />

    <!-- Multiple image selection -->
    <AdvancedImageUpload
      v-model="galleryImages"
      :extension-name="'gallery'"
      :extension-display-name="'Gallery'"
      :multiple="true"
      :max-size="5"
      @images-selected="updateGallery"
    />

    <!-- Display selected images -->
    <div class="gallery-grid" v-if="galleryImages.length > 0">
      <div v-for="url in galleryImages" :key="url" class="gallery-item">
        <img :src="url" :alt="getImageName(url)" />
        <button @click="removeImage(url)">Remove</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import AdvancedImageUpload from '@/components/AdvancedImageUpload.vue'

const featuredImage = ref('')
const galleryImages = ref<string[]>([])

const handleFeaturedImage = (image: any) => {
  console.log('Featured image selected:', image)
}

const updateGallery = (images: any[]) => {
  console.log('Gallery updated with:', images)
  // Images are automatically added to galleryImages via v-model
}

const getImageName = (url: string): string => {
  return url.split('/').pop()?.split('?')[0] || 'Unknown'
}

const removeImage = (urlToRemove: string) => {
  galleryImages.value = galleryImages.value.filter(url => url !== urlToRemove)
}
</script>
```

#### Backend Image Upload Endpoint

Extensions should implement a standardized upload endpoint:

```python
@router.post("/upload-image")
def upload_image(file: UploadFile = File(...), claims: dict = Depends(require_user)):
    """Upload image with proper file handling"""
    try:
        # Validate file type and size
        allowed_types = ["image/jpeg", "image/png", "image/gif", "image/webp"]
        if file.content_type not in allowed_types:
            raise HTTPException(status_code=400, detail="Invalid file type")

        if file.size > 5 * 1024 * 1024:  # 5MB limit
            raise HTTPException(status_code=400, detail="File too large")

        # Generate unique filename
        file_extension = os.path.splitext(file.filename)[1]
        unique_filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex}{file_extension}"

        # Save to project root uploads directory
        uploads_dir = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'uploads', 'extension-name')
        os.makedirs(uploads_dir, exist_ok=True)

        file_path = os.path.join(uploads_dir, unique_filename)
        with open(file_path, "wb") as buffer:
            buffer.write(file.file.read())

        return {
            "filename": unique_filename,
            "url": f"/uploads/extension-name/{unique_filename}",
            "message": "File uploaded successfully"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
```

#### Frontend Usage

Import and use the universal components in your extension:

```vue
<template>
  <div class="image-management">
    <!-- Image Upload Component -->
    <ImageUpload
      v-model="uploadedImageUrls"
      :upload-url="'/api/extension-name/upload-image'"
      :multiple="true"
      :max-files="10"
      :max-size="5"
      :disabled="false"
      @upload-success="handleUploadSuccess"
      @upload-error="handleUploadError"
    />

    <!-- Image Gallery Component -->
    <ImageGallery
      v-model="uploadedImageUrls"
      :max-images="10"
      :disabled="false"
      @image-removed="handleImageRemoved"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import ImageUpload from '@/components/ImageUpload.vue';
import ImageGallery from '@/components/ImageGallery.vue';

const uploadedImageUrls = ref<string[]>([]);

const handleUploadSuccess = (response: any) => {
  console.log('Upload successful:', response);
  // Handle successful upload (URLs are automatically added to v-model)
};

const handleUploadError = (error: any) => {
  console.error('Upload failed:', error);
  // Handle upload error
};

const handleImageRemoved = (index: number) => {
  console.log('Image removed at index:', index);
  // Handle image removal (URLs are automatically removed from v-model)
};
</script>
```

#### ImageUpload Component Props

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `v-model` | `string[]` | `[]` | Array of uploaded image URLs |
| `upload-url` | `string` | Required | API endpoint for file uploads |
| `multiple` | `boolean` | `true` | Allow multiple file selection |
| `max-files` | `number` | `10` | Maximum number of files allowed |
| `max-size` | `number` | `5` | Maximum file size in MB |
| `accept` | `string` | `"image/*"` | Accepted file types |
| `disabled` | `boolean` | `false` | Disable the upload component |

#### ImageUpload Component Events

| Event | Payload | Description |
|-------|---------|-------------|
| `upload-success` | `{ filename: string, url: string }` | Fired when a file is successfully uploaded |
| `upload-error` | `Error` | Fired when an upload fails |
| `upload-progress` | `{ loaded: number, total: number }` | Fired during upload progress |

#### ImageGallery Component Props

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `images` | `ImageData[]` | `[]` | Array of image objects to display |
| `title` | `string` | - | Optional gallery title |
| `removable` | `boolean` | `true` | Allow image removal |
| `showInfo` | `boolean` | `true` | Show image filename and size |
| `showSize` | `boolean` | `true` | Show file size in info |
| `showEmptyState` | `boolean` | `true` | Show empty state when no images |
| `emptyText` | `string` | - | Custom empty state text |
| `gridColumns` | `number` | `4` | Number of columns in grid (1-6) |
| `maxHeight` | `string` | `'400px'` | Maximum height of gallery |

#### ImageGallery Component Events

| Event | Payload | Description |
|-------|---------|-------------|
| `remove` | `[index: number, image: ImageData]` | Fired when an image is removed |

#### Integration Example

Here's how the StoreExtension integrates these components:

```vue
<!-- In ProductForm.vue -->
<div class="form-group">
  <label>{{ t('store.images', 'Images') }}</label>

  <!-- Upload new images -->
  <ImageUpload
    v-model="uploadedImageUrls"
    :upload-url="'/api/store/upload-image'"
    :multiple="true"
    :max-files="10"
    :max-size="5"
    @upload-success="handleUploadSuccess"
    @upload-error="handleUploadError"
  />

  <!-- Display all images (existing + newly uploaded) -->
  <ImageGallery
    v-if="allImagesForDisplay.length > 0"
    :images="allImagesForDisplay"
    :title="t('store.productImages', 'Product Images')"
    :removable="true"
    :show-info="false"
    :grid-columns="4"
    @remove="removeImage"
  />
</div>
```

```javascript
// In the component script
const uploadedImageUrls = ref<string[]>([]);

// Combined display of existing and newly uploaded images
const allImagesForDisplay = computed(() => {
  const existing = form.value.images.map(url => ({ url, isExisting: true }));
  const uploaded = uploadedImageUrls.value.map(url => ({ url, isExisting: false }));
  return [...existing, ...uploaded];
});

// Handle image removal from combined gallery
const removeImage = (index: number, image: any) => {
  if (image.isExisting) {
    // Remove from existing images
    const existingIndex = form.value.images.findIndex(url => url === image.url);
    if (existingIndex !== -1) form.value.images.splice(existingIndex, 1);
  } else {
    // Remove from newly uploaded images
    const uploadedIndex = uploadedImageUrls.value.findIndex(url => url === image.url);
    if (uploadedIndex !== -1) uploadedImageUrls.value.splice(uploadedIndex, 1);
  }
};
```

#### Benefits of Universal Components

1. **Consistency**: All extensions use the same upload interface and behavior
2. **Maintainability**: Bug fixes and improvements benefit all extensions
3. **Accessibility**: Built-in keyboard navigation and screen reader support
4. **Validation**: Consistent file type and size validation
5. **Progress Tracking**: Visual feedback during uploads
6. **Error Handling**: Standardized error messages and recovery
7. **Theming**: Automatic integration with the application's theme system
8. **Internationalization**: Built-in support for multiple languages (English and Bulgarian translations included)

### PostgreSQL Compatibility Issues

**Table Naming Convention**: Use lowercase table names without quotes for PostgreSQL compatibility:
```python
# Wrong (mixed case with quotes):
table_name = "ext_StoreExtension_table"
context.execute_query(f'SELECT * FROM "{table_name}"')

# Correct (lowercase without quotes):
table_name = "ext_storeextension_table"
context.execute_query(f"SELECT * FROM {table_name}")
```

**Why lowercase?** PostgreSQL folds unquoted identifiers to lowercase. Using lowercase names ensures consistent table access across different database configurations.

**Table Name Generation**: Generate table names using lowercase base names:
```python
# Recommended approach:
base_name = context.extension_id.split('_')[0].lower()  # "storeextension"
table_name = f"ext_{base_name}_table"  # "ext_storeextension_table"

# For shared tables across versions:
table_name = "ext_extensionname_table"  # Same for all versions
```

**Auto-increment Columns**: Use `SERIAL` instead of `AUTOINCREMENT`:
```sql
-- Wrong:
id INTEGER PRIMARY KEY AUTOINCREMENT

-- Correct:
id SERIAL PRIMARY KEY
```

**Query Formatting**: Always use unquoted lowercase table names in queries:
```python
# Wrong:
f'SELECT * FROM "{table_name}" WHERE id = :id'

# Correct:
f"SELECT * FROM {table_name} WHERE id = :id"
```

### Basic Backend Structure

```python
from fastapi import APIRouter, Depends, HTTPException
from backend.utils.auth_dep import require_user
from backend.db.base import get_db
import json

def initialize_extension(context):
    """Initialize the extension"""
    try:
        # Get table name (automatically prefixed)
        table_name = f"ext_{context.extension_id.replace('.', '_')}_table"

        # Register API routes
        router = APIRouter(prefix="/api/extension")

        @router.get("/data")
        def get_data(claims: dict = Depends(require_user)):
            """Get extension data"""
            user_id = claims.get("user_id")
            # Query your data
            result = context.execute_query(f"SELECT * FROM {table_name}")
            return {"items": result}

        @router.post("/create")
        def create_item(data: dict, claims: dict = Depends(require_user)):
            """Create new item"""
            result = context.execute_query(
                f"INSERT INTO {table_name} (column1, column2) VALUES (:val1, :val2) RETURNING id",
                {"val1": data["field1"], "val2": data["field2"]}
            )
            return {"id": result[0]["id"]}

        context.register_router(router)

        return {
            "routes_registered": 2,
            "status": "initialized"
        }

    except Exception as e:
        return {"status": "error", "error": str(e)}

def cleanup_extension(context):
    """Cleanup when extension is disabled"""
    return {"status": "cleaned_up"}
```

### Database Operations

Use `context.execute_query()` for all database operations:

```python
# SELECT queries
result = context.execute_query("SELECT * FROM table WHERE id = :id", {"id": item_id})

# INSERT queries (use RETURNING for IDs)
result = context.execute_query(
    "INSERT INTO table (col1, col2) VALUES (:val1, :val2) RETURNING id",
    {"val1": value1, "val2": value2}
)

# UPDATE queries
context.execute_query(
    "UPDATE table SET col1 = :val WHERE id = :id",
    {"val": new_value, "id": item_id}
)

# DELETE queries
context.execute_query("DELETE FROM table WHERE id = :id", {"id": item_id})
```

## 4. Frontend Implementation

### Main Component Structure

```vue
<template>
  <div class="extension-container">
    <div class="extension-header">
      <h1>{{ t('extensions.extensionname.title', 'Extension Title') }}</h1>
    </div>

    <div class="extension-content">
      <!-- Your extension UI -->
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useI18n } from '@/utils/i18n';
import http from '@/utils/dynamic-http';

const { t } = useI18n();
const data = ref([]);

const loadData = async () => {
  try {
    const response = await http.get('/api/extension/data');
    data.value = response.data.items;
  } catch (error) {
    console.error('Failed to load data:', error);
  }
};

onMounted(() => {
  loadData();
});
</script>

<style scoped>
.extension-container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 2rem;
}

.extension-header h1 {
  color: var(--text-primary);
  margin-bottom: 2rem;
}
</style>
```

### Advanced: Route Query Watching

For components that respond to URL query parameters (filtering, search, etc.):

```vue
<script setup lang="ts">
import { watch } from 'vue';
import { useRoute } from 'vue-router';

const route = useRoute();

// Watch for route query changes
watch(() => route.query.category, () => {
  loadFilteredData();
});

watch(() => route.query.search, () => {
  loadFilteredData();
});

// For multiple query params, use a single watcher
watch(() => route.query, () => {
  loadFilteredData();
}, { deep: true });
</script>
```

### Advanced: Multilingual Content Forms with Language Switching

For extensions with translatable content, implement language-aware forms with proper state management:

```vue
<template>
  <div class="multilingual-form">
    <!-- Language Selector -->
    <div v-if="availableLanguages.length > 1" class="language-selector">
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
    </div>

    <!-- Multilingual Fields -->
    <div class="form-group">
      <label>{{ t('title', 'Title') }} ({{ getLanguageName(contentLanguage) }}) *</label>
      <input
        v-model="currentTitle"
        :placeholder="`${t('title', 'Title')} (${contentLanguage.toUpperCase()})`"
      />
    </div>

    <div class="form-group">
      <label>{{ t('content', 'Content') }} ({{ getLanguageName(contentLanguage) }})</label>
      <textarea
        v-model="currentContent"
        :placeholder="`${t('content', 'Content')} (${contentLanguage.toUpperCase()})`"
        rows="8"
      ></textarea>
    </div>

    <!-- Save Button -->
    <div class="form-actions">
      <button @click="saveContent" class="save-btn">
        {{ contentLanguage === 'en' ? t('save', 'Save') : t('saveTranslation', 'Save Translation') }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { useI18n } from '@/utils/i18n';
import http from '@/utils/dynamic-http';

const { t } = useI18n();

// Multilingual data structure - separate from form fields
const contentLanguage = ref('en');
const availableLanguages = ref(['en', 'bg', 'es']);
const contentTranslations = ref<any>({}); // { en: {title, content}, bg: {title, content} }

// Form fields that change with language selection
const currentTitle = ref('');
const currentContent = ref('');

// Computed properties for form binding
const formTitle = computed({
  get: () => currentTitle.value,
  set: (value) => currentTitle.value = value
});

const formContent = computed({
  get: () => currentContent.value,
  set: (value) => currentContent.value = value
});

// Language switching with proper state management
const switchContentLanguage = (lang: string) => {
  // Save current language data before switching
  contentTranslations.value[contentLanguage.value] = {
    title: currentTitle.value,
    content: currentContent.value
  };

  contentLanguage.value = lang;

  // Load data for new language
  const translation = contentTranslations.value[lang];
  if (translation) {
    currentTitle.value = translation.title || '';
    currentContent.value = translation.content || '';
  } else {
    // No translation exists yet, start with empty fields
    currentTitle.value = '';
    currentContent.value = '';
  }
};

// Save content based on current language
const saveContent = async () => {
  try {
    // Save current form data to translations
    contentTranslations.value[contentLanguage.value] = {
      title: currentTitle.value,
      content: currentContent.value
    };

    if (contentLanguage.value === 'en') {
      // Save base English content
      await http.post('/api/extension/content', {
        title: currentTitle.value,
        content: currentContent.value
      });
    } else {
      // Save translation
      await http.post('/api/extension/content/translations', {
        language_code: contentLanguage.value,
        translations: {
          title: currentTitle.value,
          content: currentContent.value
        }
      });
    }

    // Show success message
  } catch (error) {
    console.error('Failed to save content:', error);
  }
};

const getLanguageName = (code: string): string => {
  const names: Record<string, string> = {
    'bg': 'Български', 'es': 'Español', 'fr': 'Français'
  };
  return names[code] || code.toUpperCase();
};
</script>
```

### Form State Management Best Practices

**Critical Issue**: Modal forms can retain state between operations if not properly managed.

**Solution**: Always clear editing state when cancelling modals:

```vue
<script setup lang="ts">
const showForm = ref(false);
const editingItem = ref<any>(null);

// Wrong - doesn't clear editing state
const cancelForm = () => {
  showForm.value = false;
  // editingItem.value still has old data!
};

// Correct - clears all state
const cancelForm = () => {
  showForm.value = false;
  editingItem.value = null;  // Clear editing state
};

// When opening forms
const addNewItem = () => {
  editingItem.value = null;  // Explicitly clear for new items
  showForm.value = true;
};

const editItem = (item: any) => {
  editingItem.value = item;  // Set for editing
  showForm.value = true;
};
</script>
```

### Translation Merging for Display

For displaying translated content in components:

```vue
<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
  item: any;
  currentLanguage?: string;
}>();

// Merge base item with translations
const translatedItem = computed(() => {
  if (!props.item || props.currentLanguage === 'en') {
    return props.item;
  }

  // Try to get translation from item.translations or API
  const translation = props.item.translations?.find((t: any) =>
    t.language_code === props.currentLanguage
  );

  if (translation?.data) {
    // Deep merge translation with base item
    return { ...props.item, ...translation.data };
  }

  return props.item;
});
</script>

<template>
  <div>
    <h3>{{ translatedItem.title || item.title }}</h3>
    <p>{{ translatedItem.description || item.description }}</p>
  </div>
</template>
```

### Translation Keys Structure

Create locale files with consistent naming:

**locales/en.json:**
```json
{
  "settings": {
    "title": "Extension Settings",
    "settingName": "Setting Label"
  },
  "title": "Extension Title",
  "description": "Extension description",
  "createNew": "Create New Item",
  "edit": "Edit",
  "delete": "Delete",
  "save": "Save",
  "cancel": "Cancel"
}
```

## 5. Multilingual Content Support

### For Extensions with Translatable Content

Extensions can implement multilingual support using extension-specific translation tables:

#### Backend Setup
```python
# In initialize_extension
translations_table = f"ext_{context.extension_id.split('_')[0].lower()}_translations"

# Create translations table
execute_main_db_query(f"""
    CREATE TABLE IF NOT EXISTS "{translations_table}" (
        id SERIAL PRIMARY KEY,
        record_id INTEGER NOT NULL,
        language_code TEXT NOT NULL,
        translation_data JSONB NOT NULL,
        translation_coverage DECIMAL(5,2) DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(record_id, language_code)
    )
""")

# Translation API endpoints
@router.post("/items/{item_id}/translations")
def add_translation(item_id: int, data: Dict[str, Any], claims: dict = Depends(require_user)):
    language_code = data.get("language_code")
    translations = data.get("translations", {})

    execute_main_db_query(f"""
        INSERT INTO "{translations_table}"
        (record_id, language_code, translation_data, translation_coverage)
        VALUES (:record_id, :language_code, :translation_data, :coverage)
        ON CONFLICT (record_id, language_code) DO UPDATE SET
            translation_data = EXCLUDED.translation_data,
            translation_coverage = EXCLUDED.translation_coverage,
            updated_at = CURRENT_TIMESTAMP
    """, {
        "record_id": item_id,
        "language_code": language_code,
        "translation_data": json.dumps(translations),
        "coverage": len(translations) / total_fields * 100
    })
```

#### Frontend Usage
```vue
<template>
  <div>
    <input v-model="item.title" :placeholder="t('titlePlaceholder')" />
    <textarea v-model="item.description" :placeholder="t('descriptionPlaceholder')"></textarea>
  </div>
</template>
```

### For Core System Content (Pages, Menus, etc.)

Core system content uses the universal translation engine for multilingual support:

#### Backend Implementation
```python
from backend.utils.universal_translation_engine import translation_engine

# Register content types in main application
def initialize_multilingual_content():
    # Register page content
    translation_engine.register_content_type(
        "pages",
        ["title", "content", "meta_description"],
        fallback_language="en"
    )

    # Register menu content
    translation_engine.register_content_type(
        "menus",
        ["title", "description"],
        fallback_language="en"
    )

    # Register settings content
    translation_engine.register_content_type(
        "settings",
        ["site_title", "site_description", "footer_text"],
        fallback_language="en"
    )

# API endpoints for content translation
@router.post("/api/content/{content_type}/{content_id}/translations")
def add_content_translation(
    content_type: str,
    content_id: int,
    data: Dict[str, Any],
    claims: dict = Depends(require_user)
):
    """Add translation for core content"""
    language_code = data.get("language_code")
    translations = data.get("translations", {})

    # Validate content type is registered
    if not translation_engine.is_content_type_registered(content_type):
        raise HTTPException(status_code=400, detail=f"Content type {content_type} not registered")

    # Add translation
    success = translation_engine.add_translation(
        content_type=content_type,
        content_id=content_id,
        language_code=language_code,
        translations=translations,
        user_id=claims.get("user_id")
    )

    if success:
        return {"message": f"Translation added for {language_code}"}
    else:
        raise HTTPException(status_code=500, detail="Failed to add translation")

@router.get("/api/content/{content_type}/{content_id}")
def get_content_with_translations(
    content_type: str,
    content_id: int,
    language: str = None
):
    """Get content with automatic translation merging"""
    # Get base content
    base_content = get_content_by_id(content_type, content_id)
    if not base_content:
        raise HTTPException(status_code=404, detail="Content not found")

    # Get current language
    current_language = language or "en"

    # If requesting default language, return base content
    if current_language == translation_engine.get_fallback_language(content_type):
        return base_content

    # Get translation and merge
    translated_content = translation_engine.get_translated_content(
        content_type=content_type,
        content_id=content_id,
        language_code=current_language,
        base_content=base_content
    )

    return translated_content
```

#### Database Schema for Core Translations
```sql
-- Universal translations table for core content
CREATE TABLE table_translations (
    id SERIAL PRIMARY KEY,
    extension_id INTEGER,                    -- NULL for core content
    table_name TEXT NOT NULL,               -- 'pages', 'menus', 'settings'
    record_id INTEGER NOT NULL,             -- ID of the content record
    language_code TEXT NOT NULL,            -- 'bg', 'es', 'fr', etc.
    translation_data JSONB NOT NULL,        -- Translated field values
    translation_coverage DECIMAL(5,2),      -- % of fields translated
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(extension_id, table_name, record_id, language_code)
);

-- Content type registry
CREATE TABLE translation_content_types (
    id SERIAL PRIMARY KEY,
    content_type TEXT UNIQUE NOT NULL,      -- 'pages', 'menus', 'settings'
    translatable_fields JSONB NOT NULL,     -- ["title", "content", "description"]
    fallback_language TEXT DEFAULT 'en',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### Frontend Integration for Core Content
```vue
<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useI18n } from '@/utils/i18n';
import http from '@/utils/dynamic-http';

const { currentLanguage } = useI18n();

const pageContent = ref(null);

// Load content with translations
const loadContent = async (contentId: number) => {
  try {
    const response = await http.get(`/api/content/pages/${contentId}`, {
      params: { language: currentLanguage.value }
    });
    pageContent.value = response.data;
  } catch (error) {
    console.error('Failed to load content:', error);
  }
};

// Watch for language changes
watch(currentLanguage, (newLang) => {
  if (pageContent.value?.id) {
    loadContent(pageContent.value.id);
  }
});
</script>

<template>
  <div v-if="pageContent">
    <h1>{{ pageContent.title }}</h1>
    <div v-html="pageContent.content"></div>
  </div>
</template>
```

#### Admin Interface for Content Translation
```vue
<template>
  <div class="translation-manager">
    <div class="language-selector">
      <select v-model="selectedLanguage" @change="loadTranslations">
        <option v-for="lang in availableLanguages" :key="lang" :value="lang">
          {{ getLanguageName(lang) }}
        </option>
      </select>
    </div>

    <div v-if="selectedLanguage !== 'en'" class="translation-form">
      <div class="form-group">
        <label>Title ({{ selectedLanguage.toUpperCase() }})</label>
        <input v-model="translations.title" :placeholder="`Title in ${getLanguageName(selectedLanguage)}`" />
      </div>

      <div class="form-group">
        <label>Content ({{ selectedLanguage.toUpperCase() }})</label>
        <textarea v-model="translations.content" :placeholder="`Content in ${getLanguageName(selectedLanguage)}`"></textarea>
      </div>

      <button @click="saveTranslations" class="save-btn">
        Save {{ getLanguageName(selectedLanguage) }} Translation
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, watch } from 'vue';

const selectedLanguage = ref('bg');
const translations = reactive({
  title: '',
  content: ''
});

const saveTranslations = async () => {
  try {
    await http.post(`/api/content/pages/${contentId}/translations`, {
      language_code: selectedLanguage.value,
      translations: { ...translations }
    });
    // Show success message
  } catch (error) {
    console.error('Failed to save translations:', error);
  }
};
</script>
```

## 6. Extension Types

### Widget Extensions
- Type: `"widget"`
- Focus: Dashboard widgets
- Requires: `frontend_entry` and `frontend_editor`

### Full Extensions
- Type: `"extension"`
- Can have: Routes, database tables, full UI
- Most flexible type

### Language Packs
- Type: `"language"`
- Provide: UI translations
- Structure: Translation files only

### Themes
- Type: `"theme"`
- Provide: CSS/styling overrides

## 7. Testing and Deployment

### Development Testing
1. Place extension in `temp_ExtensionName_1.0.0/`
2. Upload via Extensions page
3. Test functionality
4. Check logs for errors

### Production Deployment
1. Move to `backend/extensions/` (installed by system)
2. Update manifest version for updates
3. Test upgrade scenarios

## 8. Best Practices

### Security
- Always validate user input
- Use parameterized queries
- Request minimal required permissions
- Sanitize HTML content

### Performance
- Use database indexes for frequently queried columns
- Implement pagination for large datasets
- Cache expensive operations
- Lazy load components when possible

### User Experience
- Provide clear error messages
- Use consistent UI patterns
- Support keyboard navigation
- Make settings intuitive

### Code Quality
- Use TypeScript for frontend components
- Follow Vue 3 Composition API patterns
- Write descriptive commit messages
- Document complex logic

## 9. Complete Example: StoreExtension

The StoreExtension demonstrates a full-featured e-commerce implementation with multilingual support:

### Key Features Implemented:
- ✅ **Complete CRUD operations** for products and categories
- ✅ **Multilingual content** with extension-specific translation tables
- ✅ **Image upload** with proper file handling and serving
- ✅ **Admin interface** with form state management
- ✅ **Public storefront** with translation merging
- ✅ **PostgreSQL compatibility** with proper syntax
- ✅ **Multilingual page editing** with dynamic product insertion
- ✅ **Cross-extension component sharing** (PagesExtension uses StoreExtension's ProductSelector)
- ✅ **Dynamic extension relationships** with automatic discovery
- ✅ **Advanced language switching** with proper content preservation

### Architecture Highlights:

**Backend Structure:**
```python
# Extension-specific tables
products_table = "ext_storeextension_products"
categories_table = "ext_storeextension_categories"
translations_table = "ext_storeextension_translations"

# Multilingual API endpoints
@router.post("/products/{product_id}/translations")
@router.get("/products/{product_id}/translations")
@router.delete("/products/{product_id}/translations/{language_code}")

# File upload with validation
@router.post("/upload-image")  # Saves to uploads/store/ directory
```

**Frontend Patterns:**
```vue
<!-- Multilingual forms with language selector -->
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

<!-- Translation merging for display -->
const translatedProduct = computed(() => {
  const translation = product.translations?.find(t => t.language_code === currentLanguage);
  return translation?.data ? { ...product, ...translation.data } : product;
});
```

**Advanced Multilingual Page Editing:**
```vue
<!-- Language tabs for page creation/editing -->
<div class="language-selector">
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

<!-- Content form that changes with language -->
<div class="form-group">
  <label>{{ t('pages.title') }} ({{ getLanguageName(newPageContentLanguage) }}) *</label>
  <input v-model="newPageTitle" />
</div>

<div class="form-group">
  <label>{{ t('pages.content') }} ({{ getLanguageName(newPageContentLanguage) }})</label>
  <textarea v-model="newPageContent" rows="8"></textarea>
</div>
```

**Language Switching Logic:**
```javascript
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
    newPageTitle.value = '';
    newPageContent.value = '';
  }
};
```

**Save Logic with Translations:**
```javascript
const submitCreatePage = async () => {
  // Get English content for base page creation
  const englishTranslation = newPageTranslations.value['en'];
  const englishTitle = englishTranslation ? englishTranslation.title : newPageTitle.value;
  const englishContent = englishTranslation ? englishTranslation.content : newPageContent.value;

  // Create page with English content
  const pageData = { title: englishTitle, content: englishContent, ... };
  const response = await http.post('/api/pages/create', formData);

  if (response.data.id) {
    const pageId = response.data.id;

    // Save current form content to translations
    newPageTranslations.value[newPageContentLanguage.value] = {
      title: newPageTitle.value,
      content: newPageContent.value
    };

    // Save translations for other languages
    await saveNewPageTranslations(pageId);
  }
};
```

**Database Design:**
```sql
-- Extension-specific translation table
CREATE TABLE ext_storeextension_translations (
    id SERIAL PRIMARY KEY,
    record_id INTEGER NOT NULL,           -- Links to products/categories
    language_code TEXT NOT NULL,          -- 'bg', 'es', etc.
    translation_data JSONB NOT NULL,      -- Translated fields
    translation_coverage DECIMAL(5,2),    -- % of fields translated
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(record_id, language_code)
);
```

## 10. Common Patterns

### CRUD Operations
```python
@router.get("/items")
def get_items(claims: dict = Depends(require_user)):
    result = context.execute_query(f"SELECT * FROM {table_name} WHERE user_id = :user_id", {"user_id": claims["user_id"]})
    return {"items": result}

@router.post("/items")
def create_item(item: dict, claims: dict = Depends(require_user)):
    result = context.execute_query(
        f"INSERT INTO {table_name} (user_id, title, content) VALUES (:user_id, :title, :content) RETURNING id",
        {"user_id": claims["user_id"], "title": item["title"], "content": item["content"]}
    )
    return {"id": result[0]["id"]}
```

### Settings Management
```vue
<script setup lang="ts">
import { ref } from 'vue';
import { useSettingsStore } from '@/stores/settings';

const settingsStore = useSettingsStore();
const extensionSettings = ref({});

// Load extension settings
const loadSettings = async () => {
  await settingsStore.loadSettings();
  extensionSettings.value = settingsStore.getExtensionSettings('ExtensionName');
};

// Save settings
const saveSettings = async () => {
  await settingsStore.updateExtensionSettings('ExtensionName', extensionSettings.value);
};
</script>
```

## 11. Troubleshooting

### Common Issues:

**1. Extension still accessible when disabled:**
- **Backend**: Ensure only enabled extensions are loaded in `main.py`
- **Frontend**: Verify `/api/extensions/public` filters by `is_enabled = True`
- **Security**: Disabled extensions should not have routes or API access

**2. Images not displaying (404 errors):**
- Check that files are saved to the correct directory (`uploads/extension-name/`)
- Verify backend static file mount points to the right location
- Ensure file permissions allow reading

**3. Translations not loading:**
- Verify extension-specific translation table exists
- Check that `extension_id` is properly cast to integer in queries
- Ensure translation data is valid JSON

**4. Form state persistence:**
- Always clear `editingItem.value = null` in cancel handlers
- Use separate functions for add vs edit operations

**5. PostgreSQL syntax errors:**
- Use `SERIAL` instead of `AUTOINCREMENT`
- Use lowercase table names without quotes
- Ensure proper parameter binding in queries

**6. JSON field queries:**
- Use `field::jsonb ? value` to check if value exists in JSON array
- Use `field::jsonb @> '[value]'` to check if array contains value
- Parse JSON strings properly in frontend: `JSON.parse(jsonString)`

**7. Category filtering with JSON arrays:**
```python
# Wrong - doesn't work with JSON arrays:
"categories LIKE :category"  # params["category"] = f"%{category}%"

# Correct - convert slug to ID, cast to string in Python:
category_result = execute_main_db_query("SELECT id FROM categories WHERE slug = :slug", {"slug": category})
if category_result:
    category_id = category_result[0]["id"]
    category_id_str = str(category_id)  # Cast to string for JSON ? operator
    query += " AND categories::jsonb ? :category_id"
    params["category_id"] = category_id_str
```

**8. PostgreSQL JSON operators:**
- `jsonb ? text` - Check if JSON object has key OR array contains string
- `jsonb @> jsonb` - Check if left contains right (for objects/arrays)
- `jsonb <@ jsonb` - Check if left is contained by right
- For arrays with numbers: Use `? value::text` to cast integer to string

**9. Multilingual form language switching issues:**
- **Problem**: Content from one language overwrites another when switching tabs
- **Solution**: Always save current form data to translations before switching languages
- **Pattern**:
```javascript
const switchContentLanguage = (lang: string) => {
  // Save current language data before switching
  contentTranslations.value[contentLanguage.value] = {
    title: currentTitle.value,
    content: currentContent.value
  };

  contentLanguage.value = lang;

  // Load data for new language
  const translation = contentTranslations.value[lang];
  if (translation) {
    currentTitle.value = translation.title || '';
    currentContent.value = translation.content || '';
  } else {
    currentTitle.value = '';
    currentContent.value = '';
  }
};
```

**10. Creating pages with translations - content not saving correctly:**
- **Problem**: When saving while on non-English language tab, wrong content gets saved
- **Solution**: Always use English content from translations for base page creation, save current form content to translations before saving
- **Pattern**:
```javascript
const submitCreatePage = async () => {
  // Get English content for base page creation
  const englishTranslation = newPageTranslations.value['en'];
  const englishTitle = englishTranslation ? englishTranslation.title : newPageTitle.value;
  const englishContent = englishTranslation ? englishTranslation.content : newPageContent.value;

  // Create page with English content first
  const pageData = { title: englishTitle, content: englishContent, ... };

  // Then save current form content to translations
  newPageTranslations.value[newPageContentLanguage.value] = {
    title: newPageTitle.value,
    content: newPageContent.value
  };

  // Save translations for other languages
  await saveNewPageTranslations(pageId);
};
```

**11. Database transaction commits with RETURNING clauses:**
- **Problem**: `context.execute_query` doesn't auto-commit for queries with RETURNING
- **Solution**: Use `execute_main_db_query` for critical operations or manually commit
- **Pattern**:
```python
def execute_main_db_query(query: str, params: dict = None):
    db = next(get_db())
    try:
        result = db.execute(text(query), params or {})
        rows = []
        if result.returns_rows:
            for row in result.fetchall():
                if hasattr(row, '_mapping'):
                    rows.append(dict(row._mapping))
                else:
                    rows.append(dict(row))
        db.commit()  # Always commit
        return rows
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()
```

**12. CSS vendor prefix warnings:**
- **Problem**: Linter warns about missing standard property for vendor prefixes
- **Solution**: Include both vendor-prefixed and standard properties
- **Pattern**:
```css
.product-name {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  line-clamp: 2;  /* Add standard property */
  overflow: hidden;
}
```

## 12. Implementing Multilingual Pages Extension

The PagesExtension can be extended to support multilingual content using the universal translation engine:

### Enhanced PagesExtension with Translations

```python
def initialize_extension(context):
    """Initialize the Pages extension with multilingual support"""
    try:
        table_name = "ext_PagesExtension"

        # Create pages table (existing code)
        # ... existing table creation code ...

        # Create translations table for pages
        translations_table = "ext_pagesextension_translations"
        execute_main_db_query(f"""
            CREATE TABLE IF NOT EXISTS "{translations_table}" (
                id SERIAL PRIMARY KEY,
                record_id INTEGER NOT NULL,
                language_code TEXT NOT NULL,
                translation_data JSONB NOT NULL,
                translation_coverage DECIMAL(5,2) DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(record_id, language_code)
            )
        """)

        router = APIRouter(prefix="/api/pages")

        # ... existing CRUD endpoints ...

        # Add translation endpoints
        @router.post("/{page_id}/translations")
        def add_page_translation(
            page_id: int,
            data: Dict[str, Any],
            claims: dict = Depends(require_user)
        ):
            """Add translation for a page"""
            language_code = data.get("language_code")
            translations = data.get("translations", {})

            if not language_code or not translations:
                raise HTTPException(status_code=400, detail="language_code and translations required")

            # Check page ownership
            page = context.execute_query(f'SELECT owner_id FROM "{table_name}" WHERE id = :id', {"id": page_id})
            if not page or str(page[0]["owner_id"]) != str(claims.get("user_id")):
                raise HTTPException(status_code=403, detail="No permission to translate this page")

            # Save translation
            execute_main_db_query(f"""
                INSERT INTO "{translations_table}"
                (record_id, language_code, translation_data, translation_coverage)
                VALUES (:record_id, :language_code, :translation_data, :coverage)
                ON CONFLICT (record_id, language_code) DO UPDATE SET
                    translation_data = EXCLUDED.translation_data,
                    translation_coverage = EXCLUDED.translation_coverage,
                    updated_at = CURRENT_TIMESTAMP
            """, {
                "record_id": page_id,
                "language_code": language_code,
                "translation_data": json.dumps(translations),
                "coverage": len(translations) / 2 * 100  # title, content
            })

            return {"message": f"Translation added for {language_code}"}

        @router.get("/{page_id}/translations")
        def get_page_translations(page_id: int, claims: dict = Depends(require_user)):
            """Get all translations for a page"""
            # Check ownership
            page = context.execute_query(f'SELECT owner_id FROM "{table_name}" WHERE id = :id', {"id": page_id})
            if not page or str(page[0]["owner_id"]) != str(claims.get("user_id")):
                raise HTTPException(status_code=403, detail="No permission to view translations")

            translations = execute_main_db_query(f"""
                SELECT language_code, translation_data, translation_coverage
                FROM "{translations_table}"
                WHERE record_id = :record_id
            """, {"record_id": page_id})

            return {
                "page_id": page_id,
                "translations": [{
                    "language_code": t["language_code"],
                    "data": json.loads(t["translation_data"]),
                    "coverage": float(t["translation_coverage"] or 0)
                } for t in translations or []]
            }

        # Enhanced page retrieval with translations
        @router.get("/by-slug/{slug}")
        def get_page_by_slug_with_translations(
            slug: str,
            language: str = None,
            authorization: Optional[str] = Header(default=None)
        ):
            """Get page by slug with automatic translation merging"""
            current_language = language or "en"

            # Get base page
            page = context.execute_query(f"""
                SELECT id, title, content, is_public, allowed_roles, owner_id
                FROM "{table_name}"
                WHERE slug = :slug
            """, {"slug": slug})

            if not page:
                raise HTTPException(status_code=404, detail="Page not found")

            page_data = page[0]

            # Check permissions (existing logic)
            # ... existing permission checks ...

            # If requesting non-English, try to get translation
            if current_language != "en":
                translation = execute_main_db_query(f"""
                    SELECT translation_data FROM "{translations_table}"
                    WHERE record_id = :record_id AND language_code = :language_code
                """, {
                    "record_id": page_data["id"],
                    "language_code": current_language
                })

                if translation and translation[0]["translation_data"]:
                    translation_data = json.loads(translation[0]["translation_data"])
                    # Merge translation with base content
                    page_data.update(translation_data)

            return {
                "id": page_data["id"],
                "title": page_data["title"],
                "content": page_data["content"],
                "language": current_language
            }

        context.register_router(router)

        return {
            "routes_registered": 7,  # Original 5 + 2 translation routes
            "tables_created": 2,     # pages + translations tables
            "status": "initialized"
        }

    except Exception as e:
        print(f"Pages extension initialization error: {e}")
        return {"status": "error", "error": str(e)}
```

### Frontend Pages Editor with Translations

```vue
<template>
  <div class="pages-editor">
    <!-- Language Selector -->
    <div class="language-tabs">
      <button
        v-for="lang in availableLanguages"
        :key="lang"
        :class="{ active: activeLanguage === lang }"
        @click="switchLanguage(lang)"
      >
        {{ getLanguageName(lang) }}
      </button>
    </div>

    <!-- Multilingual Content Form -->
    <div class="content-form">
      <div class="form-group">
        <label>{{ t('pageTitle', 'Page Title') }} *</label>
        <input
          v-model="currentPage.title"
          :placeholder="`${t('pageTitle', 'Page Title')} (${activeLanguage.toUpperCase()})`"
        />
      </div>

      <div class="form-group">
        <label>{{ t('pageContent', 'Page Content') }}</label>
        <textarea
          v-model="currentPage.content"
          :placeholder="`${t('pageContent', 'Page Content')} (${activeLanguage.toUpperCase()})`"
          rows="10"
        ></textarea>
      </div>

      <div class="form-actions">
        <button @click="savePage" class="save-btn">
          {{ t('save', 'Save') }} {{ getLanguageName(activeLanguage) }}
        </button>
      </div>
    </div>

    <!-- Translation Status -->
    <div class="translation-status">
      <h4>{{ t('translations', 'Translations') }}</h4>
      <div v-for="lang in availableLanguages" :key="lang" class="translation-item">
        <span>{{ getLanguageName(lang) }} ({{ lang.toUpperCase() }})</span>
        <span :class="getTranslationStatus(lang)">
          {{ getTranslationStatusText(lang) }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue';
import { useI18n } from '@/utils/i18n';
import http from '@/utils/dynamic-http';

const { t } = useI18n();

const activeLanguage = ref('en');
const availableLanguages = ref(['en', 'bg', 'es']);
const pageId = ref(null);

// Multilingual page data structure
const pageData = reactive({
  en: { title: '', content: '' },
  bg: { title: '', content: '' },
  es: { title: '', content: '' }
});

// Computed property for current language content
const currentPage = computed({
  get: () => pageData[activeLanguage.value] || { title: '', content: '' },
  set: (value) => {
    pageData[activeLanguage.value] = value;
  }
});

const switchLanguage = (lang: string) => {
  activeLanguage.value = lang;
};

const savePage = async () => {
  try {
    const content = currentPage.value;

    if (activeLanguage.value === 'en') {
      // Save base English content
      if (pageId.value) {
        await http.put(`/api/pages/${pageId.value}`, content);
      } else {
        const response = await http.post('/api/pages/create', content);
        pageId.value = response.data.id;
      }
    } else {
      // Save translation
      await http.post(`/api/pages/${pageId.value}/translations`, {
        language_code: activeLanguage.value,
        translations: content
      });
    }

    // Show success message
  } catch (error) {
    console.error('Failed to save page:', error);
  }
};

const getTranslationStatus = (lang: string) => {
  if (lang === 'en') return 'complete';
  const translation = pageData[lang];
  if (translation.title || translation.content) return 'partial';
  return 'missing';
};

const getTranslationStatusText = (lang: string) => {
  const status = getTranslationStatus(lang);
  return t(`translationStatus.${status}`, status);
};
</script>
```

This guide provides the foundation for creating robust, maintainable extensions that integrate seamlessly with the application ecosystem. The StoreExtension serves as a comprehensive reference implementation demonstrating advanced patterns for multilingual content, file uploads, and complex CRUD operations.
