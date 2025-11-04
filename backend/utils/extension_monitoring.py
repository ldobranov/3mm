"""
Extension Performance Monitoring and Analytics
"""

import time
import asyncio
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import psutil
import threading

@dataclass
class PerformanceMetrics:
    """Performance metrics for an extension"""
    extension_id: str
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    response_time: float = 0.0
    request_count: int = 0
    error_count: int = 0
    last_activity: Optional[datetime] = None
    uptime: float = 0.0
    database_queries: int = 0
    database_query_time: float = 0.0

@dataclass
class ExtensionStats:
    """Statistical data for extension performance"""
    extension_id: str
    hourly_stats: List[Dict[str, Any]] = field(default_factory=list)
    daily_stats: List[Dict[str, Any]] = field(default_factory=list)
    alerts_triggered: List[Dict[str, Any]] = field(default_factory=list)

class ExtensionPerformanceMonitor:
    """Monitors extension performance and resource usage"""

    def __init__(self):
        self.metrics: Dict[str, PerformanceMetrics] = {}
        self.stats: Dict[str, ExtensionStats] = {}
        self.alerts: Dict[str, List[Dict[str, Any]]] = {}
        self.monitoring_active = False
        self.collection_interval = 60  # seconds
        self.alert_thresholds = {
            'cpu_usage': 80.0,  # percent
            'memory_usage': 100.0,  # MB
            'response_time': 5.0,  # seconds
            'error_rate': 0.1  # 10% error rate
        }

    async def start_monitoring(self):
        """Start the performance monitoring system"""
        self.monitoring_active = True
        asyncio.create_task(self._monitoring_loop())

    async def stop_monitoring(self):
        """Stop the performance monitoring system"""
        self.monitoring_active = False

    def register_extension(self, extension_id: str):
        """Register an extension for monitoring"""
        if extension_id not in self.metrics:
            self.metrics[extension_id] = PerformanceMetrics(extension_id=extension_id)
            self.stats[extension_id] = ExtensionStats(extension_id=extension_id)
            self.alerts[extension_id] = []

    def unregister_extension(self, extension_id: str):
        """Unregister an extension from monitoring"""
        if extension_id in self.metrics:
            del self.metrics[extension_id]
        if extension_id in self.stats:
            del self.stats[extension_id]
        if extension_id in self.alerts:
            del self.alerts[extension_id]

    def record_request(self, extension_id: str, response_time: float, success: bool = True):
        """Record a request for an extension"""
        if extension_id not in self.metrics:
            return

        metrics = self.metrics[extension_id]
        metrics.request_count += 1
        metrics.response_time = (metrics.response_time + response_time) / 2  # Running average
        metrics.last_activity = datetime.utcnow()

        if not success:
            metrics.error_count += 1

        # Check for alerts
        self._check_alerts(extension_id, metrics)

    def record_database_operation(self, extension_id: str, query_time: float):
        """Record a database operation"""
        if extension_id not in self.metrics:
            return

        metrics = self.metrics[extension_id]
        metrics.database_queries += 1
        metrics.database_query_time += query_time

    async def _monitoring_loop(self):
        """Main monitoring loop"""
        while self.monitoring_active:
            try:
                await self._collect_system_metrics()
                await self._aggregate_stats()
                await self._cleanup_old_data()
            except Exception as e:
                print(f"Error in monitoring loop: {e}")

            await asyncio.sleep(self.collection_interval)

    async def _collect_system_metrics(self):
        """Collect system-level metrics for extensions"""
        try:
            # Get process information (simplified - would need more sophisticated tracking)
            current_process = psutil.Process()

            # For each extension, estimate resource usage
            # This is a simplified approach - real implementation would need
            # per-extension process isolation
            for extension_id, metrics in self.metrics.items():
                try:
                    # Update uptime
                    if metrics.last_activity:
                        metrics.uptime = (datetime.utcnow() - metrics.last_activity).total_seconds()

                    # Estimate CPU and memory (simplified)
                    # In a real implementation, you'd track per-extension processes
                    metrics.cpu_usage = current_process.cpu_percent() / len(self.metrics)
                    memory_info = current_process.memory_info()
                    metrics.memory_usage = memory_info.rss / (1024 * 1024) / len(self.metrics)  # MB

                except Exception as e:
                    print(f"Error collecting metrics for {extension_id}: {e}")

        except Exception as e:
            print(f"Error collecting system metrics: {e}")

    def _check_alerts(self, extension_id: str, metrics: PerformanceMetrics):
        """Check if any alert thresholds are exceeded"""
        alerts = []

        # CPU usage alert
        if metrics.cpu_usage > self.alert_thresholds['cpu_usage']:
            alerts.append({
                'type': 'cpu_usage',
                'value': metrics.cpu_usage,
                'threshold': self.alert_thresholds['cpu_usage'],
                'timestamp': datetime.utcnow()
            })

        # Memory usage alert
        if metrics.memory_usage > self.alert_thresholds['memory_usage']:
            alerts.append({
                'type': 'memory_usage',
                'value': metrics.memory_usage,
                'threshold': self.alert_thresholds['memory_usage'],
                'timestamp': datetime.utcnow()
            })

        # Response time alert
        if metrics.response_time > self.alert_thresholds['response_time']:
            alerts.append({
                'type': 'response_time',
                'value': metrics.response_time,
                'threshold': self.alert_thresholds['response_time'],
                'timestamp': datetime.utcnow()
            })

        # Error rate alert
        if metrics.request_count > 0:
            error_rate = metrics.error_count / metrics.request_count
            if error_rate > self.alert_thresholds['error_rate']:
                alerts.append({
                    'type': 'error_rate',
                    'value': error_rate,
                    'threshold': self.alert_thresholds['error_rate'],
                    'timestamp': datetime.utcnow()
                })

        # Record alerts
        if alerts:
            self.alerts[extension_id].extend(alerts)
            # Keep only recent alerts (last 100)
            self.alerts[extension_id] = self.alerts[extension_id][-100:]

    async def _aggregate_stats(self):
        """Aggregate metrics into hourly/daily statistics"""
        current_hour = datetime.utcnow().replace(minute=0, second=0, microsecond=0)

        for extension_id, metrics in self.metrics.items():
            if extension_id not in self.stats:
                continue

            stats = self.stats[extension_id]

            # Create hourly stats
            hourly_stat = {
                'timestamp': current_hour,
                'cpu_avg': metrics.cpu_usage,
                'memory_avg': metrics.memory_usage,
                'response_time_avg': metrics.response_time,
                'requests': metrics.request_count,
                'errors': metrics.error_count,
                'db_queries': metrics.database_queries,
                'db_query_time': metrics.database_query_time
            }

            # Add to hourly stats (keep last 24 hours)
            stats.hourly_stats.append(hourly_stat)
            stats.hourly_stats = [
                s for s in stats.hourly_stats
                if (datetime.utcnow() - s['timestamp']).total_seconds() < 86400
            ]

            # Reset counters for next hour
            metrics.request_count = 0
            metrics.error_count = 0
            metrics.database_queries = 0
            metrics.database_query_time = 0.0

    async def _cleanup_old_data(self):
        """Clean up old statistical data"""
        cutoff_date = datetime.utcnow() - timedelta(days=7)  # Keep 7 days of data

        for stats in self.stats.values():
            # Clean hourly stats
            stats.hourly_stats = [
                s for s in stats.hourly_stats
                if s['timestamp'] > cutoff_date
            ]

            # Clean alerts (keep last 30 days)
            alert_cutoff = datetime.utcnow() - timedelta(days=30)
            for alert_list in self.alerts.values():
                alert_list[:] = [
                    a for a in alert_list
                    if a['timestamp'] > alert_cutoff
                ]

    def get_metrics(self, extension_id: str) -> Optional[PerformanceMetrics]:
        """Get current metrics for an extension"""
        return self.metrics.get(extension_id)

    def get_stats(self, extension_id: str) -> Optional[ExtensionStats]:
        """Get statistical data for an extension"""
        return self.stats.get(extension_id)

    def get_alerts(self, extension_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent alerts for an extension"""
        if extension_id not in self.alerts:
            return []
        return self.alerts[extension_id][-limit:]

    def get_all_metrics(self) -> Dict[str, PerformanceMetrics]:
        """Get metrics for all extensions"""
        return self.metrics.copy()

    def set_alert_threshold(self, metric_type: str, threshold: float):
        """Set alert threshold for a metric type"""
        if metric_type in self.alert_thresholds:
            self.alert_thresholds[metric_type] = threshold

class ExtensionHealthChecker:
    """Checks the health status of extensions"""

    def __init__(self, monitor: ExtensionPerformanceMonitor):
        self.monitor = monitor
        self.health_checks: Dict[str, Dict[str, Any]] = {}

    def register_health_check(self, extension_id: str, check_function: callable, interval: int = 300):
        """Register a health check function for an extension"""
        self.health_checks[extension_id] = {
            'function': check_function,
            'interval': interval,
            'last_check': None,
            'last_result': None
        }

    async def run_health_checks(self):
        """Run all registered health checks"""
        current_time = time.time()

        for extension_id, check_info in self.health_checks.items():
            if (check_info['last_check'] is None or
                current_time - check_info['last_check'] >= check_info['interval']):

                try:
                    result = await check_info['function'](extension_id)
                    check_info['last_result'] = {
                        'status': 'healthy' if result else 'unhealthy',
                        'timestamp': datetime.utcnow(),
                        'details': result
                    }
                except Exception as e:
                    check_info['last_result'] = {
                        'status': 'error',
                        'timestamp': datetime.utcnow(),
                        'error': str(e)
                    }

                check_info['last_check'] = current_time

    def get_health_status(self, extension_id: str) -> Optional[Dict[str, Any]]:
        """Get health status for an extension"""
        if extension_id in self.health_checks:
            return self.health_checks[extension_id].get('last_result')
        return None

# Global instances
performance_monitor = ExtensionPerformanceMonitor()
health_checker = ExtensionHealthChecker(performance_monitor)

# Helper functions
def record_extension_request(extension_id: str, response_time: float, success: bool = True):
    """Helper function to record extension requests"""
    performance_monitor.record_request(extension_id, response_time, success)

def record_database_operation(extension_id: str, query_time: float):
    """Helper function to record database operations"""
    performance_monitor.record_database_operation(extension_id, query_time)

def get_extension_performance(extension_id: str) -> Optional[PerformanceMetrics]:
    """Helper function to get extension performance metrics"""
    return performance_monitor.get_metrics(extension_id)