# Platform Requirements and Approach

## Requirements for the Platform

### 1. Authentication
- Secure login and registration using JWT (JSON Web Tokens).
- Password hashing with bcrypt for secure storage.
- Role-based access control to restrict access to certain features based on user roles.

### 2. User Management
- CRUD operations for users:
  - Create, read, update, and delete users.
- Role management:
  - Assign roles to users.
  - Create and manage roles.

### 3. Dynamic Menu Editor
- Ability to add, edit, and delete menu items and submenus.
- Save menu structure to the backend.
- Fetch menu items dynamically via `/menu/read` endpoint.

### 4. Settings Management
- Admin settings for configuring the platform.
- Ability to update settings such as site name, languages, and other preferences.
- Fetch settings dynamically via `/settings/read` endpoint.

### 5. Extension Installer
- Upload `.zip` files to install extensions.
- Validate and extract extensions securely.
- Enable or disable extensions.

---

## Backend Information

### Framework
- **FastAPI**: Used for API development.

### Database Models
- **User**: Includes fields for `username`, `email`, `password`, and `role`.
- **Menu**: Includes fields for `id`, `name`, `path`, and `order`.
- **Settings**: Stores dynamic settings in a JSON field.
- **Extension**: Manages uploaded extensions.

### API Endpoints

#### Menu Management
- **POST** `/menu/create`: Create a menu item.
- **GET** `/menu/read`: Fetch menu items.
- **PUT** `/menu/update`: Update a menu item.
- **DELETE** `/menu/delete/{item_id}`: Delete a menu item.

#### Page Management
- **POST** `/pages/create`: Create a page.
- **GET** `/pages/read`: Fetch pages.
- **PUT** `/pages/update`: Update a page.
- **DELETE** `/pages/delete/{item_id}`: Delete a page.

#### Settings Management
- **POST** `/settings/create`: Create a setting.
- **GET** `/settings/read`: Fetch settings.
- **PUT** `/settings/update`: Update a setting.
- **DELETE** `/settings/delete/{item_id}`: Delete a setting.

#### User Management
- **POST** `/user/create`: Create a user.
- **GET** `/user/read`: Fetch users.
- **PUT** `/user/update`: Update a user.
- **DELETE** `/user/delete/{item_id}`: Delete a user.

#### Role Management
- **POST** `/role/create`: Create a role.
- **GET** `/role/read`: Fetch roles.
- **PUT** `/role/update`: Update a role.
- **DELETE** `/role/delete/{item_id}`: Delete a role.

#### Extensions
- **GET** `/extensions`: Get extensions.
- **POST** `/upload`: Upload an extension.
- **POST** `/generate`: Generate an extension.


#### Authentication
- **POST** `/register`: Register a user.
- **POST** `/login`: Login a user.
- **GET** `/profile`: Fetch user profile.

#### Miscellaneous
- **GET** `/users`: List users.
- **GET** `/roles`: List roles.

---

## Approach

### Frontend
- Use Vue.js for the user interface.
- Implement modular components for authentication, user management, menu editor, settings, and extensions.
- Use Pinia or Vuex for state management.
- Integrate Axios for API calls to the backend.

### Testing
- Write unit tests for backend API endpoints.
- Write frontend tests for components and functionality.

### Deployment
- Ensure the platform is deployable with Docker or similar tools.

---

## Notes for Frontend Development
- Use the backend API endpoints for data fetching and manipulation.
- Ensure proper error handling for API calls.
- Align frontend components with backend models and endpoints.
- Use environment variables (e.g., `VITE_API_BASE_URL`) for dynamic backend URL configuration.

---

## Additional Information for Frontend Development

### 1. Backend Response Structure
- **Example Response for `/menu/read`**:
  ```json
  {
    "items": [
      { "id": 1, "name": "Home", "path": "/", "order": 1 },
      { "id": 2, "name": "Settings", "path": "/settings", "order": 2 }
    ]
  }
  ```

- **Example Response for `/settings/read`**:
  ```json
  {
    "items": [
      { "id": 1, "name": "Mega Monitor", "language": "en", "data": { "additional_data": "test data" } }
    ]
  }
  ```
- **Example Response for `/user/read`**:
  ```json
  {
  "users": [
      { "id": 1, "username": "admin", "email": "admin@example.com", "role": "admin" },
      { "id": 2, "username": "user", "email": "user@example.com", "role": "user" }
    ]
  }
  ```


### 2. Authentication Flow
- **JWT Handling**:
  - Tokens are issued upon login and expire after a set duration (e.g., 1 hour).
  - Refresh tokens can be used to obtain new access tokens.
- **Headers for Authenticated Requests**:
  - Include Authorization: Bearer <token> in the headers for protected endpoints.

### 3. Design Guidelines
- **UI/UX Requirements**:
  - Use a clean and responsive design.
  - Preferred CSS framework: TailwindCSS.
  - Ensure accessibility and mobile-friendly layouts.

### 4. Error Handling
- **Expected Error Responses**:
  - Validation errors:
    ```json
    {
      "detail": [
        { "loc": ["body", "username"], "msg": "field required", "type": "value_error" }
      ]
    }
    ```
  - Authentication errors:
    ```json
    {
      "detail": "Invalid credentials"
    }
    ```

- **Frontend Guidelines**:
  - Display user-friendly error messages.
  - Use toast notifications for success and error messages.
  - Implement retry logic for failed API calls where appropriate.
  - Display error messages clearly near the relevant input fields.

---

### Alembic Migration Commands

To create and apply Alembic migrations, use the following commands:

1. **Set the `PYTHONPATH` environment variable**:
   ```bash
   export PYTHONPATH=/home/laz/3mm/backend
   ```

2. **Apply migrations**:
   ```bash
   PYTHONPATH=/home/laz/3mm/backend python -m alembic -c /home/laz/3mm/backend/alembic.ini upgrade head
   ```

3. **Generate a new migration**:
   ```bash
   PYTHONPATH=/home/laz/3mm/backend python -m alembic -c /home/laz/3mm/backend/alembic.ini revision --autogenerate -m "Update Settings schema"
   ```

---

# Ensure the backend runs on port 8887
# Note: This is a fixed requirement and should not be changed.

# Updated instructions to emphasize using the existing CRUD functionality for managing resources.
# Avoid adding separate endpoints like `/pages/create` unless absolutely necessary.
# Leverage the `crud.py` utility for all CRUD operations to ensure consistency and avoid hardcoding routes.

