#!/bin/bash

# 3mm Application Uninstall Script
# Clean removal of all components

# Color codes for better output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration file
CONFIG_FILE="install_config.json"
LOG_FILE="uninstall.log"
BACKUP_DIR="uninstall_backup_$(date +%Y%m%d_%H%M%S)"

# Logging function
log() {
  echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Error handling
error_exit() {
  log "${RED}❌ Error: $1${NC}"
  exit 1
}

# Backup configuration
backup_config() {
  if [ -f "$CONFIG_FILE" ]; then
    mkdir -p "$BACKUP_DIR"
    cp "$CONFIG_FILE" "$BACKUP_DIR/"
    log "${GREEN}✅ Configuration backed up to $BACKUP_DIR/${NC}"
  fi
}

# Stop services
stop_services() {
  log "${BLUE}🛑 Stopping services...${NC}"
  
  if sudo systemctl is-active --quiet 3mm.service; then
    sudo systemctl stop 3mm.service
    log "${GREEN}✅ 3mm service stopped${NC}"
  fi
  
  # Disable service
  if sudo systemctl is-enabled --quiet 3mm.service; then
    sudo systemctl disable 3mm.service
    log "${GREEN}✅ 3mm service disabled${NC}"
  fi
  
  # Remove service file
  if [ -f "/etc/systemd/system/3mm.service" ]; then
    sudo rm /etc/systemd/system/3mm.service
    sudo systemctl daemon-reload
    log "${GREEN}✅ Service file removed${NC}"
  fi
}

# Remove database
remove_database() {
  log "${BLUE}🗄️  Removing database...${NC}"
  
  if [ -f "$CONFIG_FILE" ]; then
    DB_TYPE=$(jq -r '.database.type' "$CONFIG_FILE")
    DB_USER=$(jq -r '.database.username' "$CONFIG_FILE")
    DB_NAME=$(jq -r '.database.db_name' "$CONFIG_FILE")
    
    case "$DB_TYPE" in
      sqlite)
        if [ -f "backend/mega_monitor.db" ]; then
          read -p "Delete SQLite database file? (y/n) [n]: " DELETE_DB
          if [[ "$DELETE_DB" =~ ^[Yy]$ ]]; then
            rm -f backend/mega_monitor.db
            log "${GREEN}✅ SQLite database file removed${NC}"
          else
            log "${YELLOW}⚠️  SQLite database file preserved${NC}"
          fi
        fi
        ;;
      postgresql)
        log "${BLUE}🐘 Removing PostgreSQL database and user...${NC}"
        
        # Check if PostgreSQL is running
        if pg_isready -q; then
          sudo -u postgres psql -c "DROP DATABASE IF EXISTS $DB_NAME;" || log "${YELLOW}⚠️  Failed to drop database${NC}"
          sudo -u postgres psql -c "DROP USER IF EXISTS $DB_USER;" || log "${YELLOW}⚠️  Failed to drop user${NC}"
          log "${GREEN}✅ PostgreSQL database and user removed${NC}"
        else
          log "${YELLOW}⚠️  PostgreSQL not running, skipping database removal${NC}"
        fi
        ;;
      mysql)
        log "${YELLOW}⚠️  MySQL/MariaDB removal not yet implemented${NC}"
        ;;
    esac
  else
    log "${YELLOW}⚠️  No configuration file found, skipping database removal${NC}"
  fi
}

# Remove application files
remove_application() {
  log "${BLUE}🗑️  Removing application files...${NC}"
  
  # Create backup of important files
  mkdir -p "$BACKUP_DIR"
  
  # List of files/directories to remove
  FILES_TO_REMOVE=(
    "backend/venv"
    "backend/mega_monitor.db"
    "backend/logs"
    "backend/data"
    "install_config.json"
    "install.log"
  )
  
  for file in "${FILES_TO_REMOVE[@]}"; do
    if [ -e "$file" ]; then
      if [ -d "$file" ]; then
        # Backup directory
        cp -r "$file" "$BACKUP_DIR/" 2>/dev/null || true
        rm -rf "$file"
        log "${GREEN}✅ Removed directory: $file${NC}"
      else
        # Backup file
        cp "$file" "$BACKUP_DIR/" 2>/dev/null || true
        rm -f "$file"
        log "${GREEN}✅ Removed file: $file${NC}"
      fi
    fi
  done
}

# Clean up dependencies
cleanup_dependencies() {
  log "${BLUE}🧹 Cleaning up dependencies...${NC}"
  
  # Note: We don't remove system packages as they might be used by other applications
  log "${YELLOW}⚠️  System dependencies preserved (may be used by other applications)${NC}"
  
  # Remove Python virtual environment if it exists
  if [ -d "backend/venv" ]; then
    rm -rf backend/venv
    log "${GREEN}✅ Python virtual environment removed${NC}"
  fi
}

# Restore firewall
restore_firewall() {
  log "${BLUE}🔥 Restoring firewall rules...${NC}"
  
  # This is a basic restoration - in a production environment, you might want to be more specific
  if command -v ufw &> /dev/null; then
    # Remove our application ports
    sudo ufw delete allow 80/tcp 2>/dev/null || true
    sudo ufw delete allow 443/tcp 2>/dev/null || true
    sudo ufw delete allow 8887/tcp 2>/dev/null || true
    log "${GREEN}✅ Firewall rules restored${NC}"
  elif command -v firewall-cmd &> /dev/null; then
    sudo firewall-cmd --remove-port=80/tcp --permanent 2>/dev/null || true
    sudo firewall-cmd --remove-port=443/tcp --permanent 2>/dev/null || true
    sudo firewall-cmd --remove-port=8887/tcp --permanent 2>/dev/null || true
    sudo firewall-cmd --reload 2>/dev/null || true
    log "${GREEN}✅ Firewall rules restored${NC}"
  else
    log "${YELLOW}⚠️  No firewall manager found${NC}"
  fi
}

# Final cleanup
final_cleanup() {
  log "${BLUE}🧼 Final cleanup...${NC}"
  
  # Remove log files
  rm -f uninstall.log
  
  log "${GREEN}✅ Uninstallation complete${NC}"
  
  echo ""
  echo "Backup of your configuration and data has been saved to: $BACKUP_DIR"
  echo ""
  echo "If you want to completely remove all traces, you can delete:"
  echo "  - The backup directory: $BACKUP_DIR"
  echo "  - Any remaining application files in the installation directory"
  echo ""
}

# Main uninstall function
main() {
  log "${BLUE}🧹 Starting 3mm Application Uninstallation${NC}"
  echo ""
  
  # Confirm uninstallation
  read -p "Are you sure you want to uninstall 3mm Application? (y/n) [n]: " CONFIRM
  if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
    log "${YELLOW}⚠️  Uninstallation cancelled${NC}"
    exit 0
  fi
  
  # Perform uninstallation
  backup_config
  stop_services
  remove_database
  remove_application
  cleanup_dependencies
  restore_firewall
  final_cleanup
}

# Run main function
main "$@"
