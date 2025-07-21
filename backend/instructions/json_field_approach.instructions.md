# JSON Field Approach for Dynamic Settings

## Overview
The JSON Field approach allows dynamic addition of settings fields without requiring schema changes. This is ideal for applications where settings need to be flexible and extensible.

---

## Implementation Plan

### 1. Database Models
#### Update the `Settings` Model:
- Replace individual columns with a single `data` column of type `JSON`.
- Example:
  ```python
  from sqlalchemy import Column, Integer, JSON
  from backend.db.base import Base

  class Settings(Base):
      __tablename__ = "settings"
      id = Column(Integer, primary_key=True, index=True)
      data = Column(JSON, nullable=False, default={})
  ```

#### Migration:
- Create a migration script to update the database schema.
- Example:
  ```python
  from alembic import op
  import sqlalchemy as sa

  def upgrade():
      op.add_column('settings', sa.Column('data', sa.JSON(), nullable=False, server_default='{}'))
      op.drop_column('settings', 'languages')
      op.drop_column('settings', 'site_name')
      op.drop_column('settings', 'menu')

  def downgrade():
      op.add_column('settings', sa.Column('languages', sa.String(), nullable=False))
      op.add_column('settings', sa.Column('site_name', sa.String(), nullable=False))
      op.add_column('settings', sa.Column('menu', sa.String(), nullable=True))
      op.drop_column('settings', 'data')
  ```

---

### 2. Pydantic Models
#### Update the `SettingsSchema`:
- Use a dictionary to represent dynamic fields.
- Example:
  ```python
  from pydantic import BaseModel

  class SettingsSchema(BaseModel):
      data: dict
  ```

---

### 3. CRUD Operations
#### Update `create_crud_routes`:
- Modify the `create`, `read`, `update`, and `delete` operations to handle the JSON field.
- Example:
  ```python
  def create_crud_routes(model: Any, model_name: str, pydantic_model: Type[BaseModel]):
      router = APIRouter()

      @router.post(f"/{model_name}/create")
      def create_item(item: pydantic_model, db: Session = Depends(get_db)):
          db_item = model(data=item.data)
          db.add(db_item)
          db.commit()
          return {"message": f"{model_name} created successfully"}

      @router.get(f"/{model_name}/read")
      def read_items(db: Session = Depends(get_db)):
          items = db.query(model).all()
          return {"items": [item.data for item in items]}

      @router.put(f"/{model_name}/update")
      def update_item(item: pydantic_model, db: Session = Depends(get_db)):
          db_item = db.query(model).filter(model.id == item.id).first()
          if not db_item:
              raise HTTPException(status_code=404, detail=f"{model_name} not found")
          db_item.data.update(item.data)
          db.commit()
          return {"message": f"{model_name} updated successfully"}

      @router.delete(f"/{model_name}/delete/{{item_id}}")
      def delete_item(item_id: int, db: Session = Depends(get_db)):
          db_item = db.query(model).filter(model.id == item_id).first()
          if not db_item:
              raise HTTPException(status_code=404, detail=f"{model_name} not found")
          db.delete(db_item)
          db.commit()
          return {"message": f"{model_name} deleted successfully"}

      return router
  ```

---

### 4. API Endpoints
#### Update Routes:
- Use the updated `create_crud_routes` function to handle dynamic settings.
- Example:
  ```python
  from backend.utils.crud import create_crud_routes
  from backend.db.settings import Settings
  from backend.routes.settings import SettingsSchema

  settings_crud_router = create_crud_routes(Settings, "settings", SettingsSchema)
  router.include_router(settings_crud_router)
  ```

---

### 5. Validation
#### Add Validation Logic:
- Use Pydantic models to validate the structure of the JSON data.
- Example:
  ```python
  class SettingsSchema(BaseModel):
      data: dict

      @validator("data")
      def validate_data(cls, value):
          if "app_name" in value and not isinstance(value["app_name"], str):
              raise ValueError("app_name must be a string")
          if "background_color" in value and not isinstance(value["background_color"], str):
              raise ValueError("background_color must be a string")
          return value
  ```

---

### 6. Testing
#### Update Test Cases:
- Modify tests to validate CRUD operations for the JSON field.
- Example:
  ```python
  def test_create_settings():
      response = client.post("/settings/create", json={"data": {"app_name": "Mega Monitor", "background_color": "#FFFFFF"}})
      assert response.status_code == 200
      assert response.json().get("message") == "settings created successfully"

  def test_read_settings():
      response = client.get("/settings/read")
      assert response.status_code == 200
      assert "items" in response.json()
  ```

---

### 7. Documentation
#### Update OpenAPI Documentation:
- Ensure the dynamic structure of the `data` field is reflected in the API documentation.

---

### 8. Additional Considerations
- **Frontend Integration**:
  - Update the frontend to handle dynamic settings.
  - Example: Use a form builder to dynamically generate fields based on the JSON structure.

- **Migration Strategy**:
  - Ensure existing data is migrated to the new JSON structure.

- **Performance**:
  - Optimize queries for the JSON field using database-specific features (e.g., PostgreSQL's JSONB).
