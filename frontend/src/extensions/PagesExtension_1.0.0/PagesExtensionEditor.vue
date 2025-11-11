<template>
  <div class="pages-extension-editor">
    <div class="editor-section">
      <h4>Pages Extension Settings</h4>

      <div class="form-group">
        <label class="checkbox-label">
          <input
            type="checkbox"
            v-model="localConfig.defaultPublic"
          />
          Make pages public by default
        </label>
      </div>

      <div class="form-group">
        <label class="checkbox-label">
          <input
            type="checkbox"
            v-model="localConfig.allowAnonymousRead"
          />
          Allow anonymous users to read public pages
        </label>
      </div>

      <div class="form-group">
        <label class="checkbox-label">
          <input
            type="checkbox"
            v-model="localConfig.enableRichEditor"
          />
          Enable rich text editor
        </label>
      </div>

      <div class="form-group">
        <label for="maxPageSize">Maximum page content size (KB):</label>
        <input
          id="maxPageSize"
          v-model.number="localConfig.maxPageSize"
          type="number"
          class="form-control"
          min="100"
          max="10000"
          step="100"
        />
      </div>

      <div class="form-group">
        <label for="autoSaveInterval">Auto-save interval (seconds):</label>
        <input
          id="autoSaveInterval"
          v-model.number="localConfig.autoSaveInterval"
          type="number"
          class="form-control"
          min="30"
          max="300"
          step="30"
        />
      </div>
    </div>

    <div class="preview-section">
      <h4>Preview</h4>
      <div class="editor-preview" :style="previewStyle">
        <div class="preview-header">
          <h3>Pages Management</h3>
          <div class="preview-status">
            <span class="status-dot"></span>
            Extension Active
          </div>
        </div>

        <div class="preview-content">
          <p><strong>Configuration:</strong></p>
          <ul>
            <li>Default Public: {{ localConfig.defaultPublic ? 'Yes' : 'No' }}</li>
            <li>Anonymous Read: {{ localConfig.allowAnonymousRead ? 'Yes' : 'No' }}</li>
            <li>Rich Editor: {{ localConfig.enableRichEditor ? 'Yes' : 'No' }}</li>
            <li>Max Size: {{ localConfig.maxPageSize }}KB</li>
            <li>Auto-save: {{ localConfig.autoSaveInterval }}s</li>
          </ul>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'PagesExtensionEditor',
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
        defaultPublic: cfg.defaultPublic !== false,
        allowAnonymousRead: cfg.allowAnonymousRead !== false,
        enableRichEditor: cfg.enableRichEditor !== false,
        maxPageSize: cfg.maxPageSize || 1000,
        autoSaveInterval: cfg.autoSaveInterval || 60
      };
    }
  },
  computed: {
    previewStyle() {
      return {
        backgroundColor: '#ffffff',
        color: '#333333',
        padding: '1rem',
        borderRadius: '8px',
        border: '1px solid #ddd',
        minHeight: '200px',
        fontFamily: 'system-ui, -apple-system, sans-serif',
        fontSize: '0.9rem'
      };
    }
  },
  watch: {
    config: {
      handler(newConfig) {
        if (newConfig && Object.keys(newConfig).length > 0) {
          const newDefaults = this.getDefaultConfig();
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
.pages-extension-editor {
  padding: 1rem;
}

.editor-section {
  margin-bottom: 2rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid #eee;
}

.editor-section:last-child {
  border-bottom: none;
}

.editor-section h4 {
  margin: 0 0 1rem 0;
  color: #333;
  font-size: 1rem;
  font-weight: 600;
}

.form-group {
  margin-bottom: 1rem;
}

.form-group label {
  display: block;
  margin-bottom: 0.5rem;
  font-weight: 500;
  color: #555;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  font-weight: normal !important;
}

.checkbox-label input[type="checkbox"] {
  margin: 0;
  width: auto;
}

.form-control {
  width: 100%;
  padding: 0.5rem;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 0.9rem;
}

.preview-section {
  margin-top: 2rem;
}

.preview-section h4 {
  margin-bottom: 1rem;
}

.editor-preview {
  font-family: system-ui, -apple-system, sans-serif;
}

.preview-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.preview-header h3 {
  margin: 0;
  font-size: 1rem;
}

.preview-status {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.8rem;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: #28a745;
}

.preview-content {
  color: #666;
}

.preview-content ul {
  margin: 0.5rem 0;
  padding-left: 1.5rem;
}

.preview-content li {
  margin-bottom: 0.25rem;
}
</style>