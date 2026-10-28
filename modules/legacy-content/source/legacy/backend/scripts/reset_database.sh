#!/bin/bash

# Define paths
db_path="backend/mega_monitor.db"
alembic_path="backend/alembic"
admin_script_path="/home/laz/3mm/backend/scripts/create_admin_user.py"

# Function to log messages
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log "Starting database reset script."

# Ensure backend directory exists
if [ ! -d "backend" ]; then
    log "Creating missing backend directory."
    mkdir -p backend
fi

# Set PYTHONPATH dynamically
export PYTHONPATH=$(pwd)
log "PYTHONPATH set to $(pwd)"

# Recreate database file with writable permissions
if [ -f "$db_path" ]; then
    log "Removing existing database file at $db_path."
    rm "$db_path"
fi
log "Creating new database file at $db_path."
touch "$db_path"
chmod 666 "$db_path"

# Ensure Alembic is initialized
if [ ! -d "$alembic_path" ]; then
    log "Initializing Alembic."
    alembic init backend/alembic
else
    log "Alembic already initialized."
fi

# Drop all tables and reset the database
log "Dropping all tables and resetting the database."
python -c "from backend.db.base import Base; from backend.utils.db_engine import engine; Base.metadata.drop_all(bind=engine)"

# Apply Alembic migrations to recreate tables
log "Applying Alembic migrations to recreate tables."
alembic --config backend/alembic.ini upgrade head

# Populate the database with initial data
log "Populating the database with initial data."
python "$admin_script_path"

log "Finished database reset script."