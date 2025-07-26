# Worker Manager Extension Instructions

## Overview
This document provides instructions for implementing a Worker Manager extension that integrates HiveOS API and Raspberry Pi Controller to monitor workers and perform actions like hardware restarts and shutdowns. The Worker Manager acts as a centralized controller, leveraging HiveOS and Raspberry Pi Controller as utility modules for specific functionalities.

---

## 1. Backend Implementation

### a. Database Models
- Add a model to store monitoring rules and conditions.
- Example:

```python
class MonitoringRule(Base):
    __tablename__ = "monitoring_rules"
    id = Column(Integer, primary_key=True, index=True)
    farm_id = Column(Integer, nullable=False)
    worker_id = Column(Integer, nullable=False)
    condition = Column(String, nullable=False)  # e.g., "temperature > 80"
    action = Column(String, nullable=False)  # e.g., "reboot"
    enabled = Column(Boolean, default=True)
```

### b. API Endpoints
- **Create Rules**: Add an endpoint to define monitoring rules.
- **Fetch Worker Status**: Periodically fetch worker statuses and evaluate rules.
- **Perform Actions**: Trigger actions based on rule evaluation.

Example:

```python
@router.post("/monitoring/rules")
def create_rule(rule: MonitoringRuleCreate, db: Session = Depends(get_db)):
    new_rule = MonitoringRule(**rule.dict())
    db.add(new_rule)
    db.commit()
    return {"message": "Rule created successfully"}

@router.get("/monitoring/evaluate")
def evaluate_rules(db: Session = Depends(get_db)):
    rules = db.query(MonitoringRule).filter_by(enabled=True).all()
    for rule in rules:
        # Fetch worker status and evaluate condition
        # Perform action if condition is met
    return {"message": "Rules evaluated"}
```

### c. Background Task
- Use a background task to periodically fetch worker statuses and evaluate rules.
- Example:

```python
from fastapi_utils.tasks import repeat_every

@app.on_event("startup")
@repeat_every(seconds=60)  # Run every minute
def monitor_workers():
    # Fetch worker statuses and evaluate rules
    pass
```

---

## 2. Integration with HiveOS and Raspberry Pi Controller

### a. Utility Modules
- Treat HiveOS and Raspberry Pi Controller as utility modules for managing keys, routes, and specific actions.
- Example:

```python
from backend.extensions.hiveos.hiveos_api import HiveOSAPI
from backend.extensions.raspberry_pi_controller.mqtt_client import send_mqtt_command

hiveos_api = HiveOSAPI(api_key="your_api_key")
worker_status = hiveos_api.get_worker_status(worker_id)

if rule.action == "reboot":
    send_mqtt_command(topic="reboot", payload=worker_id)
elif rule.action == "shutdown":
    send_mqtt_command(topic="shutdown", payload=worker_id)
```

---

## 3. Frontend Implementation

### a. Monitoring Dashboard
- Create a dashboard to display worker statuses and monitoring rules.
- Example:
  - **Table**: Show worker details (e.g., name, status, temperature, hashrate).
  - **Actions**: Add buttons to manually trigger actions (e.g., reboot, shutdown).

### b. Rule Management
- Add a form to define monitoring rules (e.g., condition, action).
- Example:

```vue
<template>
    <form @submit.prevent="createRule">
        <input v-model="condition" placeholder="Condition (e.g., temperature > 80)" />
        <select v-model="action">
            <option value="reboot">Reboot</option>
            <option value="shutdown">Shutdown</option>
        </select>
        <button type="submit">Create Rule</button>
    </form>
</template>
```

---

## 4. Error Handling and Logging

### a. Error Handling
- Add detailed error handling for rule evaluation and actions.
- Example:

```python
try:
    # Evaluate rules
except Exception as e:
    logger.error(f"Error evaluating rules: {str(e)}")
    raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
```

### b. Logging
- Configure logging to track rule evaluations and actions.
- Example:

```python
import logging

logger = logging.getLogger("worker_manager")
logger.setLevel(logging.DEBUG)
```

---

## 5. Testing

### a. Unit Tests
- Write unit tests for rule evaluation logic.

### b. Integration Tests
- Test the end-to-end flow for monitoring and hardware actions.

---

## 6. Deployment

### a. Dynamic Extension Loading
- Ensure the extension is dynamically loaded and registered.

### b. Menu Integration
- Add the extension to the menu for easy access.

---

## Folder Restrictions

For the Worker Manager extension, only the following folders can be modified:

1. `backend/extensions/manager`
2. `frontend/src/extensions/manager`

Ensure all changes related to the Worker Manager extension are confined to these directories.

---

This document consolidates all necessary steps to implement the Worker Manager extension effectively, integrating HiveOS API and Raspberry Pi Controller for comprehensive worker management.