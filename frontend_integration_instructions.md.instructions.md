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
  - `PUT /menu/update`: Update a menu item (uses `MenuUpdate` schema).
  - `DELETE /menu/delete/{item_id}`: Delete a menu item by ID.
- **Settings Management**:
  - `POST /settings/create`: Create a setting.
  - `GET /settings/read`: Fetch all settings.
  - `PUT /settings/update`: Update a setting.
  - `DELETE /settings/delete/{item_id}`: Delete a setting.
- **Extensions**:
  - `GET /extensions`: Fetch all extensions.
  - `POST /upload`: Upload a new extension.
  - `POST /generate`: Generate an extension.
- **Authentication**:
  - `POST /register`: Register a new user.
  - `POST /login`: Login a user.
  - `GET /profile`: Fetch the logged-in user's profile.

### Request Payloads
- **Menu Item Update (`PUT /menu/update`)**:
  ```json
  {
    "id": "integer",
    "name": "string",
    "path": "string",
    "order": "integer"
  }
  ```

### Response Schemas
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

## Authentication

### JWT Handling
- **Storage**: Store the JWT token in `localStorage` or `sessionStorage` for persistence.
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

## Frontend Routes

### Navigation Structure
- `/menu`: Menu editor.

### Role-Based Access
- **Admin**:
  - Full access to all routes.
- **User**:
  - Access to `/dashboard` and `/profile` only.