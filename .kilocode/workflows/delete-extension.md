# Workflow — Delete an extension (backend + frontend + files)

Goal: safely remove an extension and all its data/files.

## 1) Confirm what will be deleted

- DB records + tables (if `deleteData=true`)
- Extension files (backend + frontend)
- Uploaded files (images, etc. in `uploads/extension-name/`)
- Language pack records (if applicable)

## 2) Disable extension first

- Set `is_enabled=false` via PATCH `/api/extensions/{id}` to trigger cleanup.

## 3) Delete via API

- Call DELETE `/api/extensions/{id}?deleteData=true&deleteFiles=true` (see [`backend/routes/extension_routes.py`](backend/routes/extension_routes.py:783)).

This automatically:
- Cleans up backend routes
- Drops extension tables (if `deleteData=true`)
- Removes extension directories under `backend/extensions/` and `frontend/src/extensions/`
- Removes uploaded files (if `deleteFiles=true`)
- Removes language pack records
- Deletes extension DB record

## 4) Manual file cleanup (if needed)

If the API deletion misses uploaded files (e.g., images in `uploads/store/` for StoreExtension):

- Check `uploads/{extensionName}/` directory
- Remove directory and contents: `rm -rf uploads/{extensionName}/`

## 5) Verify cleanup

- Confirm extension no longer appears in Extensions UI
- Check DB: no extension tables/records remain
- Check filesystem: no extension directories remain
- Check uploads: no orphaned files remain

## Table naming rules (critical for deletion)

Extensions must create tables with consistent naming:

- **Correct**: `ext_{extension.name.lower()}_table` (lowercase)
- **Example**: PagesExtension → `ext_pagesextension_table`
- **Deletion query**: looks for `ext_{extension.name.lower()}%` (case-sensitive)

**✅ Fixed**: All extensions now use lowercase table names for proper deletion.