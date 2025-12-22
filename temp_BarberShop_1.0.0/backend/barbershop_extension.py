"""
Barbershop Extension Backend Module
Complete barbershop management system with reservation functionality
"""

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, List, Dict, Any
from backend.database import get_db
from backend.utils.jwt_utils import decode_token
from backend.utils.auth_dep import try_get_claims, require_user
from backend.utils.extension_relationships import declare_extension_capabilities, call_api_endpoint
import json
import os
from datetime import datetime, time, timedelta
import uuid

# Helper function for database operations with commit

def execute_main_db_query(query: str, params: dict = None):
    """Execute query using main database session with proper commit/rollback"""
    db = next(get_db())
    try:
        result = db.execute(text(query), params or {})
        rows = []
        if result.returns_rows:
            for row in result.fetchall():
                if hasattr(row, '_mapping'):
                    rows.append(dict(row._mapping))
                else:
                    rows.append(dict(row))
        db.commit()
        return rows
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()

# Table names based on extension naming convention
TABLE_BARBERS = "ext_barbershopextension_barbers"
TABLE_SERVICES = "ext_barbershopextension_services"
TABLE_WORKING_HOURS = "ext_barbershopextension_working_hours"
TABLE_RESERVATIONS = "ext_barbershopextension_reservations"
TABLE_SERVICES_TRANSLATIONS = "ext_barbershopextension_services_translations"
TABLE_BARBERS_TRANSLATIONS = "ext_barbershopextension_barbers_translations"

def initialize_extension(context):
    """Initialize the Barbershop extension"""
    try:
        # Create tables if they don't exist
        create_tables()
        
        # Register tables with extension registry
        register_tables_with_extension_registry(context)
        
        # Declare extension capabilities
        declare_extension_capabilities("BarberShop", {
            "provides": {
                "components": {
                    "reservation_widget": {
                        "label": "barbershop.reservationWidget",
                        "component": "BarbershopWidget",
                        "description": "Embeddable reservation widget for pages"
                    }
                },
                "apis": {
                    "get_available_slots": {
                        "description": "Get available reservation slots",
                        "params": ["date", "barber_id", "service_id"]
                    },
                    "create_reservation": {
                        "description": "Create a new reservation",
                        "params": ["customer_data", "barber_id", "service_id", "date", "time"]
                    }
                }
            },
            "consumes": {
                "PagesExtension": {
                    "components": ["page_view"],
                    "apis": ["get_pages", "get_page_by_slug"]
                }
            }
        })
        
        # Register API routes
        router = APIRouter(prefix="/api/barbershop")
        
        # Barber Management Endpoints
        register_barber_endpoints(router)
        
        # Service Management Endpoints
        register_service_endpoints(router)
        
        # Working Hours Management Endpoints
        register_working_hours_endpoints(router)
        
        # Reservation Management Endpoints
        register_reservation_endpoints(router)
        
        # Translation Management Endpoints
        register_translation_endpoints(router)
        
        # Integration Endpoints
        register_integration_endpoints(router)
        
        context.register_router(router)
        
        return {
            "routes_registered": 25,
            "tables_created": 6,
            "status": "initialized"
        }
        
    except Exception as e:
        print(f"Barbershop extension initialization error: {e}")
        return {"status": "error", "error": str(e)}


def create_tables():
    """Create all necessary tables for the barbershop extension"""
    try:
        # Create barbers table
        execute_main_db_query(f"""
            CREATE TABLE IF NOT EXISTS "{TABLE_BARBERS}" (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT,
                phone TEXT,
                bio TEXT,
                image_url TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create services table
        execute_main_db_query(f"""
            CREATE TABLE IF NOT EXISTS "{TABLE_SERVICES}" (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                duration_minutes INTEGER NOT NULL,
                price DECIMAL(10,2) NOT NULL,
                image_url TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create working hours table
        execute_main_db_query(f"""
            CREATE TABLE IF NOT EXISTS "{TABLE_WORKING_HOURS}" (
                id SERIAL PRIMARY KEY,
                barber_id INTEGER REFERENCES "{TABLE_BARBERS}"(id),
                day_of_week INTEGER NOT NULL,
                start_time TIME NOT NULL,
                end_time TIME NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create reservations table
        execute_main_db_query(f"""
            CREATE TABLE IF NOT EXISTS "{TABLE_RESERVATIONS}" (
                id SERIAL PRIMARY KEY,
                customer_id INTEGER,
                customer_name TEXT NOT NULL,
                customer_email TEXT,
                customer_phone TEXT NOT NULL,
                barber_id INTEGER REFERENCES "{TABLE_BARBERS}"(id),
                service_id INTEGER REFERENCES "{TABLE_SERVICES}"(id),
                reservation_date DATE NOT NULL,
                start_time TIME NOT NULL,
                end_time TIME NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create services translations table
        execute_main_db_query(f"""
            CREATE TABLE IF NOT EXISTS "{TABLE_SERVICES_TRANSLATIONS}" (
                id SERIAL PRIMARY KEY,
                record_id INTEGER NOT NULL,
                language_code TEXT NOT NULL,
                translation_data JSONB NOT NULL,
                translation_coverage DECIMAL(5,2) DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(record_id, language_code)
            )
        """)
        
        # Create barbers translations table
        execute_main_db_query(f"""
            CREATE TABLE IF NOT EXISTS "{TABLE_BARBERS_TRANSLATIONS}" (
                id SERIAL PRIMARY KEY,
                record_id INTEGER NOT NULL,
                language_code TEXT NOT NULL,
                translation_data JSONB NOT NULL,
                translation_coverage DECIMAL(5,2) DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(record_id, language_code)
            )
        """)
        
        # Create indexes for performance
        execute_main_db_query(f'CREATE INDEX IF NOT EXISTS idx_{TABLE_BARBERS}_name ON "{TABLE_BARBERS}" (name)')
        execute_main_db_query(f'CREATE INDEX IF NOT EXISTS idx_{TABLE_BARBERS}_active ON "{TABLE_BARBERS}" (is_active)')
        execute_main_db_query(f'CREATE INDEX IF NOT EXISTS idx_{TABLE_SERVICES}_name ON "{TABLE_SERVICES}" (name)')
        execute_main_db_query(f'CREATE INDEX IF NOT EXISTS idx_{TABLE_SERVICES}_active ON "{TABLE_SERVICES}" (is_active)')
        execute_main_db_query(f'CREATE INDEX IF NOT EXISTS idx_{TABLE_WORKING_HOURS}_barber_day ON "{TABLE_WORKING_HOURS}" (barber_id, day_of_week)')
        execute_main_db_query(f'CREATE INDEX IF NOT EXISTS idx_{TABLE_RESERVATIONS}_barber_date ON "{TABLE_RESERVATIONS}" (barber_id, reservation_date, start_time)')
        execute_main_db_query(f'CREATE INDEX IF NOT EXISTS idx_{TABLE_RESERVATIONS}_customer ON "{TABLE_RESERVATIONS}" (customer_id)')
        
    except Exception as e:
        print(f"Error creating tables: {e}")
        raise


def register_tables_with_extension_registry(context):
    """Register tables with the extension registry for proper management"""
    try:
        # Get the extension database ID from name/version
        extension_name, extension_version = context.extension_id.rsplit('_', 1)
        extension_result = execute_main_db_query("""
            SELECT id FROM extensions
            WHERE name = :name AND version = :version
        """, {"name": extension_name, "version": extension_version})
        
        if extension_result:
            extension_db_id = extension_result[0]["id"]
            
            # Define table schemas for registration
            table_schemas = {
                TABLE_BARBERS: {
                    "id": {"type": "integer", "primary_key": True},
                    "name": {"type": "text", "multilingual": True},
                    "email": {"type": "text"},
                    "phone": {"type": "text"},
                    "bio": {"type": "text", "multilingual": True},
                    "image_url": {"type": "text"},
                    "is_active": {"type": "boolean"},
                    "created_at": {"type": "timestamp"},
                    "updated_at": {"type": "timestamp"}
                },
                TABLE_SERVICES: {
                    "id": {"type": "integer", "primary_key": True},
                    "name": {"type": "text", "multilingual": True},
                    "description": {"type": "text", "multilingual": True},
                    "duration_minutes": {"type": "integer"},
                    "price": {"type": "decimal"},
                    "image_url": {"type": "text"},
                    "is_active": {"type": "boolean"},
                    "created_at": {"type": "timestamp"},
                    "updated_at": {"type": "timestamp"}
                },
                TABLE_WORKING_HOURS: {
                    "id": {"type": "integer", "primary_key": True},
                    "barber_id": {"type": "integer"},
                    "day_of_week": {"type": "integer"},
                    "start_time": {"type": "time"},
                    "end_time": {"type": "time"},
                    "is_active": {"type": "boolean"},
                    "created_at": {"type": "timestamp"},
                    "updated_at": {"type": "timestamp"}
                },
                TABLE_RESERVATIONS: {
                    "id": {"type": "integer", "primary_key": True},
                    "customer_id": {"type": "integer"},
                    "customer_name": {"type": "text"},
                    "customer_email": {"type": "text"},
                    "customer_phone": {"type": "text"},
                    "barber_id": {"type": "integer"},
                    "service_id": {"type": "integer"},
                    "reservation_date": {"type": "date"},
                    "start_time": {"type": "time"},
                    "end_time": {"type": "time"},
                    "status": {"type": "text"},
                    "notes": {"type": "text"},
                    "created_at": {"type": "timestamp"},
                    "updated_at": {"type": "timestamp"}
                },
                TABLE_SERVICES_TRANSLATIONS: {
                    "id": {"type": "integer", "primary_key": True},
                    "record_id": {"type": "integer"},
                    "language_code": {"type": "text"},
                    "translation_data": {"type": "jsonb"},
                    "translation_coverage": {"type": "decimal"},
                    "created_at": {"type": "timestamp"},
                    "updated_at": {"type": "timestamp"}
                },
                TABLE_BARBERS_TRANSLATIONS: {
                    "id": {"type": "integer", "primary_key": True},
                    "record_id": {"type": "integer"},
                    "language_code": {"type": "text"},
                    "translation_data": {"type": "jsonb"},
                    "translation_coverage": {"type": "decimal"},
                    "created_at": {"type": "timestamp"},
                    "updated_at": {"type": "timestamp"}
                }
            }
            
            # Register each table
            for tbl_name, schema in table_schemas.items():
                translatable_fields = [field for field, config in schema.items() if config.get("multilingual", False)]
                
                execute_main_db_query("""
                    INSERT INTO extension_tables
                    (extension_id, table_name, table_schema, translatable_fields, primary_key_field, is_multilingual)
                    VALUES (:extension_id, :table_name, :table_schema, :translatable_fields, :primary_key, :is_multilingual)
                    ON CONFLICT (extension_id, table_name) DO UPDATE SET
                        table_schema = EXCLUDED.table_schema,
                        translatable_fields = EXCLUDED.translatable_fields,
                        primary_key_field = EXCLUDED.primary_key_field,
                        is_multilingual = EXCLUDED.is_multilingual
                """, {
                    "extension_id": extension_db_id,
                    "table_name": tbl_name,
                    "table_schema": json.dumps(schema),
                    "translatable_fields": json.dumps(translatable_fields),
                    "primary_key": "id",
                    "is_multilingual": len(translatable_fields) > 0
                })
                
                # Register fields
                for field_name, field_config in schema.items():
                    execute_main_db_query("""
                        INSERT INTO extension_fields
                        (extension_id, table_name, field_name, field_type, is_translatable, validation_rules, field_order)
                        VALUES (:extension_id, :table_name, :field_name, :field_type, :is_translatable, :validation_rules, :field_order)
                        ON CONFLICT (extension_id, table_name, field_name) DO UPDATE SET
                            field_type = EXCLUDED.field_type,
                            is_translatable = EXCLUDED.is_translatable,
                            validation_rules = EXCLUDED.validation_rules,
                            field_order = EXCLUDED.field_order
                    """, {
                        "extension_id": extension_db_id,
                        "table_name": tbl_name,
                        "field_name": field_name,
                        "field_type": field_config.get("type", "text"),
                        "is_translatable": field_config.get("multilingual", False),
                        "validation_rules": json.dumps(field_config.get("validation", {})),
                        "field_order": field_config.get("order", 0)
                    })
        
    except Exception as e:
        print(f"Warning: Failed to register table with extension registry: {e}")


def register_barber_endpoints(router):
    """Register barber management endpoints"""
    
    @router.get("/barbers")
    def get_barbers(
        claims: Optional[dict] = Depends(try_get_claims),
        language: Optional[str] = None
    ):
        """Get list of barbers"""
        try:
            current_language = language or "en"
            
            # Get all barbers
            barbers = execute_main_db_query(f"""
                SELECT id, name, email, phone, bio, image_url, is_active
                FROM "{TABLE_BARBERS}"
                ORDER BY name
            """)
            
            # Apply translations if needed
            if current_language != "en":
                for barber in barbers:
                    translation = execute_main_db_query(f"""
                        SELECT translation_data FROM "{TABLE_BARBERS_TRANSLATIONS}"
                        WHERE record_id = :record_id AND language_code = :language_code
                    """, {"record_id": barber["id"], "language_code": current_language})
                    
                    if translation and translation[0]["translation_data"]:
                        translation_data = translation[0]["translation_data"]
                        if isinstance(translation_data, str):
                            translation_data = json.loads(translation_data)
                        barber.update(translation_data)
            
            return {"barbers": barbers}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to fetch barbers: {str(e)}")
    
    @router.get("/barbers/{barber_id}")
    def get_barber(barber_id: int, language: Optional[str] = None):
        """Get specific barber"""
        try:
            current_language = language or "en"
            
            # Get barber
            barber = execute_main_db_query(f"""
                SELECT id, name, email, phone, bio, image_url, is_active
                FROM "{TABLE_BARBERS}"
                WHERE id = :barber_id
            """, {"barber_id": barber_id})
            
            if not barber:
                raise HTTPException(status_code=404, detail="Barber not found")
            
            barber_data = barber[0]
            
            # Apply translation if needed
            if current_language != "en":
                translation = execute_main_db_query(f"""
                    SELECT translation_data FROM "{TABLE_BARBERS_TRANSLATIONS}"
                    WHERE record_id = :record_id AND language_code = :language_code
                """, {"record_id": barber_id, "language_code": current_language})
                
                if translation and translation[0]["translation_data"]:
                    translation_data = translation[0]["translation_data"]
                    if isinstance(translation_data, str):
                        translation_data = json.loads(translation_data)
                    barber_data.update(translation_data)
            
            return barber_data
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to fetch barber: {str(e)}")
    
    @router.post("/barbers")
    def create_barber(
        barber_data: dict,
        claims: dict = Depends(require_user)
    ):
        """Create a new barber"""
        try:
            # Validate required fields
            if not barber_data.get("name"):
                raise HTTPException(status_code=400, detail="Name is required")
            
            # Insert barber
            result = execute_main_db_query(f"""
                INSERT INTO "{TABLE_BARBERS}"
                (name, email, phone, bio, image_url, is_active)
                VALUES (:name, :email, :phone, :bio, :image_url, :is_active)
                RETURNING id
            """, {
                "name": barber_data.get("name"),
                "email": barber_data.get("email"),
                "phone": barber_data.get("phone"),
                "bio": barber_data.get("bio"),
                "image_url": barber_data.get("image_url"),
                "is_active": barber_data.get("is_active", True)
            })
            
            return {"id": result[0]["id"], "message": "Barber created successfully"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create barber: {str(e)}")
    
    @router.put("/barbers/{barber_id}")
    def update_barber(
        barber_id: int,
        barber_data: dict,
        claims: dict = Depends(require_user)
    ):
        """Update a barber"""
        try:
            # Check if barber exists
            existing = execute_main_db_query(f"""
                SELECT id FROM "{TABLE_BARBERS}" WHERE id = :barber_id
            """, {"barber_id": barber_id})
            
            if not existing:
                raise HTTPException(status_code=404, detail="Barber not found")
            
            # Build update query
            update_fields = []
            update_values = {"barber_id": barber_id}
            
            if "name" in barber_data:
                update_fields.append("name = :name")
                update_values["name"] = barber_data["name"]
            
            if "email" in barber_data:
                update_fields.append("email = :email")
                update_values["email"] = barber_data["email"]
            
            if "phone" in barber_data:
                update_fields.append("phone = :phone")
                update_values["phone"] = barber_data["phone"]
            
            if "bio" in barber_data:
                update_fields.append("bio = :bio")
                update_values["bio"] = barber_data["bio"]
            
            if "image_url" in barber_data:
                update_fields.append("image_url = :image_url")
                update_values["image_url"] = barber_data["image_url"]
            
            if "is_active" in barber_data:
                update_fields.append("is_active = :is_active")
                update_values["is_active"] = barber_data["is_active"]
            
            if update_fields:
                execute_main_db_query(f"""
                    UPDATE "{TABLE_BARBERS}"
                    SET {', '.join(update_fields)}
                    WHERE id = :barber_id
                """, update_values)
            
            return {"message": "Barber updated successfully"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to update barber: {str(e)}")
    
    @router.delete("/barbers/{barber_id}")
    def delete_barber(
        barber_id: int,
        claims: dict = Depends(require_user)
    ):
        """Delete a barber"""
        try:
            # Check if barber exists
            existing = execute_main_db_query(f"""
                SELECT id FROM "{TABLE_BARBERS}" WHERE id = :barber_id
            """, {"barber_id": barber_id})
            
            if not existing:
                raise HTTPException(status_code=404, detail="Barber not found")
            
            # Delete barber
            execute_main_db_query(f"""
                DELETE FROM "{TABLE_BARBERS}" WHERE id = :barber_id
            """, {"barber_id": barber_id})
            
            return {"message": "Barber deleted successfully"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to delete barber: {str(e)}")


def register_service_endpoints(router):
    """Register service management endpoints"""
    
    @router.get("/services")
    def get_services(
        claims: Optional[dict] = Depends(try_get_claims),
        language: Optional[str] = None
    ):
        """Get list of services"""
        try:
            current_language = language or "en"
            
            # Get all services
            services = execute_main_db_query(f"""
                SELECT id, name, description, duration_minutes, price, image_url, is_active
                FROM "{TABLE_SERVICES}"
                ORDER BY name
            """)
            
            # Apply translations if needed
            if current_language != "en":
                for service in services:
                    translation = execute_main_db_query(f"""
                        SELECT translation_data FROM "{TABLE_SERVICES_TRANSLATIONS}"
                        WHERE record_id = :record_id AND language_code = :language_code
                    """, {"record_id": service["id"], "language_code": current_language})
                    
                    if translation and translation[0]["translation_data"]:
                        translation_data = translation[0]["translation_data"]
                        if isinstance(translation_data, str):
                            translation_data = json.loads(translation_data)
                        service.update(translation_data)
            
            return {"services": services}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to fetch services: {str(e)}")
    
    @router.get("/services/{service_id}")
    def get_service(service_id: int, language: Optional[str] = None):
        """Get specific service"""
        try:
            current_language = language or "en"
            
            # Get service
            service = execute_main_db_query(f"""
                SELECT id, name, description, duration_minutes, price, image_url, is_active
                FROM "{TABLE_SERVICES}"
                WHERE id = :service_id
            """, {"service_id": service_id})
            
            if not service:
                raise HTTPException(status_code=404, detail="Service not found")
            
            service_data = service[0]
            
            # Apply translation if needed
            if current_language != "en":
                translation = execute_main_db_query(f"""
                    SELECT translation_data FROM "{TABLE_SERVICES_TRANSLATIONS}"
                    WHERE record_id = :record_id AND language_code = :language_code
                """, {"record_id": service_id, "language_code": current_language})
                
                if translation and translation[0]["translation_data"]:
                    translation_data = translation[0]["translation_data"]
                    if isinstance(translation_data, str):
                        translation_data = json.loads(translation_data)
                    service_data.update(translation_data)
            
            return service_data
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to fetch service: {str(e)}")
    
    @router.post("/services")
    def create_service(
        service_data: dict,
        claims: dict = Depends(require_user)
    ):
        """Create a new service"""
        try:
            # Validate required fields
            if not service_data.get("name"):
                raise HTTPException(status_code=400, detail="Name is required")
            
            if not service_data.get("duration_minutes"):
                raise HTTPException(status_code=400, detail="Duration is required")
            
            if not service_data.get("price"):
                raise HTTPException(status_code=400, detail="Price is required")
            
            # Insert service
            result = execute_main_db_query(f"""
                INSERT INTO "{TABLE_SERVICES}"
                (name, description, duration_minutes, price, image_url, is_active)
                VALUES (:name, :description, :duration_minutes, :price, :image_url, :is_active)
                RETURNING id
            """, {
                "name": service_data.get("name"),
                "description": service_data.get("description"),
                "duration_minutes": service_data.get("duration_minutes"),
                "price": service_data.get("price"),
                "image_url": service_data.get("image_url"),
                "is_active": service_data.get("is_active", True)
            })
            
            return {"id": result[0]["id"], "message": "Service created successfully"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create service: {str(e)}")
    
    @router.put("/services/{service_id}")
    def update_service(
        service_id: int,
        service_data: dict,
        claims: dict = Depends(require_user)
    ):
        """Update a service"""
        try:
            # Check if service exists
            existing = execute_main_db_query(f"""
                SELECT id FROM "{TABLE_SERVICES}" WHERE id = :service_id
            """, {"service_id": service_id})
            
            if not existing:
                raise HTTPException(status_code=404, detail="Service not found")
            
            # Build update query
            update_fields = []
            update_values = {"service_id": service_id}
            
            if "name" in service_data:
                update_fields.append("name = :name")
                update_values["name"] = service_data["name"]
            
            if "description" in service_data:
                update_fields.append("description = :description")
                update_values["description"] = service_data["description"]
            
            if "duration_minutes" in service_data:
                update_fields.append("duration_minutes = :duration_minutes")
                update_values["duration_minutes"] = service_data["duration_minutes"]
            
            if "price" in service_data:
                update_fields.append("price = :price")
                update_values["price"] = service_data["price"]
            
            if "image_url" in service_data:
                update_fields.append("image_url = :image_url")
                update_values["image_url"] = service_data["image_url"]
            
            if "is_active" in service_data:
                update_fields.append("is_active = :is_active")
                update_values["is_active"] = service_data["is_active"]
            
            if update_fields:
                execute_main_db_query(f"""
                    UPDATE "{TABLE_SERVICES}"
                    SET {', '.join(update_fields)}
                    WHERE id = :service_id
                """, update_values)
            
            return {"message": "Service updated successfully"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to update service: {str(e)}")
    
    @router.delete("/services/{service_id}")
    def delete_service(
        service_id: int,
        claims: dict = Depends(require_user)
    ):
        """Delete a service"""
        try:
            # Check if service exists
            existing = execute_main_db_query(f"""
                SELECT id FROM "{TABLE_SERVICES}" WHERE id = :service_id
            """, {"service_id": service_id})
            
            if not existing:
                raise HTTPException(status_code=404, detail="Service not found")
            
            # Delete service
            execute_main_db_query(f"""
                DELETE FROM "{TABLE_SERVICES}" WHERE id = :service_id
            """, {"service_id": service_id})
            
            return {"message": "Service deleted successfully"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to delete service: {str(e)}")


def register_working_hours_endpoints(router):
    """Register working hours management endpoints"""
    
    @router.get("/working-hours")
    def get_working_hours(
        barber_id: Optional[int] = None,
        claims: Optional[dict] = Depends(try_get_claims)
    ):
        """Get working hours"""
        try:
            query = f"""
                SELECT id, barber_id, day_of_week, start_time, end_time, is_active
                FROM "{TABLE_WORKING_HOURS}"
            """
            params = {}
            
            if barber_id:
                query += " WHERE barber_id = :barber_id"
                params["barber_id"] = barber_id
            
            query += " ORDER BY barber_id, day_of_week"
            
            working_hours = execute_main_db_query(query, params)
            
            return {"working_hours": working_hours}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to fetch working hours: {str(e)}")
    
    @router.get("/working-hours/{working_hours_id}")
    def get_working_hours_item(working_hours_id: int):
        """Get specific working hours item"""
        try:
            working_hours = execute_main_db_query(f"""
                SELECT id, barber_id, day_of_week, start_time, end_time, is_active
                FROM "{TABLE_WORKING_HOURS}"
                WHERE id = :working_hours_id
            """, {"working_hours_id": working_hours_id})
            
            if not working_hours:
                raise HTTPException(status_code=404, detail="Working hours not found")
            
            return working_hours[0]
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to fetch working hours: {str(e)}")
    
    @router.post("/working-hours")
    def create_working_hours(
        working_hours_data: dict,
        claims: dict = Depends(require_user)
    ):
        """Create new working hours"""
        try:
            # Validate required fields
            if not working_hours_data.get("barber_id"):
                raise HTTPException(status_code=400, detail="Barber ID is required")
            
            if not working_hours_data.get("day_of_week"):
                raise HTTPException(status_code=400, detail="Day of week is required")
            
            if not working_hours_data.get("start_time"):
                raise HTTPException(status_code=400, detail="Start time is required")
            
            if not working_hours_data.get("end_time"):
                raise HTTPException(status_code=400, detail="End time is required")
            
            # Insert working hours
            result = execute_main_db_query(f"""
                INSERT INTO "{TABLE_WORKING_HOURS}"
                (barber_id, day_of_week, start_time, end_time, is_active)
                VALUES (:barber_id, :day_of_week, :start_time, :end_time, :is_active)
                RETURNING id
            """, {
                "barber_id": working_hours_data.get("barber_id"),
                "day_of_week": working_hours_data.get("day_of_week"),
                "start_time": working_hours_data.get("start_time"),
                "end_time": working_hours_data.get("end_time"),
                "is_active": working_hours_data.get("is_active", True)
            })
            
            return {"id": result[0]["id"], "message": "Working hours created successfully"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create working hours: {str(e)}")
    
    @router.put("/working-hours/{working_hours_id}")
    def update_working_hours(
        working_hours_id: int,
        working_hours_data: dict,
        claims: dict = Depends(require_user)
    ):
        """Update working hours"""
        try:
            # Check if working hours exist
            existing = execute_main_db_query(f"""
                SELECT id FROM "{TABLE_WORKING_HOURS}" WHERE id = :working_hours_id
            """, {"working_hours_id": working_hours_id})
            
            if not existing:
                raise HTTPException(status_code=404, detail="Working hours not found")
            
            # Build update query
            update_fields = []
            update_values = {"working_hours_id": working_hours_id}
            
            if "barber_id" in working_hours_data:
                update_fields.append("barber_id = :barber_id")
                update_values["barber_id"] = working_hours_data["barber_id"]
            
            if "day_of_week" in working_hours_data:
                update_fields.append("day_of_week = :day_of_week")
                update_values["day_of_week"] = working_hours_data["day_of_week"]
            
            if "start_time" in working_hours_data:
                update_fields.append("start_time = :start_time")
                update_values["start_time"] = working_hours_data["start_time"]
            
            if "end_time" in working_hours_data:
                update_fields.append("end_time = :end_time")
                update_values["end_time"] = working_hours_data["end_time"]
            
            if "is_active" in working_hours_data:
                update_fields.append("is_active = :is_active")
                update_values["is_active"] = working_hours_data["is_active"]
            
            if update_fields:
                execute_main_db_query(f"""
                    UPDATE "{TABLE_WORKING_HOURS}"
                    SET {', '.join(update_fields)}
                    WHERE id = :working_hours_id
                """, update_values)
            
            return {"message": "Working hours updated successfully"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to update working hours: {str(e)}")
    
    @router.delete("/working-hours/{working_hours_id}")
    def delete_working_hours(
        working_hours_id: int,
        claims: dict = Depends(require_user)
    ):
        """Delete working hours"""
        try:
            # Check if working hours exist
            existing = execute_main_db_query(f"""
                SELECT id FROM "{TABLE_WORKING_HOURS}" WHERE id = :working_hours_id
            """, {"working_hours_id": working_hours_id})
            
            if not existing:
                raise HTTPException(status_code=404, detail="Working hours not found")
            
            # Delete working hours
            execute_main_db_query(f"""
                DELETE FROM "{TABLE_WORKING_HOURS}" WHERE id = :working_hours_id
            """, {"working_hours_id": working_hours_id})
            
            return {"message": "Working hours deleted successfully"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to delete working hours: {str(e)}")


def register_reservation_endpoints(router):
    """Register reservation management endpoints"""
    
    @router.get("/reservations")
    def get_reservations(
        claims: Optional[dict] = Depends(try_get_claims),
        barber_id: Optional[int] = None,
        customer_id: Optional[int] = None,
        date: Optional[str] = None,
        status: Optional[str] = None
    ):
        """Get list of reservations"""
        try:
            query = f"""
                SELECT r.id, r.customer_id, r.customer_name, r.customer_email, r.customer_phone,
                       r.barber_id, r.service_id, r.reservation_date, r.start_time, r.end_time,
                       r.status, r.notes, r.created_at, r.updated_at
                FROM "{TABLE_RESERVATIONS}" r
            """
            params = {}
            conditions = []
            
            # Filter by user role
            if claims:
                user_id = claims.get("sub") or claims.get("user_id")
                user_role = claims.get("role", "")
                
                if user_role != "admin":
                    # Non-admin users can only see their own reservations
                    conditions.append(f"(r.customer_id = :user_id OR r.barber_id IN (SELECT id FROM '{TABLE_BARBERS}' WHERE id = :user_id))")
                    params["user_id"] = user_id
            else:
                # Anonymous users can only see their own reservations if they provide customer_id
                if customer_id:
                    conditions.append("r.customer_id = :customer_id")
                    params["customer_id"] = customer_id
                else:
                    # No access for anonymous users without customer_id
                    return {"reservations": []}
            
            # Additional filters
            if barber_id:
                conditions.append("r.barber_id = :barber_id")
                params["barber_id"] = barber_id
            
            if customer_id and "customer_id" not in params:
                conditions.append("r.customer_id = :customer_id")
                params["customer_id"] = customer_id
            
            if date:
                conditions.append("r.reservation_date = :date")
                params["date"] = date
            
            if status:
                conditions.append("r.status = :status")
                params["status"] = status
            
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            
            query += " ORDER BY r.reservation_date, r.start_time"
            
            reservations = execute_main_db_query(query, params)
            
            return {"reservations": reservations}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to fetch reservations: {str(e)}")
    
    @router.get("/reservations/{reservation_id}")
    def get_reservation(
        reservation_id: int,
        claims: Optional[dict] = Depends(try_get_claims)
    ):
        """Get specific reservation"""
        try:
            # Get reservation
            reservation = execute_main_db_query(f"""
                SELECT r.id, r.customer_id, r.customer_name, r.customer_email, r.customer_phone,
                       r.barber_id, r.service_id, r.reservation_date, r.start_time, r.end_time,
                       r.status, r.notes, r.created_at, r.updated_at
                FROM "{TABLE_RESERVATIONS}" r
                WHERE r.id = :reservation_id
            """, {"reservation_id": reservation_id})
            
            if not reservation:
                raise HTTPException(status_code=404, detail="Reservation not found")
            
            reservation_data = reservation[0]
            
            # Check permissions
            if claims:
                user_id = claims.get("sub") or claims.get("user_id")
                user_role = claims.get("role", "")
                
                if user_role != "admin":
                    # Check if user is the customer or the barber
                    if (reservation_data["customer_id"] != user_id and 
                        reservation_data["barber_id"] != user_id):
                        raise HTTPException(status_code=403, detail="No permission to view this reservation")
            else:
                # Anonymous users can only view their own reservations
                if not reservation_data["customer_id"]:
                    raise HTTPException(status_code=403, detail="No permission to view this reservation")
            
            return reservation_data
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to fetch reservation: {str(e)}")
    
    @router.post("/reservations")
    def create_reservation(
        reservation_data: dict,
        claims: Optional[dict] = Depends(try_get_claims)
    ):
        """Create a new reservation"""
        try:
            # Validate required fields
            if not reservation_data.get("customer_name"):
                raise HTTPException(status_code=400, detail="Customer name is required")
            
            if not reservation_data.get("customer_phone"):
                raise HTTPException(status_code=400, detail="Customer phone is required")
            
            if not reservation_data.get("barber_id"):
                raise HTTPException(status_code=400, detail="Barber ID is required")
            
            if not reservation_data.get("service_id"):
                raise HTTPException(status_code=400, detail="Service ID is required")
            
            if not reservation_data.get("reservation_date"):
                raise HTTPException(status_code=400, detail="Reservation date is required")
            
            if not reservation_data.get("start_time"):
                raise HTTPException(status_code=400, detail="Start time is required")
            
            # Get service duration to calculate end time
            service = execute_main_db_query(f"""
                SELECT duration_minutes FROM "{TABLE_SERVICES}" WHERE id = :service_id
            """, {"service_id": reservation_data["service_id"]})
            
            if not service:
                raise HTTPException(status_code=400, detail="Service not found")
            
            duration_minutes = service[0]["duration_minutes"]
            
            # Calculate end time
            start_time = datetime.strptime(reservation_data["start_time"], "%H:%M:%S").time()
            start_datetime = datetime.combine(datetime.now().date(), start_time)
            end_datetime = start_datetime + timedelta(minutes=duration_minutes)
            end_time = end_datetime.time()
            
            # Check availability
            check_availability(
                reservation_data["barber_id"],
                reservation_data["reservation_date"],
                reservation_data["start_time"],
                end_time.strftime("%H:%M:%S")
            )
            
            # Set customer_id if authenticated
            customer_id = None
            if claims:
                customer_id = claims.get("sub") or claims.get("user_id")
            
            # Insert reservation
            result = execute_main_db_query(f"""
                INSERT INTO "{TABLE_RESERVATIONS}"
                (customer_id, customer_name, customer_email, customer_phone, barber_id, service_id,
                 reservation_date, start_time, end_time, status, notes)
                VALUES (:customer_id, :customer_name, :customer_email, :customer_phone, :barber_id, :service_id,
                        :reservation_date, :start_time, :end_time, :status, :notes)
                RETURNING id
            """, {
                "customer_id": customer_id,
                "customer_name": reservation_data["customer_name"],
                "customer_email": reservation_data.get("customer_email"),
                "customer_phone": reservation_data["customer_phone"],
                "barber_id": reservation_data["barber_id"],
                "service_id": reservation_data["service_id"],
                "reservation_date": reservation_data["reservation_date"],
                "start_time": reservation_data["start_time"],
                "end_time": end_time.strftime("%H:%M:%S"),
                "status": reservation_data.get("status", "pending"),
                "notes": reservation_data.get("notes")
            })
            
            return {"id": result[0]["id"], "message": "Reservation created successfully"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create reservation: {str(e)}")
    
    @router.put("/reservations/{reservation_id}")
    def update_reservation(
        reservation_id: int,
        reservation_data: dict,
        claims: dict = Depends(require_user)
    ):
        """Update a reservation"""
        try:
            # Get existing reservation
            existing = execute_main_db_query(f"""
                SELECT id, customer_id, barber_id, service_id, status
                FROM "{TABLE_RESERVATIONS}" WHERE id = :reservation_id
            """, {"reservation_id": reservation_id})
            
            if not existing:
                raise HTTPException(status_code=404, detail="Reservation not found")
            
            existing_reservation = existing[0]
            
            # Check permissions
            user_id = claims.get("sub") or claims.get("user_id")
            user_role = claims.get("role", "")
            
            if user_role != "admin":
                # Check if user is the customer or the barber
                if (existing_reservation["customer_id"] != user_id and 
                    existing_reservation["barber_id"] != user_id):
                    raise HTTPException(status_code=403, detail="No permission to update this reservation")
            
            # Build update query
            update_fields = []
            update_values = {"reservation_id": reservation_id}
            
            if "customer_name" in reservation_data:
                update_fields.append("customer_name = :customer_name")
                update_values["customer_name"] = reservation_data["customer_name"]
            
            if "customer_email" in reservation_data:
                update_fields.append("customer_email = :customer_email")
                update_values["customer_email"] = reservation_data["customer_email"]
            
            if "customer_phone" in reservation_data:
                update_fields.append("customer_phone = :customer_phone")
                update_values["customer_phone"] = reservation_data["customer_phone"]
            
            if "barber_id" in reservation_data:
                update_fields.append("barber_id = :barber_id")
                update_values["barber_id"] = reservation_data["barber_id"]
            
            if "service_id" in reservation_data:
                update_fields.append("service_id = :service_id")
                update_values["service_id"] = reservation_data["service_id"]
            
            if "reservation_date" in reservation_data:
                update_fields.append("reservation_date = :reservation_date")
                update_values["reservation_date"] = reservation_data["reservation_date"]
            
            if "start_time" in reservation_data:
                update_fields.append("start_time = :start_time")
                update_values["start_time"] = reservation_data["start_time"]
            
            if "status" in reservation_data:
                update_fields.append("status = :status")
                update_values["status"] = reservation_data["status"]
            
            if "notes" in reservation_data:
                update_fields.append("notes = :notes")
                update_values["notes"] = reservation_data["notes"]
            
            if update_fields:
                execute_main_db_query(f"""
                    UPDATE "{TABLE_RESERVATIONS}"
                    SET {', '.join(update_fields)}
                    WHERE id = :reservation_id
                """, update_values)
            
            return {"message": "Reservation updated successfully"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to update reservation: {str(e)}")
    
    @router.delete("/reservations/{reservation_id}")
    def delete_reservation(
        reservation_id: int,
        claims: dict = Depends(require_user)
    ):
        """Cancel a reservation"""
        try:
            # Get existing reservation
            existing = execute_main_db_query(f"""
                SELECT id, customer_id, barber_id, status
                FROM "{TABLE_RESERVATIONS}" WHERE id = :reservation_id
            """, {"reservation_id": reservation_id})
            
            if not existing:
                raise HTTPException(status_code=404, detail="Reservation not found")
            
            existing_reservation = existing[0]
            
            # Check permissions
            user_id = claims.get("sub") or claims.get("user_id")
            user_role = claims.get("role", "")
            
            if user_role != "admin":
                # Check if user is the customer or the barber
                if (existing_reservation["customer_id"] != user_id and 
                    existing_reservation["barber_id"] != user_id):
                    raise HTTPException(status_code=403, detail="No permission to cancel this reservation")
            
            # Delete reservation
            execute_main_db_query(f"""
                DELETE FROM "{TABLE_RESERVATIONS}" WHERE id = :reservation_id
            """, {"reservation_id": reservation_id})
            
            return {"message": "Reservation cancelled successfully"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to cancel reservation: {str(e)}")
    
    @router.get("/reservations/available")
    def get_available_slots(
        date: str,
        barber_id: Optional[int] = None,
        service_id: Optional[int] = None
    ):
        """Get available time slots for reservations"""
        try:
            # Validate date format
            try:
                reservation_date = datetime.strptime(date, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
            
            # Get service duration if service_id provided
            service_duration = 30  # default
            if service_id:
                service = execute_main_db_query(f"""
                    SELECT duration_minutes FROM "{TABLE_SERVICES}" WHERE id = :service_id
                """, {"service_id": service_id})
                
                if service:
                    service_duration = service[0]["duration_minutes"]
            
            # Get working hours for the barber
            working_hours_query = f"""
                SELECT day_of_week, start_time, end_time
                FROM "{TABLE_WORKING_HOURS}"
                WHERE is_active = TRUE
            """
            params = {}
            
            if barber_id:
                working_hours_query += " AND barber_id = :barber_id"
                params["barber_id"] = barber_id
            
            working_hours = execute_main_db_query(working_hours_query, params)
            
            # Get day of week (0=Monday, 6=Sunday)
            day_of_week = reservation_date.weekday()
            
            # Find working hours for this day
            today_working_hours = None
            for wh in working_hours:
                if wh["day_of_week"] == day_of_week:
                    if barber_id and wh["barber_id"] == barber_id:
                        today_working_hours = wh
                        break
                    elif not barber_id:
                        today_working_hours = wh
                        break
            
            if not today_working_hours:
                return {"available_slots": [], "message": "No working hours for this day"}
            
            # Calculate available slots
            start_time = datetime.strptime(today_working_hours["start_time"], "%H:%M:%S").time()
            end_time = datetime.strptime(today_working_hours["end_time"], "%H:%M:%S").time()
            
            # Get existing reservations for this day
            existing_reservations = execute_main_db_query(f"""
                SELECT start_time, end_time
                FROM "{TABLE_RESERVATIONS}"
                WHERE reservation_date = :date
                AND status IN ('pending', 'confirmed')
                {"AND barber_id = :barber_id" if barber_id else ""}
            """, {"date": date, **({"barber_id": barber_id} if barber_id else {})})
            
            # Generate time slots
            available_slots = []
            current_time = datetime.combine(reservation_date, start_time)
            end_datetime = datetime.combine(reservation_date, end_time)
            
            while current_time < end_datetime:
                slot_end = current_time + timedelta(minutes=service_duration)
                
                # Check if this slot is available
                slot_available = True
                for reservation in existing_reservations:
                    res_start = datetime.strptime(reservation["start_time"], "%H:%M:%S").time()
                    res_end = datetime.strptime(reservation["end_time"], "%H:%M:%S").time()
                    
                    res_start_dt = datetime.combine(reservation_date, res_start)
                    res_end_dt = datetime.combine(reservation_date, res_end)
                    
                    # Check for overlap
                    if not (slot_end <= res_start_dt or current_time >= res_end_dt):
                        slot_available = False
                        break
                
                if slot_available:
                    available_slots.append({
                        "start_time": current_time.strftime("%H:%M"),
                        "end_time": slot_end.strftime("%H:%M"),
                        "formatted": f"{current_time.strftime('%H:%M')} - {slot_end.strftime('%H:%M')}"
                    })
                
                current_time = slot_end
            
            return {"available_slots": available_slots}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to get available slots: {str(e)}")


def check_availability(barber_id: int, date: str, start_time: str, end_time: str):
    """Check if a time slot is available for reservation"""
    try:
        # Check if barber exists and is active
        barber = execute_main_db_query(f"""
            SELECT id FROM "{TABLE_BARBERS}" WHERE id = :barber_id AND is_active = TRUE
        """, {"barber_id": barber_id})
        
        if not barber:
            raise HTTPException(status_code=400, detail="Barber not found or not active")
        
        # Check if there's a conflicting reservation
        conflicting = execute_main_db_query(f"""
            SELECT id FROM "{TABLE_RESERVATIONS}"
            WHERE barber_id = :barber_id
            AND reservation_date = :date
            AND status IN ('pending', 'confirmed')
            AND (
                (start_time < :end_time AND end_time > :start_time)
            )
        """, {
            "barber_id": barber_id,
            "date": date,
            "start_time": start_time,
            "end_time": end_time
        })
        
        if conflicting:
            raise HTTPException(status_code=400, detail="Time slot is not available")
        
        return True
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Availability check failed: {str(e)}")


def register_translation_endpoints(router):
    """Register translation management endpoints"""
    
    @router.post("/services/{service_id}/translations")
    def add_service_translation(
        service_id: int,
        translation_data: dict,
        claims: dict = Depends(require_user)
    ):
        """Add translation for a service"""
        try:
            # Validate service exists
            service = execute_main_db_query(f"""
                SELECT id FROM "{TABLE_SERVICES}" WHERE id = :service_id
            """, {"service_id": service_id})
            
            if not service:
                raise HTTPException(status_code=404, detail="Service not found")
            
            # Validate translation data
            if not translation_data.get("language_code"):
                raise HTTPException(status_code=400, detail="language_code is required")
            
            if not translation_data.get("translations"):
                raise HTTPException(status_code=400, detail="translations is required")
            
            language_code = translation_data["language_code"]
            translations = translation_data["translations"]
            
            # Insert or update translation
            translation_json = json.dumps(translations)
            
            # Check if translation already exists
            existing = execute_main_db_query(f"""
                SELECT id FROM "{TABLE_SERVICES_TRANSLATIONS}"
                WHERE record_id = :record_id AND language_code = :language_code
            """, {"record_id": service_id, "language_code": language_code})
            
            if existing:
                # Update existing translation
                execute_main_db_query(f"""
                    UPDATE "{TABLE_SERVICES_TRANSLATIONS}"
                    SET translation_data = :translation_data,
                        translation_coverage = :coverage,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE record_id = :record_id AND language_code = :language_code
                """, {
                    "translation_data": translation_json,
                    "coverage": len(translations) / 2 * 100,  # 2 translatable fields
                    "record_id": service_id,
                    "language_code": language_code
                })
            else:
                # Insert new translation
                execute_main_db_query(f"""
                    INSERT INTO "{TABLE_SERVICES_TRANSLATIONS}"
                    (record_id, language_code, translation_data, translation_coverage)
                    VALUES (:record_id, :language_code, :translation_data, :coverage)
                """, {
                    "record_id": service_id,
                    "language_code": language_code,
                    "translation_data": translation_json,
                    "coverage": len(translations) / 2 * 100
                })
            
            return {"message": f"Service translation added for {language_code}"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to add service translation: {str(e)}")
    
    @router.get("/services/{service_id}/translations")
    def get_service_translations(
        service_id: int,
        claims: Optional[dict] = Depends(try_get_claims)
    ):
        """Get all translations for a service"""
        try:
            # Validate service exists
            service = execute_main_db_query(f"""
                SELECT id FROM "{TABLE_SERVICES}" WHERE id = :service_id
            """, {"service_id": service_id})
            
            if not service:
                raise HTTPException(status_code=404, detail="Service not found")
            
            # Get translations
            translations = execute_main_db_query(f"""
                SELECT language_code, translation_data, translation_coverage
                FROM "{TABLE_SERVICES_TRANSLATIONS}"
                WHERE record_id = :record_id
            """, {"record_id": service_id})
            
            return {
                "service_id": service_id,
                "translations": [{
                    "language_code": t["language_code"],
                    "data": json.loads(t["translation_data"]) if isinstance(t["translation_data"], str) else t["translation_data"],
                    "coverage": float(t["translation_coverage"]) if t["translation_coverage"] else 0
                } for t in translations]
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to get service translations: {str(e)}")
    
    @router.post("/barbers/{barber_id}/translations")
    def add_barber_translation(
        barber_id: int,
        translation_data: dict,
        claims: dict = Depends(require_user)
    ):
        """Add translation for a barber"""
        try:
            # Validate barber exists
            barber = execute_main_db_query(f"""
                SELECT id FROM "{TABLE_BARBERS}" WHERE id = :barber_id
            """, {"barber_id": barber_id})
            
            if not barber:
                raise HTTPException(status_code=404, detail="Barber not found")
            
            # Validate translation data
            if not translation_data.get("language_code"):
                raise HTTPException(status_code=400, detail="language_code is required")
            
            if not translation_data.get("translations"):
                raise HTTPException(status_code=400, detail="translations is required")
            
            language_code = translation_data["language_code"]
            translations = translation_data["translations"]
            
            # Insert or update translation
            translation_json = json.dumps(translations)
            
            # Check if translation already exists
            existing = execute_main_db_query(f"""
                SELECT id FROM "{TABLE_BARBERS_TRANSLATIONS}"
                WHERE record_id = :record_id AND language_code = :language_code
            """, {"record_id": barber_id, "language_code": language_code})
            
            if existing:
                # Update existing translation
                execute_main_db_query(f"""
                    UPDATE "{TABLE_BARBERS_TRANSLATIONS}"
                    SET translation_data = :translation_data,
                        translation_coverage = :coverage,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE record_id = :record_id AND language_code = :language_code
                """, {
                    "translation_data": translation_json,
                    "coverage": len(translations) / 2 * 100,  # 2 translatable fields
                    "record_id": barber_id,
                    "language_code": language_code
                })
            else:
                # Insert new translation
                execute_main_db_query(f"""
                    INSERT INTO "{TABLE_BARBERS_TRANSLATIONS}"
                    (record_id, language_code, translation_data, translation_coverage)
                    VALUES (:record_id, :language_code, :translation_data, :coverage)
                """, {
                    "record_id": barber_id,
                    "language_code": language_code,
                    "translation_data": translation_json,
                    "coverage": len(translations) / 2 * 100
                })
            
            return {"message": f"Barber translation added for {language_code}"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to add barber translation: {str(e)}")
    
    @router.get("/barbers/{barber_id}/translations")
    def get_barber_translations(
        barber_id: int,
        claims: Optional[dict] = Depends(try_get_claims)
    ):
        """Get all translations for a barber"""
        try:
            # Validate barber exists
            barber = execute_main_db_query(f"""
                SELECT id FROM "{TABLE_BARBERS}" WHERE id = :barber_id
            """, {"barber_id": barber_id})
            
            if not barber:
                raise HTTPException(status_code=404, detail="Barber not found")
            
            # Get translations
            translations = execute_main_db_query(f"""
                SELECT language_code, translation_data, translation_coverage
                FROM "{TABLE_BARBERS_TRANSLATIONS}"
                WHERE record_id = :record_id
            """, {"record_id": barber_id})
            
            return {
                "barber_id": barber_id,
                "translations": [{
                    "language_code": t["language_code"],
                    "data": json.loads(t["translation_data"]) if isinstance(t["translation_data"], str) else t["translation_data"],
                    "coverage": float(t["translation_coverage"]) if t["translation_coverage"] else 0
                } for t in translations]
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to get barber translations: {str(e)}")


def register_integration_endpoints(router):
    """Register integration endpoints for Pages extension"""
    
    @router.get("/integration/pages-contact")
    def get_pages_contact_info():
        """Get contact information from Pages extension"""
        try:
            # Call Pages extension API to get contact page
            result = call_api_endpoint("PagesExtension", "get_page_by_slug", slug="contact")
            return result
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to get contact info: {str(e)}")
    
    @router.get("/integration/pages-about")
    def get_pages_about_info():
        """Get about information from Pages extension"""
        try:
            # Call Pages extension API to get about page
            result = call_api_endpoint("PagesExtension", "get_page_by_slug", slug="about")
            return result
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to get about info: {str(e)}")


def cleanup_extension(context):
    """Cleanup when extension is disabled"""
    try:
        # Note: We don't drop tables as they might contain user data
        # The extension can be safely disabled while preserving data
        return {"status": "cleaned_up"}
    except Exception as e:
        print(f"Barbershop extension cleanup error: {e}")
        return {"status": "cleanup_error", "error": str(e)}