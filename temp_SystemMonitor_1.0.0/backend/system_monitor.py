"""
System Monitor Extension Backend Module
Provides real-time system monitoring with metrics collection and API endpoints.
"""

import psutil
import time
import threading
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any

# In-memory storage for metrics (could be replaced with database)
metrics_history = []
MAX_HISTORY_POINTS = 1000

def collect_system_metrics() -> Dict[str, Any]:
    """Collect current system metrics using psutil"""
    try:
        # CPU metrics
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_cores = psutil.cpu_percent(percpu=True, interval=1)
        load_avg = psutil.getloadavg() if hasattr(psutil, 'getloadavg') else [0, 0, 0]

        # Memory metrics
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()

        # Disk metrics
        disk = psutil.disk_usage('/')
        disk_io = psutil.disk_io_counters()

        # Network metrics
        network = psutil.net_io_counters()

        metrics = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "cpu": {
                "usage_percent": round(cpu_percent, 1),
                "cores": [round(core, 1) for core in cpu_cores],
                "load_avg": [round(load, 2) for load in load_avg]
            },
            "memory": {
                "total_gb": round(memory.total / (1024**3), 1),
                "used_gb": round(memory.used / (1024**3), 1),
                "available_gb": round(memory.available / (1024**3), 1),
                "usage_percent": round(memory.percent, 1),
                "swap_used_gb": round(swap.used / (1024**3), 1),
                "swap_total_gb": round(swap.total / (1024**3), 1)
            },
            "disk": {
                "total_gb": round(disk.total / (1024**3), 1),
                "used_gb": round(disk.used / (1024**3), 1),
                "available_gb": round(disk.free / (1024**3), 1),
                "usage_percent": round(disk.percent, 1),
                "io_read_mb": round(disk_io.read_bytes / (1024**2), 1) if disk_io else 0,
                "io_write_mb": round(disk_io.write_bytes / (1024**2), 1) if disk_io else 0
            },
            "network": {
                "bytes_sent_mb": round(network.bytes_sent / (1024**2), 1),
                "bytes_recv_mb": round(network.bytes_recv / (1024**2), 1),
                "packets_sent": network.packets_sent,
                "packets_recv": network.packets_recv
            }
        }

        return metrics

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to collect system metrics: {str(e)}")

def store_metrics(metrics: Dict[str, Any]):
    """Store metrics in history"""
    global metrics_history

    # Add timestamp for easier querying
    metrics['_timestamp'] = datetime.fromisoformat(metrics['timestamp'].replace('Z', ''))

    metrics_history.append(metrics)

    # Keep only recent history
    if len(metrics_history) > MAX_HISTORY_POINTS:
        metrics_history = metrics_history[-MAX_HISTORY_POINTS:]

def initialize_extension(context):
    """Initialize the System Monitor extension"""
    try:
        # Create database tables for storing metrics (optional, using in-memory for now)
        context.execute_query("""
            CREATE TABLE IF NOT EXISTS system_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                cpu_usage REAL,
                memory_usage REAL,
                disk_usage REAL,
                network_sent REAL,
                network_recv REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Register API routes
        router = APIRouter(prefix="/api/system")

        @router.get("/metrics/current")
        async def get_current_metrics():
            """Get current system metrics"""
            try:
                metrics = collect_system_metrics()
                store_metrics(metrics.copy())  # Store for history
                return metrics
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to collect metrics: {str(e)}")

        @router.get("/metrics/history")
        async def get_metrics_history(hours: int = 24, interval: int = 60):
            """Get historical system metrics"""
            if hours < 1 or hours > 168:  # Max 1 week
                raise HTTPException(status_code=400, detail="Hours must be between 1 and 168")

            if interval < 10 or interval > 3600:  # 10 seconds to 1 hour
                raise HTTPException(status_code=400, detail="Interval must be between 10 and 3600 seconds")

            # Calculate cutoff time
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)

            # Filter historical data
            filtered_data = [
                m for m in metrics_history
                if m.get('_timestamp', datetime.min) >= cutoff_time
            ]

            # Sample data at requested interval
            if filtered_data:
                sampled_data = []
                last_timestamp = None

                for metric in sorted(filtered_data, key=lambda x: x.get('_timestamp', datetime.min)):
                    current_time = metric['_timestamp']

                    if last_timestamp is None or (current_time - last_timestamp).total_seconds() >= interval:
                        # Remove internal timestamp before returning
                        clean_metric = {k: v for k, v in metric.items() if not k.startswith('_')}
                        sampled_data.append(clean_metric)
                        last_timestamp = current_time

                return {"data": sampled_data, "count": len(sampled_data)}

            return {"data": [], "count": 0}

        @router.get("/info")
        async def get_system_info():
            """Get basic system information"""
            try:
                return {
                    "platform": psutil.sys.platform,
                    "cpu_count": psutil.cpu_count(),
                    "cpu_count_logical": psutil.cpu_count(logical=True),
                    "memory_total_gb": round(psutil.virtual_memory().total / (1024**3), 1),
                    "disk_total_gb": round(psutil.disk_usage('/').total / (1024**3), 1),
                    "boot_time": datetime.fromtimestamp(psutil.boot_time()).isoformat()
                }
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to get system info: {str(e)}")

        context.register_router(router)

        # Start background metrics collection
        def start_background_collection():
            """Start background metrics collection thread"""
            def collect_loop():
                while True:
                    try:
                        metrics = collect_system_metrics()
                        store_metrics(metrics.copy())
                    except Exception as e:
                        print(f"System Monitor: Metrics collection error: {e}")
                    time.sleep(30)  # Collect every 30 seconds

            thread = threading.Thread(target=collect_loop, daemon=True)
            thread.start()
            return thread

        # Start the background collection
        collection_thread = start_background_collection()

        return {
            "routes_registered": 3,
            "tables_created": 1,
            "background_collection_started": True,
            "status": "initialized"
        }

    except Exception as e:
        print(f"System Monitor extension initialization error: {e}")
        return {"status": "error", "error": str(e)}

def cleanup_extension(context):
    """Cleanup when extension is disabled"""
    try:
        # Clear metrics history
        global metrics_history
        metrics_history.clear()

        # Note: The background thread will stop automatically when the extension is unloaded
        # since it's a daemon thread

        return {"status": "cleaned_up"}
    except Exception as e:
        print(f"System Monitor extension cleanup error: {e}")
        return {"status": "cleanup_error", "error": str(e)}