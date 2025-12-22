# Main Server Extension - Testing Guide

This guide provides instructions for testing the Main Server Extension update system.

## Prerequisites

1. Main Server Extension installed and enabled
2. At least one Raspberry Pi device registered
3. Test extensions available for updates

## Test Cases

### 1. Extension Installation Test

**Objective**: Verify that the Main Server Extension can be installed and initialized.

**Steps**:
1. Upload the Main Server Extension ZIP file via the Extensions UI
2. Enable the extension
3. Verify that the extension appears in the enabled extensions list
4. Check that the API endpoints are accessible

**Expected Results**:
- Extension installs without errors
- Extension appears in the enabled extensions list
- API endpoints respond with expected data

### 2. Update Availability Test

**Objective**: Verify that the system can detect available updates.

**Steps**:
1. Navigate to the Main Server Extension UI
2. Check the "Available Updates" section
3. Verify that any available updates are displayed
4. Check that update compatibility is correctly indicated

**Expected Results**:
- Available updates are displayed with correct information
- Compatibility status is accurate
- No errors in the UI

### 3. Update Scheduling Test

**Objective**: Verify that updates can be scheduled.

**Steps**:
1. In the "Available Updates" section, click "Schedule Update" for a test extension
2. Verify that the update is scheduled
3. Check the update status endpoint

**Expected Results**:
- Update scheduling succeeds
- Update status shows "scheduled"
- No errors in the process

### 4. Device Management Test

**Objective**: Verify that devices can be managed and updates deployed to them.

**Steps**:
1. Navigate to the "Connected Devices" section
2. Verify that registered devices are displayed
3. Click "Deploy to Device" for a test device
4. Select an update and confirm deployment
5. Check the deployment status

**Expected Results**:
- Devices are displayed with correct status
- Deployment dialog opens correctly
- Deployment succeeds or provides meaningful error
- Status is updated appropriately

### 5. Settings Management Test

**Objective**: Verify that update settings can be configured.

**Steps**:
1. Navigate to the "Update Settings" section
2. Modify settings (auto-update, interval, etc.)
3. Save the settings
4. Refresh the page and verify settings persist

**Expected Results**:
- Settings can be modified
- Settings are saved successfully
- Settings persist across page refreshes

## API Testing

### Test API Endpoints

Use tools like `curl`, Postman, or the browser's developer console to test the API endpoints.

#### Test Health Endpoint

```bash
curl -X GET http://localhost:8000/api/main-server/health
```

**Expected Response**:
```json
{
  "ok": true,
  "message": "Main Server Extension is running"
}
```

#### Test Updates Endpoint

```bash
curl -X GET http://localhost:8000/api/main-server/updates \
  -H "Authorization: Bearer <your-token>"
```

**Expected Response**:
```json
{
  "updates": []
}
```

#### Test Devices Endpoint

```bash
curl -X GET http://localhost:8000/api/main-server/devices \
  -H "Authorization: Bearer <your-token>"
```

**Expected Response**:
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

## Integration Testing

### Test with Real Devices

1. **Register a Raspberry Pi Device**:
   ```bash
   curl -X POST http://localhost:8000/api/main-server/register-device \
     -H "Content-Type: application/json" \
     -d '{
       "device_id": "raspi-test",
       "name": "Test Device",
       "ip": "192.168.1.200",
       "extensions": []
     }'
   ```

2. **Test Heartbeat**:
   ```bash
   curl -X POST http://localhost:8000/api/main-server/heartbeat \
     -H "Content-Type: application/json" \
     -d '{
       "device_id": "raspi-test",
       "status": "online",
       "timestamp": "2023-12-22T10:30:00Z"
     }'
   ```

3. **Test Update Deployment**:
   ```bash
   curl -X POST http://localhost:8000/api/main-server/deploy-update \
     -H "Authorization: Bearer <your-token>" \
     -H "Content-Type: application/json" \
     -d '{
       "device_id": "raspi-test",
       "extension_id": 1,
       "version": "1.1.0"
     }'
   ```

## Troubleshooting

### Common Issues

1. **Authentication Errors**:
   - Verify JWT token is valid
   - Check token expiration
   - Ensure proper user permissions

2. **Device Not Showing**:
   - Verify device registration
   - Check heartbeat is being sent
   - Verify network connectivity

3. **Update Deployment Failures**:
   - Check update package exists
   - Verify device is online
   - Check device storage space

### Debugging Tips

1. Check backend logs for errors
2. Use browser developer tools to inspect API requests
3. Verify network connectivity between server and devices
4. Check file permissions for update packages

## Performance Testing

### Load Testing

Test with multiple devices to ensure the system can handle the load:

1. Register 10+ test devices
2. Schedule updates for all devices simultaneously
3. Monitor system performance and response times

### Stress Testing

Test the system under heavy load:

1. Create large update packages (100MB+)
2. Deploy to multiple devices simultaneously
3. Monitor memory usage and network bandwidth

## Security Testing

### Authentication Testing

1. Test API endpoints without authentication (should fail)
2. Test with invalid tokens (should fail)
3. Test with expired tokens (should fail)

### Authorization Testing

1. Test with user roles that don't have update permissions
2. Verify that only authorized users can deploy updates

## Test Completion

After completing all tests:

1. Document any issues found
2. Note any performance bottlenecks
3. Verify all functionality works as expected
4. Update this guide with any new test cases

The Main Server Extension should now be ready for production use with Raspberry Pi devices.