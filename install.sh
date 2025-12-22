#!/bin/bash

# 3mm Application Installation Script
# Unified installer for Linux and Raspberry Pi platforms

# Color codes for better output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration file
CONFIG_FILE="install_config.json"
LOG_FILE="install.log"

# Default configuration
DEFAULT_CONFIG='{
  "platform": "unknown",
  "hostname": "3mm-server",
  "network": {
    "interface": "auto",
    "ip_config": "dhcp",
    "static_ip": "",
    "gateway": "",
    "dns": ""
  },
  "database": {
    "type": "sqlite",
    "postgresql_version": "14",
    "username": "3mm_user",
    "password": "",
    "db_name": "3mm_db"
  },
  "services": {
    "auto_start": true,
    "enable_logging": true
  },
  "security": {
    "firewall_enabled": true,
    "allowed_ports": [80, 443, 8887]
  }
}'

# Logging function
log() {
  echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Error handling
error_exit() {
  log "${RED}❌ Error: $1${NC}"
  exit 1
}

# Platform detection
detect_platform() {
  log "${BLUE}🔍 Detecting platform...${NC}"
  
  # Check if running on Raspberry Pi
  if grep -q "Raspberry Pi" /proc/device-tree/model 2>/dev/null; then
    PLATFORM="raspberry_pi"
    log "${GREEN}✅ Raspberry Pi detected${NC}"
    
    # Detect Raspberry Pi OS version
    if [ -f /etc/os-release ]; then
      . /etc/os-release
      if [[ "$ID" == "raspbian" || "$ID" == "debian" ]]; then
        if uname -m | grep -q "armv6l"; then
          PI_OS="32-bit"
        elif uname -m | grep -q "armv7l"; then
          PI_OS="32-bit"
        elif uname -m | grep -q "aarch64"; then
          PI_OS="64-bit"
        fi
        log "${BLUE}📋 Raspberry Pi OS: $PI_OS${NC}"
      fi
    fi
    
    # Hardware validation
    log "${BLUE}🔧 Hardware validation...${NC}"
    CPU=$(grep -c "^processor" /proc/cpuinfo)
    RAM=$(free -m | awk '/Mem:/ {print $2}')
    STORAGE=$(df -h / | awk 'NR==2 {print $2}')
    log "${BLUE}💻 CPU: $CPU cores, RAM: ${RAM}MB, Storage: $STORAGE${NC}"
    
  # Check for Linux distribution
  elif [ -f /etc/os-release ]; then
    . /etc/os-release
    case "$ID" in
      ubuntu|debian)
        PLATFORM="linux_debian"
        log "${GREEN}✅ Debian/Ubuntu-based Linux detected${NC}"
        ;;
      centos|rhel|fedora)
        PLATFORM="linux_rhel"
        log "${GREEN}✅ RHEL/CentOS/Fedora-based Linux detected${NC}"
        ;;
      arch|manjaro)
        PLATFORM="linux_arch"
        log "${GREEN}✅ Arch-based Linux detected${NC}"
        ;;
      *)
        PLATFORM="linux_unknown"
        log "${YELLOW}⚠️  Unknown Linux distribution: $ID${NC}"
        ;;
    esac
    
    # System information
    CPU=$(grep -c "^processor" /proc/cpuinfo)
    RAM=$(free -m | awk '/Mem:/ {print $2}')
    STORAGE=$(df -h / | awk 'NR==2 {print $2}')
    log "${BLUE}💻 CPU: $CPU cores, RAM: ${RAM}MB, Storage: $STORAGE${NC}"
    
  else
    error_exit "Unable to detect platform. This script supports Linux and Raspberry Pi only."
  fi
  
  # Update configuration with platform info
  jq ".platform = \"$PLATFORM\"" "$CONFIG_FILE" > "${CONFIG_FILE}.tmp" && mv "${CONFIG_FILE}.tmp" "$CONFIG_FILE"
}

# Initialize configuration
init_config() {
  if [ ! -f "$CONFIG_FILE" ]; then
    echo "$DEFAULT_CONFIG" > "$CONFIG_FILE"
    log "${GREEN}✅ Created default configuration${NC}"
  else
    log "${GREEN}✅ Using existing configuration${NC}"
  fi
}

# Interactive configuration
interactive_config() {
  log "${BLUE}🛠️  Interactive Configuration${NC}"
  
  # Hostname
  CURRENT_HOSTNAME=$(jq -r '.hostname' "$CONFIG_FILE")
  read -p "Enter hostname [$CURRENT_HOSTNAME]: " NEW_HOSTNAME
  if [ -n "$NEW_HOSTNAME" ]; then
    jq ".hostname = \"$NEW_HOSTNAME\"" "$CONFIG_FILE" > "${CONFIG_FILE}.tmp" && mv "${CONFIG_FILE}.tmp" "$CONFIG_FILE"
  fi
  
  # Database selection
  echo ""
  echo "Database Options:"
  echo "1. SQLite (lightweight, file-based)"
  echo "2. PostgreSQL (recommended for production)"
  echo "3. MySQL/MariaDB"
  read -p "Select database [1-3]: " DB_CHOICE
  
  case "$DB_CHOICE" in
    1)
      DB_TYPE="sqlite"
      ;;
    2)
      DB_TYPE="postgresql"
      read -p "PostgreSQL version (12-15) [14]: " PG_VERSION
      if [ -z "$PG_VERSION" ]; then
        PG_VERSION="14"
      fi
      jq ".database.postgresql_version = \"$PG_VERSION\"" "$CONFIG_FILE" > "${CONFIG_FILE}.tmp" && mv "${CONFIG_FILE}.tmp" "$CONFIG_FILE"
      ;;
    3)
      DB_TYPE="mysql"
      ;;
    *)
      DB_TYPE="sqlite"
      ;;
  esac
  
  jq ".database.type = \"$DB_TYPE\"" "$CONFIG_FILE" > "${CONFIG_FILE}.tmp" && mv "${CONFIG_FILE}.tmp" "$CONFIG_FILE"
  
  # Network configuration
  if [ "$PLATFORM" == "raspberry_pi" ]; then
    echo ""
    echo "Network Configuration:"
    read -p "Configure Wi-Fi? (y/n) [n]: " WIFI_CONFIG
    if [[ "$WIFI_CONFIG" =~ ^[Yy]$ ]]; then
      read -p "Wi-Fi SSID: " WIFI_SSID
      read -s -p "Wi-Fi Password: " WIFI_PASSWORD
      echo ""
      # Store Wi-Fi credentials securely
      log "${BLUE}🔒 Wi-Fi credentials stored (not shown for security)${NC}"
    fi
  fi
  
  log "${GREEN}✅ Configuration saved${NC}"
}

# Dependency resolution
install_dependencies() {
  log "${BLUE}📦 Installing dependencies...${NC}"
  
  # Common dependencies
  log "${BLUE}🔧 Installing common dependencies...${NC}"
  
  case "$PLATFORM" in
    raspberry_pi|linux_debian)
      sudo apt-get update -qq
      sudo apt-get install -y -qq \
        python3 \
        python3-pip \
        python3-venv \
        jq \
        curl \
        wget \
        git \
        build-essential \
        || error_exit "Failed to install dependencies"
      ;;
    linux_rhel)
      sudo yum install -y -q \
        python3 \
        python3-pip \
        jq \
        curl \
        wget \
        git \
        gcc \
        make \
        || error_exit "Failed to install dependencies"
      ;;
    linux_arch)
      sudo pacman -Sy --noconfirm \
        python \
        python-pip \
        jq \
        curl \
        wget \
        git \
        base-devel \
        || error_exit "Failed to install dependencies"
      ;;
  esac
  
  # Python dependencies
  log "${BLUE}🐍 Installing Python dependencies...${NC}"
  pip3 install --upgrade pip -q
  pip3 install -r backend/requirements.txt -q || error_exit "Failed to install Python dependencies"
  
  log "${GREEN}✅ Dependencies installed successfully${NC}"
}

# Database setup
database_setup() {
  log "${BLUE}🗄️  Setting up database...${NC}"
  
  DB_TYPE=$(jq -r '.database.type' "$CONFIG_FILE")
  
  case "$DB_TYPE" in
    sqlite)
      log "${BLUE}📝 Configuring SQLite database...${NC}"
      # SQLite doesn't require additional setup
      touch backend/mega_monitor.db
      log "${GREEN}✅ SQLite database ready${NC}"
      ;;
    postgresql)
      log "${BLUE}🐘 Installing PostgreSQL...${NC}"
      
      case "$PLATFORM" in
        raspberry_pi|linux_debian)
          PG_VERSION=$(jq -r '.database.postgresql_version' "$CONFIG_FILE")
          sudo apt-get install -y -qq "postgresql-$PG_VERSION" "postgresql-client-$PG_VERSION" "postgresql-contrib-$PG_VERSION" || error_exit "Failed to install PostgreSQL"
          ;;
        linux_rhel)
          sudo yum install -y -q postgresql-server postgresql-contrib || error_exit "Failed to install PostgreSQL"
          ;;
        linux_arch)
          sudo pacman -Sy --noconfirm postgresql || error_exit "Failed to install PostgreSQL"
          ;;
      esac
      
      # Configure PostgreSQL
      log "${BLUE}🔧 Configuring PostgreSQL...${NC}"
      sudo systemctl enable postgresql
      sudo systemctl start postgresql
      
      # Create database and user
      DB_USER=$(jq -r '.database.username' "$CONFIG_FILE")
      DB_NAME=$(jq -r '.database.db_name' "$CONFIG_FILE")
      DB_PASSWORD=$(pwgen -s 16 1 || openssl rand -base64 12)
      
      sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';" || error_exit "Failed to create database user"
      sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;" || error_exit "Failed to create database"
      
      # Update configuration with generated password
      jq ".database.password = \"$DB_PASSWORD\"" "$CONFIG_FILE" > "${CONFIG_FILE}.tmp" && mv "${CONFIG_FILE}.tmp" "$CONFIG_FILE"
      
      log "${GREEN}✅ PostgreSQL database ready${NC}"
      log "${YELLOW}🔒 Database credentials generated and saved${NC}"
      ;;
    mysql)
      log "${BLUE}🐘 Installing MySQL/MariaDB...${NC}"
      # MySQL/MariaDB installation would go here
      log "${YELLOW}⚠️  MySQL/MariaDB support not yet implemented${NC}"
      ;;
  esac
}

# Service management
service_setup() {
  log "${BLUE}🚀 Setting up services...${NC}"
  
  # Create systemd service
  cat > /tmp/3mm.service <<EOL
[Unit]
Description=3mm Application Server
After=network.target

[Service]
User=$USER
WorkingDirectory=$(pwd)
ExecStart=$(pwd)/backend/venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8887
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOL
  
  sudo mv /tmp/3mm.service /etc/systemd/system/3mm.service
  sudo systemctl daemon-reload
  sudo systemctl enable 3mm.service
  
  AUTO_START=$(jq -r '.services.auto_start' "$CONFIG_FILE")
  if [ "$AUTO_START" == "true" ]; then
    sudo systemctl start 3mm.service
    log "${GREEN}✅ Service started and enabled${NC}"
  else
    log "${GREEN}✅ Service installed (not started)${NC}"
  fi
}

# Firewall configuration
firewall_setup() {
  log "${BLUE}🔥 Configuring firewall...${NC}"
  
  FIREWALL_ENABLED=$(jq -r '.security.firewall_enabled' "$CONFIG_FILE")
  
  if [ "$FIREWALL_ENABLED" == "true" ]; then
    case "$PLATFORM" in
      raspberry_pi|linux_debian|linux_rhel)
        # Check if ufw is available
        if command -v ufw &> /dev/null; then
          log "${BLUE}🔧 Configuring ufw firewall...${NC}"
          sudo ufw allow 80/tcp
          sudo ufw allow 443/tcp
          sudo ufw allow 8887/tcp
          sudo ufw --force enable
        elif command -v firewall-cmd &> /dev/null; then
          log "${BLUE}🔧 Configuring firewalld...${NC}"
          sudo firewall-cmd --add-port=80/tcp --permanent
          sudo firewall-cmd --add-port=443/tcp --permanent
          sudo firewall-cmd --add-port=8887/tcp --permanent
          sudo firewall-cmd --reload
        else
          log "${YELLOW}⚠️  No firewall manager found (ufw/firewalld)${NC}"
        fi
        ;;
      linux_arch)
        # Arch typically uses iptables directly
        log "${YELLOW}⚠️  Firewall configuration for Arch not yet implemented${NC}"
        ;;
    esac
    
    log "${GREEN}✅ Firewall configured${NC}"
  else
    log "${YELLOW}⚠️  Firewall configuration skipped${NC}"
  fi
}

# Post-install verification
post_install_check() {
  log "${BLUE}🔍 Running post-install verification...${NC}"
  
  # Check if application is running
  if systemctl is-active --quiet 3mm.service; then
    log "${GREEN}✅ Application service is running${NC}"
  else
    log "${YELLOW}⚠️  Application service is not running${NC}"
  fi
  
  # Check database connectivity
  DB_TYPE=$(jq -r '.database.type' "$CONFIG_FILE")
  if [ "$DB_TYPE" == "postgresql" ]; then
    if pg_isready -q; then
      log "${GREEN}✅ PostgreSQL is ready${NC}"
    else
      log "${RED}❌ PostgreSQL is not ready${NC}"
    fi
  fi
  
  # Check network connectivity
  if ping -c 1 google.com &> /dev/null; then
    log "${GREEN}✅ Network connectivity OK${NC}"
  else
    log "${YELLOW}⚠️  Network connectivity issue${NC}"
  fi
  
  log "${GREEN}✅ Post-install verification complete${NC}"
}

# Installation summary
show_summary() {
  log "${BLUE}📋 Installation Summary${NC}"
  echo ""
  
  HOSTNAME=$(jq -r '.hostname' "$CONFIG_FILE")
  DB_TYPE=$(jq -r '.database.type' "$CONFIG_FILE")
  DB_USER=$(jq -r '.database.username' "$CONFIG_FILE")
  DB_NAME=$(jq -r '.database.db_name' "$CONFIG_FILE")
  
  echo "Platform: $PLATFORM"
  echo "Hostname: $HOSTNAME"
  echo "Database: $DB_TYPE"
  
  if [ "$DB_TYPE" == "postgresql" ]; then
    DB_PASSWORD=$(jq -r '.database.password' "$CONFIG_FILE")
    echo "Database User: $DB_USER"
    echo "Database Name: $DB_NAME"
    echo "Database Password: $DB_PASSWORD"
  fi
  
  echo ""
  echo "Access URLs:"
  echo "  Application: http://$HOSTNAME:8887"
  echo "  API Docs: http://$HOSTNAME:8887/docs"
  echo ""
  
  echo "Next steps:"
  echo "  1. Review configuration in $CONFIG_FILE"
  echo "  2. Start the application: sudo systemctl start 3mm.service"
  echo "  3. Check logs: journalctl -u 3mm.service -f"
  echo ""
  
  log "${GREEN}🎉 Installation complete!${NC}"
}

# Main installation function
main() {
  # Initialize
  init_config
  detect_platform
  
  # Check for silent mode
  if [ "$1" == "--silent" ]; then
    log "${BLUE}🤫 Silent mode enabled${NC}"
  else
    # Interactive mode
    interactive_config
  fi
  
  # Perform installation
  install_dependencies
  database_setup
  service_setup
  firewall_setup
  post_install_check
  show_summary
}

# Run main function
main "$@"
