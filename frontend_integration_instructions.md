# Frontend Integration Instructions

## Backend API Details

### Routes
A complete list of all backend API endpoints, including their HTTP methods:
- **User Management**:
  - `POST /user/create`: Create a new user.
  - `GET /user/read`: Fetch all users.
  - `PUT /user/update`: Update user details.
  - `DELETE /user/delete/{item_id}`: Delete a user by ID.
- **Role Management**:
  - `POST /role/create`: Create a new role.
  - `GET /role/read`: Fetch all roles.
  - `PUT /role/update`: Update role details.
  - `DELETE /role/delete/{item_id}`: Delete a role by ID.
- **Menu Management**:
  - `POST /menu/create`: Create a menu item.
  - `GET /menu/read`: Fetch all menu items.
  - `PUT /menu/update`: Update a menu item.
  - `DELETE /menu/delete/{item_id}`: Delete a menu item by ID.
- **Settings Management**:
  - `POST /settings/create`: Create a setting.
  - `GET /settings/read`: Fetch all settings.
  - `PUT /settings/update`: Update a setting.
  - `DELETE /settings/delete/{item_id}`: Delete a setting by ID.
- **Extensions**:
  - `GET /extensions`: Fetch all extensions.
  - `POST /upload`: Upload a new extension.
  - `POST /generate`: Generate an extension.
- **Authentication**:
  - `POST /register`: Register a new user.
  - `POST /login`: Login a user.
  - `GET /profile`: Fetch the logged-in user's profile.

### Request Payloads
- **User Creation (`POST /user/create`)**:
  ```json
  {
    "username": "string",
    "email": "string",
    "password": "string",
    "role": "string"
  }
  ```
- **Role Creation (`POST /role/create`)**:
  ```json
  {
    "name": "string"
  }
  ```
- **Menu Item Creation (`POST /menu/create`)**:
  ```json
  {
    "name": "string",
    "path": "string",
    "order": "integer"
  }
  ```
- **Settings Update (`PUT /settings/update`)**:
  ```json
  {
    "id": "integer",
    "name": "string",
    "value": "string"
  }
  ```

### Response Schemas
- **User Read (`GET /user/read`)**:
  ```json
  {
    "users": [
      {
        "id": "integer",
        "username": "string",
        "email": "string",
        "role": "string",
        "hashed_password": "string"
      }
    ]
  }
  ```
- **Menu Read (`GET /menu/read`)**:
  ```json
  {
    "items": [
      {
        "id": "integer",
        "name": "string",
        "path": "string",
        "order": "integer"
      }
    ]
  }
  ```
- **Error Responses**:
  - Validation errors:
    ```json
    {
      "detail": [
        { "loc": ["body", "field"], "msg": "field required", "type": "value_error" }
      ]
    }
    ```
  - Authentication errors:
    ```json
    {
      "detail": "Invalid credentials"
    }
    ```

## Authentication

### JWT Handling
- **Storage**: Store the JWT token in `localStorage` or `sessionStorage` for persistence.
- **Refresh**: Use a refresh token endpoint (if available) to renew expired tokens.
- **Headers**: Include the token in the `Authorization` header for protected API calls:
  ```
  Authorization: Bearer <token>
  ```

### Protected Routes
- **Routes requiring authentication**:
  - `/user/read`
  - `/menu/read`
  - `/settings/read`
  - `/extensions`
- **Role-based access**:
  - Admin-only routes: `/user/create`, `/role/create`, `/menu/create`, `/settings/create`.

## Frontend Routes

### Navigation Structure
- `/login`: Login page.
- `/dashboard`: Main dashboard.
- `/settings`: Settings management.
- `/users`: User management.
- `/roles`: Role management.
- `/menu`: Menu editor.
- `/extensions`: Extension manager.

### Role-Based Access
- **Admin**:
  - Full access to all routes.
- **User**:
  - Access to `/dashboard` and `/profile` only.
- **Guest**:
  - Access to `/login` and `/register` only.
