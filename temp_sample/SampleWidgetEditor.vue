<template>
  <div class="sample-widget-editor">
    <h4>Sample Widget Editor</h4>

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
        <h3>{{ localConfig.message || 'Hello from extension!' }}</h3>
        <p>This is a sample extension widget</p>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'SampleWidgetEditor',
  props: {
    config: {
      type: Object,
      default: () => ({})
    }
  },
  emits: ['update:modelValue'],
  data() {
    return {
      localConfig: {
        message: this.config.message || 'Hello from extension!',
        color: this.config.color || '#007bff'
      }
    }
  },
  computed: {
    previewStyle() {
      return {
        backgroundColor: this.localConfig.color || '#007bff',
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
        this.localConfig = { ...newConfig };
      },
      deep: true
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
.sample-widget-editor {
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