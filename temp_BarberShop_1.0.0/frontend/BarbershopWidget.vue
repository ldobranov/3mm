<template>
  <div class="barbershop-widget">
    <div class="widget-header">
      <h3>{{ t('barbershop.reservationWidget', 'Reservation Widget') }}</h3>
      <p>{{ t('barbershop.bookNowDescription', 'Book an appointment quickly') }}</p>
    </div>
    
    <div class="widget-content">
      <div class="widget-section">
        <label>{{ t('barbershop.reservations.selectService', 'Service') }}</label>
        <select v-model="selectedServiceId" @change="fetchAvailableBarbers">
          <option value="">{{ t('barbershop.selectOption', 'Select a service') }}</option>
          <option v-for="service in services" :key="service.id" :value="service.id">
            {{ service.name }} ({{ service.duration_minutes }} {{ t('minutes', 'min') }})
          </option>
        </select>
      </div>
      
      <div class="widget-section">
        <label>{{ t('barbershop.reservations.selectBarber', 'Barber') }}</label>
        <select v-model="selectedBarberId" :disabled="!selectedServiceId">
          <option value="">{{ t('barbershop.selectOption', 'Select a barber') }}</option>
          <option v-for="barber in availableBarbers" :key="barber.id" :value="barber.id">
            {{ barber.name }}
          </option>
        </select>
      </div>
      
      <div class="widget-section">
        <label>{{ t('barbershop.reservations.selectDate', 'Date') }}</label>
        <input type="date" v-model="selectedDate" :min="minDate" @change="fetchAvailableSlots" />
      </div>
      
      <div class="widget-section" v-if="availableSlots.length > 0">
        <label>{{ t('barbershop.reservations.availableSlots', 'Available Times') }}</label>
        <select v-model="selectedTimeSlot">
          <option value="">{{ t('barbershop.selectOption', 'Select a time') }}</option>
          <option v-for="slot in availableSlots" :key="slot.start_time" :value="slot.start_time">
            {{ slot.formatted }}
          </option>
        </select>
      </div>
      
      <div v-if="loading" class="widget-loading">
        {{ t('barbershop.loading', 'Loading...') }}
      </div>
      
      <div v-if="error" class="widget-error">
        {{ error }}
      </div>
      
      <button @click="openFullForm" class="widget-button" :disabled="!isWidgetFormValid">
        {{ t('barbershop.bookNow', 'Book Now') }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from '@/utils/i18n'
import { useRouter } from 'vue-router'
import http from '@/utils/dynamic-http'

const { t } = useI18n()
const router = useRouter()

// Props
const props = defineProps({
  compact: {
    type: Boolean,
    default: false
  }
})

// State
const services = ref([])
const availableBarbers = ref([])
const selectedServiceId = ref('')
const selectedBarberId = ref('')
const selectedDate = ref('')
const availableSlots = ref([])
const selectedTimeSlot = ref('')
const loading = ref(false)
const error = ref(null)

// Computed properties
const minDate = computed(() => {
  const today = new Date()
  return today.toISOString().split('T')[0]
})

const isWidgetFormValid = computed(() => {
  return selectedServiceId.value && selectedBarberId.value && 
         selectedDate.value && selectedTimeSlot.value
})

// Fetch data
const fetchServices = async () => {
  try {
    loading.value = true
    error.value = null
    
    const response = await http.get('/api/barbershop/services', {
      params: { limit: 10 }
    })
    services.value = response.data.services || []
  } catch (err) {
    console.error('Failed to fetch services:', err)
    error.value = t('barbershop.error', 'Error') + ': ' + (err.message || 'Failed to load services')
  } finally {
    loading.value = false
  }
}

const fetchAvailableBarbers = async () => {
  if (!selectedServiceId.value) return
  
  try {
    loading.value = true
    error.value = null
    
    const response = await http.get('/api/barbershop/barbers', {
      params: { is_active: true }
    })
    availableBarbers.value = response.data.barbers || []
  } catch (err) {
    console.error('Failed to fetch barbers:', err)
    error.value = t('barbershop.error', 'Error') + ': ' + (err.message || 'Failed to load barbers')
  } finally {
    loading.value = false
  }
}

const fetchAvailableSlots = async () => {
  if (!selectedServiceId.value || !selectedBarberId.value || !selectedDate.value) {
    availableSlots.value = []
    return
  }
  
  try {
    loading.value = true
    error.value = null
    
    const response = await http.get('/api/barbershop/reservations/available', {
      params: {
        date: selectedDate.value,
        barber_id: selectedBarberId.value,
        service_id: selectedServiceId.value
      }
    })
    
    availableSlots.value = response.data.available_slots || []
  } catch (err) {
    console.error('Failed to fetch available slots:', err)
    error.value = t('barbershop.error', 'Error') + ': ' + (err.message || 'Failed to load available slots')
    availableSlots.value = []
  } finally {
    loading.value = false
  }
}

const openFullForm = () => {
  if (!isWidgetFormValid.value) return
  
  // Navigate to full reservation form with pre-selected values
  router.push({
    path: '/barbershop/book',
    query: {
      service_id: selectedServiceId.value,
      barber_id: selectedBarberId.value,
      date: selectedDate.value,
      time: selectedTimeSlot.value
    }
  })
}

// Lifecycle
onMounted(() => {
  fetchServices()
  selectedDate.value = minDate.value
})
</script>

<style scoped>
.barbershop-widget {
  max-width: 400px;
  margin: 0 auto;
  background-color: var(--background-secondary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 1.5rem;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}

.widget-header {
  margin-bottom: 1.5rem;
  text-align: center;
}

.widget-header h3 {
  color: var(--text-primary);
  font-size: 1.25rem;
  margin-bottom: 0.5rem;
}

.widget-header p {
  color: var(--text-secondary);
  font-size: 0.9rem;
}

.widget-content {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.widget-section {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.widget-section label {
  color: var(--text-primary);
  font-size: 0.85rem;
  font-weight: 500;
}

.widget-section select,
.widget-section input {
  padding: 0.75rem;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background-color: var(--background-tertiary);
  color: var(--text-primary);
  font-size: 0.9rem;
}

.widget-section select:focus,
.widget-section input:focus {
  outline: none;
  border-color: var(--primary-color);
  box-shadow: 0 0 0 2px var(--primary-color-light);
}

.widget-loading {
  padding: 0.5rem;
  text-align: center;
  color: var(--text-secondary);
  font-size: 0.85rem;
  font-style: italic;
}

.widget-error {
  padding: 0.5rem;
  background-color: var(--danger-color-light);
  color: var(--danger-color);
  border-radius: 4px;
  font-size: 0.8rem;
  text-align: center;
}

.widget-button {
  padding: 0.75rem;
  background-color: var(--primary-color);
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 1rem;
  font-weight: 600;
  transition: all 0.2s ease;
  margin-top: 0.5rem;
}

.widget-button:hover:not(:disabled) {
  background-color: var(--primary-color-dark);
}

.widget-button:disabled {
  background-color: var(--background-disabled);
  cursor: not-allowed;
}

@media (max-width: 480px) {
  .barbershop-widget {
    padding: 1rem;
  }
}
</style>