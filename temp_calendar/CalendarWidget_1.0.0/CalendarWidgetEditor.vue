<template>
  <div class="calendar-editor">
    <div class="form-section">
      <h4>Basic Settings</h4>

      <div class="form-group">
        <label for="title">Calendar Title:</label>
        <input
          id="title"
          v-model="localConfig.title"
          type="text"
          class="form-control"
          placeholder="Enter calendar title"
        />
      </div>

      <div class="form-group">
        <label class="checkbox-label">
          <input
            type="checkbox"
            v-model="localConfig.showWeekNumbers"
          />
          Show Week Numbers
        </label>
      </div>

      <div class="form-group">
        <label class="checkbox-label">
          <input
            type="checkbox"
            v-model="localConfig.highlightToday"
          />
          Highlight Today
        </label>
      </div>
    </div>

    <div class="form-section">
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

      <div class="form-group">
        <label for="headerColor">Header Background:</label>
        <div class="color-input-group">
          <input
            id="headerColor"
            v-model="localConfig.headerColor"
            type="color"
            class="form-control color-input"
          />
          <input
            type="text"
            v-model="localConfig.headerColor"
            class="form-control color-text"
            placeholder="#f8f9fa"
          />
        </div>
      </div>
    </div>

    <div class="preview-section">
      <h4>Preview</h4>
      <div class="calendar-preview" :style="previewStyle">
        <div class="preview-header">
          <button class="preview-nav-btn">‹</button>
          <h3>{{ localConfig.title || 'Calendar' }}</h3>
          <button class="preview-nav-btn">›</button>
        </div>

        <div class="preview-grid">
          <div class="preview-month-year">
            <span>November 2024</span>
          </div>

          <div class="preview-weekdays">
            <div v-if="localConfig.showWeekNumbers" class="preview-weekday">#</div>
            <div v-for="day in ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']"
                 :key="day"
                 class="preview-weekday">
              {{ day }}
            </div>
          </div>

          <div class="preview-days">
            <div v-for="week in previewWeeks"
                 :key="week.id"
                 class="preview-week">
              <div v-if="localConfig.showWeekNumbers" class="preview-day week-num">{{ week.weekNum }}</div>
              <div v-for="day in week.days"
                   :key="day.id"
                   :class="['preview-day', day.classes]">
                {{ day.num }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'CalendarWidgetEditor',
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
        title: this.config.title || 'My Calendar',
        showWeekNumbers: this.config.showWeekNumbers || false,
        highlightToday: this.config.highlightToday !== false,
        backgroundColor: this.config.backgroundColor || '#ffffff',
        textColor: this.config.textColor || '#333333',
        headerColor: this.config.headerColor || '#f8f9fa'
      },
      previewWeeks: this.generatePreviewWeeks()
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
        border: '1px solid #ddd'
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
  },
  methods: {
    generatePreviewWeeks() {
      const weeks = [];
      for (let w = 0; w < 4; w++) {
        const week = {
          id: w,
          weekNum: 45 + w,
          days: []
        };

        for (let d = 0; d < 7; d++) {
          const dayNum = w * 7 + d + 1;
          const classes = {
            'current-month': dayNum <= 30,
            'other-month': dayNum > 30,
            'today': dayNum === 15 && this.localConfig.highlightToday
          };

          week.days.push({
            id: d,
            num: dayNum <= 30 ? dayNum : (dayNum - 30),
            classes
          });
        }

        weeks.push(week);
      }
      return weeks;
    }
  }
}
</script>

<style scoped>
.calendar-editor {
  padding: 1rem;
}

.form-section {
  margin-bottom: 2rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid #eee;
}

.form-section:last-child {
  border-bottom: none;
}

.form-section h4 {
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

.preview-section {
  margin-top: 2rem;
}

.preview-section h4 {
  margin-bottom: 1rem;
}

.calendar-preview {
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

.preview-nav-btn {
  background: none;
  border: 1px solid #ddd;
  border-radius: 4px;
  width: 24px;
  height: 24px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1rem;
  color: #666;
}

.preview-grid {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.preview-month-year {
  text-align: center;
  font-weight: bold;
  margin-bottom: 0.5rem;
}

.preview-weekdays {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 2px;
  margin-bottom: 0.5rem;
}

.preview-weekdays.has-week-numbers {
  grid-template-columns: 24px repeat(7, 1fr);
}

.preview-weekday {
  text-align: center;
  font-weight: 600;
  font-size: 0.7rem;
  padding: 0.25rem 0;
  color: #666;
}

.preview-days {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.preview-week {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 2px;
}

.preview-week.has-week-numbers {
  grid-template-columns: 24px repeat(7, 1fr);
}

.preview-day {
  aspect-ratio: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 2px;
  font-size: 0.7rem;
  background-color: transparent;
}

.preview-day.current-month {
  color: inherit;
}

.preview-day.other-month {
  color: #ccc;
}

.preview-day.today {
  background-color: #007bff;
  color: white;
  font-weight: bold;
}

.week-num {
  font-size: 0.6rem;
  color: #999;
}
</style>