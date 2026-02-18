"""Tests for tokenizer telemetry and monitoring system.

This module tests the comprehensive telemetry collection, performance monitoring,
and error tracking capabilities for tokenizer adapters.
"""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from kano_backlog_core.tokenizer import TokenCount, HeuristicTokenizer
from kano_backlog_core.tokenizer_telemetry import (
    TokenizationTelemetry,
    TelemetryCollector,
    PerformanceMonitor,
    AlertThresholds,
    AdapterUsageStats,
    PerformanceMetrics,
    get_default_collector,
    get_default_monitor,
    configure_telemetry,
    setup_default_alerting,
)
from kano_backlog_core.tokenizer_reporting import (
    TelemetryReporter,
    HealthChecker,
    HealthStatus,
    DashboardData,
)


class TestTokenizationTelemetry:
    """Test TokenizationTelemetry data structure."""
    
    def test_telemetry_creation(self):
        """Test creating telemetry record."""
        timestamp = datetime.now()
        token_count = TokenCount(10, "heuristic", "heuristic:test", False)
        
        telemetry = TokenizationTelemetry(
            operation_id="test_op_1",
            timestamp=timestamp,
            adapter_name="heuristic",
            adapter_id="heuristic:test-model",
            model_name="test-model",
            text_length=50,
            text_preview="This is a test text for telemetry",
            token_count=token_count,
            processing_time_ms=15.5,
            memory_used_mb=2.1,
            was_fallback=False,
            error_occurred=False
        )
        
        assert telemetry.operation_id == "test_op_1"
        assert telemetry.timestamp == timestamp
        assert telemetry.adapter_name == "heuristic"
        assert telemetry.token_count.count == 10
        assert telemetry.processing_time_ms == 15.5
        assert not telemetry.was_fallback
        assert not telemetry.error_occurred
    
    def test_telemetry_with_error(self):
        """Test telemetry record with error information."""
        token_count = TokenCount(0, "unknown", "unknown", False)
        
        telemetry = TokenizationTelemetry(
            operation_id="error_op_1",
            timestamp=datetime.now(),
            adapter_name="tiktoken",
            adapter_id="tiktoken:gpt-4",
            model_name="gpt-4",
            text_length=100,
            text_preview="Text that caused an error",
            token_count=token_count,
            processing_time_ms=5.0,
            error_occurred=True,
            error_type="ImportError",
            error_message="tiktoken package not available"
        )
        
        assert telemetry.error_occurred
        assert telemetry.error_type == "ImportError"
        assert "tiktoken package" in telemetry.error_message
    
    def test_telemetry_with_fallback(self):
        """Test telemetry record with fallback information."""
        token_count = TokenCount(8, "heuristic", "heuristic:fallback", False)
        
        telemetry = TokenizationTelemetry(
            operation_id="fallback_op_1",
            timestamp=datetime.now(),
            adapter_name="heuristic",
            adapter_id="heuristic:test-model",
            model_name="test-model",
            text_length=30,
            text_preview="Fallback test text",
            token_count=token_count,
            processing_time_ms=12.0,
            was_fallback=True,
            fallback_from="tiktoken"
        )
        
        assert telemetry.was_fallback
        assert telemetry.fallback_from == "tiktoken"


class TestTelemetryCollector:
    """Test TelemetryCollector functionality."""
    
    def test_collector_initialization(self):
        """Test collector initialization."""
        collector = TelemetryCollector(max_history=100, enable_memory_tracking=False)
        
        assert len(collector._telemetry_history) == 0
        assert len(collector._adapter_stats) == 0
        assert not collector._enable_memory_tracking
    
    def test_record_operation(self):
        """Test recording telemetry operations."""
        collector = TelemetryCollector(max_history=10)
        
        # Create test telemetry
        token_count = TokenCount(15, "heuristic", "heuristic:test", False)
        telemetry = TokenizationTelemetry(
            operation_id="test_1",
            timestamp=datetime.now(),
            adapter_name="heuristic",
            adapter_id="heuristic:test",
            model_name="test-model",
            text_length=60,
            text_preview="Test text for recording",
            token_count=token_count,
            processing_time_ms=20.0
        )
        
        collector.record_operation(telemetry)
        
        # Check history
        assert len(collector._telemetry_history) == 1
        assert collector._telemetry_history[0] == telemetry
        
        # Check adapter stats
        assert "heuristic" in collector._adapter_stats
        stats = collector._adapter_stats["heuristic"]
        assert stats.total_operations == 1
        assert stats.successful_operations == 1
        assert stats.total_tokens_processed == 15
        assert stats.total_processing_time_ms == 20.0
    
    def test_adapter_stats_calculation(self):
        """Test adapter statistics calculation."""
        collector = TelemetryCollector()
        
        # Record multiple operations
        for i in range(5):
            token_count = TokenCount(10 + i, "heuristic", "heuristic:test", False)
            telemetry = TokenizationTelemetry(
                operation_id=f"test_{i}",
                timestamp=datetime.now(),
                adapter_name="heuristic",
                adapter_id="heuristic:test",
                model_name="test-model",
                text_length=50 + i * 10,
                text_preview=f"Test text {i}",
                token_count=token_count,
                processing_time_ms=15.0 + i * 2
            )
            collector.record_operation(telemetry)
        
        stats = collector.get_adapter_stats("heuristic")
        assert stats.total_operations == 5
        assert stats.successful_operations == 5
        assert stats.total_tokens_processed == 60  # 10+11+12+13+14
        assert stats.avg_tokens_per_operation == 12.0
        assert stats.success_rate == 1.0
        assert stats.fallback_rate == 0.0
    
    def test_track_operation_context_manager(self):
        """Test the track_operation context manager."""
        collector = TelemetryCollector()
        
        # Test successful operation
        with collector.track_operation(
            adapter_name="heuristic",
            adapter_id="heuristic:test",
            model_name="test-model",
            text="Test text for context manager"
        ) as tracker:
            # Simulate some work
            time.sleep(0.01)
            result = TokenCount(8, "heuristic", "heuristic:test", False)
            tracker.set_result(result)
        
        # Check that telemetry was recorded
        assert len(collector._telemetry_history) == 1
        telemetry = collector._telemetry_history[0]
        assert telemetry.adapter_name == "heuristic"
        assert telemetry.token_count.count == 8
        assert telemetry.processing_time_ms > 0
        assert not telemetry.error_occurred
    
    def test_track_operation_with_error(self):
        """Test track_operation context manager with error."""
        collector = TelemetryCollector()
        
        # Test operation with error
        with pytest.raises(ValueError):
            with collector.track_operation(
                adapter_name="tiktoken",
                adapter_id="tiktoken:gpt-4",
                model_name="gpt-4",
                text="Error test text"
            ) as tracker:
                raise ValueError("Test error")
        
        # Check that error telemetry was recorded
        assert len(collector._telemetry_history) == 1
        telemetry = collector._telemetry_history[0]
        assert telemetry.error_occurred
        assert telemetry.error_type == "ValueError"
        assert "Test error" in telemetry.error_message
    
    def test_get_recent_telemetry(self):
        """Test getting recent telemetry records."""
        collector = TelemetryCollector(max_history=100)
        
        # Add multiple records
        for i in range(10):
            token_count = TokenCount(i + 1, "heuristic", "heuristic:test", False)
            telemetry = TokenizationTelemetry(
                operation_id=f"test_{i}",
                timestamp=datetime.now(),
                adapter_name="heuristic",
                adapter_id="heuristic:test",
                model_name="test-model",
                text_length=20,
                text_preview=f"Test {i}",
                token_count=token_count,
                processing_time_ms=10.0
            )
            collector.record_operation(telemetry)
        
        # Get recent records
        recent = collector.get_recent_telemetry(limit=5)
        assert len(recent) == 5
        
        # Should be the last 5 records
        for i, telemetry in enumerate(recent[-5:]):
            assert telemetry.operation_id == f"test_{5 + i}"
    
    def test_get_telemetry_since(self):
        """Test getting telemetry since a specific time."""
        collector = TelemetryCollector()
        
        base_time = datetime.now()
        
        # Add records with different timestamps
        for i in range(5):
            timestamp = base_time + timedelta(minutes=i)
            token_count = TokenCount(i + 1, "heuristic", "heuristic:test", False)
            telemetry = TokenizationTelemetry(
                operation_id=f"test_{i}",
                timestamp=timestamp,
                adapter_name="heuristic",
                adapter_id="heuristic:test",
                model_name="test-model",
                text_length=20,
                text_preview=f"Test {i}",
                token_count=token_count,
                processing_time_ms=10.0
            )
            collector.record_operation(telemetry)
        
        # Get records since 2 minutes ago
        since_time = base_time + timedelta(minutes=2)
        recent = collector.get_telemetry_since(since_time)
        
        # Should get records 2, 3, 4
        assert len(recent) == 3
        assert all(t.timestamp >= since_time for t in recent)
    
    def test_export_telemetry(self, tmp_path):
        """Test exporting telemetry data."""
        collector = TelemetryCollector()
        
        # Add some test data
        token_count = TokenCount(10, "heuristic", "heuristic:test", False)
        telemetry = TokenizationTelemetry(
            operation_id="export_test",
            timestamp=datetime.now(),
            adapter_name="heuristic",
            adapter_id="heuristic:test",
            model_name="test-model",
            text_length=40,
            text_preview="Export test text",
            token_count=token_count,
            processing_time_ms=15.0
        )
        collector.record_operation(telemetry)
        
        # Export to file
        export_path = tmp_path / "telemetry_export.json"
        collector.export_telemetry(export_path, format="json")
        
        # Verify export
        assert export_path.exists()
        
        with open(export_path) as f:
            data = json.load(f)
        
        assert "export_timestamp" in data
        assert data["telemetry_count"] == 1
        assert "adapter_stats" in data
        assert "telemetry_records" in data
        assert len(data["telemetry_records"]) == 1
        
        record = data["telemetry_records"][0]
        assert record["operation_id"] == "export_test"
        assert record["adapter_name"] == "heuristic"


class TestPerformanceMonitor:
    """Test PerformanceMonitor functionality."""
    
    def test_monitor_initialization(self):
        """Test monitor initialization."""
        collector = TelemetryCollector()
        thresholds = AlertThresholds(max_avg_processing_time_ms=500.0)
        monitor = PerformanceMonitor(collector, thresholds)
        
        assert monitor._collector == collector
        assert monitor._thresholds.max_avg_processing_time_ms == 500.0
        assert len(monitor._alert_callbacks) == 0
    
    def test_calculate_metrics(self):
        """Test performance metrics calculation."""
        collector = TelemetryCollector()
        monitor = PerformanceMonitor(collector)
        
        # Add test data
        base_time = datetime.now()
        processing_times = [10.0, 15.0, 20.0, 25.0, 30.0]
        
        for i, proc_time in enumerate(processing_times):
            token_count = TokenCount(10 + i, "heuristic", "heuristic:test", False)
            telemetry = TokenizationTelemetry(
                operation_id=f"perf_test_{i}",
                timestamp=base_time + timedelta(seconds=i),
                adapter_name="heuristic",
                adapter_id="heuristic:test",
                model_name="test-model",
                text_length=50,
                text_preview=f"Performance test {i}",
                token_count=token_count,
                processing_time_ms=proc_time
            )
            collector.record_operation(telemetry)
        
        # Calculate metrics
        metrics = monitor.calculate_metrics(window_minutes=5)
        
        assert "heuristic" in metrics
        heuristic_metrics = metrics["heuristic"]
        
        assert heuristic_metrics.avg_processing_time_ms == 20.0  # Average of processing times
        assert heuristic_metrics.sample_count == 5
        assert heuristic_metrics.operations_per_second > 0
        assert heuristic_metrics.tokens_per_second > 0
    
    def test_alert_callbacks(self):
        """Test alert callback functionality."""
        collector = TelemetryCollector()
        thresholds = AlertThresholds(max_avg_processing_time_ms=10.0)  # Low threshold
        monitor = PerformanceMonitor(collector, thresholds)
        
        # Add callback
        alerts_received = []
        
        def test_callback(alert_type, alert_data):
            alerts_received.append((alert_type, alert_data))
        
        monitor.add_alert_callback(test_callback)
        
        # Add slow operations to trigger alert
        for i in range(15):  # Need minimum samples
            token_count = TokenCount(10, "heuristic", "heuristic:test", False)
            telemetry = TokenizationTelemetry(
                operation_id=f"slow_test_{i}",
                timestamp=datetime.now(),
                adapter_name="heuristic",
                adapter_id="heuristic:test",
                model_name="test-model",
                text_length=50,
                text_preview="Slow operation test",
                token_count=token_count,
                processing_time_ms=50.0  # Exceeds threshold
            )
            collector.record_operation(telemetry)
        
        # Check for alerts
        alerts = monitor.check_alerts(window_minutes=5)
        
        # Should have triggered high processing time alert
        assert len(alerts) > 0
        assert any(alert["alert_type"] == "high_avg_processing_time" for alert in alerts)
        
        # Callback should have been called
        assert len(alerts_received) > 0
    
    def test_alert_cooldown(self):
        """Test alert cooldown mechanism."""
        collector = TelemetryCollector()
        thresholds = AlertThresholds(
            max_error_rate=0.1,  # 10% error rate threshold
            min_operations_per_second=0.0,  # Disable throughput alerts for this test
        )
        monitor = PerformanceMonitor(collector, thresholds)
        
        alerts_received = []
        
        def test_callback(alert_type, alert_data):
            alerts_received.append((alert_type, alert_data))
        
        monitor.add_alert_callback(test_callback)
        
        # Add operations with high error rate
        for i in range(20):
            token_count = TokenCount(10, "heuristic", "heuristic:test", False)
            telemetry = TokenizationTelemetry(
                operation_id=f"error_test_{i}",
                timestamp=datetime.now(),
                adapter_name="heuristic",
                adapter_id="heuristic:test",
                model_name="test-model",
                text_length=50,
                text_preview="Error test",
                token_count=token_count,
                processing_time_ms=10.0,
                error_occurred=(i % 2 == 0)  # 50% error rate
            )
            collector.record_operation(telemetry)
        
        # Check alerts multiple times
        alerts1 = monitor.check_alerts(window_minutes=5)
        alerts2 = monitor.check_alerts(window_minutes=5)  # Should be in cooldown
        
        # First check should trigger alert
        assert len(alerts1) > 0
        
        # Second check should not trigger due to cooldown
        # (but alerts2 might still contain the alert data, cooldown affects callbacks)
        assert len(alerts_received) == 1  # Only one callback due to cooldown


class TestTelemetryReporter:
    """Test TelemetryReporter functionality."""
    
    def test_generate_dashboard_data(self):
        """Test dashboard data generation."""
        collector = TelemetryCollector()
        monitor = PerformanceMonitor(collector)
        reporter = TelemetryReporter(collector, monitor)
        
        # Add test data
        base_time = datetime.now()
        
        for i in range(10):
            token_count = TokenCount(10 + i, "heuristic", "heuristic:test", False)
            telemetry = TokenizationTelemetry(
                operation_id=f"dashboard_test_{i}",
                timestamp=base_time + timedelta(minutes=i),
                adapter_name="heuristic",
                adapter_id="heuristic:test",
                model_name="test-model",
                text_length=50,
                text_preview=f"Dashboard test {i}",
                token_count=token_count,
                processing_time_ms=15.0 + i,
                error_occurred=(i == 8)  # One error
            )
            collector.record_operation(telemetry)
        
        # Generate dashboard data
        dashboard = reporter.generate_dashboard_data(window_hours=1)
        
        assert isinstance(dashboard, DashboardData)
        assert dashboard.total_operations == 10
        assert dashboard.successful_operations == 9
        assert dashboard.failed_operations == 1
        assert dashboard.total_adapters == 1
        assert dashboard.active_adapters == 1
        
        # Check adapter usage
        assert "heuristic" in dashboard.adapter_usage
        heuristic_stats = dashboard.adapter_usage["heuristic"]
        assert heuristic_stats.total_operations == 10
        assert heuristic_stats.successful_operations == 9
        
        # Check health status
        assert isinstance(dashboard.health_status, HealthStatus)
        assert dashboard.health_status.status in ["healthy", "warning", "critical"]
    
    def test_generate_text_report(self):
        """Test text report generation."""
        collector = TelemetryCollector()
        monitor = PerformanceMonitor(collector)
        reporter = TelemetryReporter(collector, monitor)
        
        # Add minimal test data
        token_count = TokenCount(10, "heuristic", "heuristic:test", False)
        telemetry = TokenizationTelemetry(
            operation_id="report_test",
            timestamp=datetime.now(),
            adapter_name="heuristic",
            adapter_id="heuristic:test",
            model_name="test-model",
            text_length=50,
            text_preview="Report test",
            token_count=token_count,
            processing_time_ms=15.0
        )
        collector.record_operation(telemetry)
        
        # Generate text report
        report = reporter.generate_text_report(window_hours=1)
        
        assert isinstance(report, str)
        assert "TOKENIZER TELEMETRY REPORT" in report
        assert "SUMMARY" in report
        assert "HEALTH STATUS" in report
        assert "ADAPTER USAGE" in report
        assert "heuristic" in report.lower()
    
    def test_generate_json_report(self):
        """Test JSON report generation."""
        collector = TelemetryCollector()
        monitor = PerformanceMonitor(collector)
        reporter = TelemetryReporter(collector, monitor)
        
        # Add test data
        token_count = TokenCount(10, "heuristic", "heuristic:test", False)
        telemetry = TokenizationTelemetry(
            operation_id="json_test",
            timestamp=datetime.now(),
            adapter_name="heuristic",
            adapter_id="heuristic:test",
            model_name="test-model",
            text_length=50,
            text_preview="JSON test",
            token_count=token_count,
            processing_time_ms=15.0
        )
        collector.record_operation(telemetry)
        
        # Generate JSON report
        report = reporter.generate_json_report(window_hours=1)
        
        assert isinstance(report, dict)
        assert "total_operations" in report
        assert "successful_operations" in report
        assert "adapter_usage" in report
        assert "health_status" in report
        assert "generated_at" in report
        
        # Check that datetime fields are ISO strings
        assert isinstance(report["generated_at"], str)
        assert isinstance(report["health_status"]["last_updated"], str)
    
    def test_export_report(self, tmp_path):
        """Test report export functionality."""
        collector = TelemetryCollector()
        monitor = PerformanceMonitor(collector)
        reporter = TelemetryReporter(collector, monitor)
        
        # Add test data
        token_count = TokenCount(10, "heuristic", "heuristic:test", False)
        telemetry = TokenizationTelemetry(
            operation_id="export_test",
            timestamp=datetime.now(),
            adapter_name="heuristic",
            adapter_id="heuristic:test",
            model_name="test-model",
            text_length=50,
            text_preview="Export test",
            token_count=token_count,
            processing_time_ms=15.0
        )
        collector.record_operation(telemetry)
        
        # Export JSON report
        json_path = tmp_path / "report.json"
        reporter.export_report(json_path, format="json", window_hours=1)
        
        assert json_path.exists()
        
        with open(json_path) as f:
            data = json.load(f)
        
        assert "total_operations" in data
        assert data["total_operations"] == 1
        
        # Export text report
        txt_path = tmp_path / "report.txt"
        reporter.export_report(txt_path, format="txt", window_hours=1)
        
        assert txt_path.exists()
        
        content = txt_path.read_text()
        assert "TOKENIZER TELEMETRY REPORT" in content


class TestHealthChecker:
    """Test HealthChecker functionality."""
    
    def test_check_system_health(self):
        """Test system health check."""
        collector = TelemetryCollector()
        monitor = PerformanceMonitor(collector)
        health_checker = HealthChecker(collector, monitor)
        
        # Add healthy operations
        for i in range(10):
            token_count = TokenCount(10, "heuristic", "heuristic:test", False)
            telemetry = TokenizationTelemetry(
                operation_id=f"health_test_{i}",
                timestamp=datetime.now(),
                adapter_name="heuristic",
                adapter_id="heuristic:test",
                model_name="test-model",
                text_length=50,
                text_preview="Health test",
                token_count=token_count,
                processing_time_ms=15.0
            )
            collector.record_operation(telemetry)
        
        # Check health
        health_status = health_checker.check_system_health(window_minutes=5)
        
        assert isinstance(health_status, HealthStatus)
        assert health_status.status in ["healthy", "warning", "critical"]
        assert 0.0 <= health_status.score <= 1.0
        assert isinstance(health_status.issues, list)
        assert isinstance(health_status.recommendations, list)
    
    def test_get_health_summary(self):
        """Test health summary generation."""
        collector = TelemetryCollector()
        monitor = PerformanceMonitor(collector)
        health_checker = HealthChecker(collector, monitor)
        
        # Add test data
        token_count = TokenCount(10, "heuristic", "heuristic:test", False)
        telemetry = TokenizationTelemetry(
            operation_id="summary_test",
            timestamp=datetime.now(),
            adapter_name="heuristic",
            adapter_id="heuristic:test",
            model_name="test-model",
            text_length=50,
            text_preview="Summary test",
            token_count=token_count,
            processing_time_ms=15.0
        )
        collector.record_operation(telemetry)
        
        # Get health summary
        summary = health_checker.get_health_summary()
        
        assert isinstance(summary, dict)
        assert "status" in summary
        assert "score" in summary
        assert "issue_count" in summary
        assert "last_updated" in summary
        assert "component_health" in summary
        
        # Check component health structure
        component_health = summary["component_health"]
        assert "adapters" in component_health
        assert "performance" in component_health
        assert "errors" in component_health
        assert "resources" in component_health
    
    def test_diagnose_issues(self):
        """Test issue diagnosis."""
        collector = TelemetryCollector()
        monitor = PerformanceMonitor(collector)
        health_checker = HealthChecker(collector, monitor)
        
        # Add operations with issues (high error rate)
        for i in range(20):
            token_count = TokenCount(10, "heuristic", "heuristic:test", False)
            telemetry = TokenizationTelemetry(
                operation_id=f"issue_test_{i}",
                timestamp=datetime.now(),
                adapter_name="heuristic",
                adapter_id="heuristic:test",
                model_name="test-model",
                text_length=50,
                text_preview="Issue test",
                token_count=token_count,
                processing_time_ms=15.0,
                error_occurred=(i % 3 == 0)  # 33% error rate
            )
            collector.record_operation(telemetry)
        
        # Diagnose issues
        diagnostics = health_checker.diagnose_issues()
        
        assert isinstance(diagnostics, list)
        
        if diagnostics:  # May not have issues with small dataset
            for diagnostic in diagnostics:
                assert "issue" in diagnostic
                assert "severity" in diagnostic
                assert "category" in diagnostic
                assert "recommendations" in diagnostic
                assert "detected_at" in diagnostic
                
                assert diagnostic["severity"] in ["warning", "critical"]
                assert isinstance(diagnostic["recommendations"], list)


class TestGlobalTelemetryFunctions:
    """Test global telemetry functions."""
    
    def test_get_default_collector(self):
        """Test getting default collector."""
        collector1 = get_default_collector()
        collector2 = get_default_collector()
        
        # Should return same instance
        assert collector1 is collector2
        assert isinstance(collector1, TelemetryCollector)
    
    def test_get_default_monitor(self):
        """Test getting default monitor."""
        monitor1 = get_default_monitor()
        monitor2 = get_default_monitor()
        
        # Should return same instance
        assert monitor1 is monitor2
        assert isinstance(monitor1, PerformanceMonitor)
    
    def test_configure_telemetry(self):
        """Test telemetry configuration."""
        collector, monitor = configure_telemetry(
            max_history=500,
            enable_memory_tracking=False,
            alert_thresholds=AlertThresholds(max_avg_processing_time_ms=100.0)
        )
        
        assert isinstance(collector, TelemetryCollector)
        assert isinstance(monitor, PerformanceMonitor)
        assert monitor._thresholds.max_avg_processing_time_ms == 100.0
    
    def test_setup_default_alerting(self):
        """Test default alerting setup."""
        # This should not raise an exception
        setup_default_alerting()
        
        # Verify that alert callback was added
        monitor = get_default_monitor()
        assert len(monitor._alert_callbacks) > 0


class TestTelemetryIntegration:
    """Test telemetry integration with tokenizer adapters."""
    
    def test_telemetry_with_heuristic_adapter(self):
        """Test telemetry collection with heuristic adapter."""
        collector = TelemetryCollector()
        
        # Create adapter and use track_operation
        adapter = HeuristicTokenizer("test-model", chars_per_token=4.0)
        
        with collector.track_operation(
            adapter_name="heuristic",
            adapter_id="heuristic:test-model",
            model_name="test-model",
            text="This is a test text for telemetry integration"
        ) as tracker:
            result = adapter.count_tokens("This is a test text for telemetry integration")
            tracker.set_result(result)
        
        # Verify telemetry was collected
        assert len(collector._telemetry_history) == 1
        telemetry = collector._telemetry_history[0]
        
        assert telemetry.adapter_name == "heuristic"
        assert telemetry.model_name == "test-model"
        assert telemetry.token_count.count == result.count
        assert telemetry.processing_time_ms > 0
        assert not telemetry.error_occurred
        assert not telemetry.was_fallback
    
    def test_telemetry_with_fallback_scenario(self):
        """Test telemetry collection in fallback scenario."""
        collector = TelemetryCollector()
        
        # Simulate fallback scenario
        with collector.track_operation(
            adapter_name="heuristic",
            adapter_id="heuristic:test-model",
            model_name="test-model",
            text="Fallback test text",
            was_fallback=True,
            fallback_from="tiktoken"
        ) as tracker:
            result = TokenCount(8, "heuristic", "heuristic:fallback", False)
            tracker.set_result(result)
        
        # Verify fallback information was recorded
        assert len(collector._telemetry_history) == 1
        telemetry = collector._telemetry_history[0]
        
        assert telemetry.was_fallback
        assert telemetry.fallback_from == "tiktoken"
        assert telemetry.adapter_name == "heuristic"
    
    @patch('kano_backlog_core.tokenizer_telemetry.get_default_collector')
    def test_telemetry_disabled_gracefully(self, mock_get_collector):
        """Test that telemetry failures don't break tokenization."""
        # Make collector unavailable
        mock_get_collector.side_effect = Exception("Telemetry unavailable")
        
        # This should still work without telemetry
        adapter = HeuristicTokenizer("test-model")
        result = adapter.count_tokens("Test text without telemetry")
        
        assert result.count > 0
        assert result.method == "heuristic"
    
    def test_memory_tracking_availability(self):
        """Test memory tracking with and without psutil."""
        # Test with memory tracking disabled
        collector = TelemetryCollector(enable_memory_tracking=False)
        assert not collector._enable_memory_tracking
        
        # Test memory usage method
        memory_usage = collector._get_memory_usage()
        assert memory_usage is None  # Should be None when disabled
    
    def test_performance_metrics_edge_cases(self):
        """Test performance metrics with edge cases."""
        collector = TelemetryCollector()
        monitor = PerformanceMonitor(collector)
        
        # Test with no data
        metrics = monitor.calculate_metrics(window_minutes=5)
        assert len(metrics) == 0
        
        # Test with single operation
        token_count = TokenCount(10, "heuristic", "heuristic:test", False)
        telemetry = TokenizationTelemetry(
            operation_id="single_test",
            timestamp=datetime.now(),
            adapter_name="heuristic",
            adapter_id="heuristic:test",
            model_name="test-model",
            text_length=50,
            text_preview="Single test",
            token_count=token_count,
            processing_time_ms=15.0
        )
        collector.record_operation(telemetry)
        
        metrics = monitor.calculate_metrics(window_minutes=5)
        assert "heuristic" in metrics
        
        heuristic_metrics = metrics["heuristic"]
        assert heuristic_metrics.sample_count == 1
        assert heuristic_metrics.avg_processing_time_ms == 15.0
        assert heuristic_metrics.p50_processing_time_ms == 15.0
        assert heuristic_metrics.p95_processing_time_ms == 15.0
        assert heuristic_metrics.p99_processing_time_ms == 15.0


if __name__ == "__main__":
    pytest.main([__file__])
