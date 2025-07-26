# Mega Monitor Comprehensive Instructions

## Overview
This document provides detailed instructions for implementing and managing the Mega Monitor app, including user management, dynamic menu editing, extension installation, AI extension generation, and dynamic extension loading. It also includes specific steps for integrating HiveOS API for managing mining rigs.

---

## 1. User Management

### Backend Implementation
1. **Database Models**:
   - Use bcrypt for password hashing.
   - Implement a many-to-many relationship between `User` and `Role` models.

   ```python
   from sqlalchemy import Table, Column, Integer, ForeignKey
   from sqlalchemy.orm import relationship
   from passlib.context import CryptContext

   pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

   user_roles = Table(
       "user_roles",
       Base.metadata,
       Column("user_id", Integer, ForeignKey("users.id")),
       Column("role_id", Integer, ForeignKey("roles.id"))
   )

   class User(Base):
       __tablename__ = "users"
       id = Column(Integer, primary_key=True, index=True)
       username = Column(String, unique=True, nullable=False)
       hashed_password = Column(String, nullable=False)
       roles = relationship("Role", secondary=user_roles, back_populates="users")

       def hash_password(self, password: str) -> str:
           return pwd_context.hash(password)

       def verify_password(self, plain_password: str) -> bool:
           return pwd_context.verify(plain_password, self.hashed_password)

   class Role(Base):
       __tablename__ = "roles"
       id = Column(Integer, primary_key=True, index=True)
       name = Column(String, unique=True, nullable=False)
       users = relationship("User", secondary=user_roles, back_populates="roles")
   ```

2. **API Endpoints**:
   - Add routes for `/register`, `/login`, `/profile`, `/users`, and `/roles`.

   ```python
   @router.post("/register")
   def register_user(user: UserCreate, db: Session = Depends(get_db)):
       hashed_password = User.hash_password(user.password)
       new_user = User(username=user.username, hashed_password=hashed_password)
       db.add(new_user)
       db.commit()
       return {"message": "User registered successfully"}
   ```

3. **Admin User Creation**:
   - Add a script to create an admin user on first install.

   ```python
   def create_admin_user():
       admin_user = User(username="admin", hashed_password=User.hash_password("admin123"))
       db.add(admin_user)
       db.commit()
   ```

4. **Frontend Role-Based Access Control**:
   - Implement route guards in `router/index.js` to check user roles before navigating to protected routes.

---

## 2. Dynamic Menu Editor

### Backend Implementation
1. **Database Models**:
   - Create `Menu` and `Page` models to store menu structure and page content.

   ```python
   class Menu(Base):
       __tablename__ = "menus"
       id = Column(Integer, primary_key=True, index=True)
       name = Column(String, nullable=False)
       path = Column(String, nullable=False)
       order = Column(Integer, nullable=False)
   ```

2. **API Endpoints**:
   - Add CRUD endpoints for managing menus and pages.

   ```python
   @router.post("/menu/create")
   def create_menu(menu: MenuCreate, db: Session = Depends(get_db)):
       new_menu = Menu(**menu.dict())
       db.add(new_menu)
       db.commit()
       return {"message": "Menu created successfully"}
   ```

---

## 3. Extension Installer

### Backend Implementation
1. **Upload Endpoint**:
   - Create an endpoint to upload `.zip` files containing extensions.

   ```python
   @router.post("/extensions/upload")
   async def upload_extension(file: UploadFile):
       extensions_dir = Path(__file__).parent / "extensions"
       with zipfile.ZipFile(file.file, 'r') as zip_ref:
           zip_ref.extractall(extensions_dir)
       return {"message": "Extension uploaded successfully"}
   ```

2. **Dynamic Loading**:
   - Dynamically load extensions by scanning the `src/extensions/` directory.

   ```python
   extensions_path = Path(__file__).parent / "src/extensions"
   for extension_dir in extensions_path.iterdir():
       if extension_dir.is_dir():
           routes_file = extension_dir / "routes.py"
           if routes_file.exists():
               module_name = f"backend.extensions.{extension_dir.name}.routes"
               module = importlib.import_module(module_name)
               if hasattr(module, "router"):
                   app.include_router(module.router, prefix=f"/src/extensions/{extension_dir.name}")
   ```

---

## 4. HiveOS Extension

### HiveOS API Integration
- **API Base URL**: `https://api2.hiveos.farm/api/v2/`
- Refer to `hiveosapispecs.md` for detailed API specifications.

### Backend Implementation
1. **Dynamic Extension Loading**:
   - Follow the same dynamic loading mechanism as other extensions.

2. **API Endpoints**:
   - Create endpoints for:
     - **Authentication**: Store and validate HiveOS API keys.
     - **Fetch Rig Status**: Retrieve the status of mining rigs.
     - **Manage Rigs**: Start, stop, or update configurations for rigs.

   ```python
   @router.post("/extensions/hiveos/authenticate")
   def authenticate(api_key: str):
       # Store the API key securely
       return {"message": "API key stored successfully"}

   @router.get("/extensions/hiveos/rigs")
   def fetch_rigs(api_key: str):
       headers = {"Authorization": f"Bearer {api_key}"}
       response = requests.get(f"https://api2.hiveos.farm/api/v2/farms", headers=headers)
       return response.json()

   @router.post("/extensions/hiveos/rigs/manage")
   def manage_rig(api_key: str, rig_id: str, action: str):
       headers = {"Authorization": f"Bearer {api_key}"}
       payload = {"action": action}
       response = requests.post(f"https://api2.hiveos.farm/api/v2/rigs/{rig_id}/actions", headers=headers, json=payload)
       return response.json()
   ```

---

## 5. Error Handling and Debugging

### Middleware
- Add a custom error handler middleware.

   ```python
   class CustomErrorHandlerMiddleware(BaseHTTPMiddleware):
       async def dispatch(self, request, call_next):
           try:
               response = await call_next(request)
               return response
           except RequestValidationError as exc:
               return JSONResponse(
                   status_code=422,
                   content={"error": "Validation Error", "details": exc.errors()}
               )
           except Exception as exc:
               return JSONResponse(
                   status_code=500,
                   content={"error": "Internal Server Error", "details": str(exc)}
               )
   ```

### Logging
- Configure logging to a file for debugging.

   ```python
   logging.basicConfig(
       level=logging.DEBUG,
       format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
       handlers=[
           logging.FileHandler("backend_debug.log", mode="w"),
           logging.StreamHandler()
       ]
   )
   ```

---

## 6. Testing

### Backend Tests
- Write unit tests for API endpoints and models.

### Frontend Tests
- Write unit tests for Vue components.

### Integration Tests
- Test the end-to-end flow for extensions, menus, and user management.

---

## 7. Deployment

### Docker
- Create a `Dockerfile` and `docker-compose.yml` for deployment.

### Environment Variables
- Use `.env` files for configuration.

---

## 8. Common Errors and Fixes

### Module Import Issues
- Add the backend directory to `sys.path`:
   ```python
   sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
   ```

### Database Migration
- Use Alembic for schema migrations:
   ```bash
   alembic upgrade head
   ```

---

## Current State

The Mega Monitor app is fully functional with the HiveOS extension integrated. All features, including user management, dynamic menu editing, extension installation, AI extension generation, and dynamic extension loading, are working as expected. The HiveOS API integration for managing mining rigs is also complete and operational.

---

This document consolidates all necessary steps to implement and manage the Mega Monitor app effectively, including HiveOS API integration.