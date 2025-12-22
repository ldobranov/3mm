<template>
  <div class="reservation-form">
    <div class="form-header">
      <h1>{{ t('barbershop.reservations.newReservation', 'New Reservation') }}</h1>
      <p>{{ t('barbershop.reservations.description', 'Book an appointment with our barbers') }}</p>
    </div>
    
    <form @submit.prevent="submitReservation" class="reservation-form-content">
      <div class="form-section">
        <h2>{{ t('barbershop.reservations.selectService', 'Select Service') }}</h2>
        <div class="service-grid">
          <div v-for="service in services" :key="service.id" 
               class="service-card" 
               :class="{ 'selected': selectedServiceId === service.id }" 
               @click="selectService(service.id)">
            <div class="service-image">
              <img v-if="service.image_url" :src="service.image_url" :alt="service.name" />
              <div v-else class="service-icon">✂️</div>
            </div>
            <div class="service-info">
              <h3>{{ service.name }}</h3>
              <p class="service-duration">{{ service.duration_minutes }} {{ t('minutes', 'minutes') }}</p>
              <p class="service-price">{{ formatPrice(service.price) }}</p>
            </div>
          </div>
        </div>
        <div v-if="services.length === 0" class="no-services">
          {{ t('barbershop.noData', 'No services available') }}
        </div>
      </div>
      
      <div class="form-section">
        <h2>{{ t('barbershop.reservations.selectBarber', 'Select Barber') }}</h2>
        <div class="barber-grid">
          <div v-for="barber in availableBarbers" :key="barber.id" 
               class="barber-card" 
               :class="{ 'selected': selectedBarberId === barber.id }" 
               @click="selectBarber(barber.id)">
            <div class="barber-image">
              <img v-if="barber.image_url" :src="barber.image_url" :alt="barber.name" />
              <div v-else class="barber-initial">{{ barber.name.charAt(0) }}</div>
            </div>
            <div class="barber-info">
              <h3>{{ barber.name }}</h3>
              <p class="barber-bio" v-if="barber.bio">{{ barber.bio }}</p>
              <p class="barber-availability">
                {{ t('barbershop.barbers.available', 'Available') }}
              </p>
            </div>
          </div>
        </div>
        <div v-if="availableBarbers.length === 0" class="no-barbers">
          {{ t('barbershop.noData', 'No barbers available') }}
        </div>
      </div>
      
      <div class="form-section">
        <h2>{{ t('barbershop.reservations.selectDate', 'Select Date') }}</h2>
        <div class="date-selector">
          <input type="date" v-model="selectedDate" 
                 :min="minDate" 
                 @change="fetchAvailableSlots" 
                 class="date-input" />
          <button type="button" @click="fetchAvailableSlots" class="refresh-button">
            {{ t('barbershop.refresh', 'Refresh') }}
          </button>
        </div>
        
        <div v-if="loadingSlots" class="loading-slots">
          {{ t('barbershop.loading', 'Loading available slots...') }}
        </div>
        
        <div v-if="!loadingSlots && availableSlots.length > 0" class="time-slots">
          <h3>{{ t('barbershop.reservations.availableSlots', 'Available Time Slots') }}</h3>
          <div class="slot-grid">
            <button v-for="slot in availableSlots" :key="slot.start_time" 
                    type="button" 
                    class="time-slot" 
                    :class="{ 'selected': selectedTimeSlot === slot.start_time }" 
                    @click="selectTimeSlot(slot.start_time)">
              {{ slot.formatted }}
            </button>
          </div>
        </div>
        
        <div v-if="!loadingSlots && availableSlots.length === 0 && selectedDate" class="no-slots">
          {{ t('barbershop.reservations.noSlotsAvailable', 'No available slots for this day') }}
        </div>
      </div>
      
      <div class="form-section">
        <h2>{{ t('barbershop.reservations.customerInfo', 'Customer Information') }}</h2>
        <div class="form-group">
          <label for="customerName">{{ t('barbershop.reservations.customerName', 'Your Name') }} *</label>
          <input type="text" id="customerName" v-model="customerName" required 
                 :placeholder="t('barbershop.reservations.customerName', 'Your Name')" />
        </div>
        
        <div class="form-group">
          <label for="customerPhone">{{ t('barbershop.reservations.customerPhone', 'Your Phone') }} *</label>
          <input type="tel" id="customerPhone" v-model="customerPhone" required 
                 :placeholder="t('barbershop.reservations.customerPhone', 'Your Phone')" />
        </div>
        
        <div class="form-group">
          <label for="customerEmail">{{ t('barbershop.reservations.customerEmail', 'Your Email (optional)') }}</label>
          <input type="email" id="customerEmail" v-model="customerEmail" 
                 :placeholder="t('barbershop.reservations.customerEmail', 'Your Email (optional)')" />
        </div>
        
        <div class="form-group">
          <label for="notes">{{ t('barbershop.reservations.notes', 'Additional Notes') }}</label>
          <textarea id="notes" v-model="notes" 
                    :placeholder="t('barbershop.reservations.notesPlaceholder', 'Any special requests?')"></textarea>
        </div>
      </div>
      
      <div class="form-actions">
        <button type="submit" class="submit-button" :disabled="!isFormValid || loading">
          <span v-if="loading">{{ t('barbershop.loading', 'Loading...') }}</span>
          <span v-else>{{ t('barbershop.reservations.confirmReservation', 'Confirm Reservation') }}</span>
        </button>
        <button type="button" class="cancel-button" @click="cancelForm">
          {{ t('barbershop.cancel', 'Cancel') }}
        </button>
      </div>
      
      <div v-if="error" class="form-error">
        {{ error }}
      </div>
      
      <div v-if="success" class="form-success">
        {{ t('barbershop.reservations.reservationConfirmed', 'Reservation Confirmed!') }}
      </div>
    </form>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useI18n } from '@/utils/i18n'
import { useRouter } from 'vue-router'
import http from '@/utils/dynamic-http'

const { t } = useI18n()
const router = useRouter()

// State
const services = ref([])
const barbers = ref([])
const availableBarbers = ref([])
const selectedServiceId = ref(null)
const selectedBarberId = ref(null)
const selectedDate = ref('')
const availableSlots = ref([])
const selectedTimeSlot = ref('')
const customerName = ref('')
const customerPhone = ref('')
const customerEmail = ref('')
const notes = ref('')
const loading = ref(false)
const loadingSlots = ref(false)
const error = ref(null)
const success = ref(false)

// Computed properties
const minDate = computed(() => {
  const today = new Date()
  return today.toISOString().split('T')[0]
})

const isFormValid = computed(() => {
  return selectedServiceId.value && selectedBarberId.value && 
         selectedDate.value && selectedTimeSlot.value && 
         customerName.value && customerPhone.value
})

const selectedService = computed(() => {
  return services.value.find(s => s.id === selectedServiceId.value)
})

// Fetch data
const fetchServices = async () => {
  try {
    const response = await http.get('/api/barbershop/services')
    services.value = response.data.services || []
  } catch (err) {
    console.error('Failed to fetch services:', err)
    error.value = t('barbershop.error', 'Error') + ': ' + (err.message || 'Failed to load services')
  }
}

const fetchBarbers = async () => {
  try {
    const response = await http.get('/api/barbershop/barbers')
    barbers.value = response.data.barbers || []
    availableBarbers.value = barbers.value.filter(b => b.is_active)
  } catch (err) {
    console.error('Failed to fetch barbers:', err)
    error.value = t('barbershop.error', 'Error') + ': ' + (err.message || 'Failed to load barbers')
  }
}

const fetchAvailableSlots = async () => {
  if (!selectedDate.value || !selectedBarberId.value || !selectedServiceId.value) {
    availableSlots.value = []
    return
  }
  
  try {
    loadingSlots.value = true
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
    loadingSlots.value = false
  }
}

// Form actions
const selectService = (serviceId: number) => {
  selectedServiceId.value = serviceId
  // Reset slots when service changes
  availableSlots.value = []
  selectedTimeSlot.value = ''
}

const selectBarber = (barberId: number) => {
  selectedBarberId.value = barberId
  // Reset slots when barber changes
  availableSlots.value = []
  selectedTimeSlot.value = ''
}

const selectTimeSlot = (startTime: string) => {
  selectedTimeSlot.value = startTime
}

const submitReservation = async () => {
  if (!isFormValid.value) return
  
  try {
    loading.value = true
    error.value = null
    success.value = false
    
    // Calculate end time based on service duration
    const service = selectedService.value
    if (!service) {
      throw new Error('Service not found')
    }
    
    const [startHours, startMinutes] = selectedTimeSlot.value.split(':').map(Number)
    const startDateTime = new Date()
    startDateTime.setHours(startHours, startMinutes, 0, 0)
    
    const endDateTime = new Date(startDateTime.getTime() + service.duration_minutes * 60000)
    const endTime = endDateTime.toTimeString().split(' ')[0]
    
    const reservationData = {
      customer_name: customerName.value,
      customer_phone: customerPhone.value,
      customer_email: customerEmail.value || null,
      barber_id: selectedBarberId.value,
      service_id: selectedServiceId.value,
      reservation_date: selectedDate.value,
      start_time: selectedTimeSlot.value + ':00',
      notes: notes.value || null
    }
    
    const response = await http.post('/api/barbershop/reservations', reservationData)
    
    success.value = true
    
    // Reset form after successful submission
    setTimeout(() => {
      router.push('/barbershop/my-reservations')
    }, 2000)
    
  } catch (err) {
    console.error('Failed to create reservation:', err)
    error.value = t('barbershop.error', 'Error') + ': ' + (err.message || 'Failed to create reservation')
  } finally {
    loading.value = false
  }
}

const cancelForm = () => {
  router.push('/barbershop')
}

const formatPrice = (price: number) => {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD'
  }).format(price)
}

// Watchers
watch([selectedServiceId, selectedBarberId, selectedDate], () => {
  if (selectedServiceId.value && selectedBarberId.value && selectedDate.value) {
    fetchAvailableSlots()
  }
})

// Lifecycle
onMounted(() => {
  fetchServices()
  fetchBarbers()
  
  // Set default date to today
  selectedDate.value = minDate.value
})
</script>

<style scoped>
.reservation-form {
  max-width: 1000px;
  margin: 0 auto;
  padding: 2rem;
}

.form-header {
  text-align: center;
  margin-bottom: 2rem;
}

.form-header h1 {
  color: var(--text-primary);
  font-size: 1.75rem;
  margin-bottom: 0.5rem;
}

.form-header p {
  color: var(--text-secondary);
  font-size: 1rem;
}

.reservation-form-content {
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.form-section {
  background-color: var(--background-secondary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 1.5rem;
}

.form-section h2 {
  color: var(--text-primary);
  margin-bottom: 1.5rem;
  font-size: 1.25rem;
}

.service-grid, .barber-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 1rem;
  margin-bottom: 1rem;
}

.service-card, .barber-card {
  border: 2px solid var(--border-color);
  border-radius: 8px;
  padding: 1rem;
  cursor: pointer;
  transition: all 0.2s ease;
  background-color: var(--background-tertiary);
}

.service-card:hover, .barber-card:hover {
  border-color: var(--primary-color);
  background-color: var(--background-quaternary);
}

.service-card.selected, .barber-card.selected {
  border-color: var(--primary-color);
  background-color: var(--primary-color-light);
}

.service-image, .barber-image {
  width: 100%;
  height: 120px;
  background-color: var(--background-quaternary);
  border-radius: 6px;
  margin-bottom: 0.75rem;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.service-image img, .barber-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.service-icon, .barber-initial {
  font-size: 2rem;
  color: var(--text-secondary);
}

.barber-initial {
  width: 60px;
  height: 60px;
  background-color: var(--primary-color);
  color: white;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
}

.service-info h3, .barber-info h3 {
  color: var(--text-primary);
  font-size: 1rem;
  margin-bottom: 0.5rem;
  font-weight: 600;
}

.service-duration, .barber-bio {
  color: var(--text-secondary);
  font-size: 0.85rem;
  margin-bottom: 0.25rem;
}

.service-price {
  color: var(--primary-color);
  font-size: 1rem;
  font-weight: 600;
}

.barber-availability {
  color: var(--success-color);
  font-size: 0.8rem;
  font-weight: 500;
}

.date-selector {
  display: flex;
  gap: 1rem;
  margin-bottom: 1.5rem;
  align-items: center;
}

.date-input {
  padding: 0.75rem;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background-color: var(--background-tertiary);
  color: var(--text-primary);
  font-size: 1rem;
  flex: 1;
}

.refresh-button {
  padding: 0.75rem 1.5rem;
  background-color: var(--background-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.refresh-button:hover {
  background-color: var(--background-quaternary);
}

.loading-slots {
  padding: 1rem;
  text-align: center;
  color: var(--text-secondary);
  font-style: italic;
}

.time-slots {
  margin-top: 1rem;
}

.time-slots h3 {
  color: var(--text-primary);
  margin-bottom: 1rem;
  font-size: 1rem;
}

.slot-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 0.75rem;
}

.time-slot {
  padding: 0.75rem;
  background-color: var(--background-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
  text-align: center;
}

.time-slot:hover {
  background-color: var(--background-quaternary);
  border-color: var(--primary-color);
}

.time-slot.selected {
  background-color: var(--primary-color);
  color: white;
  border-color: var(--primary-color);
}

.no-slots, .no-services, .no-barbers {
  text-align: center;
  padding: 1.5rem;
  color: var(--text-secondary);
  font-style: italic;
}

.form-group {
  margin-bottom: 1.5rem;
}

.form-group label {
  display: block;
  margin-bottom: 0.5rem;
  color: var(--text-primary);
  font-weight: 500;
}

.form-group input, .form-group textarea {
  width: 100%;
  padding: 0.75rem;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background-color: var(--background-tertiary);
  color: var(--text-primary);
  font-size: 1rem;
}

.form-group input:focus, .form-group textarea:focus {
  outline: none;
  border-color: var(--primary-color);
  box-shadow: 0 0 0 2px var(--primary-color-light);
}

.form-group textarea {
  min-height: 100px;
  resize: vertical;
}

.form-actions {
  display: flex;
  gap: 1rem;
  justify-content: flex-end;
  margin-top: 1rem;
}

.submit-button {
  padding: 0.75rem 2rem;
  background-color: var(--primary-color);
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 1rem;
  font-weight: 600;
  transition: all 0.2s ease;
}

.submit-button:hover:not(:disabled) {
  background-color: var(--primary-color-dark);
}

.submit-button:disabled {
  background-color: var(--background-disabled);
  cursor: not-allowed;
}

.cancel-button {
  padding: 0.75rem 2rem;
  background-color: var(--background-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  cursor: pointer;
  font-size: 1rem;
  font-weight: 500;
  transition: all 0.2s ease;
}

.cancel-button:hover {
  background-color: var(--background-quaternary);
}

.form-error {
  padding: 1rem;
  background-color: var(--danger-color-light);
  color: var(--danger-color);
  border-radius: 6px;
  margin-top: 1rem;
  text-align: center;
}

.form-success {
  padding: 1rem;
  background-color: var(--success-color-light);
  color: var(--success-color);
  border-radius: 6px;
  margin-top: 1rem;
  text-align: center;
  font-weight: 600;
}

@media (max-width: 768px) {
  .service-grid, .barber-grid {
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  }
  
  .slot-grid {
    grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
  }
  
  .form-actions {
    flex-direction: column;
  }
  
  .cancel-button {
    order: -1;
  }
}
</style>