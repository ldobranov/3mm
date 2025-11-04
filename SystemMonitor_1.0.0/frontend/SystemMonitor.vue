<template>
  <div class="system-monitor-widget" :style="widgetStyle">
    <div class="monitor-header">
      <h3 class="monitor-title">{{ config.title || 'System Monitor' }}</h3>
      <div class="status-indicator" :class="statusClass">
        <span class="status-dot"></span>
        {{ statusText }}
      </div>
    </div>

    <!-- Compact Mode -->
    <div v-if="config.displayMode === 'compact'" class="compact-view">
      <div class="metrics-grid">
        <div v-if="config.metrics.includes('cpu')" class="metric-item">
          <span class="metric-label">CPU</span>
          <span class="metric-value">{{ currentMetrics.cpu?.usage_percent || 0 }}%</span>
        </div>
        <div v-if="config.metrics.includes('memory')" class="metric-item">
          <span class="metric-label">RAM</span>
          <span class="metric-value">{{ currentMetrics.memory?.usage_percent || 0 }}%</span>
        </div>
        <div v-if="config.metrics.includes('disk')" class="metric-item">
          <span class="metric-label">Disk</span>
          <span class="metric-value">{{ currentMetrics.disk?.usage_percent || 0 }}%</span>
        </div>
        <div v-if="config.metrics.includes('network')" class="metric-item">
          <span class="metric-label">Net</span>
          <span class="metric-value">{{ formatBytes(currentMetrics.network?.bytes_recv || 0) }}</span>
        </div>
      </div>
    </div>

    <!-- Detailed Mode -->
    <div v-else-if="config.displayMode === 'detailed'" class="detailed-view">
      <div class="metrics-section">
        <div v-if="config.metrics.includes('cpu')" class="metric-group">
          <h4 class="metric-group-title">CPU</h4>
          <div class="cpu-details">
            <div class="cpu-main">
              <div class="progress-bar">
                <div class="progress-fill" :style="{ width: `${currentMetrics.cpu?.usage_percent || 0}%` }"></div>
              </div>
              <span class="cpu-percent">{{ currentMetrics.cpu?.usage_percent || 0 }}%</span>
            </div>
            <div class="cpu-cores">
              <small>Cores: {{ currentMetrics.cpu?.cores?.join(', ') || 'N/A' }}</small>
            </div>
          </div>
        </div>

        <div v-if="config.metrics.includes('memory')" class="metric-group">
          <h4 class="metric-group-title">Memory</h4>
          <div class="memory-details">
            <div class="progress-bar">
              <div class="progress-fill memory-fill" :style="{ width: `${currentMetrics.memory?.usage_percent || 0}%` }"></div>
            </div>
            <div class="memory-stats">
              <span>{{ currentMetrics.memory?.used_gb || 0 }}GB / {{ currentMetrics.memory?.total_gb || 0 }}GB</span>
              <small>{{ currentMetrics.memory?.usage_percent || 0 }}%</small>
            </div>
          </div>
        </div>

        <div v-if="config.metrics.includes('disk')" class="metric-group">
          <h4 class="metric-group-title">Disk</h4>
          <div class="disk-details">
            <div class="progress-bar">
              <div class="progress-fill disk-fill" :style="{ width: `${currentMetrics.disk?.usage_percent || 0}%` }"></div>
            </div>
            <div class="disk-stats">
              <span>{{ currentMetrics.disk?.used_gb || 0 }}GB / {{ currentMetrics.disk?.total_gb || 0 }}GB</span>
              <small>{{ currentMetrics.disk?.usage_percent || 0 }}%</small>
            </div>
          </div>
        </div>

        <div v-if="config.metrics.includes('network')" class="metric-group">
          <h4 class="metric-group-title">Network</h4>
          <div class="network-details">
            <div class="network-stats">
              <div class="network-stat">
                <span class="stat-label">↓</span>
                <span class="stat-value">{{ formatBytes(currentMetrics.network?.bytes_recv || 0) }}</span>
              </div>
              <div class="network-stat">
                <span class="stat-label">↑</span>
                <span class="stat-value">{{ formatBytes(currentMetrics.network?.bytes_sent || 0) }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Chart Mode -->
    <div v-else-if="config.displayMode === 'chart'" class="chart-view">
      <div class="chart-container">
        <canvas ref="chartCanvas" :width="chartWidth" :height="chartHeight"></canvas>
      </div>
    </div>

    <!-- Loading/Error States -->
    <div v-else-if="loading" class="loading-state">
      <div class="loading-spinner"></div>
      <span>Loading system metrics...</span>
    </div>

    <div v-else-if="error" class="error-state">
      <span class="error-icon">⚠️</span>
      <span>{{ error }}</span>
    </div>
  </div>
</template>

<script>
import Chart from 'chart.js/auto';

export default {
  name: 'SystemMonitor',
  props: {
    config: {
      type: Object,
      default: () => ({})
    }
  },
  emits: ['update:modelValue'],
  data() {
    return {
      currentMetrics: {},
      historicalData: [],
      loading: true,
      error: null,
      chart: null,
      updateInterval: null
    }
  },
  computed: {
    widgetStyle() {
      return {
        backgroundColor: this.config.backgroundColor || '#ffffff',
        color: this.config.textColor || '#333333',
        padding: '1rem',
        borderRadius: '8px',
        height: '100%',
        fontFamily: 'system-ui, -apple-system, sans-serif',
        fontSize: '0.9rem'
      };
    },
    chartWidth() {
      return 300;
    },
    chartHeight() {
      return 150;
    },
    statusClass() {
      if (!this.currentMetrics.cpu) return 'status-unknown';
      const cpuUsage = this.currentMetrics.cpu.usage_percent || 0;
      if (cpuUsage >= (this.config.alerts?.cpuCritical || 95)) return 'status-critical';
      if (cpuUsage >= (this.config.alerts?.cpuWarning || 80)) return 'status-warning';
      return 'status-normal';
    },
    statusText() {
      if (!this.currentMetrics.cpu) return 'Unknown';
      const cpuUsage = this.currentMetrics.cpu.usage_percent || 0;
      if (cpuUsage >= (this.config.alerts?.cpuCritical || 95)) return 'Critical';
      if (cpuUsage >= (this.config.alerts?.cpuWarning || 80)) return 'Warning';
      return 'Normal';
    }
  },
  mounted() {
    this.fetchMetrics();
    this.startAutoUpdate();
  },
  beforeUnmount() {
    this.stopAutoUpdate();
    if (this.chart) {
      this.chart.destroy();
    }
  },
  watch: {
    'config.displayMode': function() {
      this.updateChart();
    },
    'config.metrics': function() {
      this.updateChart();
    },
    'config.showHistory': function() {
      this.updateChart();
    }
  },
  methods: {
    async fetchMetrics() {
      try {
        this.loading = true;
        this.error = null;

        const response = await fetch('/api/system/metrics/current');

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        this.currentMetrics = await response.json();

        if (this.config.showHistory) {
          await this.fetchHistoricalData();
        }

        this.loading = false;
      } catch (err) {
        this.error = `Failed to load metrics: ${err.message}`;
        this.loading = false;
        console.error('Metrics fetch error:', err);
      }
    },

    async fetchHistoricalData() {
      try {
        const response = await fetch(`/api/system/metrics/history?hours=${this.config.historyHours || 24}&interval=60`);

        if (response.ok) {
          const data = await response.json();
          this.historicalData = data.data || [];
          // Only update chart if we're in chart mode
          if (this.config.displayMode === 'chart') {
            this.updateChart();
          }
        }
      } catch (err) {
        console.error('Historical data fetch error:', err);
      }
    },

    startAutoUpdate() {
      const interval = (this.config.refreshInterval || 30) * 1000;
      this.updateInterval = setInterval(() => {
        this.fetchMetrics();
      }, interval);
    },

    stopAutoUpdate() {
      if (this.updateInterval) {
        clearInterval(this.updateInterval);
        this.updateInterval = null;
      }
    },

    updateChart() {
      if (this.config.displayMode !== 'chart' || !this.$refs.chartCanvas) return;

      if (this.chart) {
        this.chart.destroy();
      }

      const ctx = this.$refs.chartCanvas.getContext('2d');
      const datasets = [];

      if (this.config.metrics.includes('cpu') && this.historicalData.length > 0) {
        datasets.push({
          label: 'CPU Usage (%)',
          data: this.historicalData.map(d => ({ x: new Date(d.timestamp), y: d.cpu?.usage_percent || 0 })),
          borderColor: '#007bff',
          backgroundColor: 'rgba(0, 123, 255, 0.1)',
          fill: true,
          tension: 0.4
        });
      }

      if (this.config.metrics.includes('memory') && this.historicalData.length > 0) {
        datasets.push({
          label: 'Memory Usage (%)',
          data: this.historicalData.map(d => ({ x: new Date(d.timestamp), y: d.memory?.usage_percent || 0 })),
          borderColor: '#28a745',
          backgroundColor: 'rgba(40, 167, 69, 0.1)',
          fill: true,
          tension: 0.4
        });
      }

      // Only create chart if we have data
      if (datasets.length > 0) {
        try {
          this.chart = new Chart(ctx, {
            type: this.config.chartType || 'line',
            data: {
              datasets: datasets
            },
            options: {
              responsive: true,
              maintainAspectRatio: false,
              scales: {
                x: {
                  type: 'time',
                  time: {
                    unit: 'hour',
                    displayFormats: {
                      hour: 'HH:mm'
                    }
                  }
                },
                y: {
                  beginAtZero: true,
                  max: 100
                }
              },
              plugins: {
                legend: {
                  display: datasets.length > 1
                }
              }
            }
          });
        } catch (error) {
          console.error('Chart creation error:', error);
          // Fallback: don't create chart if date adapter is missing
        }
      }
    },

    formatBytes(bytes) {
      if (bytes === 0) return '0 B';
      const k = 1024;
      const sizes = ['B', 'KB', 'MB', 'GB'];
      const i = Math.floor(Math.log(bytes) / Math.log(k));
      return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
    }
  }
}
</script>

<style scoped>
.system-monitor-widget {
  display: flex;
  flex-direction: column;
}

.monitor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.monitor-title {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 600;
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.8rem;
  font-weight: 500;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.status-normal .status-dot {
  background-color: #28a745;
}

.status-warning .status-dot {
  background-color: #ffc107;
}

.status-critical .status-dot {
  background-color: #dc3545;
}

.status-unknown .status-dot {
  background-color: #6c757d;
}

/* Compact View */
.compact-view .metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(80px, 1fr));
  gap: 0.5rem;
}

.metric-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 0.5rem;
  background-color: rgba(0, 0, 0, 0.05);
  border-radius: 4px;
}

.metric-label {
  font-size: 0.8rem;
  font-weight: 500;
  opacity: 0.8;
}

.metric-value {
  font-size: 1.1rem;
  font-weight: 600;
}

/* Detailed View */
.detailed-view .metrics-section {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.metric-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.metric-group-title {
  margin: 0;
  font-size: 0.9rem;
  font-weight: 600;
  color: inherit;
}

.progress-bar {
  width: 100%;
  height: 8px;
  background-color: rgba(0, 0, 0, 0.1);
  border-radius: 4px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background-color: #007bff;
  transition: width 0.3s ease;
}

.progress-fill.memory-fill {
  background-color: #28a745;
}

.progress-fill.disk-fill {
  background-color: #ffc107;
}

.cpu-main {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.cpu-percent {
  font-weight: 600;
  min-width: 40px;
}

.cpu-cores {
  margin-top: 0.25rem;
}

.memory-stats,
.disk-stats {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 0.25rem;
}

.memory-stats small,
.disk-stats small {
  opacity: 0.8;
}

.network-details .network-stats {
  display: flex;
  gap: 1rem;
}

.network-stat {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

.stat-label {
  font-weight: 600;
  min-width: 12px;
}

.stat-value {
  font-size: 0.9rem;
}

/* Chart View */
.chart-view .chart-container {
  flex: 1;
  min-height: 150px;
}

/* States */
.loading-state,
.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 0.5rem;
  color: #6c757d;
}

.loading-spinner {
  width: 24px;
  height: 24px;
  border: 2px solid rgba(0, 0, 0, 0.1);
  border-top: 2px solid #007bff;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.error-icon {
  font-size: 1.5rem;
}

/* Responsive adjustments */
@media (max-width: 480px) {
  .monitor-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 0.5rem;
  }

  .compact-view .metrics-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .network-details .network-stats {
    flex-direction: column;
    gap: 0.25rem;
  }
}
</style>