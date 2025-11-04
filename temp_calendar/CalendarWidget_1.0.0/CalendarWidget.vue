<template>
  <div class="calendar-widget" :style="widgetStyle">
    <div class="calendar-header">
      <button @click="previousMonth" class="nav-button prev-btn" aria-label="Previous month">‹</button>
      <h3 class="calendar-title">{{ config.title || 'Calendar' }}</h3>
      <button @click="nextMonth" class="nav-button next-btn" aria-label="Next month">›</button>
    </div>

    <div class="calendar-grid">
      <div class="month-year-header">
        <span class="month-year">{{ currentMonthName }} {{ currentYear }}</span>
      </div>

      <div class="weekdays-header">
        <div v-if="config.showWeekNumbers" class="weekday week-number">#</div>
        <div v-for="day in weekdays" :key="day" class="weekday">{{ day }}</div>
      </div>

      <div class="calendar-days">
        <div
          v-for="week in calendarWeeks"
          :key="week.weekNumber"
          class="calendar-week"
        >
          <div v-if="config.showWeekNumbers" class="day week-number-cell">{{ week.weekNumber }}</div>
          <div
            v-for="day in week.days"
            :key="day.date"
            :class="['day', day.classes]"
            @click="selectDate(day)"
          >
            {{ day.day }}
          </div>
        </div>
      </div>
    </div>

    <div v-if="selectedDate" class="selected-date-info">
      <small>Selected: {{ formatSelectedDate() }}</small>
    </div>
  </div>
</template>

<script>
export default {
  name: 'CalendarWidget',
  props: {
    config: {
      type: Object,
      default: () => ({})
    }
  },
  emits: ['date-selected'],
  data() {
    return {
      currentDate: new Date(),
      selectedDate: null,
      weekdays: ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
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
        display: 'flex',
        flexDirection: 'column',
        fontFamily: 'system-ui, -apple-system, sans-serif'
      };
    },
    currentMonthName() {
      return this.currentDate.toLocaleString('default', { month: 'long' });
    },
    currentYear() {
      return this.currentDate.getFullYear();
    },
    calendarWeeks() {
      const year = this.currentDate.getFullYear();
      const month = this.currentDate.getMonth();
      const firstDay = new Date(year, month, 1);
      const lastDay = new Date(year, month + 1, 0);
      const startDate = new Date(firstDay);
      startDate.setDate(startDate.getDate() - firstDay.getDay());

      const weeks = [];
      const today = new Date();
      today.setHours(0, 0, 0, 0);

      for (let weekIndex = 0; weekIndex < 6; weekIndex++) {
        const week = {
          weekNumber: this.getWeekNumber(new Date(startDate.getTime() + weekIndex * 7 * 24 * 60 * 60 * 1000)),
          days: []
        };

        for (let dayIndex = 0; dayIndex < 7; dayIndex++) {
          const date = new Date(startDate);
          date.setDate(startDate.getDate() + weekIndex * 7 + dayIndex);
          const isCurrentMonth = date.getMonth() === month;
          const isToday = this.config.highlightToday && date.toDateString() === today.toDateString();
          const isSelected = this.selectedDate && date.toDateString() === this.selectedDate.toDateString();

          const classes = {
            'current-month': isCurrentMonth,
            'other-month': !isCurrentMonth,
            'today': isToday,
            'selected': isSelected
          };

          week.days.push({
            date: date,
            day: date.getDate(),
            classes
          });
        }

        weeks.push(week);
      }

      return weeks;
    }
  },
  methods: {
    previousMonth() {
      this.currentDate = new Date(this.currentDate.getFullYear(), this.currentDate.getMonth() - 1, 1);
    },
    nextMonth() {
      this.currentDate = new Date(this.currentDate.getFullYear(), this.currentDate.getMonth() + 1, 1);
    },
    selectDate(day) {
      this.selectedDate = day.date;
      this.$emit('date-selected', day.date);
    },
    formatSelectedDate() {
      if (!this.selectedDate) return '';
      return this.selectedDate.toLocaleDateString('default', {
        weekday: 'long',
        year: 'numeric',
        month: 'long',
        day: 'numeric'
      });
    },
    getWeekNumber(date) {
      const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
      const dayNum = d.getUTCDay() || 7;
      d.setUTCDate(d.getUTCDate() + 4 - dayNum);
      const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
      return Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
    }
  }
}
</script>

<style scoped>
.calendar-widget {
  font-size: 0.9rem;
}

.calendar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.calendar-title {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 600;
}

.nav-button {
  background: none;
  border: 1px solid #ddd;
  border-radius: 4px;
  width: 30px;
  height: 30px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.2rem;
  color: #666;
  transition: all 0.2s;
}

.nav-button:hover {
  background-color: #f0f0f0;
  border-color: #ccc;
}

.month-year-header {
  text-align: center;
  margin-bottom: 0.5rem;
}

.month-year {
  font-weight: bold;
  font-size: 1rem;
}

.weekdays-header {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 2px;
  margin-bottom: 0.5rem;
}

.weekdays-header.has-week-numbers {
  grid-template-columns: 30px repeat(7, 1fr);
}

.weekday {
  text-align: center;
  font-weight: 600;
  font-size: 0.8rem;
  padding: 0.5rem 0;
  color: #666;
}

.week-number {
  font-size: 0.7rem;
  color: #999;
}

.calendar-days {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.calendar-week {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 2px;
}

.calendar-week.has-week-numbers {
  grid-template-columns: 30px repeat(7, 1fr);
}

.day {
  aspect-ratio: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
  font-size: 0.85rem;
  position: relative;
}

.day:hover {
  background-color: rgba(0, 123, 255, 0.1);
}

.day.current-month {
  color: inherit;
}

.day.other-month {
  color: #ccc;
  cursor: default;
}

.day.other-month:hover {
  background-color: transparent;
}

.day.today {
  background-color: #007bff;
  color: white;
  font-weight: bold;
}

.day.today:hover {
  background-color: #0056b3;
}

.day.selected {
  background-color: #28a745;
  color: white;
}

.day.selected:hover {
  background-color: #1e7e34;
}

.week-number-cell {
  font-size: 0.7rem;
  color: #999;
  font-weight: normal;
  cursor: default;
}

.selected-date-info {
  margin-top: 1rem;
  text-align: center;
  color: #666;
}

.selected-date-info small {
  font-style: italic;
}
</style>