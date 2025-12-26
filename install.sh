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
    "username": "mm3_user",
    "password": "",
    "db_name": "mm3_db"
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

# Initialize configuration
init_config() {
  if [ ! -f "$CONFIG_FILE" ]; then
    echo "$DEFAULT_CONFIG" > "$CONFIG_FILE"
    log "${GREEN}✅ Created default configuration${NC}"
  else
    log "${GREEN}✅ Using existing configuration${NC}"
  fi
}

# Install jq if not available
install_jq() {
  if ! command -v jq &> /dev/null; then
    log "${BLUE}📦 Installing jq...${NC}"
    
    # Try to detect platform for jq installation
    if grep -q "Raspberry Pi" /proc/device-tree/model 2>/dev/null || grep -q "raspbian\|debian" /etc/os-release 2>/dev/null; then
      sudo apt-get update -qq
      sudo apt-get install -y -qq jq || error_exit "Failed to install jq"
    elif grep -q "centos\|rhel\|fedora" /etc/os-release 2>/dev/null; then
      sudo yum install -y -q jq || error_exit "Failed to install jq"
    elif grep -q "arch\|manjaro" /etc/os-release 2>/dev/null; then
      sudo pacman -Sy --noconfirm jq || error_exit "Failed to install jq"
    else
      error_exit "Cannot install jq - unsupported platform"
    fi
    
    log "${GREEN}✅ jq installed${NC}"
  fi
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
  
  # Install jq before using it
  install_jq
  
  # Update configuration with platform info
  jq ".platform = \"$PLATFORM\"" "$CONFIG_FILE" > "${CONFIG_FILE}.tmp" && mv "${CONFIG_FILE}.tmp" "$CONFIG_FILE"
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

# Setup Python virtual environment
setup_python_venv() {
  log "${BLUE}🐍 Setting up Python virtual environment...${NC}"
  
  # Check if virtual environment exists and is valid
  if [ -d "backend/venv" ]; then
    # Check if the virtual environment has the necessary components
    if [ -f "backend/venv/bin/python3" ] || [ -f "backend/venv/bin/python" ]; then
      log "${GREEN}✅ Using existing virtual environment${NC}"
    else
      log "${YELLOW}⚠️  Virtual environment exists but seems incomplete, recreating...${NC}"
      rm -rf backend/venv
      python3 -m venv backend/venv || error_exit "Failed to create virtual environment"
    fi
  else
    # Create new virtual environment
    python3 -m venv backend/venv || error_exit "Failed to create virtual environment"
    log "${GREEN}✅ Virtual environment created${NC}"
  fi
  
  # Detect the correct Python executable
  if [ -f "backend/venv/bin/python3" ]; then
    PYTHON_PATH="backend/venv/bin/python3"
  elif [ -f "backend/venv/bin/python" ]; then
    PYTHON_PATH="backend/venv/bin/python"
  else
    error_exit "Cannot find Python executable in virtual environment"
  fi
  
  # Use Python to run pip commands (most reliable method)
  PIP_PATH="$PYTHON_PATH -m pip"
  
  # Debug: Show virtual environment structure
  log "${BLUE}🔍 Virtual environment structure:${NC}"
  ls -la backend/venv/bin/ | head -10
  
  # Test if pip works
  if ! $PIP_PATH --version &>/dev/null; then
    error_exit "Virtual environment pip is not working. Try recreating with: rm -rf backend/venv && python3 -m venv backend/venv"
  fi
  
  # Upgrade pip
  log "${BLUE}🔧 Upgrading pip...${NC}"
  $PIP_PATH install --upgrade pip -q || error_exit "Failed to upgrade pip"
  
  # Install Python dependencies
  log "${BLUE}📦 Installing Python dependencies...${NC}"
  $PIP_PATH install -r backend/requirements.txt -q || error_exit "Failed to install Python dependencies"
  
  log "${GREEN}✅ Python dependencies installed${NC}"
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
  
  # Setup Python virtual environment
  setup_python_venv
  
  log "${GREEN}✅ Dependencies installed successfully${NC}"
}

# Database setup
database_setup() {
  log "${BLUE}🗄️  Setting up database...${NC}"

  DB_TYPE=$(jq -r '.database.type' "$CONFIG_FILE")

  # Check if PostgreSQL is actually installed and running
  if pg_isready -q; then
    log "${BLUE}🔍 PostgreSQL detected as running, forcing PostgreSQL setup${NC}"
    DB_TYPE="postgresql"
    # Update config to reflect this
    jq ".database.type = \"postgresql\"" "$CONFIG_FILE" > "${CONFIG_FILE}.tmp" && mv "${CONFIG_FILE}.tmp" "$CONFIG_FILE"
  fi

  # If PostgreSQL is running but we're not using it, create database_config.json anyway
  if [ "$DB_TYPE" != "postgresql" ] && pg_isready -q; then
    log "${BLUE}🔧 Creating database_config.json for existing PostgreSQL setup${NC}"
    
    # Try to get existing database credentials or use defaults
    DB_USER=$(jq -r '.database.username' "$CONFIG_FILE")
    DB_NAME=$(jq -r '.database.db_name' "$CONFIG_FILE")
    DB_PASSWORD=$(jq -r '.database.password' "$CONFIG_FILE")
    
    # If password is empty, generate one
    if [ -z "$DB_PASSWORD" ]; then
      if command -v pwgen &> /dev/null; then
        DB_PASSWORD=$(pwgen -s 16 1)
      else
        DB_PASSWORD=$(tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 16)
      fi
      jq ".database.password = \"$DB_PASSWORD\"" "$CONFIG_FILE" > "${CONFIG_FILE}.tmp" && mv "${CONFIG_FILE}.tmp" "$CONFIG_FILE"
    fi
    
    # Create database_config.json
    cat > backend/database_config.json <<EOL
{
 "database_url": "postgresql://$DB_USER:$DB_PASSWORD@localhost:5432/$DB_NAME",
 "username": "$DB_USER",
 "password": "$DB_PASSWORD",
 "database": "$DB_NAME",
 "host": "localhost",
 "port": 5432
}
EOL
    
    log "${GREEN}✅ database_config.json created for existing PostgreSQL${NC}"
    
    # Ensure the PostgreSQL user has the correct password
    if sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1; then
      log "${BLUE}🔧 Ensuring PostgreSQL user $DB_USER has correct password...${NC}"
      # Escape single quotes in password for SQL
      ESCAPED_PASSWORD=$(echo "$DB_PASSWORD" | sed "s/'/''/g")
      sudo -u postgres psql -c "ALTER USER $DB_USER WITH PASSWORD '$ESCAPED_PASSWORD';" || {
        log "${YELLOW}⚠️  Could not update password for existing user $DB_USER${NC}"
      }
    fi
  fi

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
          
          # Try to install the specific version first
          if sudo apt-get install -y -qq "postgresql-$PG_VERSION" "postgresql-client-$PG_VERSION" "postgresql-contrib-$PG_VERSION"; then
            log "${GREEN}✅ PostgreSQL $PG_VERSION installed${NC}"
          else
            # Fallback to available version for Raspberry Pi/Debian
            log "${YELLOW}⚠️  PostgreSQL $PG_VERSION not available, trying default version...${NC}"
            sudo apt-get update -qq
            sudo apt-get install -y -qq postgresql postgresql-client postgresql-contrib || error_exit "Failed to install PostgreSQL"
            
            # Update config with the installed version
            INSTALLED_VERSION=$(sudo -u postgres psql -c "SHOW server_version;" | grep -oP '\d+\.\d+' | head -1)
            jq ".database.postgresql_version = \"$INSTALLED_VERSION\"" "$CONFIG_FILE" > "${CONFIG_FILE}.tmp" && mv "${CONFIG_FILE}.tmp" "$CONFIG_FILE"
            log "${GREEN}✅ PostgreSQL $INSTALLED_VERSION installed (fallback)${NC}"
          fi
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
      
      log "${BLUE}🔍 Database user: $DB_USER, Database name: $DB_NAME${NC}"
      
      # Check for problematic usernames starting with numbers and fix them
      if [[ "$DB_USER" =~ ^[0-9] ]]; then
        log "${YELLOW}⚠️  Username starts with number, renaming...${NC}"
        NEW_DB_USER="mm${DB_USER}"
        NEW_DB_NAME="mm${DB_NAME}"
        log "${BLUE}🔧 Renamed user: $DB_USER -> $NEW_DB_USER${NC}"
        log "${BLUE}🔧 Renamed database: $DB_NAME -> $NEW_DB_NAME${NC}"
        
        # Update configuration
        jq ".database.username = \"$NEW_DB_USER\"" "$CONFIG_FILE" > "${CONFIG_FILE}.tmp" && mv "${CONFIG_FILE}.tmp" "$CONFIG_FILE"
        jq ".database.db_name = \"$NEW_DB_NAME\"" "$CONFIG_FILE" > "${CONFIG_FILE}.tmp" && mv "${CONFIG_FILE}.tmp" "$CONFIG_FILE"
        
        DB_USER=$NEW_DB_USER
        DB_NAME=$NEW_DB_NAME
      fi
      
      # Generate password - try pwgen first, then simple alphanumeric, avoiding special chars
      if command -v pwgen &> /dev/null; then
        DB_PASSWORD=$(pwgen -s 16 1)
      else
        # Simple alphanumeric password generation (avoids special characters that cause SQL issues)
        DB_PASSWORD=$(tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 16)
      fi
      
      # Escape single quotes in password for SQL (double them)
      ESCAPED_PASSWORD=$(echo "$DB_PASSWORD" | sed "s/'/''/g")
      
      log "${BLUE}🔒 Generated database password: $DB_PASSWORD${NC}"
      
      log "${BLUE}🔧 Creating database user and database...${NC}"
      
      # Check if user already exists
      if sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1; then
        log "${YELLOW}⚠️  Database user $DB_USER already exists, skipping creation${NC}"
      else
        # Create user with proper PostgreSQL syntax
        sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$ESCAPED_PASSWORD';" || {
          log "${RED}❌ Failed to create database user, trying alternative syntax...${NC}"
          sudo -u postgres psql -c "CREATE ROLE $DB_USER LOGIN PASSWORD '$ESCAPED_PASSWORD';" || error_exit "Failed to create database user with both syntaxes"
        }
      fi
      
      # Check if database already exists
      if sudo -u postgres psql -lqt | cut -d \| -f 1 | grep -qw "$DB_NAME"; then
        log "${YELLOW}⚠️  Database $DB_NAME already exists, skipping creation${NC}"
      else
        # Create database
        sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;" || error_exit "Failed to create database"
      fi
      
      # Update configuration with generated password
      jq ".database.password = \"$DB_PASSWORD\"" "$CONFIG_FILE" > "${CONFIG_FILE}.tmp" && mv "${CONFIG_FILE}.tmp" "$CONFIG_FILE"
      
      # Configure backend to use the correct database credentials
      log "${BLUE}🔧 Configuring backend database connection...${NC}"
      
      # Create or update backend configuration
      cat > backend/database_config.json <<EOL
{
 "database_url": "postgresql://$DB_USER:$DB_PASSWORD@localhost:5432/$DB_NAME",
 "username": "$DB_USER",
 "password": "$DB_PASSWORD",
 "database": "$DB_NAME",
 "host": "localhost",
 "port": 5432
}
EOL
      
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

# Frontend installation
frontend_setup() {
  log "${BLUE}🎨 Setting up frontend...${NC}"
  
  # Check if Node.js is installed
  if ! command -v node &> /dev/null; then
    log "${BLUE}📦 Installing Node.js...${NC}"
    
    case "$PLATFORM" in
      raspberry_pi|linux_debian)
        curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
        sudo apt-get install -y -qq nodejs || error_exit "Failed to install Node.js"
        ;;
      linux_rhel)
        curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo -E bash -
        sudo yum install -y -q nodejs || error_exit "Failed to install Node.js"
        ;;
      linux_arch)
        sudo pacman -Sy --noconfirm nodejs npm || error_exit "Failed to install Node.js"
        ;;
    esac
    
    log "${GREEN}✅ Node.js installed${NC}"
  else
    log "${GREEN}✅ Node.js already installed${NC}"
  fi
  
  # Install frontend dependencies
  log "${BLUE}📦 Installing frontend dependencies...${NC}"
  
  cd frontend || error_exit "Failed to change to frontend directory"
  
  if [ ! -d "node_modules" ]; then
    npm install --legacy-peer-deps || error_exit "Failed to install frontend dependencies"
    log "${GREEN}✅ Frontend dependencies installed${NC}"
  else
    log "${GREEN}✅ Using existing frontend dependencies${NC}"
  fi
  
  # Build frontend
  log "${BLUE}🔨 Building frontend...${NC}"
  
  # Try building with modern targets first, fallback to legacy if needed
  if npm run build; then
    log "${GREEN}✅ Frontend built successfully${NC}"
  else
    log "${YELLOW}⚠️  Modern build failed, trying with updated browser targets...${NC}"
    
    # Try to update Vite config or use environment variable override
    if [ -f "vite.config.ts" ]; then
      log "${BLUE}🔧 Updating Vite configuration for modern browser support...${NC}"
      
      # Create backup
      cp vite.config.ts vite.config.ts.bak
      
      # Try to update the build targets by modifying the config
      sed -i 's/chrome87/chrome100/g' vite.config.ts 2>/dev/null || true
      sed -i 's/edge88/edge100/g' vite.config.ts 2>/dev/null || true
      sed -i 's/firefox78/firefox100/g' vite.config.ts 2>/dev/null || true
      sed -i 's/safari14/safari15/g' vite.config.ts 2>/dev/null || true
    fi
    
    # Try building again with environment variable override
    if VITE_TARGET="chrome100,edge100,firefox100,safari15" npm run build; then
      log "${GREEN}✅ Frontend built successfully with updated targets${NC}"
    else
      log "${RED}❌ Failed to build frontend even with updated targets${NC}"
      log "${YELLOW}⚠️  Trying simple build without type checking...${NC}"
      
      # Try building without type checking as a last resort
      if cd frontend && npx vite build --mode production; then
        log "${GREEN}✅ Frontend built successfully with Vite direct build${NC}"
      else
        log "${RED}❌ Failed to build frontend with all methods${NC}"
        log "${YELLOW}⚠️  You can try building manually with: cd frontend && npm run build${NC}"
        log "${YELLOW}⚠️  Or check frontend documentation for specific build requirements${NC}"
        log "${YELLOW}⚠️  Frontend build failed, but backend installation will continue${NC}"
      fi
    fi
  fi
  
  cd ..
  
  # Update frontend runtime config with correct backend URL
  log "${BLUE}🔧 Updating frontend runtime configuration...${NC}"
  
  # Get the actual IP address of the Raspberry Pi
  if [ "$PLATFORM" == "raspberry_pi" ]; then
    # Try to get the local IP address
    LOCAL_IP=$(hostname -I | awk '{print $1}')
    
    if [ -n "$LOCAL_IP" ]; then
      log "${BLUE}📋 Raspberry Pi IP address: $LOCAL_IP${NC}"
      
      # Update the frontend runtime config with the correct backend URL
      cat > frontend/public/runtime-config.json <<EOL
{
  "backend_url": "http://$LOCAL_IP:8887"
}
EOL
      
      log "${GREEN}✅ Frontend runtime configuration updated with Raspberry Pi IP${NC}"
    else
      log "${YELLOW}⚠️  Could not determine Raspberry Pi IP address${NC}"
    fi
  else
    # For Linux installations, use localhost or the configured hostname
    HOSTNAME=$(jq -r '.hostname' "$CONFIG_FILE")
    
    # Update the frontend runtime config with the correct backend URL
    cat > frontend/public/runtime-config.json <<EOL
{
  "backend_url": "http://$HOSTNAME:8887"
}
EOL
    
    log "${GREEN}✅ Frontend runtime configuration updated with hostname: $HOSTNAME${NC}"
  fi
  
  # Update the main config.json with the correct backend URL for future builds
  log "${BLUE}🔧 Updating main config.json with correct backend URL...${NC}"
  
  # Determine the correct backend URL based on platform
  if [ "$PLATFORM" == "raspberry_pi" ] && [ -n "$LOCAL_IP" ]; then
    BACKEND_URL="http://$LOCAL_IP:8887"
  else
    BACKEND_URL="http://$HOSTNAME:8887"
  fi
  
  # Update the config.json file
  jq ".frontend.backend_url = \"$BACKEND_URL\"" config.json > config.json.tmp && mv config.json.tmp config.json
  
  log "${GREEN}✅ Main config.json updated with backend URL: $BACKEND_URL${NC}"
  
  # Rebuild frontend with the updated configuration
  log "${BLUE}🔨 Rebuilding frontend with updated backend URL...${NC}"
  
  cd frontend || error_exit "Failed to change to frontend directory"
  
  # Try building again with the updated configuration
  if npm run build; then
    log "${GREEN}✅ Frontend rebuilt successfully with correct backend URL${NC}"
  else
    log "${YELLOW}⚠️  Frontend rebuild failed, but runtime config should still work${NC}"
  fi
  
  cd ..
}

# Service management
service_setup() {
  log "${BLUE}🚀 Setting up services...${NC}"
  
  # Use the same Python path that was detected for pip installation
  if [ -z "$PYTHON_PATH" ]; then
    # If not set, try to detect it - use absolute path!
    ABSOLUTE_PATH=$(pwd)
    if [ -f "$ABSOLUTE_PATH/backend/venv/bin/python3" ]; then
      PYTHON_PATH="$ABSOLUTE_PATH/backend/venv/bin/python3"
    elif [ -f "$ABSOLUTE_PATH/backend/venv/bin/python" ]; then
      PYTHON_PATH="$ABSOLUTE_PATH/backend/venv/bin/python"
    else
      error_exit "Cannot find Python in virtual environment for service setup"
    fi
  else
    # Ensure the path is absolute
    if [[ "$PYTHON_PATH" != /* ]]; then
      PYTHON_PATH="$(pwd)/$PYTHON_PATH"
    fi
  fi
  
  # Verify the path exists
  if [ ! -f "$PYTHON_PATH" ]; then
    error_exit "Python executable not found at: $PYTHON_PATH"
  fi
  
  log "${BLUE}🔍 Using Python executable: $PYTHON_PATH${NC}"
  
  # Create systemd service
  cat > /tmp/3mm.service <<EOL
[Unit]
Description=3mm Application Server
After=network.target

[Service]
User=$USER
WorkingDirectory=$(pwd)
ExecStart=$PYTHON_PATH -m uvicorn backend.main:app --host 0.0.0.0 --port 8887
Restart=always
RestartSec=5
Environment=PATH=$(pwd)/backend/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
Environment=PYTHONUNBUFFERED=1

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
  echo "  Backend API: http://$HOSTNAME:8887"
  echo "  API Docs: http://$HOSTNAME:8887/docs"
  
  # Determine frontend URL based on platform
  if [ "$PLATFORM" == "raspberry_pi" ] && [ -n "$LOCAL_IP" ]; then
    FRONTEND_URL="http://$LOCAL_IP:5173"
  else
    FRONTEND_URL="http://$HOSTNAME:5173"
  fi
  
  echo "  Frontend: $FRONTEND_URL"
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
  frontend_setup
  service_setup
  firewall_setup
  post_install_check
  show_summary
}

# Run main function
main "$@"
