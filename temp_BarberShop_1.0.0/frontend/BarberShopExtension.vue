<template>
  <div class="barbershop-extension">
    <div class="extension-header">
      <h1>{{ t('barbershop.title', 'Barbershop') }}</h1>
      <p>{{ t('barbershop.description', 'Complete barbershop management system') }}</p>
    </div>
    
    <div class="extension-navigation">
      <router-link to="/barbershop/reservations" class="nav-button">
        {{ t('barbershop.reservations.title', 'Reservations') }}
      </router-link>
      <router-link to="/barbershop/barbers" class="nav-button">
        {{ t('barbershop.barbers.title', 'Barbers') }}
      </router-link>
      <router-link to="/barbershop/services" class="nav-button">
        {{ t('barbershop.services.title', 'Services') }}
      </router-link>
      <router-link to="/barbershop/book" class="nav-button primary">
        {{ t('barbershop.reservations.newReservation', 'New Reservation') }}
      </router-link>
    </div>
    
    <div class="extension-content">
      <div class="dashboard-summary">
        <div class="summary-card">
          <h3>{{ t('barbershop.dashboard.todayReservations', "Today's Reservations") }}</h3>
          <p class="summary-value">{{ todayReservationsCount }}</p>
        </div>
        
        <div class="summary-card">
          <h3>{{ t('barbershop.dashboard.upcomingReservations', 'Upcoming Reservations') }}</h3>
          <p class="summary-value">{{ upcomingReservationsCount }}</p>
        </div>
        
        <div class="summary-card">
          <h3>{{ t('barbershop.dashboard.totalBarbers', 'Total Barbers') }}</h3>
          <p class="summary-value">{{ totalBarbers }}</p>
        </div>
        
        <div class="summary-card">
          <h3>{{ t('barbershop.dashboard.totalServices', 'Total Services') }}</h3>
          <p class="summary-value">{{ totalServices }}</p>
        </div>
      </div>
      
      <div class="recent-activity">
        <h2>{{ t('barbershop.dashboard.upcomingReservations', 'Upcoming Reservations') }}</h2>
        <div class="reservations-list">
          <div v-for="reservation in upcomingReservations" :key="reservation.id" class="reservation-item">
            <div class="reservation-info">
              <span class="reservation-time">{{ formatTime(reservation.start_time) }} - {{ formatTime(reservation.end_time) }}</span>
              <span class="reservation-customer">{{ reservation.customer_name }}</span>
              <span class="reservation-service">{{ getServiceName(reservation.service_id) }}</span>
              <span class="reservation-barber">{{ getBarberName(reservation.barber_id) }}</span>
            </div>
            <div class="reservation-status" :class="getStatusClass(reservation.status)">
              {{ t(`barbershop.reservations.status.${reservation.status}`, reservation.status) }}
            </div>
          </div>
          <div v-if="upcomingReservations.length === 0" class="no-data">
            {{ t('barbershop.noData', 'No data available') }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useI18n } from '@/utils/i18n'
import { useRouter } from 'vue-router'
import http from '@/utils/dynamic-http'

const { t } = useI18n()
const router = useRouter()

// State
const todayReservations = ref([])
const upcomingReservations = ref([])
const barbers = ref([])
const services = ref([])
const loading = ref(true)
const error = ref(null)

// Computed properties
const todayReservationsCount = computed(() => todayReservations.value.length)
const upcomingReservationsCount = computed(() => upcomingReservations.value.length)
const totalBarbers = computed(() => barbers.value.length)
const totalServices = computed(() => services.value.length)

// Fetch data
const fetchDashboardData = async () => {
  try {
    loading.value = true
    error.value = null
    
    // Fetch today's reservations
    const today = new Date().toISOString().split('T')[0]
    const todayRes = await http.get('/api/barbershop/reservations', {
      params: { date: today }
    })
    todayReservations.value = todayRes.data.reservations || []
    
    // Fetch upcoming reservations (next 7 days)
    const upcomingRes = await http.get('/api/barbershop/reservations', {
      params: { status: 'pending,confirmed' }
    })
    
    // Filter for future reservations
    const todayDate = new Date()
    upcomingReservations.value = (upcomingRes.data.reservations || [])
      .filter(r => new Date(r.reservation_date) >= todayDate)
      .sort((a, b) => new Date(a.reservation_date + ' ' + a.start_time) - new Date(b.reservation_date + ' ' + b.start_time))
      .slice(0, 5) // Show top 5 upcoming
    
    // Fetch barbers
    const barbersRes = await http.get('/api/barbershop/barbers')
    barbers.value = barbersRes.data.barbers || []
    
    // Fetch services
    const servicesRes = await http.get('/api/barbershop/services')
    services.value = servicesRes.data.services || []
    
  } catch (err) {
    console.error('Failed to fetch dashboard data:', err)
    error.value = t('barbershop.error', 'Error') + ': ' + (err.message || 'Unknown error')
  } finally {
    loading.value = false
  }
}

// Helper functions
const formatTime = (timeString: string) => {
  if (!timeString) return ''
  // Convert HH:MM:SS to HH:MM
  return timeString.substring(0, 5)
}

const getServiceName = (serviceId: number) => {
  const service = services.value.find(s => s.id === serviceId)
  return service ? service.name : 'Unknown Service'
}

const getBarberName = (barberId: number) => {
  const barber = barbers.value.find(b => b.id === barberId)
  return barber ? barber.name : 'Unknown Barber'
}

const getStatusClass = (status: string) => {
  return {
    'pending': 'status-pending',
    'confirmed': 'status-confirmed',
    'completed': 'status-completed',
    'cancelled': 'status-cancelled'
  }[status.toLowerCase()] || 'status-pending'
}

// Lifecycle
onMounted(() => {
  fetchDashboardData()
})
</script>

<style scoped>
.barbershop-extension {
  max-width: 1200px;
  margin: 0 auto;
  padding: 2rem;
}

.extension-header {
  margin-bottom: 2rem;
  text-align: center;
}

.extension-header h1 {
  color: var(--text-primary);
  font-size: 2rem;
  margin-bottom: 0.5rem;
}

.extension-header p {
  color: var(--text-secondary);
  font-size: 1rem;
}

.extension-navigation {
  display: flex;
  gap: 1rem;
  margin-bottom: 2rem;
  flex-wrap: wrap;
}

.nav-button {
  padding: 0.75rem 1.5rem;
  background-color: var(--background-secondary);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  text-decoration: none;
  transition: all 0.2s ease;
  font-weight: 500;
}

.nav-button:hover {
  background-color: var(--background-tertiary);
}

.nav-button.primary {
  background-color: var(--primary-color);
  color: white;
  border-color: var(--primary-color);
}

.nav-button.primary:hover {
  background-color: var(--primary-color-dark);
  border-color: var(--primary-color-dark);
}

.dashboard-summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1.5rem;
  margin-bottom: 2rem;
}

.summary-card {
  background-color: var(--background-secondary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 1.5rem;
  text-align: center;
}

.summary-card h3 {
  color: var(--text-secondary);
  font-size: 0.9rem;
  margin-bottom: 0.5rem;
  font-weight: 500;
}

.summary-value {
  color: var(--text-primary);
  font-size: 2rem;
  font-weight: 600;
  margin: 0;
}

.recent-activity {
  background-color: var(--background-secondary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 1.5rem;
}

.recent-activity h2 {
  color: var(--text-primary);
  margin-bottom: 1.5rem;
  font-size: 1.25rem;
}

.reservations-list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.reservation-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  background-color: var(--background-tertiary);
  border-radius: 6px;
  border: 1px solid var(--border-color);
}

.reservation-info {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.reservation-time {
  font-weight: 600;
  color: var(--primary-color);
}

.reservation-customer {
  font-weight: 500;
  color: var(--text-primary);
}

.reservation-service, .reservation-barber {
  color: var(--text-secondary);
  font-size: 0.9rem;
}

.reservation-status {
  padding: 0.25rem 0.75rem;
  border-radius: 12px;
  font-size: 0.8rem;
  font-weight: 600;
  text-transform: capitalize;
}

.status-pending {
  background-color: var(--warning-color-light);
  color: var(--warning-color);
}

.status-confirmed {
  background-color: var(--success-color-light);
  color: var(--success-color);
}

.status-completed {
  background-color: var(--info-color-light);
  color: var(--info-color);
}

.status-cancelled {
  background-color: var(--danger-color-light);
  color: var(--danger-color);
}

.no-data {
  text-align: center;
  padding: 2rem;
  color: var(--text-secondary);
  font-style: italic;
}

.loading {
  text-align: center;
  padding: 2rem;
  color: var(--text-secondary);
}

.error {
  text-align: center;
  padding: 2rem;
  color: var(--danger-color);
  background-color: var(--danger-color-light);
  border-radius: 8px;
  margin-top: 1rem;
}
</style>