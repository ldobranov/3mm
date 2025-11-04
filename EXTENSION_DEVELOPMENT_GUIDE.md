# Mega Monitor Extension Development Guide

## Overview

Mega Monitor supports extensions that allow developers to add custom functionality to the dashboard system. Extensions can provide new widget types, themes, and backend API integrations.

## Extension Types

### Widget Extensions
Custom dashboard widgets that users can add to their displays. Can be frontend-only or full-stack with backend integration.

### Theme Extensions
Custom visual themes for the dashboard interface.

### Backend API Extensions
Server-side extensions that provide API integrations with external services.

## Extension Structure

Each extension must be packaged as a ZIP file containing:

```
extension.zip
├── manifest.json          # Extension metadata and configuration
├── frontend/              # Frontend components and assets
│   ├── Component.vue      # Main component (for widgets)
│   ├── ComponentEditor.vue # Editor component (for widgets)
│   └── [other files...]   # Additional frontend assets
└── backend/               # Backend module (optional)
    ├── system_monitor.py # Main backend module
    └── [other files...]   # Additional backend files
```

**Important**: The ZIP file should contain files directly - no wrapper folder with the extension name.

## Manifest File (`manifest.json`)

The manifest file defines the extension's metadata and capabilities:

```json
{
  "name": "SampleWidget",
  "version": "1.0.0",
  "type": "widget",
  "description": "A sample widget extension",
  "author": "Your Name",
  "dependencies": {},
  "entry_point": "SampleWidget.vue",
  "frontend_entry": "SampleWidget.vue",
  "frontend_editor": "SampleWidgetEditor.vue",
  "config_schema": {
    "type": "object",
    "properties": {
      "message": {
        "type": "string",
        "title": "Message",
        "default": "Hello from extension!"
      },
      "color": {
        "type": "string",
        "title": "Background Color",
        "format": "color",
        "default": "#007bff"
      }
    }
  },
  "permissions": []
}
```

### Manifest Fields

- `name`: Unique extension name (used for identification)
- `version`: Semantic version string (e.g., "1.0.0")
- `type`: Extension type ("widget", "theme", or "backend-api")
- `description`: Human-readable description
- `author`: Extension author name
- `dependencies`: Object mapping dependency names to version constraints
- `backend_entry`: Main backend module file (relative to backend/ directory)
- `frontend_entry`: Main Vue component file (do not include frontend/ prefix)
- `frontend_editor`: Editor Vue component file (do not include frontend/ prefix)
- `config_schema`: JSON Schema defining configuration options
- `permissions`: Array of required permissions

## Widget Extensions

### Main Component (`Component.vue`)

The main widget component that renders on the dashboard:

```vue
<template>
  <div class="my-widget" :style="widgetStyle">
    <h3>{{ config.message || 'Default message' }}</h3>
    <p>This is my custom widget</p>
  </div>
</template>

<script>
export default {
  name: 'MyWidget',
  props: {
    config: {
      type: Object,
      default: () => ({})
    }
  },
  computed: {
    widgetStyle() {
      return {
        backgroundColor: this.config.color || '#007bff',
        color: 'white',
        padding: '1rem',
        borderRadius: '8px',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        alignItems: 'center',
        textAlign: 'center'
      };
    }
  }
}
</script>
```

### Editor Component (`ComponentEditor.vue`)

The editor component for configuring the widget. **Important**: For extension widgets to properly save and load configuration, follow this exact pattern:

```vue
<template>
  <div class="widget-editor">
    <div class="form-group">
      <label for="message">Message:</label>
      <input
        id="message"
        v-model="localConfig.message"
        type="text"
        class="form-control"
        placeholder="Enter your message"
      />
    </div>

    <div class="form-group">
      <label for="color">Color:</label>
      <input
        id="color"
        v-model="localConfig.color"
        type="color"
        class="form-control"
      />
    </div>

    <div class="preview">
      <h5>Preview:</h5>
      <div class="preview-widget" :style="previewStyle">
        <h3>{{ localConfig.message || 'Preview' }}</h3>
        <p>Widget preview</p>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'MyWidgetEditor',
  props: {
    config: {
      type: Object,
      default: () => ({})
    }
  },
  emits: ['update:modelValue'],
  data() {
    return {
      localConfig: this.getDefaultConfig()
    }
  },
  methods: {
    getDefaultConfig() {
      const cfg = this.config || {};
      return {
        message: cfg.message || 'Default message',
        color: cfg.color || '#007bff'
      };
    }
  },
  computed: {
    previewStyle() {
      return {
        backgroundColor: this.localConfig.color,
        color: 'white',
        padding: '1rem',
        borderRadius: '8px',
        height: '150px',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        alignItems: 'center',
        textAlign: 'center',
        fontSize: '0.8rem'
      };
    }
  },
  watch: {
    config: {
      handler(newConfig) {
        // Only update if we have actual config data and it's different from current
        if (newConfig && Object.keys(newConfig).length > 0) {
          const newDefaults = this.getDefaultConfig();
          // Only update if the config actually changed
          if (JSON.stringify(this.localConfig) !== JSON.stringify(newDefaults)) {
            this.localConfig = newDefaults;
          }
        }
      },
      deep: true,
      immediate: true
    },
    localConfig: {
      handler() {
        this.$emit('update:modelValue', { ...this.localConfig });
      },
      deep: true
    }
  }
}
</script>

<style scoped>
.widget-editor {
  padding: 1rem;
}

.form-group {
  margin-bottom: 1rem;
}

.form-group label {
  display: block;
  margin-bottom: 0.5rem;
  font-weight: 500;
}

.form-control {
  width: 100%;
  padding: 0.5rem;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 0.9rem;
}

.preview {
  margin-top: 1.5rem;
  padding: 1rem;
  border: 1px solid #eee;
  border-radius: 8px;
  background-color: #f9f9f9;
}

.preview h5 {
  margin-bottom: 0.5rem;
  color: #666;
}

.preview-widget {
  border-radius: 4px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}
</style>
```

## Configuration Schema

Extensions can define configuration options using JSON Schema:

```json
{
  "config_schema": {
    "type": "object",
    "properties": {
      "apiKey": {
        "type": "string",
        "title": "API Key",
        "description": "Your API key for the service"
      },
      "refreshInterval": {
        "type": "number",
        "title": "Refresh Interval",
        "description": "How often to refresh data (seconds)",
        "default": 300,
        "minimum": 60,
        "maximum": 3600
      },
      "theme": {
        "type": "string",
        "title": "Theme",
        "enum": ["light", "dark", "auto"],
        "default": "auto"
      }
    },
    "required": ["apiKey"]
  }
}
```

## Development Workflow

### Frontend-Only Extensions
1. **Create Extension Files**: Develop your Vue components and manifest
2. **Test Locally**: Test your components in a development environment
3. **Package Extension**: Create a ZIP file with all required files
4. **Upload to Mega Monitor**: Use the Extensions page to upload and enable
5. **Test in Dashboard**: Add the widget to a display and configure it

### Full-Stack Extensions
1. **Design API**: Plan your backend API endpoints and data models
2. **Create Backend Module**: Implement initialization, routes, and database logic
3. **Create Frontend Components**: Develop Vue components with API integration
4. **Configure Permissions**: Define required permissions in manifest
5. **Test Backend Module**: Test backend functionality independently
6. **Package Extension**: Include both frontend and backend files
7. **Upload and Enable**: Extension backend will initialize automatically
8. **Test Integration**: Verify frontend-backend communication

### Backend Module Development

**File Structure:**
```
extension.zip
├── manifest.json
├── frontend/
│   ├── Component.vue
│   └── ComponentEditor.vue
└── backend/
    ├── system_monitor.py    # Main backend module (matches backend_entry)
    ├── routes.py            # Additional route definitions
    ├── models.py            # Database models
    └── services.py          # Business logic
```

**Backend Module Template:**
```python
# backend/system_monitor.py
from fastapi import APIRouter, HTTPException
from sqlalchemy import text

def initialize_extension(context):
    """Initialize extension when enabled"""

    # Register API routes
    router = APIRouter(prefix="/api/myextension")

    @router.get("/status")
    async def get_status():
        return {"status": "active", "version": "1.0.0"}

    @router.get("/data")
    async def get_data():
        # Query extension database
        results = context.execute_query("SELECT * FROM my_data")
        return {"data": results}

    @router.post("/data")
    async def create_data(data: dict):
        # Insert into extension database
        context.execute_query(
            "INSERT INTO my_data (value) VALUES (?)",
            [data["value"]]
        )
        return {"message": "Data created"}

    context.register_router(router)

    # Create database tables
    context.execute_query("""
        CREATE TABLE IF NOT EXISTS my_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            value TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    return {
        "routes_registered": 3,
        "tables_created": 1,
        "status": "initialized"
    }

def cleanup_extension(context):
    """Cleanup when extension is disabled"""
    # Optional: Clean up resources, stop background tasks
    pass
```

### Database Schema Definition

Extensions can define complex database schemas:

```json
{
  "database_schema": {
    "tables": {
      "metrics": {
        "columns": {
          "timestamp": {"type": "datetime", "nullable": false},
          "cpu_usage": {"type": "float", "nullable": false},
          "memory_usage": {"type": "float", "nullable": false}
        }
      },
      "alerts": {
        "columns": {
          "metric": {"type": "string", "nullable": false},
          "threshold": {"type": "float", "nullable": false},
          "active": {"type": "boolean", "nullable": false, "default": true}
        }
      }
    }
  }
}
```

### Security Best Practices

**Backend Extensions:**
- Declare minimal required permissions
- Validate all input data
- Use parameterized queries for database access
- Handle errors gracefully without exposing sensitive information
- Clean up resources in cleanup_extension()

**Permission Examples:**
```json
{
  "permissions": [
    "system_read",     // Read CPU, memory, disk stats
    "network_access",  // Make HTTP requests
    "database_write"   // Create/modify extension tables
  ]
}
```

## Quick Start Template

To create a new extension quickly, copy the `SampleWidget_1.0.0` directory structure:

```
frontend/src/extensions/
└── YourWidgetName_1.0.0/
    ├── manifest.json
    ├── YourWidgetName.vue
    └── YourWidgetNameEditor.vue
```

Use the existing `SampleWidget_1.0.0` and `CalendarWidget_1.0.0` as templates for your new extensions.

## Best Practices

### Component Design
- Use Vue 3 Composition API or Options API consistently
- Follow Vue SFC best practices with `<template>`, `<script>`, and `<style>` sections
- Make components responsive and accessible
- Use scoped styles to avoid conflicts

### Configuration
- Provide sensible defaults for all configuration options
- Use JSON Schema to validate configuration
- Include helpful descriptions and titles
- Consider backward compatibility when updating schemas

### Security
- Validate all user inputs
- Sanitize data before rendering
- Use HTTPS for external API calls
- Don't store sensitive data in client-side configuration

### Performance
- Lazy load heavy components when possible
- Optimize images and assets
- Minimize bundle size
- Use efficient Vue reactivity patterns
- Avoid infinite reactive loops by comparing config changes before updating
- Debounce frequent updates to prevent excessive re-renders

## Extension Types

### Frontend-Only Widgets
Simple extensions that only provide UI components. These are the original extension type and remain fully supported.

### Full-Stack Extensions
Advanced extensions with both frontend and backend components. These can:
- Register API routes dynamically
- Create and manage database tables
- Access system resources (with permissions)
- Run background tasks
- Communicate with external services

**Chart.js Integration**: For extensions using Chart.js with time-based charts, install the date adapter:
```bash
npm install chartjs-adapter-date-fns
```

And import it in your component:
```javascript
import Chart from 'chart.js/auto';
import 'chartjs-adapter-date-fns';
```

## Backend Extensions

Extensions can now include backend modules that run server-side with full access to system resources (subject to permissions).

### Backend Module Structure

```python
# backend_extension.py
def initialize_extension(context):
    """Called when extension is enabled"""
    # Register routes
    router = APIRouter(prefix="/api/extension/myextension")
    # ... define routes ...

    context.register_router(router)

    # Create database tables
    context.execute_query("""
        CREATE TABLE IF NOT EXISTS ext_myextension_data (
            id INTEGER PRIMARY KEY,
            data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    return {"routes_registered": 1, "tables_created": 1}

def cleanup_extension(context):
    """Called when extension is disabled"""
    # Cleanup resources
    pass
```

### Manifest Configuration

```json
{
  "name": "MyExtension",
  "version": "1.0.0",
  "type": "widget",
  "backend_entry": "backend_extension.py",
  "permissions": ["system_read", "database_write"],
  "dependencies": {
    "psutil": ">=5.9.0",
    "requests": ">=2.25.0"
  },
  "config_schema": { ... }
}
```

### Permissions System

Extensions must declare permissions for sensitive operations:

- `system_read`: Access system information (CPU, memory, disk usage)
- `network_access`: Make HTTP requests to external services
- `file_system`: Read/write files (restricted paths only)
- `database_write`: Create/modify extension database tables
- `process_control`: Start/stop system processes

### Database Access

Extensions get isolated database access with automatic table prefixing:

```python
# In extension backend module
def initialize_extension(context):
    # Create extension-specific tables
    context.execute_query("""
        CREATE TABLE IF NOT EXISTS my_data (
            id INTEGER PRIMARY KEY,
            value TEXT
        )
    """)

    # Insert data
    context.execute_query(
        "INSERT INTO my_data (value) VALUES (?)",
        ["example"]
    )

    # Query data
    results = context.execute_query("SELECT * FROM my_data")
    return results
```

### Route Registration

Extensions can register API endpoints dynamically:

```python
def initialize_extension(context):
    router = APIRouter(prefix="/api/myextension")

    @router.get("/status")
    async def get_status():
        return {"status": "running"}

    @router.post("/data")
    async def create_data(data: dict):
        # Store data in extension database
        context.execute_query(
            "INSERT INTO my_data (value) VALUES (?)",
            [data["value"]]
        )
        return {"id": "new_id"}

    context.register_router(router)
    return {"routes_registered": 2}
```

## Example Extensions

### Calendar Widget (Frontend-Only)
- Displays a fully functional calendar with dates and events
- Configurable title, colors, and display options
- Supports week numbers and today highlighting

### Sample Widget (Frontend-Only)
- Basic example widget with configurable message and color
- Demonstrates extension structure and configuration
- Includes both main component and editor

### System Monitor (Full-Stack)
- Shows real-time system metrics (CPU, memory, disk, network)
- Backend collects metrics using psutil
- Stores historical data in extension database
- Registers API endpoints for data access
- Permissions: `system_read`, `database_write`

### Weather Widget (Full-Stack)
- Fetches weather data from external APIs
- Caches data in extension database
- Updates periodically in background
- Permissions: `network_access`, `database_write`

### RSS Feed Reader (Full-Stack)
- Aggregates content from RSS/Atom feeds
- Stores articles in extension database
- Background task for feed updates
- Permissions: `network_access`, `database_write`

## Troubleshooting

### Common Issues

**Component not loading**: Check that the manifest references the correct file names and that all required files are included in the ZIP.

**Configuration not saving**: Ensure the editor emits `update:modelValue` events and that the config schema is valid. For extension widgets, make sure the editor component follows the exact pattern shown above with proper config merging and watch handlers.

**Configuration not persisting**: If the editor shows default values instead of saved values, check that the config watch handler properly merges saved config with defaults, and that the component avoids infinite reactive loops by comparing config changes before updating.

**Styling issues**: Use scoped styles and avoid conflicts with existing CSS classes.

**API errors**: Check network requests in browser dev tools and ensure proper error handling.

### Debug Tips

**Frontend Extensions:**
- Use browser dev tools to inspect component rendering
- Check the browser console for Vue warnings and errors
- Verify manifest syntax with a JSON validator
- Test components in isolation before packaging
- For config issues, add temporary console.log statements to watch handlers to trace config flow
- Check that config changes are properly debounced to avoid infinite reactive loops

**Backend Extensions:**
- Check server logs for extension initialization messages
- Verify backend_entry file exists and is properly structured
- Test backend module independently before packaging
- Use database tools to inspect extension tables
- Check API endpoints are registered correctly

**Security Issues:**
- Review extension permissions in manifest
- Check sandbox restrictions aren't blocking legitimate operations
- Verify external API calls are allowed by permissions
- Monitor resource usage for performance issues

### Extension Development Best Practices

**Security:**
- Request minimal permissions needed
- Validate all external data inputs
- Use parameterized database queries
- Handle errors without exposing sensitive information
- Clean up resources in cleanup_extension()

**Performance:**
- Cache frequently accessed data
- Use efficient database queries
- Limit API call frequency
- Monitor memory usage in long-running extensions

**Compatibility:**
- Test extensions on target platforms
- Handle missing dependencies gracefully
- Provide fallbacks for restricted operations
- Document system requirements

**Maintenance:**
- Version extensions properly
- Document breaking changes
- Provide migration scripts for data changes
- Support graceful degradation

## Support

For extension development support, refer to the Mega Monitor documentation or community forums.