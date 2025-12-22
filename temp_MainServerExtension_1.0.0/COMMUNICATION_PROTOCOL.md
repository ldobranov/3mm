# Main Server Extension - Communication Protocol

This document defines the communication protocol between the Main Server and Raspberry Pi devices for update management.

## Overview

The Main Server Extension enables centralized management and distribution of updates to multiple Raspberry Pi devices. The communication follows a client-server model where:

- **Main Server**: Acts as the update server and management console
- **Raspberry Pi Devices**: Act as clients that receive and apply updates

## Communication Methods

### 1. HTTP REST API

The primary communication method is via HTTP REST API endpoints provided by the Main Server Extension.

#### Base URL

```
http://<main-server-ip>:<port>/api/main-server
```

#### Endpoints

##### GET `/updates`
**Description**: Get available updates for all devices
**Authentication**: Required (JWT token)
**Request Headers**:
```
Authorization: Bearer <token>
```
**Response**:
```json
{
  "updates": [
    {
      "extension_id": 1,
      "name": "ExtensionName",
      "current_version": "1.0.0",
      "available_version": "1.1.0",
      "is_compatible": true
    }
  ]
}
```

##### POST `/schedule-update`
**Description**: Schedule an update for a specific extension
**Authentication**: Required (JWT token)
**Request Headers**:
```
Authorization: Bearer <token>
Content-Type: application/json
```
**Request Body**:
```json
{
  "extension_id": 1,
  "new_version": "1.1.0"
}
```
**Response**:
```json
{
  "message": "Update scheduled",
  "extension_id": 1
}
```

##### POST `/deploy-update`
**Description**: Deploy an update to a specific device
**Authentication**: Required (JWT token)
**Request Headers**:
```
Authorization: Bearer <token>
Content-Type: application/json
```
**Request Body**:
```json
{
  "device_id": "raspi-001",
  "extension_id": 1,
  "version": "1.1.0"
}
```
**Response**:
```json
{
  "status": "queued",
  "message": "Update deployment queued for device raspi-001",
  "device_id": "raspi-001",
  "extension_id": 1,
  "version": "1.1.0",
  "package_path": "/path/to/update.zip"
}
```

##### GET `/devices`
**Description**: Get list of connected Raspberry Pi devices
**Authentication**: Required (JWT token)
**Request Headers**:
```
Authorization: Bearer <token>
```
**Response**:
```json
{
  "devices": [
    {
      "id": "raspi-001",
      "name": "Living Room Display",
      "ip": "192.168.1.100",
      "status": "online"
    }
  ]
}
```

### 2. Device Update Protocol

When a device receives an update deployment request, it follows this protocol:

#### Step 1: Update Notification
The device periodically polls the main server for available updates or receives push notifications.

#### Step 2: Update Package Download
The device downloads the update package from the main server:

```
GET /api/main-server/download-update?package_id=<package_id>
```

#### Step 3: Update Verification
The device verifies the update package integrity using checksums.

#### Step 4: Update Installation
The device:
1. Creates a backup of the current extension
2. Extracts the update package
3. Installs the new version
4. Restarts the extension/service

#### Step 5: Update Confirmation
The device sends a confirmation to the main server:

```
POST /api/main-server/update-status
Content-Type: application/json

{
  "device_id": "raspi-001",
  "extension_id": 1,
  "version": "1.1.0",
  "status": "success",
  "timestamp": "2023-12-22T10:30:00Z"
}
```

## Device Registration

Raspberry Pi devices must register with the main server to receive updates.

### Registration Endpoint

```
POST /api/main-server/register-device
Content-Type: application/json

{
  "device_id": "raspi-001",
  "name": "Living Room Display",
  "ip": "192.168.1.100",
  "extensions": [
    {
      "name": "ExtensionName",
      "version": "1.0.0"
    }
  ]
}
```

### Heartbeat Mechanism

Devices send periodic heartbeats to indicate they are online:

```
POST /api/main-server/heartbeat
Content-Type: application/json

{
  "device_id": "raspi-001",
  "status": "online",
  "timestamp": "2023-12-22T10:30:00Z"
}
```

## Security Considerations

### Authentication
- All API endpoints require JWT authentication
- Devices must authenticate using API keys or device-specific tokens

### Data Integrity
- Update packages include checksums for verification
- HTTPS is recommended for all communications

### Authorization
- Only authorized users can schedule and deploy updates
- Device registration requires approval

## Error Handling

### Error Responses
All error responses follow this format:

```json
{
  "error": "Error description",
  "details": "Additional error details"
}
```

### Common Error Codes
- `401 Unauthorized`: Authentication failed
- `403 Forbidden`: Insufficient permissions
- `404 Not Found`: Resource not found
- `500 Internal Server Error`: Server error

## Implementation Notes

### For Main Server
1. Implement the REST API endpoints as defined
2. Set up device registry and authentication
3. Configure update packaging and distribution
4. Implement monitoring and logging

### For Raspberry Pi Devices
1. Implement periodic polling for updates
2. Create update installation scripts
3. Set up heartbeat mechanism
4. Implement backup and rollback procedures

## Example Workflow

1. **Admin schedules update**: Uses Main Server UI to schedule an update
2. **Main Server packages update**: Creates device-specific update packages
3. **Device polls for updates**: Raspberry Pi device checks for available updates
4. **Update deployment**: Main Server sends update to device
5. **Device installs update**: Device applies the update and restarts
6. **Confirmation**: Device reports successful update to Main Server

This protocol ensures reliable and secure update distribution across multiple Raspberry Pi devices.