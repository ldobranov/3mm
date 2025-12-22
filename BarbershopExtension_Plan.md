# Barbershop Extension Plan

## Overview
This plan outlines the creation of a Barbershop extension with a reservation system that integrates with the existing Pages extension for contact and information pages.

## Requirements Analysis

### Core Features
1. **Reservation Management System**
   - Create, read, update, delete reservations
   - Time slot management
   - Barbers/stylists management
   - Service catalog
   - Customer information management

2. **Integration with Pages Extension**
   - Use existing Pages extension for contact information
   - Use existing Pages extension for barbershop information pages
   - Embed reservation widgets in pages

3. **Multilingual Support**
   - English and Bulgarian support
   - Translatable content for services, barbers, etc.

4. **User Roles**
   - Admin: Full access
   - Barbers: View and manage their own reservations
   - Customers: Create and manage their own reservations

## Database Schema Design

### Main Tables

#### 1. Barbers Table (`ext_barbershopextension_barbers`)
```sql
CREATE TABLE ext_barbershopextension_barbers (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    bio TEXT,
    image_url TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 2. Services Table (`ext_barbershopextension_services`)
```sql
CREATE TABLE ext_barbershopextension_services (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    duration_minutes INTEGER NOT NULL,
    price DECIMAL(10,2) NOT NULL,
    image_url TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 3. Working Hours Table (`ext_barbershopextension_working_hours`)
```sql
CREATE TABLE ext_barbershopextension_working_hours (
    id SERIAL PRIMARY KEY,
    barber_id INTEGER REFERENCES ext_barbershopextension_barbers(id),
    day_of_week INTEGER NOT NULL, -- 0=Monday, 6=Sunday
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 4. Reservations Table (`ext_barbershopextension_reservations`)
```sql
CREATE TABLE ext_barbershopextension_reservations (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER, -- User ID from main system
    customer_name TEXT NOT NULL,
    customer_email TEXT,
    customer_phone TEXT NOT NULL,
    barber_id INTEGER REFERENCES ext_barbershopextension_barbers(id),
    service_id INTEGER REFERENCES ext_barbershopextension_services(id),
    reservation_date DATE NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending', -- pending, confirmed, completed, cancelled
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 5. Translations Tables
```sql
CREATE TABLE ext_barbershopextension_services_translations (
    id SERIAL PRIMARY KEY,
    record_id INTEGER NOT NULL,
    language_code TEXT NOT NULL,
    translation_data JSONB NOT NULL,
    translation_coverage DECIMAL(5,2) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(record_id, language_code)
);

CREATE TABLE ext_barbershopextension_barbers_translations (
    id SERIAL PRIMARY KEY,
    record_id INTEGER NOT NULL,
    language_code TEXT NOT NULL,
    translation_data JSONB NOT NULL,
    translation_coverage DECIMAL(5,2) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(record_id, language_code)
);
```

## Backend Architecture

### API Endpoints

#### Barbers Management
- `GET /api/barbershop/barbers` - List all barbers
- `GET /api/barbershop/barbers/{id}` - Get specific barber
- `POST /api/barbershop/barbers` - Create new barber
- `PUT /api/barbershop/barbers/{id}` - Update barber
- `DELETE /api/barbershop/barbers/{id}` - Delete barber

#### Services Management
- `GET /api/barbershop/services` - List all services
- `GET /api/barbershop/services/{id}` - Get specific service
- `POST /api/barbershop/services` - Create new service
- `PUT /api/barbershop/services/{id}` - Update service
- `DELETE /api/barbershop/services/{id}` - Delete service

#### Working Hours Management
- `GET /api/barbershop/working-hours` - List working hours
- `GET /api/barbershop/working-hours/{id}` - Get specific working hours
- `POST /api/barbershop/working-hours` - Create working hours
- `PUT /api/barbershop/working-hours/{id}` - Update working hours
- `DELETE /api/barbershop/working-hours/{id}` - Delete working hours

#### Reservations Management
- `GET /api/barbershop/reservations` - List all reservations
- `GET /api/barbershop/reservations/{id}` - Get specific reservation
- `POST /api/barbershop/reservations` - Create new reservation
- `PUT /api/barbershop/reservations/{id}` - Update reservation
- `DELETE /api/barbershop/reservations/{id}` - Cancel reservation
- `GET /api/barbershop/reservations/available` - Get available time slots

#### Translation Management
- `POST /api/barbershop/services/{id}/translations` - Add service translation
- `GET /api/barbershop/services/{id}/translations` - Get service translations
- `POST /api/barbershop/barbers/{id}/translations` - Add barber translation
- `GET /api/barbershop/barbers/{id}/translations` - Get barber translations

## Frontend Architecture

### Vue Components

#### 1. Main Components
- `BarbershopExtension.vue` - Main entry point
- `BarbershopDashboard.vue` - Admin dashboard
- `ReservationCalendar.vue` - Calendar view for reservations
- `BarberManagement.vue` - Manage barbers
- `ServiceManagement.vue` - Manage services
- `WorkingHoursManagement.vue` - Manage working hours

#### 2. Customer Components
- `ReservationForm.vue` - Customer reservation form
- `MyReservations.vue` - Customer's reservation history
- `BarberList.vue` - List of available barbers
- `ServiceList.vue` - List of available services

#### 3. Integration Components
- `BarbershopWidget.vue` - Embeddable widget for pages
- `ReservationWidget.vue` - Mini reservation form for pages

### Routes
```json
{
  "frontend_routes": [
    {
      "path": "/barbershop",
      "component": "BarbershopExtension.vue",
      "name": "Barbershop",
      "meta": {"requiresAuth": true}
    },
    {
      "path": "/barbershop/reservations",
      "component": "ReservationCalendar.vue",
      "name": "BarbershopReservations",
      "meta": {"requiresAuth": true}
    },
    {
      "path": "/barbershop/barbers",
      "component": "BarberManagement.vue",
      "name": "BarbershopBarbers",
      "meta": {"requiresAuth": true}
    },
    {
      "path": "/barbershop/services",
      "component": "ServiceManagement.vue",
      "name": "BarbershopServices",
      "meta": {"requiresAuth": true}
    },
    {
      "path": "/barbershop/book",
      "component": "ReservationForm.vue",
      "name": "BarbershopBook",
      "meta": {"requiresAuth": false}
    },
    {
      "path": "/barbershop/my-reservations",
      "component": "MyReservations.vue",
      "name": "BarbershopMyReservations",
      "meta": {"requiresAuth": true}
    }
  ]
}
```

## Integration with Pages Extension

### Embedding Strategy
1. **Reservation Widget**: Embed a mini reservation form in contact pages
2. **Barbershop Info**: Use Pages extension for barbershop information pages
3. **Contact Information**: Use Pages extension for contact details

### API Integration
- Use Pages extension API to fetch contact information
- Embed reservation widgets using iframe or component injection
- Share authentication between extensions

## Multilingual Support

### Translation Keys Structure
```json
{
  "barbershop": {
    "title": "Barbershop",
    "reservations": {
      "title": "Reservations",
      "newReservation": "New Reservation",
      "myReservations": "My Reservations"
    },
    "services": {
      "title": "Services",
      "haircut": "Haircut",
      "shave": "Shave",
      "beardTrim": "Beard Trim"
    },
    "barbers": {
      "title": "Barbers",
      "available": "Available Barbers"
    }
  }
}
```

## Implementation Plan

### Phase 1: Backend Development
1. Create database tables and migrations
2. Implement API endpoints for barbers management
3. Implement API endpoints for services management
4. Implement API endpoints for working hours management
5. Implement API endpoints for reservations management
6. Implement translation management endpoints

### Phase 2: Frontend Development
1. Create main Vue components
2. Implement reservation calendar
3. Create management interfaces
4. Implement customer-facing components
5. Create embeddable widgets

### Phase 3: Integration
1. Integrate with Pages extension
2. Set up authentication sharing
3. Create embeddable widgets for pages
4. Test cross-extension functionality

### Phase 4: Testing
1. Unit testing for backend endpoints
2. Component testing for frontend
3. Integration testing between extensions
4. User acceptance testing

## Timeline

- **Week 1**: Backend development (database + API)
- **Week 2**: Frontend development (Vue components)
- **Week 3**: Integration with Pages extension
- **Week 4**: Testing and bug fixing
- **Week 5**: Deployment and documentation

## Technical Considerations

1. **Performance**: Optimize database queries for reservation availability
2. **Security**: Ensure proper authentication and authorization
3. **Error Handling**: Comprehensive error handling for API endpoints
4. **Validation**: Input validation for all forms and API calls
5. **Documentation**: Complete API documentation and user guides

## Success Criteria

1. Users can create, view, and manage reservations
2. Admin can manage barbers, services, and working hours
3. System supports multiple languages (English, Bulgarian)
4. Integration with Pages extension works seamlessly
5. All functionality is properly tested and documented

This plan provides a comprehensive roadmap for developing the Barbershop extension with reservation system that integrates with the existing Pages extension.