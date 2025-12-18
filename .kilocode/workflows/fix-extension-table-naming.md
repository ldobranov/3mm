# Workflow — Fix extension table naming for proper deletion

Goal: ensure extension tables follow the naming convention so they can be properly deleted.

## Problem

StoreExtension creates tables like `ext_storeextension_products` but deletion looks for `ext_StoreExtension%`. This causes tables to not be dropped during deletion.

## Solution

Update extension table naming to match the deletion query pattern.

## 1) Identify affected extensions

Check extensions that create tables dynamically (not via database_schema.json):

- StoreExtension (creates 9 tables)
- Any other extensions that create tables in initialize_extension()

## 2) Update table naming logic

In extension's `initialize_extension()` function:

**Before (wrong):**
```python
products_table = "ext_storeextension_products"
```

**After (correct):**
```python
# Get consistent base name
base_name = context.extension_id.split('_')[0].lower()  # "storeextension"
products_table = f"ext_{base_name}_products"
```

## 3) Update all table references

Find all places in the extension code that reference the old table names and update them.

## 4) Migration strategy

For existing installations:

- Add migration logic to rename existing tables
- Or provide upgrade path that recreates tables with correct names

## 5) Test deletion

After fix:

- Delete extension with `deleteData=true`
- Verify tables are properly dropped
- Verify no orphaned tables remain

## Prevention

Going forward, all extensions should use this pattern:

```python
def initialize_extension(context):
    # Get consistent base name for all tables
    base_name = context.extension_id.split('_')[0].lower()
    
    # Create table names
    products_table = f"ext_{base_name}_products"
    categories_table = f"ext_{base_name}_categories"
    # etc.
```</content>
</xai:function_call