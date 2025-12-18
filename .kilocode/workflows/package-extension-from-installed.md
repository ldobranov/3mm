# Workflow — Package extension from installed/development location

Goal: Create a ZIP file from an extension that's already installed or being developed in the correct directory structure.

## Problem

The installer expects frontend files in a `frontend/` directory inside the ZIP, but when developing extensions, files are already in `frontend/src/extensions/Name_Version/`.

## Solution

Package the extension from its installed location, preserving the correct directory structure.

## 1) Extension structure in repo

Your extension should be in the correct locations:

```
backend/extensions/StoreExtension_1.0.0/
├── manifest.json
├── store_extension.py
├── locales/
│   ├── en.json
│   └── bg.json
└── database_schema.json

frontend/src/extensions/StoreExtension_1.0.0/
├── manifest.json
├── StoreExtension.vue
├── locales/
│   ├── en.json
│   └── bg.json
└── utils/
    └── currency.ts
```

## 2) Create ZIP with correct structure

From the repo root, create a ZIP that includes:

- Backend files: `backend/extensions/StoreExtension_1.0.0/*`
- Frontend files: `frontend/src/extensions/StoreExtension_1.0.0/*`
- Manifest: `backend/extensions/StoreExtension_1.0.0/manifest.json`

## 3) ZIP command

```bash
# Create ZIP with the correct internal structure
cd /path/to/repo
zip -r StoreExtension_1.0.0.zip \
    backend/extensions/StoreExtension_1.0.0/ \
    frontend/src/extensions/StoreExtension_1.0.0/
```

This creates a ZIP with:
```
StoreExtension_1.0.0.zip
├── backend/extensions/StoreExtension_1.0.0/manifest.json
├── backend/extensions/StoreExtension_1.0.0/store_extension.py
├── backend/extensions/StoreExtension_1.0.0/locales/en.json
├── frontend/src/extensions/StoreExtension_1.0.0/StoreExtension.vue
├── frontend/src/extensions/StoreExtension_1.0.0/utils/currency.ts
└── ...
```

**Alternative structure**: If your ZIP has `frontend/utils/currency.ts` (not the full path), the installer will still extract it correctly to the extension directory.

## 4) Upload the ZIP

The updated installer now recognizes files in `frontend/src/extensions/Name_Version/` structure and extracts them correctly.

## Alternative: Traditional ZIP structure

If you prefer the traditional approach, create a ZIP with:

```
StoreExtension_1.0.0.zip
├── manifest.json
├── backend/
│   └── store_extension.py
├── frontend/
│   ├── StoreExtension.vue
│   └── utils/
│       └── currency.ts
└── locales/
    ├── en.json
    └── bg.json
```

But this requires manually organizing files into the expected structure.

## Recommendation

Use the "from installed location" approach - it's simpler and matches how extensions are actually developed and stored in the repo.</content>
</xai:function_call