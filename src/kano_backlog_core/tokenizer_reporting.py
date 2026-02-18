"""Telemetry reporting and dashboard capabilities for tokenizer adapters.

This module provides comprehensive reporting and dashboard functionality for
tokenizer telemetry data, including:

- TelemetryReporter: Generate reports and dashboards
- ReportGenerator: Create formatted reports in various formats
- DashboardData: Structured data for dashboard visualization
- HealthChecker: System health assessment
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .tokenizer_telemetry import (
    TelemetryCollector, 
    PerformanceMonitor, 
    TokenizationTelemetry,
    AdapterUsageStats,
    PerformanceMetrics
)


@dataclass
class HealthStatus:
    """Overall health status of tokenizer system."""
    
    status: str  # "healthy", "warning", "critical"
    score: float  # 0.0 to 1.0
    issues: List[str]
    recommendations: List[str]
    last_updated: datetime
    
    # Component health
    adapter_health: Dict[str, str]  # adapter_name -> status
    performance_health: str
    error_health: str
    resource_health: str


@dataclass
class DashboardData:
    """Structured data for dashboard visualization."""
    
    # Summary metrics
    total_operations: int
    successful_operations: int
    failed_operations: int
    total_adapters: int
    active_adapters: int
    
    # Time-based metrics
    operations_last_hour: int
    operations_last_day: int
    avg_processing_time_ms: float
    
    # Adapter breakdown
    adapter_usage: Dict[str, AdapterUsageStats]
    adapter_performance: Dict[str, PerformanceMetrics]
    
    # Error analysis
    error_breakdown: Dict[str, int]  # error_type -> count
    fallback_analysis: Dict[str, int]  # from_adapter -> count
    
    # Performance trends
    hourly_operations: List[Tuple[datetime, int]]
    hourly_avg_time: List[Tuple[datetime, float]]
    hourly_error_rate: List[Tuple[datetime, float]]
    
    # Health status
    health_status: HealthStatus
    
    # Metadata
    generated_at: datetime
    data_window_hours: int


class TelemetryReporter:
    """Generate reports and dashboards from telemetry data."""
    
    def __init__(self, collector: TelemetryCollector, monitor: PerformanceMonitor):
        """Initialize telemetry reporter.
        
        Args:
            collector: TelemetryCollector instance
            monitor: PerformanceMonitor instance
        """
        self._collector = collector
        self._monitor = monitor
    
    def generate_dashboard_data(self, window_hours: int = 24) -> DashboardData:
        """Generate structured data for dashboard visualization."""
        window_start = datetime.now() - timedelta(hours=window_hours)
        recent_telemetry = self._collector.get_telemetry_since(window_start)
        
        # Calculate summary metrics
        total_operations = len(recent_telemetry)
        successful_operations = sum(1 for t in recent_telemetry if not t.error_occurred)
        failed_operations = total_operations - successful_operations
        
        # Get adapter statistics
        adapter_stats = self._collector.get_adapter_stats()
        total_adapters = len(adapter_stats)
        active_adapters = sum(1 for stats in adapter_stats.values() 
                            if stats.last_seen and stats.last_seen >= window_start)
        
        # Calculate time-based metrics
        one_hour_ago = datetime.now() - timedelta(hours=1)
        operations_last_hour = sum(1 for t in recent_telemetry if t.timestamp >= one_hour_ago)
        operations_last_day = total_operations
        
        successful_telemetry = [t for t in recent_telemetry if not t.error_occurred]
        avg_processing_time = (
            statistics.mean(t.processing_time_ms for t in successful_telemetry)
            if successful_telemetry else 0.0
        )
        
        # Get current performance metrics
        adapter_performance = self._monitor.calculate_metrics(window_minutes=60)
        
        # Analyze errors
        error_breakdown = defaultdict(int)
        fallback_analysis = defaultdict(int)
        
        for telemetry in recent_telemetry:
            if telemetry.error_occurred and telemetry.error_type:
                error_breakdown[telemetry.error_type] += 1
            if telemetry.was_fallback and telemetry.fallback_from:
                fallback_analysis[telemetry.fallback_from] += 1
        
        # Generate hourly trends
        hourly_operations = self._calculate_hourly_operations(recent_telemetry, window_hours)
        hourly_avg_time = self._calculate_hourly_avg_time(recent_telemetry, window_hours)
        hourly_error_rate = self._calculate_hourly_error_rate(recent_telemetry, window_hours)
        
        # Assess health status
        health_status = self._assess_health_status(recent_telemetry, adapter_performance)
        
        return DashboardData(
            total_operations=total_operations,
            successful_operations=successful_operations,
            failed_operations=failed_operations,
            total_adapters=total_adapters,
            active_adapters=active_adapters,
            operations_last_hour=operations_last_hour,
            operations_last_day=operations_last_day,
            avg_processing_time_ms=avg_processing_time,
            adapter_usage=dict(adapter_stats),
            adapter_performance=adapter_performance,
            error_breakdown=dict(error_breakdown),
            fallback_analysis=dict(fallback_analysis),
            hourly_operations=hourly_operations,
            hourly_avg_time=hourly_avg_time,
            hourly_error_rate=hourly_error_rate,
            health_status=health_status,
            generated_at=datetime.now(),
            data_window_hours=window_hours
        )
    
    def _calculate_hourly_operations(self, telemetry: List[TokenizationTelemetry], window_hours: int) -> List[Tuple[datetime, int]]:
        """Calculate hourly operation counts."""
        now = datetime.now()
        hourly_counts = []
        
        for i in range(window_hours):
            hour_start = now - timedelta(hours=i+1)
            hour_end = now - timedelta(hours=i)
            
            count = sum(1 for t in telemetry if hour_start <= t.timestamp < hour_end)
            hourly_counts.append((hour_start, count))
        
        return list(reversed(hourly_counts))
    
    def _calculate_hourly_avg_time(self, telemetry: List[TokenizationTelemetry], window_hours: int) -> List[Tuple[datetime, float]]:
        """Calculate hourly average processing times."""
        now = datetime.now()
        hourly_times = []
        
        for i in range(window_hours):
            hour_start = now - timedelta(hours=i+1)
            hour_end = now - timedelta(hours=i)
            
            hour_telemetry = [t for t in telemetry 
                            if hour_start <= t.timestamp < hour_end and not t.error_occurred]
            
            avg_time = (
                statistics.mean(t.processing_time_ms for t in hour_telemetry)
                if hour_telemetry else 0.0
            )
            hourly_times.append((hour_start, avg_time))
        
        return list(reversed(hourly_times))
    
    def _calculate_hourly_error_rate(self, telemetry: List[TokenizationTelemetry], window_hours: int) -> List[Tuple[datetime, float]]:
        """Calculate hourly error rates."""
        now = datetime.now()
        hourly_error_rates = []
        
        for i in range(window_hours):
            hour_start = now - timedelta(hours=i+1)
            hour_end = now - timedelta(hours=i)
            
            hour_telemetry = [t for t in telemetry if hour_start <= t.timestamp < hour_end]
            
            if hour_telemetry:
                error_count = sum(1 for t in hour_telemetry if t.error_occurred)
                error_rate = error_count / len(hour_telemetry)
            else:
                error_rate = 0.0
            
            hourly_error_rates.append((hour_start, error_rate))
        
        return list(reversed(hourly_error_rates))
    
    def _assess_health_status(self, telemetry: List[TokenizationTelemetry], 
                            performance: Dict[str, PerformanceMetrics]) -> HealthStatus:
        """Assess overall system health status."""
        issues = []
        recommendations = []
        adapter_health = {}
        
        # Assess adapter health
        for adapter_name, metrics in performance.items():
            if metrics.error_rate > 0.1:  # 10% error rate
                adapter_health[adapter_name] = "critical"
                issues.append(f"{adapter_name} has high error rate ({metrics.error_rate:.1%})")
                recommendations.append(f"Investigate {adapter_name} adapter errors")
            elif metrics.error_rate > 0.05:  # 5% error rate
                adapter_health[adapter_name] = "warning"
                issues.append(f"{adapter_name} has elevated error rate ({metrics.error_rate:.1%})")
            elif metrics.fallback_rate > 0.3:  # 30% fallback rate
                adapter_health[adapter_name] = "warning"
                issues.append(f"{adapter_name} has high fallback rate ({metrics.fallback_rate:.1%})")
            else:
                adapter_health[adapter_name] = "healthy"
        
        # Assess performance health
        performance_issues = []
        for adapter_name, metrics in performance.items():
            if metrics.avg_processing_time_ms > 1000:  # 1 second
                performance_issues.append(f"{adapter_name} slow processing ({metrics.avg_processing_time_ms:.0f}ms)")
            elif metrics.avg_processing_time_ms > 500:  # 500ms
                performance_issues.append(f"{adapter_name} elevated processing time ({metrics.avg_processing_time_ms:.0f}ms)")
        
        if any("slow" in issue for issue in performance_issues):
            performance_health = "critical"
            issues.extend(performance_issues)
            recommendations.append("Optimize slow adapters or increase resources")
        elif performance_issues:
            performance_health = "warning"
            issues.extend(performance_issues)
        else:
            performance_health = "healthy"
        
        # Assess error health
        recent_errors = [t for t in telemetry if t.error_occurred]
        if len(recent_errors) > len(telemetry) * 0.1:  # 10% error rate
            error_health = "critical"
            issues.append(f"High overall error rate ({len(recent_errors)/len(telemetry):.1%})")
            recommendations.append("Investigate and fix adapter errors")
        elif len(recent_errors) > len(telemetry) * 0.05:  # 5% error rate
            error_health = "warning"
            issues.append(f"Elevated error rate ({len(recent_errors)/len(telemetry):.1%})")
        else:
            error_health = "healthy"
        
        # Assess resource health (simplified)
        memory_usage = [t.memory_used_mb for t in telemetry if t.memory_used_mb is not None]
        if memory_usage:
            avg_memory = statistics.mean(memory_usage)
            max_memory = max(memory_usage)
            
            if max_memory > 1000:  # 1GB
                resource_health = "critical"
                issues.append(f"High memory usage (peak: {max_memory:.0f}MB)")
                recommendations.append("Monitor memory usage and optimize if needed")
            elif avg_memory > 500:  # 500MB
                resource_health = "warning"
                issues.append(f"Elevated memory usage (avg: {avg_memory:.0f}MB)")
            else:
                resource_health = "healthy"
        else:
            resource_health = "unknown"
        
        # Calculate overall health score
        health_scores = {
            "healthy": 1.0,
            "warning": 0.6,
            "critical": 0.2,
            "unknown": 0.8
        }
        
        component_scores = [
            health_scores.get(performance_health, 0.5),
            health_scores.get(error_health, 0.5),
            health_scores.get(resource_health, 0.8)
        ]
        
        # Add adapter scores
        for health in adapter_health.values():
            component_scores.append(health_scores.get(health, 0.5))
        
        overall_score = statistics.mean(component_scores) if component_scores else 0.5
        
        # Determine overall status
        if overall_score >= 0.8:
            overall_status = "healthy"
        elif overall_score >= 0.5:
            overall_status = "warning"
        else:
            overall_status = "critical"
        
        # Add general recommendations
        if not recommendations:
            recommendations.append("System is operating normally")
        
        return HealthStatus(
            status=overall_status,
            score=overall_score,
            issues=issues,
            recommendations=recommendations,
            last_updated=datetime.now(),
            adapter_health=adapter_health,
            performance_health=performance_health,
            error_health=error_health,
            resource_health=resource_health
        )
    
    def generate_text_report(self, window_hours: int = 24) -> str:
        """Generate a human-readable text report."""
        dashboard_data = self.generate_dashboard_data(window_hours)
        
        lines = [
            "=" * 60,
            "TOKENIZER TELEMETRY REPORT",
            "=" * 60,
            f"Generated: {dashboard_data.generated_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Data Window: {window_hours} hours",
            "",
            "SUMMARY",
            "-" * 20,
            f"Total Operations: {dashboard_data.total_operations:,}",
            f"Successful: {dashboard_data.successful_operations:,} ({dashboard_data.successful_operations/max(dashboard_data.total_operations,1):.1%})",
            f"Failed: {dashboard_data.failed_operations:,} ({dashboard_data.failed_operations/max(dashboard_data.total_operations,1):.1%})",
            f"Operations (last hour): {dashboard_data.operations_last_hour:,}",
            f"Average Processing Time: {dashboard_data.avg_processing_time_ms:.1f}ms",
            "",
            "HEALTH STATUS",
            "-" * 20,
            f"Overall Status: {dashboard_data.health_status.status.upper()}",
            f"Health Score: {dashboard_data.health_status.score:.2f}/1.00",
        ]
        
        if dashboard_data.health_status.issues:
            lines.extend([
                "",
                "Issues:",
                *[f"  • {issue}" for issue in dashboard_data.health_status.issues]
            ])
        
        if dashboard_data.health_status.recommendations:
            lines.extend([
                "",
                "Recommendations:",
                *[f"  • {rec}" for rec in dashboard_data.health_status.recommendations]
            ])
        
        lines.extend([
            "",
            "ADAPTER USAGE",
            "-" * 20
        ])
        
        for adapter_name, stats in dashboard_data.adapter_usage.items():
            if stats.total_operations > 0:
                lines.extend([
                    f"{adapter_name.upper()}:",
                    f"  Operations: {stats.total_operations:,} (success: {stats.success_rate:.1%})",
                    f"  Avg Time: {stats.avg_processing_time_ms:.1f}ms",
                    f"  Tokens Processed: {stats.total_tokens_processed:,}",
                    f"  Fallback Rate: {stats.fallback_rate:.1%}",
                    ""
                ])
        
        if dashboard_data.error_breakdown:
            lines.extend([
                "ERROR BREAKDOWN",
                "-" * 20
            ])
            for error_type, count in sorted(dashboard_data.error_breakdown.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"  {error_type}: {count:,}")
            lines.append("")
        
        if dashboard_data.fallback_analysis:
            lines.extend([
                "FALLBACK ANALYSIS",
                "-" * 20
            ])
            for from_adapter, count in sorted(dashboard_data.fallback_analysis.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"  {from_adapter} → fallback: {count:,}")
            lines.append("")
        
        lines.extend([
            "PERFORMANCE METRICS",
            "-" * 20
        ])
        
        for adapter_name, metrics in dashboard_data.adapter_performance.items():
            lines.extend([
                f"{adapter_name.upper()}:",
                f"  Avg Time: {metrics.avg_processing_time_ms:.1f}ms",
                f"  P95 Time: {metrics.p95_processing_time_ms:.1f}ms",
                f"  Throughput: {metrics.operations_per_second:.1f} ops/sec",
                f"  Error Rate: {metrics.error_rate:.1%}",
                f"  Memory: {metrics.avg_memory_mb:.1f}MB avg, {metrics.peak_memory_mb:.1f}MB peak",
                ""
            ])
        
        return "\n".join(lines)
    
    def generate_json_report(self, window_hours: int = 24) -> Dict[str, Any]:
        """Generate a JSON report suitable for API consumption."""
        dashboard_data = self.generate_dashboard_data(window_hours)
        
        # Convert to JSON-serializable format
        report = asdict(dashboard_data)
        
        # Convert datetime objects to ISO strings
        report["generated_at"] = dashboard_data.generated_at.isoformat()
        report["health_status"]["last_updated"] = dashboard_data.health_status.last_updated.isoformat()
        
        # Convert adapter stats datetime fields
        for adapter_name, stats in report["adapter_usage"].items():
            if stats["first_seen"]:
                stats["first_seen"] = dashboard_data.adapter_usage[adapter_name].first_seen.isoformat()
            if stats["last_seen"]:
                stats["last_seen"] = dashboard_data.adapter_usage[adapter_name].last_seen.isoformat()
        
        # Convert performance metrics datetime fields
        for adapter_name, metrics in report["adapter_performance"].items():
            metrics["window_start"] = dashboard_data.adapter_performance[adapter_name].window_start.isoformat()
            metrics["window_end"] = dashboard_data.adapter_performance[adapter_name].window_end.isoformat()
        
        # Convert hourly trend timestamps
        report["hourly_operations"] = [
            [timestamp.isoformat(), count] 
            for timestamp, count in dashboard_data.hourly_operations
        ]
        report["hourly_avg_time"] = [
            [timestamp.isoformat(), avg_time] 
            for timestamp, avg_time in dashboard_data.hourly_avg_time
        ]
        report["hourly_error_rate"] = [
            [timestamp.isoformat(), error_rate] 
            for timestamp, error_rate in dashboard_data.hourly_error_rate
        ]
        
        return report
    
    def export_report(self, output_path: Path, format: str = "json", window_hours: int = 24) -> None:
        """Export report to file."""
        if format.lower() == "json":
            report = self.generate_json_report(window_hours)
            with open(output_path, 'w') as f:
                json.dump(report, f, indent=2)
        elif format.lower() == "txt":
            report = self.generate_text_report(window_hours)
            with open(output_path, 'w') as f:
                f.write(report)
        else:
            raise ValueError(f"Unsupported report format: {format}")
        
        print(f"Report exported to {output_path}")


class HealthChecker:
    """System health assessment and monitoring."""
    
    def __init__(self, collector: TelemetryCollector, monitor: PerformanceMonitor):
        """Initialize health checker.
        
        Args:
            collector: TelemetryCollector instance
            monitor: PerformanceMonitor instance
        """
        self._collector = collector
        self._monitor = monitor
    
    def check_system_health(self, window_minutes: int = 15) -> HealthStatus:
        """Perform comprehensive system health check."""
        reporter = TelemetryReporter(self._collector, self._monitor)
        window_hours = max(1, (window_minutes + 59) // 60)
        dashboard_data = reporter.generate_dashboard_data(window_hours=window_hours)
        return dashboard_data.health_status
    
    def get_health_summary(self) -> Dict[str, Any]:
        """Get a quick health summary."""
        health_status = self.check_system_health()
        
        return {
            "status": health_status.status,
            "score": health_status.score,
            "issue_count": len(health_status.issues),
            "critical_issues": [issue for issue in health_status.issues if "critical" in issue.lower()],
            "last_updated": health_status.last_updated.isoformat(),
            "component_health": {
                "adapters": health_status.adapter_health,
                "performance": health_status.performance_health,
                "errors": health_status.error_health,
                "resources": health_status.resource_health
            }
        }
    
    def diagnose_issues(self) -> List[Dict[str, Any]]:
        """Diagnose specific issues and provide detailed recommendations."""
        health_status = self.check_system_health()
        diagnostics = []
        
        # Analyze each issue
        for issue in health_status.issues:
            diagnostic = {
                "issue": issue,
                "severity": "critical" if "critical" in issue.lower() else "warning",
                "category": self._categorize_issue(issue),
                "recommendations": self._get_issue_recommendations(issue),
                "detected_at": datetime.now().isoformat()
            }
            diagnostics.append(diagnostic)
        
        return diagnostics
    
    def _categorize_issue(self, issue: str) -> str:
        """Categorize an issue for better organization."""
        issue_lower = issue.lower()
        
        if "error rate" in issue_lower:
            return "error_handling"
        elif "processing time" in issue_lower or "slow" in issue_lower:
            return "performance"
        elif "memory" in issue_lower:
            return "resource_usage"
        elif "fallback" in issue_lower:
            return "adapter_reliability"
        else:
            return "general"
    
    def _get_issue_recommendations(self, issue: str) -> List[str]:
        """Get specific recommendations for an issue."""
        issue_lower = issue.lower()
        recommendations = []
        
        if "error rate" in issue_lower:
            recommendations.extend([
                "Check adapter dependencies and installation",
                "Review recent error logs for patterns",
                "Consider increasing retry attempts or timeouts",
                "Verify model names and configurations"
            ])
        
        if "processing time" in issue_lower or "slow" in issue_lower:
            recommendations.extend([
                "Profile adapter performance with different text sizes",
                "Consider using faster adapters for high-volume operations",
                "Check system resources (CPU, memory)",
                "Optimize text preprocessing if applicable"
            ])
        
        if "memory" in issue_lower:
            recommendations.extend([
                "Monitor memory usage patterns",
                "Consider reducing batch sizes",
                "Check for memory leaks in adapters",
                "Increase available system memory if needed"
            ])
        
        if "fallback" in issue_lower:
            recommendations.extend([
                "Install missing dependencies for primary adapters",
                "Check adapter configuration and model availability",
                "Review fallback chain ordering",
                "Consider using more reliable primary adapters"
            ])
        
        if not recommendations:
            recommendations.append("Monitor the situation and check logs for more details")
        
        return recommendations
