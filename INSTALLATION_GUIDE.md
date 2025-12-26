# 3mm Application Installation Guide

## Overview
This guide provides instructions for installing the 3mm application on Linux and Raspberry Pi platforms using the unified installation script.

## Prerequisites

### Supported Platforms
- **Linux:** Ubuntu 22.04/24.04, Debian 12, CentOS 7/9, Arch Linux
- **Raspberry Pi:** Raspberry Pi OS (32/64-bit) on Zero W/2W/3/4/5

### Minimum Requirements
- **CPU:** 2 cores (4 recommended for production)
- **RAM:** 2GB (4GB recommended for PostgreSQL)
- **Storage:** 4GB free space
- **Network:** Internet connection for dependency installation

## Installation Methods

### Full Installation (Backend + Frontend)
```bash
./install.sh
```

### Backend Only Installation
```bash
./install.sh --backend-only
```

### Silent Mode (Non-interactive)
```bash
./install.sh --silent
```

## Configuration Options

### Environment Variables
You can pre-configure the installation using environment variables:

```bash
export INSTALL_HOSTNAME="my-server"
export INSTALL_DB_TYPE="postgresql"
export INSTALL_DB_VERSION="14"
export INSTALL_AUTO_START="true"
./install.sh --silent
```

### Configuration File
The installer creates a configuration file `install_config.json` that you can edit before or after installation.

## Platform-Specific Notes

### Linux (PC/Server)
- Automatically detects distribution (Debian/Ubuntu, RHEL/CentOS, Arch)
- Configures firewall rules (ufw/iptables)
- Supports PostgreSQL, SQLite, and MySQL/MariaDB
- Systemd service integration

### Raspberry Pi
- Detects Raspberry Pi OS version (32/64-bit)
- Headless-friendly Wi-Fi configuration
- mDNS support for `.local` discovery
- Low-resource optimizations
- GPIO permissions configuration

### Frontend Installation
- Automatic Node.js installation (version 20 LTS)
- Frontend dependency installation with npm
- Production build with optimization
- Static file serving configuration

## Database Options

### SQLite (Default)
- Lightweight, file-based database
- No additional dependencies
- Ideal for development and lightweight deployments

### PostgreSQL (Recommended for Production)
- Version selection (12-15)
- Secure authentication setup
- Optimized configuration for server workloads
- **Note**: On Raspberry Pi, the installer will automatically fall back to the available PostgreSQL version if the requested version is not found in the repositories

### MySQL/MariaDB
- Available as an option
- Not yet fully implemented in the installer

## Post-Installation

### Access URLs
- Application: `http://[hostname]:8887`
- API Documentation: `http://[hostname]:8887/docs`

### Service Management
```bash
# Start service
sudo systemctl start 3mm.service

# Stop service
sudo systemctl stop 3mm.service

# Check status
sudo systemctl status 3mm.service

# View logs
journalctl -u 3mm.service -f
```

## Troubleshooting

### Common Issues

#### Permission Errors
```bash
sudo chmod +x install.sh
sudo ./install.sh
```

#### Missing jq Dependency
If you see `jq: command not found`, install it manually:
```bash
# For Debian/Ubuntu/Raspberry Pi
sudo apt-get update
sudo apt-get install -y jq

# For RHEL/CentOS
sudo yum install -y jq

# For Arch
sudo pacman -Sy jq
```

#### Python Externally-Managed-Environment Error
Modern Linux distributions prevent system-wide pip installations. The installer now uses a Python virtual environment automatically. If you encounter issues:

```bash
# Create virtual environment manually
python3 -m venv backend/venv

# Activate it
source backend/venv/bin/activate

# Install dependencies
backend/venv/bin/pip install -r backend/requirements.txt
```

#### Frontend Installation Issues

##### Node.js Installation Failed
```bash
# Try installing Node.js manually
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# Or use nvm for more control
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
nvm install 20
```

##### npm Build Failed
```bash
# Clean and retry
rm -rf frontend/node_modules frontend/dist
cd frontend
npm install --legacy-peer-deps
npm run build
```

##### Top-level Await Build Error
If you see "Top-level await is not available in the configured target environment":

```bash
# Update browser targets in vite.config.ts
sed -i 's/chrome87/chrome100/g' vite.config.ts
sed -i 's/edge88/edge100/g' vite.config.ts
sed -i 's/firefox78/firefox100/g' vite.config.ts
sed -i 's/safari14/safari15/g' vite.config.ts

# Then rebuild
npm run build
```

Or use modern build targets:
```bash
# Update package.json build script to use modern targets
"build": "vite build --target=chrome100,edge100,firefox100,safari15"
```

#### Database Connection Failures
1. Check if database service is running
2. Verify credentials in `install_config.json`
3. Check firewall rules

#### PostgreSQL Version Not Available
If you encounter "Unable to locate package postgresql-XY" on Raspberry Pi:

```bash
# The installer will automatically fall back to the available version
# You can also manually install the available version:
sudo apt-get update
sudo apt-get install postgresql postgresql-client postgresql-contrib

# Then continue with the installation
./install.sh
```

#### Database User Creation Errors
If you encounter database user creation errors:

```bash
# Check if the user already exists
sudo -u postgres psql -c "\\du"

# If the user exists, you can either:
# 1. Drop the existing user (if safe):
sudo -u postgres psql -c "DROP USER IF EXISTS 3mm_user;"

# 2. Or manually create the user with a simple password:
sudo -u postgres psql -c "CREATE USER 3mm_user WITH PASSWORD 'securepassword';"

# Then continue with the installation
./install.sh
```

#### Frontend-Backend Connection Issues

**Symptoms:**
- Frontend loads but cannot connect to backend API
- CORS errors or network connection refused errors in browser console
- "Failed to fetch" errors when frontend tries to call backend endpoints

**Solutions:**

**For Raspberry Pi installations:**
1. **Check frontend runtime configuration:**
   ```bash
   cat frontend/public/runtime-config.json
   ```
   Ensure it contains the correct Raspberry Pi IP address, not "localhost"

2. **Verify backend is accessible:**
   ```bash
   # Get your Raspberry Pi's IP address
   hostname -I
   
   # Test backend access from another terminal
   curl http://<RASPBERRY_PI_IP>:8887/docs
   ```

3. **Update frontend configuration manually if needed:**
   ```bash
   # Replace with your actual Raspberry Pi IP
   echo '{"backend_url": "http://192.168.1.100:8887"}' > frontend/public/runtime-config.json
   
   # Rebuild frontend
   cd frontend && npm run build && cd ..
   ```

4. **Check browser access:**
   - Access the frontend using the Raspberry Pi's IP address: `http://<RASPBERRY_PI_IP>:5173`
   - Ensure you're not using "localhost" in the browser - this refers to your local machine, not the Raspberry Pi

**For Linux installations:**
1. **Check hostname resolution:**
   ```bash
   # Verify the hostname is resolvable
   ping $(hostname)
   
   # If not, try using the actual IP address
   hostname -I
   ```

2. **Update frontend configuration:**
   ```bash
   # Use the correct hostname or IP
   jq '.frontend.backend_url = "http://your-hostname-or-ip:8887"' config.json > config.json.tmp
   mv config.json.tmp config.json
   
   # Update runtime config
   echo '{"backend_url": "http://your-hostname-or-ip:8887"}' > frontend/public/runtime-config.json
   
   # Rebuild frontend
   cd frontend && npm run build && cd ..
   ```

**General troubleshooting:**
1. **Check CORS configuration:** Ensure backend has CORS enabled (should be by default)
2. **Verify backend is running:** `sudo systemctl status 3mm.service`
3. **Check backend logs:** `journalctl -u 3mm.service -f`
4. **Test backend directly:** `curl http://localhost:8887/api/extensions/public`
5. **Check browser console:** Look for specific error messages about failed requests
6. **Clear browser cache:** Sometimes old configurations are cached

**Debugging the connection:**
```bash
# From the Raspberry Pi/Linux machine, test if backend is accessible
curl -v http://localhost:8887/api/extensions/public

# Test from another machine on the same network
curl -v http://<RASPBERRY_PI_IP>:8887/api/extensions/public

# Check what the frontend is trying to access
cat frontend/public/runtime-config.json
```

#### Dependency Installation Issues
```bash
# For Debian/Ubuntu
sudo apt-get update
sudo apt-get install -f

# For RHEL/CentOS
sudo yum clean all
sudo yum update
```

### Logs
- Installation logs: `install.log`
- Application logs: `backend/logs/`
- System logs: `journalctl -u 3mm.service`

## Uninstallation

To completely remove the 3mm application:

```bash
./uninstall.sh
```

This will:
1. Stop and disable the service
2. Remove database (with confirmation)
3. Remove application files
4. Clean up dependencies
5. Restore firewall rules
6. Create a backup of your configuration and data

## Advanced Configuration

### Custom Ports
Edit `install_config.json` and update the `allowed_ports` array, then restart the service.

### SSL/TLS Configuration
The installer doesn't currently configure SSL/TLS. For production deployments, consider:
- Let's Encrypt with Certbot
- Self-signed certificates
- Reverse proxy with Nginx/Apache

## Support

For additional help:
- Check the application logs
- Review the installation configuration
- Consult the project documentation
- Contact support with your installation logs

## License

This installation system is provided under the same license as the 3mm application.
