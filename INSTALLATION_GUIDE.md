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

### Interactive Mode (Recommended)
```bash
./install.sh
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

## Database Options

### SQLite (Default)
- Lightweight, file-based database
- No additional dependencies
- Ideal for development and lightweight deployments

### PostgreSQL (Recommended for Production)
- Version selection (12-15)
- Secure authentication setup
- Optimized configuration for server workloads

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

#### Database Connection Failures
1. Check if database service is running
2. Verify credentials in `install_config.json`
3. Check firewall rules

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
