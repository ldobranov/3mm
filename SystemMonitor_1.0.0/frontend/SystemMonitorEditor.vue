<template>
  <div class="system-monitor-editor">
    <div class="editor-section">
      <h4>Basic Settings</h4>

      <div class="form-group">
        <label for="title">Widget Title:</label>
        <input
          id="title"
          v-model="localConfig.title"
          type="text"
          class="form-control"
          placeholder="System Monitor"
        />
      </div>

      <div class="form-group">
        <label for="displayMode">Display Mode:</label>
        <select
          id="displayMode"
          v-model="localConfig.displayMode"
          class="form-control"
        >
          <option value="compact">Compact</option>
          <option value="detailed">Detailed</option>
          <option value="chart">Chart</option>
        </select>
      </div>

      <div class="form-group">
        <label for="refreshInterval">Refresh Interval (seconds):</label>
        <input
          id="refreshInterval"
          v-model.number="localConfig.refreshInterval"
          type="number"
          class="form-control"
          min="5"
          max="300"
          step="5"
        />
      </div>
    </div>

    <div class="editor-section">
      <h4>Metrics to Display</h4>

      <div class="checkbox-group">
        <label class="checkbox-label">
          <input
            type="checkbox"
            value="cpu"
            v-model="localConfig.metrics"
          />
          CPU Usage
        </label>

        <label class="checkbox-label">
          <input
            type="checkbox"
            value="memory"
            v-model="localConfig.metrics"
          />
          Memory Usage
        </label>

        <label class="checkbox-label">
          <input
            type="checkbox"
            value="disk"
            v-model="localConfig.metrics"
          />
          Disk Usage
        </label>

        <label class="checkbox-label">
          <input
            type="checkbox"
            value="network"
            v-model="localConfig.metrics"
          />
          Network I/O
        </label>
      </div>
    </div>

    <div class="editor-section">
      <h4>Appearance</h4>

      <div class="form-group">
        <label for="backgroundColor">Background Color:</label>
        <div class="color-input-group">
          <input
            id="backgroundColor"
            v-model="localConfig.backgroundColor"
            type="color"
            class="form-control color-input"
          />
          <input
            type="text"
            v-model="localConfig.backgroundColor"
            class="form-control color-text"
            placeholder="#ffffff"
          />
        </div>
      </div>

      <div class="form-group">
        <label for="textColor">Text Color:</label>
        <div class="color-input-group">
          <input
            id="textColor"
            v-model="localConfig.textColor"
            type="color"
            class="form-control color-input"
          />
          <input
            type="text"
            v-model="localConfig.textColor"
            class="form-control color-text"
            placeholder="#333333"
          />
        </div>
      </div>
    </div>

    <div v-if="localConfig.displayMode === 'chart'" class="editor-section">
      <h4>Chart Settings</h4>

      <div class="form-group">
        <label for="chartType">Chart Type:</label>
        <select
          id="chartType"
          v-model="localConfig.chartType"
          class="form-control"
        >
          <option value="line">Line Chart</option>
          <option value="area">Area Chart</option>
          <option value="bar">Bar Chart</option>
        </select>
      </div>

      <div class="form-group">
        <label class="checkbox-label">
          <input
            type="checkbox"
            v-model="localConfig.showHistory"
          />
          Show Historical Data
        </label>
      </div>

      <div v-if="localConfig.showHistory" class="form-group">
        <label for="historyHours">History Hours:</label>
        <input
          id="historyHours"
          v-model.number="localConfig.historyHours"
          type="number"
          class="form-control"
          min="1"
          max="168"
          step="1"
        />
      </div>
    </div>

    <div class="editor-section">
      <h4>Alert Thresholds</h4>

      <div class="alert-thresholds">
        <div class="threshold-group">
          <h5>CPU Alerts (%)</h5>
          <div class="form-group">
            <label for="cpuWarning">Warning:</label>
            <input
              id="cpuWarning"
              v-model.number="localConfig.alerts.cpuWarning"
              type="number"
              class="form-control"
              min="1"
              max="100"
              step="1"
            />
          </div>
          <div class="form-group">
            <label for="cpuCritical">Critical:</label>
            <input
              id="cpuCritical"
              v-model.number="localConfig.alerts.cpuCritical"
              type="number"
              class="form-control"
              min="1"
              max="100"
              step="1"
            />
          </div>
        </div>

        <div class="threshold-group">
          <h5>Memory Alerts (%)</h5>
          <div class="form-group">
            <label for="memoryWarning">Warning:</label>
            <input
              id="memoryWarning"
              v-model.number="localConfig.alerts.memoryWarning"
              type="number"
              class="form-control"
              min="1"
              max="100"
              step="1"
            />
          </div>
          <div class="form-group">
            <label for="memoryCritical">Critical:</label>
            <input
              id="memoryCritical"
              v-model.number="localConfig.alerts.memoryCritical"
              type="number"
              class="form-control"
              min="1"
              max="100"
              step="1"
            />
          </div>
        </div>

        <div class="threshold-group">
          <h5>Disk Alerts (%)</h5>
          <div class="form-group">
            <label for="diskWarning">Warning:</label>
            <input
              id="diskWarning"
              v-model.number="localConfig.alerts.diskWarning"
              type="number"
              class="form-control"
              min="1"
              max="100"
              step="1"
            />
          </div>
        </div>
      </div>
    </div>

    <div class="preview-section">
      <h4>Preview</h4>
      <div class="editor-preview" :style="previewStyle">
        <div class="preview-header">
          <h3>{{ localConfig.title || 'System Monitor' }}</h3>
          <div class="preview-status">
            <span class="status-dot"></span>
            Normal
          </div>
        </div>

        <div v-if="localConfig.displayMode === 'compact'" class="preview-compact">
          <div class="preview-metrics">
            <div v-if="localConfig.metrics.includes('cpu')" class="preview-metric">
              <span>CPU</span>
              <span>45%</span>
            </div>
            <div v-if="localConfig.metrics.includes('memory')" class="preview-metric">
              <span>RAM</span>
              <span>67%</span>
            </div>
            <div v-if="localConfig.metrics.includes('disk')" class="preview-metric">
              <span>Disk</span>
              <span>78%</span>
            </div>
            <div v-if="localConfig.metrics.includes('network')" class="preview-metric">
              <span>Net</span>
              <span>1.2 MB</span>
            </div>
          </div>
        </div>

        <div v-else-if="localConfig.displayMode === 'detailed'" class="preview-detailed">
          <div class="preview-metric-group">
            <h5>CPU</h5>
            <div class="preview-progress">
              <div class="preview-progress-fill" style="width: 45%"></div>
            </div>
            <span>45%</span>
          </div>
          <div class="preview-metric-group">
            <h5>Memory</h5>
            <div class="preview-progress">
              <div class="preview-progress-fill memory-fill" style="width: 67%"></div>
            </div>
            <span>8.5GB / 16GB (67%)</span>
          </div>
        </div>

        <div v-else-if="localConfig.displayMode === 'chart'" class="preview-chart">
          <div class="chart-placeholder">
            <span>📊 Chart Preview</span>
            <small>{{ localConfig.chartType || 'line' }} chart with {{ localConfig.metrics.length }} metrics</small>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'SystemMonitorEditor',
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
  mounted() {
    // Config is already set in data() and watch, no need to override here
  },
  methods: {
    getDefaultConfig() {
      const cfg = this.config || {};
      return {
        title: cfg.title || 'System Monitor',
        displayMode: cfg.displayMode || 'detailed',
        metrics: cfg.metrics || ['cpu', 'memory', 'disk'],
        refreshInterval: cfg.refreshInterval || 30,
        backgroundColor: cfg.backgroundColor || '#ffffff',
        textColor: cfg.textColor || '#333333',
        chartType: cfg.chartType || 'line',
        showHistory: cfg.showHistory !== false,
        historyHours: cfg.historyHours || 24,
        alerts: {
          cpuWarning: cfg.alerts?.cpuWarning || 80,
          cpuCritical: cfg.alerts?.cpuCritical || 95,
          memoryWarning: cfg.alerts?.memoryWarning || 85,
          memoryCritical: cfg.alerts?.memoryCritical || 95,
          diskWarning: cfg.alerts?.diskWarning || 90
        }
      };
    }
  },
  computed: {
    previewStyle() {
      return {
        backgroundColor: this.localConfig.backgroundColor,
        color: this.localConfig.textColor,
        padding: '1rem',
        borderRadius: '8px',
        fontSize: '0.8rem',
        border: '1px solid #ddd',
        minHeight: '200px'
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
.system-monitor-editor {
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

.checkbox-group {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
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

.color-input-group {
  display: flex;
  gap: 0.5rem;
}

.color-input {
  flex: 0 0 60px;
  padding: 0.25rem;
  height: 38px;
}

.color-text {
  flex: 1;
}

.alert-thresholds {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
}

.threshold-group h5 {
  margin: 0 0 0.5rem 0;
  font-size: 0.9rem;
  color: #666;
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

.preview-compact .preview-metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(60px, 1fr));
  gap: 0.5rem;
}

.preview-metric {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 0.5rem;
  background-color: rgba(0, 0, 0, 0.05);
  border-radius: 4px;
  font-size: 0.8rem;
}

.preview-metric span:first-child {
  opacity: 0.8;
  margin-bottom: 0.25rem;
}

.preview-detailed {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.preview-metric-group h5 {
  margin: 0 0 0.5rem 0;
  font-size: 0.9rem;
}

.preview-progress {
  width: 100%;
  height: 6px;
  background-color: rgba(0, 0, 0, 0.1);
  border-radius: 3px;
  overflow: hidden;
  margin-bottom: 0.25rem;
}

.preview-progress-fill {
  height: 100%;
  background-color: #007bff;
}

.preview-progress-fill.memory-fill {
  background-color: #28a745;
}

.preview-chart {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100px;
  background-color: rgba(0, 0, 0, 0.05);
  border-radius: 4px;
}

.chart-placeholder {
  text-align: center;
  color: #666;
}

.chart-placeholder span {
  font-size: 1.5rem;
  display: block;
  margin-bottom: 0.25rem;
}

.chart-placeholder small {
  font-size: 0.8rem;
  opacity: 0.8;
}

/* Responsive adjustments */
@media (max-width: 768px) {
  .alert-thresholds {
    grid-template-columns: 1fr;
  }

  .preview-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 0.5rem;
  }

  .preview-compact .preview-metrics {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>