# Mega Monitor Extension Development Guide

## **1. Overview**
Extensions in Mega Monitor are modular components that can be dynamically loaded into the backend. Each extension should include its own models, routes, and any additional logic required for its functionality.

---

## **2. Extension Folder Structure**
Each extension should follow this structure:

```
extensions/
    <extension_name>/
        __init__.py
        models.py
        routes.py
        utils.py (optional)
```

- **`models.py`**: Defines the database models specific to the extension.
- **`routes.py`**: Contains the API endpoints for the extension.
- **`utils.py`**: Optional file for helper functions or utilities.

---

## **3. Steps to Create a New Extension**

### **Step 1: Create the Folder**
1. Navigate to the `extensions/` directory.
2. Create a new folder with the name of your extension (e.g., `my_extension`).

### **Step 2: Define Models**
1. Create a `models.py` file in the extension folder.
2. Define the database models using SQLAlchemy. Example:
   ```python
   from sqlalchemy import Column, Integer, String
   from backend.db.base import Base

   class MyExtensionModel(Base):
       __tablename__ = "my_extension_table"
       id = Column(Integer, primary_key=True, index=True)
       name = Column(String, nullable=False)
   ```

### **Step 3: Create Routes**
1. Create a `routes.py` file in the extension folder.
2. Define the API endpoints using FastAPI. Example:
   ```python
   from fastapi import APIRouter

   router = APIRouter()

   @router.get("/example")
   def example_endpoint():
       return {"message": "This is an example endpoint"}
   ```

### **Step 4: Add Utilities (Optional)**
1. If your extension requires helper functions, create a `utils.py` file.
2. Add reusable logic here.

### **Step 5: Test the Extension**
1. Write tests for the extension in the `tests/` directory.
2. Example test file: `test_my_extension.py`.

---

## **4. Dynamic Loading**
The backend automatically loads extensions by scanning the `extensions/` directory. Ensure the following:
1. The `routes.py` file contains a `router` object.
2. The `models.py` file defines all necessary database models.

---

## **5. Example Extension**
Here’s an example of a simple extension:

### **Folder Structure**
```
extensions/
    example_extension/
        __init__.py
        models.py
        routes.py
```

### **`models.py`**
```python
from sqlalchemy import Column, Integer, String
from backend.db.base import Base

class ExampleModel(Base):
    __tablename__ = "example_table"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
```

### **`routes.py`**
```python
from fastapi import APIRouter

router = APIRouter()

@router.get("/example")
def example_endpoint():
    return {"message": "Hello from Example Extension"}
```

---

## **6. Packaging the Extension**
1. Zip the extension folder (e.g., `example_extension.zip`).
2. Upload it using the `/extensions/upload` endpoint.

---

## **7. Testing the Extension**
1. Write tests in `tests/test_<extension_name>.py`.
2. Example test:
   ```python
   from fastapi.testclient import TestClient
   from backend.main import app

   client = TestClient(app)

   def test_example_endpoint():
       response = client.get("/extensions/example_extension/example")
       assert response.status_code == 200
       assert response.json() == {"message": "Hello from Example Extension"}
   ```

---

## **8. Common Issues**
- **Missing `router` in `routes.py`**: Ensure the `router` object is defined and imported.
- **Database Migration**: Use Alembic to handle schema changes for new models.

---

## **9. Deployment**
1. Ensure the extension is tested and zipped.
2. Upload the extension to the production server using the `/extensions/upload` endpoint.

---

# Mega Monitor Frontend Extension Development Guide

## **1. Overview**
Frontend extensions in Mega Monitor are modular components that integrate seamlessly with the backend extensions. Each frontend extension should include its own views, components, and logic to interact with the backend API.

---

## **2. Extension Folder Structure**
Each frontend extension should follow this structure:

```
frontend/extensions/
    <extension_name>/
        index.ts
        views/
            <ExtensionView>.vue
        components/
            <ReusableComponent>.vue (optional)
```

- **`index.ts`**: Entry point for the extension, exporting its routes and components.
- **`views/`**: Contains the main views for the extension.
- **`components/`**: Optional folder for reusable components specific to the extension.

---

## **3. Steps to Create a New Frontend Extension**

### **Step 1: Create the Folder**
1. Navigate to the `frontend/extensions/` directory.
2. Create a new folder with the name of your extension (e.g., `my_extension`).

### **Step 2: Define the View**
1. Create a `<ExtensionView>.vue` file in the `views/` folder.
2. Define the UI and logic for the extension. Example:
   ```vue
   <template>
     <div>
       <h1>My Extension</h1>
       <button @click="fetchData">Fetch Data</button>
       <p v-if="data">{{ data }}</p>
     </div>
   </template>

   <script>
   import axios from 'axios';

   export default {
     data() {
       return {
         data: null
       };
     },
     methods: {
       async fetchData() {
         const response = await axios.get('/extensions/my_extension/data');
         this.data = response.data;
       }
     }
   };
   </script>
   ```

### **Step 3: Add Routes**
1. Create an `index.ts` file in the extension folder.
2. Export the routes for the extension. Example:
   ```typescript
   import { RouteRecordRaw } from 'vue-router';
   import ExtensionView from './views/ExtensionView.vue';

   const routes: RouteRecordRaw[] = [
     {
       path: '/extensions/my_extension',
       name: 'MyExtension',
       component: ExtensionView
     }
   ];

   export default routes;
   ```

### **Step 4: Register the Extension**
1. Import the extension routes in the main router file (e.g., `frontend/src/router/index.ts`).
2. Add the routes to the router. Example:
   ```typescript
   import myExtensionRoutes from '@/extensions/my_extension';

   const routes = [
     ...existingRoutes,
     ...myExtensionRoutes
   ];
   ```

---

## **4. Example Frontend Extension**

### **Folder Structure**
```
frontend/extensions/
    example_extension/
        index.ts
        views/
            ExampleView.vue
```

### **`ExampleView.vue`**
```vue
<template>
  <div>
    <h1>Example Extension</h1>
    <button @click="fetchExampleData">Fetch Example Data</button>
    <p v-if="exampleData">{{ exampleData }}</p>
  </div>
</template>

<script>
import axios from 'axios';

export default {
  data() {
    return {
      exampleData: null
    };
  },
  methods: {
    async fetchExampleData() {
      const response = await axios.get('/extensions/example_extension/example');
      this.exampleData = response.data;
    }
  }
};
</script>
```

### **`index.ts`**
```typescript
import { RouteRecordRaw } from 'vue-router';
import ExampleView from './views/ExampleView.vue';

const routes: RouteRecordRaw[] = [
  {
    path: '/extensions/example_extension',
    name: 'ExampleExtension',
    component: ExampleView
  }
];

export default routes;
```

---

## **5. Testing the Extension**
1. Write unit tests for the views and components in the `tests/` directory.
2. Example test:
   ```typescript
   import { mount } from '@vue/test-utils';
   import ExampleView from '@/extensions/example_extension/views/ExampleView.vue';

   describe('ExampleView.vue', () => {
     it('renders correctly', () => {
       const wrapper = mount(ExampleView);
       expect(wrapper.text()).toContain('Example Extension');
     });
   });
   ```

---

## **6. Deployment**
1. Ensure the extension is tested and functional.
2. Package the extension folder and include it in the deployment pipeline.

---

This guide provides a clear roadmap for creating, testing, and deploying extensions for the Mega Monitor app.
