"""Telemetry and monitoring support for tokenizer adapters.

This module provides comprehensive telemetry collection, performance monitoring,
and error tracking for tokenizer operations. It includes:

- TokenizationTelemetry: Core telemetry data structure
- TelemetryCollector: Centralized telemetry collection
- PerformanceMonitor: Performance metrics and monitoring
- ErrorTracker: Error rate tracking and alerting
- TelemetryReporter: Dashboard and reporting capabilities
"""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple, Union, Callable
from contextlib import contextmanager

from .tokenizer import TokenCount

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TokenizationTelemetry:
    """Telemetry data for a single tokenization operation."""
    
    # Operation identification
    operation_id: str
    timestamp: datetime
    
    # Adapter information
    adapter_name: str
    adapter_id: str
    model_name: str
    
    # Input characteristics
    text_length: int
    text_preview: str  # First 100 chars for debugging
    
    # Tokenization results
    token_count: TokenCount
    
    # Performance metrics
    processing_time_ms: float
    memory_used_mb: Optional[float] = None
    
    # Operation context
    was_fallback: bool = False
    fallback_from: Optional[str] = None
    error_occurred: bool = False
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    
    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AdapterUsageStats:
    """Usage statistics for a tokenizer adapter."""
    
    adapter_name: str
    total_operations: int = 0
    successful_operations: int = 0
    failed_operations: int = 0
    fallback_operations: int = 0
    
    total_tokens_processed: int = 0
    total_text_length: int = 0
    total_processing_time_ms: float = 0.0
    
    avg_processing_time_ms: float = 0.0
    avg_tokens_per_operation: float = 0.0
    avg_text_length: float = 0.0
    
    success_rate: float = 0.0
    fallback_rate: float = 0.0
    
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None

@dataclass
class PerformanceMetrics:
    """Performance metrics for monitoring and alerting."""
    
    # Time-based metrics
    avg_processing_time_ms: float = 0.0
    p50_processing_time_ms: float = 0.0
    p95_processing_time_ms: float = 0.0
    p99_processing_time_ms: float = 0.0
    
    # Throughput metrics
    operations_per_second: float = 0.0
    tokens_per_second: float = 0.0
    chars_per_second: float = 0.0
    
    # Error metrics
    error_rate: float = 0.0
    fallback_rate: float = 0.0
    
    # Resource metrics
    avg_memory_mb: float = 0.0
    peak_memory_mb: float = 0.0
    
    # Time window
    window_start: datetime = field(default_factory=datetime.now)
    window_end: datetime = field(default_factory=datetime.now)
    sample_count: int = 0


@dataclass
class AlertThresholds:
    """Configurable alert thresholds for monitoring."""
    
    # Performance thresholds
    max_avg_processing_time_ms: float = 1000.0
    max_p95_processing_time_ms: float = 2000.0
    min_operations_per_second: float = 1.0
    
    # Error rate thresholds
    max_error_rate: float = 0.05  # 5%
    max_fallback_rate: float = 0.20  # 20%
    
    # Resource thresholds
    max_avg_memory_mb: float = 500.0
    max_peak_memory_mb: float = 1000.0
    
    # Alert configuration
    min_sample_count: int = 10  # Minimum samples before alerting
    alert_window_minutes: int = 5  # Time window for alert evaluation


class TelemetryCollector:
    """Centralized telemetry collection for tokenizer operations."""
    
    def __init__(self, max_history: int = 10000, enable_memory_tracking: bool = True):
        """Initialize telemetry collector.
        
        Args:
            max_history: Maximum number of telemetry records to keep in memory
            enable_memory_tracking: Whether to track memory usage (requires psutil)
        """
        self._telemetry_history: deque = deque(maxlen=max_history)
        self._adapter_stats: Dict[str, AdapterUsageStats] = {}
        self._lock = Lock()
        self._enable_memory_tracking = enable_memory_tracking
        self._operation_counter = 0
        
        # Try to import psutil for memory tracking
        self._psutil_available = False
        if enable_memory_tracking:
            try:
                import psutil
                self._psutil = psutil
                self._psutil_available = True
                logger.debug("Memory tracking enabled with psutil")
            except ImportError:
                logger.debug("psutil not available, memory tracking disabled")
    
    def record_operation(self, telemetry: TokenizationTelemetry) -> None:
        """Record a tokenization operation."""
        with self._lock:
            # Add to history
            self._telemetry_history.append(telemetry)
            
            # Update adapter statistics
            self._update_adapter_stats(telemetry)
            
            logger.debug(f"Recorded telemetry for operation {telemetry.operation_id}")
    
    def _update_adapter_stats(self, telemetry: TokenizationTelemetry) -> None:
        """Update adapter usage statistics."""
        adapter_name = telemetry.adapter_name
        
        if adapter_name not in self._adapter_stats:
            self._adapter_stats[adapter_name] = AdapterUsageStats(
                adapter_name=adapter_name,
                first_seen=telemetry.timestamp
            )
        
        stats = self._adapter_stats[adapter_name]
        
        # Update counters
        stats.total_operations += 1
        stats.last_seen = telemetry.timestamp
        
        if telemetry.error_occurred:
            stats.failed_operations += 1
        else:
            stats.successful_operations += 1
            stats.total_tokens_processed += telemetry.token_count.count
            stats.total_text_length += telemetry.text_length
            stats.total_processing_time_ms += telemetry.processing_time_ms
        
        if telemetry.was_fallback:
            stats.fallback_operations += 1
        
        # Calculate derived metrics
        if stats.successful_operations > 0:
            stats.avg_processing_time_ms = stats.total_processing_time_ms / stats.successful_operations
            stats.avg_tokens_per_operation = stats.total_tokens_processed / stats.successful_operations
            stats.avg_text_length = stats.total_text_length / stats.successful_operations
        
        stats.success_rate = stats.successful_operations / stats.total_operations
        stats.fallback_rate = stats.fallback_operations / stats.total_operations
    
    @contextmanager
    def track_operation(
        self, 
        adapter_name: str, 
        adapter_id: str, 
        model_name: str, 
        text: str,
        was_fallback: bool = False,
        fallback_from: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Context manager for tracking a tokenization operation.
        
        Usage:
            with collector.track_operation("tiktoken", "tiktoken:gpt-4", "gpt-4", text) as tracker:
                result = adapter.count_tokens(text)
                tracker.set_result(result)
        """
        self._operation_counter += 1
        operation_id = f"tok_{self._operation_counter}_{int(time.time() * 1000)}"
        
        start_time = time.perf_counter()
        try:
            start_memory = self._get_memory_usage()
        except Exception:
            start_memory = None
        timestamp = datetime.now()
        
        error_occurred = False
        error_type = None
        error_message = None
        token_count = None
        
        class OperationTracker:
            def __init__(self, collector_ref):
                self.collector = collector_ref
                self.result_set = False
            
            def set_result(self, result: TokenCount):
                nonlocal token_count
                token_count = result
                self.result_set = True
            
            def set_error(self, error: Exception):
                nonlocal error_occurred, error_type, error_message
                error_occurred = True
                error_type = type(error).__name__
                error_message = str(error)[:200]  # Truncate long error messages
        
        tracker = OperationTracker(self)
        
        try:
            yield tracker
        except Exception as e:
            tracker.set_error(e)
            raise
        finally:
            # Calculate metrics
            end_time = time.perf_counter()
            processing_time_ms = (end_time - start_time) * 1000
            
            try:
                end_memory = self._get_memory_usage()
            except Exception:
                end_memory = None
            memory_used_mb = None
            if start_memory is not None and end_memory is not None:
                memory_used_mb = max(0, end_memory - start_memory)
            
            # Create telemetry record
            telemetry = TokenizationTelemetry(
                operation_id=operation_id,
                timestamp=timestamp,
                adapter_name=adapter_name,
                adapter_id=adapter_id,
                model_name=model_name,
                text_length=len(text),
                text_preview=text[:100],
                token_count=token_count or TokenCount(0, "unknown", "unknown", False),
                processing_time_ms=processing_time_ms,
                memory_used_mb=memory_used_mb,
                was_fallback=was_fallback,
                fallback_from=fallback_from,
                error_occurred=error_occurred,
                error_type=error_type,
                error_message=error_message,
                metadata=metadata or {}
            )
            
            # Record the telemetry
            self.record_operation(telemetry)
    
    def _get_memory_usage(self) -> Optional[float]:
        """Get current memory usage in MB."""
        if not self._psutil_available:
            return None
        
        try:
            import os
            process = self._psutil.Process(os.getpid())
            memory_info = process.memory_info()
            return memory_info.rss / (1024 * 1024)  # Convert to MB
        except Exception:
            return None
    
    def get_adapter_stats(self, adapter_name: Optional[str] = None) -> Union[AdapterUsageStats, Dict[str, AdapterUsageStats]]:
        """Get usage statistics for adapters."""
        with self._lock:
            if adapter_name:
                return self._adapter_stats.get(adapter_name, AdapterUsageStats(adapter_name))
            return self._adapter_stats.copy()
    
    def get_recent_telemetry(self, limit: int = 100) -> List[TokenizationTelemetry]:
        """Get recent telemetry records."""
        with self._lock:
            return list(self._telemetry_history)[-limit:]
    
    def get_telemetry_since(self, since: datetime) -> List[TokenizationTelemetry]:
        """Get telemetry records since a specific time."""
        with self._lock:
            return [t for t in self._telemetry_history if t.timestamp >= since]
    
    def clear_history(self) -> None:
        """Clear telemetry history."""
        with self._lock:
            self._telemetry_history.clear()
            self._adapter_stats.clear()
            logger.info("Cleared telemetry history")
    
    def export_telemetry(self, output_path: Path, format: str = "json") -> None:
        """Export telemetry data to file."""
        with self._lock:
            data = {
                "export_timestamp": datetime.now().isoformat(),
                "telemetry_count": len(self._telemetry_history),
                "adapter_stats": {name: asdict(stats) for name, stats in self._adapter_stats.items()},
                "telemetry_records": []
            }
            
            # Convert telemetry records to serializable format
            for telemetry in self._telemetry_history:
                record = asdict(telemetry)
                record["timestamp"] = telemetry.timestamp.isoformat()
                record["token_count"] = asdict(telemetry.token_count)
                data["telemetry_records"].append(record)
        
        if format.lower() == "json":
            with open(output_path, 'w') as f:
                json.dump(data, f, indent=2, default=str)
        else:
            raise ValueError(f"Unsupported export format: {format}")
        
        logger.info(f"Exported {len(self._telemetry_history)} telemetry records to {output_path}")


class PerformanceMonitor:
    """Performance monitoring and alerting for tokenizer operations."""
    
    def __init__(self, collector: TelemetryCollector, thresholds: Optional[AlertThresholds] = None):
        """Initialize performance monitor.
        
        Args:
            collector: TelemetryCollector instance to monitor
            thresholds: Alert thresholds configuration
        """
        self._collector = collector
        self._thresholds = thresholds or AlertThresholds()
        self._alert_callbacks: List[Callable[[str, Dict[str, Any]], None]] = []
        self._last_alert_times: Dict[str, datetime] = {}
        self._alert_cooldown = timedelta(minutes=5)  # Prevent alert spam
    
    def add_alert_callback(self, callback: Callable[[str, Dict[str, Any]], None]) -> None:
        """Add callback function for alerts.
        
        Args:
            callback: Function that takes (alert_type, alert_data) parameters
        """
        self._alert_callbacks.append(callback)
    
    def calculate_metrics(self, window_minutes: int = 5) -> Dict[str, PerformanceMetrics]:
        """Calculate performance metrics for each adapter."""
        window_start = datetime.now() - timedelta(minutes=window_minutes)
        recent_telemetry = self._collector.get_telemetry_since(window_start)
        
        # Group by adapter
        adapter_telemetry = defaultdict(list)
        for telemetry in recent_telemetry:
            if not telemetry.error_occurred:  # Only include successful operations
                adapter_telemetry[telemetry.adapter_name].append(telemetry)
        
        metrics = {}
        for adapter_name, telemetry_list in adapter_telemetry.items():
            if not telemetry_list:
                continue
            
            # Calculate timing metrics
            processing_times = [t.processing_time_ms for t in telemetry_list]
            processing_times.sort()
            
            n = len(processing_times)
            if n == 0:
                continue
            
            avg_time = sum(processing_times) / n
            p50_time = processing_times[int(n * 0.5)]
            p95_time = processing_times[int(n * 0.95)]
            p99_time = processing_times[int(n * 0.99)]
            
            # Calculate throughput
            window_duration_seconds = window_minutes * 60
            ops_per_second = len(telemetry_list) / window_duration_seconds
            
            total_tokens = sum(t.token_count.count for t in telemetry_list)
            tokens_per_second = total_tokens / window_duration_seconds
            
            total_chars = sum(t.text_length for t in telemetry_list)
            chars_per_second = total_chars / window_duration_seconds
            
            # Calculate error rates
            all_operations = [t for t in recent_telemetry if t.adapter_name == adapter_name]
            error_rate = sum(1 for t in all_operations if t.error_occurred) / len(all_operations) if all_operations else 0
            fallback_rate = sum(1 for t in all_operations if t.was_fallback) / len(all_operations) if all_operations else 0
            
            # Calculate memory metrics
            memory_values = [t.memory_used_mb for t in telemetry_list if t.memory_used_mb is not None]
            avg_memory = sum(memory_values) / len(memory_values) if memory_values else 0
            peak_memory = max(memory_values) if memory_values else 0
            
            metrics[adapter_name] = PerformanceMetrics(
                avg_processing_time_ms=avg_time,
                p50_processing_time_ms=p50_time,
                p95_processing_time_ms=p95_time,
                p99_processing_time_ms=p99_time,
                operations_per_second=ops_per_second,
                tokens_per_second=tokens_per_second,
                chars_per_second=chars_per_second,
                error_rate=error_rate,
                fallback_rate=fallback_rate,
                avg_memory_mb=avg_memory,
                peak_memory_mb=peak_memory,
                window_start=window_start,
                window_end=datetime.now(),
                sample_count=len(telemetry_list)
            )
        
        return metrics
    
    def check_alerts(self, window_minutes: int = 5) -> List[Dict[str, Any]]:
        """Check for alert conditions and trigger callbacks."""
        metrics = self.calculate_metrics(window_minutes)
        alerts = []
        
        for adapter_name, adapter_metrics in metrics.items():
            # Skip if insufficient samples
            if adapter_metrics.sample_count < self._thresholds.min_sample_count:
                continue
            
            # Check performance thresholds
            if adapter_metrics.avg_processing_time_ms > self._thresholds.max_avg_processing_time_ms:
                alert = self._create_alert(
                    "high_avg_processing_time",
                    adapter_name,
                    f"Average processing time ({adapter_metrics.avg_processing_time_ms:.1f}ms) exceeds threshold ({self._thresholds.max_avg_processing_time_ms:.1f}ms)",
                    {"current_value": adapter_metrics.avg_processing_time_ms, "threshold": self._thresholds.max_avg_processing_time_ms}
                )
                if alert:
                    alerts.append(alert)
            
            if adapter_metrics.p95_processing_time_ms > self._thresholds.max_p95_processing_time_ms:
                alert = self._create_alert(
                    "high_p95_processing_time",
                    adapter_name,
                    f"P95 processing time ({adapter_metrics.p95_processing_time_ms:.1f}ms) exceeds threshold ({self._thresholds.max_p95_processing_time_ms:.1f}ms)",
                    {"current_value": adapter_metrics.p95_processing_time_ms, "threshold": self._thresholds.max_p95_processing_time_ms}
                )
                if alert:
                    alerts.append(alert)
            
            if adapter_metrics.operations_per_second < self._thresholds.min_operations_per_second:
                alert = self._create_alert(
                    "low_throughput",
                    adapter_name,
                    f"Operations per second ({adapter_metrics.operations_per_second:.2f}) below threshold ({self._thresholds.min_operations_per_second:.2f})",
                    {"current_value": adapter_metrics.operations_per_second, "threshold": self._thresholds.min_operations_per_second}
                )
                if alert:
                    alerts.append(alert)
            
            # Check error rate thresholds
            if adapter_metrics.error_rate > self._thresholds.max_error_rate:
                alert = self._create_alert(
                    "high_error_rate",
                    adapter_name,
                    f"Error rate ({adapter_metrics.error_rate:.1%}) exceeds threshold ({self._thresholds.max_error_rate:.1%})",
                    {"current_value": adapter_metrics.error_rate, "threshold": self._thresholds.max_error_rate}
                )
                if alert:
                    alerts.append(alert)
            
            if adapter_metrics.fallback_rate > self._thresholds.max_fallback_rate:
                alert = self._create_alert(
                    "high_fallback_rate",
                    adapter_name,
                    f"Fallback rate ({adapter_metrics.fallback_rate:.1%}) exceeds threshold ({self._thresholds.max_fallback_rate:.1%})",
                    {"current_value": adapter_metrics.fallback_rate, "threshold": self._thresholds.max_fallback_rate}
                )
                if alert:
                    alerts.append(alert)
            
            # Check memory thresholds
            if adapter_metrics.avg_memory_mb > self._thresholds.max_avg_memory_mb:
                alert = self._create_alert(
                    "high_avg_memory",
                    adapter_name,
                    f"Average memory usage ({adapter_metrics.avg_memory_mb:.1f}MB) exceeds threshold ({self._thresholds.max_avg_memory_mb:.1f}MB)",
                    {"current_value": adapter_metrics.avg_memory_mb, "threshold": self._thresholds.max_avg_memory_mb}
                )
                if alert:
                    alerts.append(alert)
            
            if adapter_metrics.peak_memory_mb > self._thresholds.max_peak_memory_mb:
                alert = self._create_alert(
                    "high_peak_memory",
                    adapter_name,
                    f"Peak memory usage ({adapter_metrics.peak_memory_mb:.1f}MB) exceeds threshold ({self._thresholds.max_peak_memory_mb:.1f}MB)",
                    {"current_value": adapter_metrics.peak_memory_mb, "threshold": self._thresholds.max_peak_memory_mb}
                )
                if alert:
                    alerts.append(alert)
        
        return alerts
    
    def _create_alert(self, alert_type: str, adapter_name: str, message: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create and potentially trigger an alert."""
        alert_key = f"{alert_type}:{adapter_name}"
        now = datetime.now()
        
        # Check cooldown
        if alert_key in self._last_alert_times:
            if now - self._last_alert_times[alert_key] < self._alert_cooldown:
                return None  # Still in cooldown
        
        # Create alert
        alert = {
            "alert_type": alert_type,
            "adapter_name": adapter_name,
            "message": message,
            "timestamp": now,
            "data": data
        }
        
        # Trigger callbacks
        for callback in self._alert_callbacks:
            try:
                callback(alert_type, alert)
            except Exception as e:
                logger.error(f"Alert callback failed: {e}")
        
        # Update last alert time
        self._last_alert_times[alert_key] = now
        
        logger.warning(f"Alert triggered: {alert_type} for {adapter_name}: {message}")
        
        return alert


# Global telemetry collector instance
_default_collector: Optional[TelemetryCollector] = None
_default_monitor: Optional[PerformanceMonitor] = None


def get_default_collector() -> TelemetryCollector:
    """Get the default telemetry collector instance."""
    global _default_collector
    if _default_collector is None:
        _default_collector = TelemetryCollector()
    return _default_collector


def get_default_monitor() -> PerformanceMonitor:
    """Get the default performance monitor instance."""
    global _default_monitor, _default_collector
    if _default_monitor is None:
        if _default_collector is None:
            _default_collector = TelemetryCollector()
        _default_monitor = PerformanceMonitor(_default_collector)
    return _default_monitor


def configure_telemetry(
    max_history: int = 10000,
    enable_memory_tracking: bool = True,
    alert_thresholds: Optional[AlertThresholds] = None
) -> Tuple[TelemetryCollector, PerformanceMonitor]:
    """Configure global telemetry collection and monitoring.
    
    Args:
        max_history: Maximum telemetry records to keep in memory
        enable_memory_tracking: Whether to track memory usage
        alert_thresholds: Custom alert thresholds
    
    Returns:
        Tuple of (collector, monitor) instances
    """
    global _default_collector, _default_monitor
    
    _default_collector = TelemetryCollector(max_history, enable_memory_tracking)
    _default_monitor = PerformanceMonitor(_default_collector, alert_thresholds)
    
    logger.info(f"Configured telemetry: max_history={max_history}, memory_tracking={enable_memory_tracking}")
    
    return _default_collector, _default_monitor


def log_alert_to_console(alert_type: str, alert_data: Dict[str, Any]) -> None:
    """Default alert callback that logs to console."""
    timestamp = alert_data["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
    adapter = alert_data["adapter_name"]
    message = alert_data["message"]
    
    logger.warning(f"[{timestamp}] TOKENIZER ALERT ({alert_type.upper()}): {adapter} - {message}")


def setup_default_alerting() -> None:
    """Setup default alerting with console logging."""
    monitor = get_default_monitor()
    monitor.add_alert_callback(log_alert_to_console)
    logger.info("Setup default alerting with console logging")
