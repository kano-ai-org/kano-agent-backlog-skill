"""Performance testing utilities for tokenizer benchmarks.

This module provides utilities for:
- Performance baseline management
- Regression detection and reporting
- Performance metrics collection and analysis
- Benchmark result visualization and reporting
"""

import json
import statistics
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class PerformanceBaseline:
    """Performance baseline for regression detection."""
    timestamp: str
    version: str
    system_info: Dict[str, Any]
    benchmarks: Dict[str, Dict[str, float]]  # operation -> metrics
    
    
class BaselineManager:
    """Manages performance baselines for regression detection."""
    
    def __init__(self, baseline_dir: Path = Path("performance_baselines")):
        self.baseline_dir = baseline_dir
        self.baseline_dir.mkdir(exist_ok=True)
    
    def save_baseline(self, report_data: Dict[str, Any], version: str = "current") -> Path:
        """Save performance baseline from benchmark report."""
        baseline_file = self.baseline_dir / f"baseline_{version}.json"
        
        # Extract key metrics for baseline
        benchmarks = {}
        for result in report_data.get("tokenization_benchmarks", []):
            if result.get("error") is None:
                key = f"{result['operation']}_{result['adapter_type']}_{result['text_size_kb']:.1f}kb"
                benchmarks[key] = {
                    "processing_time_ms": result["processing_time_ms"],
                    "memory_used_mb": result["memory_used_mb"],
                    "throughput_chars_per_sec": result["throughput_chars_per_sec"],
                    "target_met": result["target_met"]
                }
        
        baseline = PerformanceBaseline(
            timestamp=datetime.now().isoformat(),
            version=version,
            system_info=report_data.get("system_info", {}),
            benchmarks=benchmarks
        )
        
        with open(baseline_file, 'w') as f:
            json.dump(asdict(baseline), f, indent=2)
        
        return baseline_file
    
    def load_baseline(self, version: str = "current") -> Optional[PerformanceBaseline]:
        """Load performance baseline."""
        baseline_file = self.baseline_dir / f"baseline_{version}.json"
        
        if not baseline_file.exists():
            return None
        
        try:
            with open(baseline_file, 'r') as f:
                data = json.load(f)
            return PerformanceBaseline(**data)
        except Exception:
            return None


def analyze_performance_trends(reports: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze performance trends across multiple reports."""
    if len(reports) < 2:
        return {"error": "Need at least 2 reports for trend analysis"}
    
    trends = {}
    
    # Sort reports by timestamp
    reports.sort(key=lambda r: r.get("timestamp", ""))
    
    # Analyze trends for each operation/adapter combination
    operation_data = {}
    
    for report in reports:
        for result in report.get("tokenization_benchmarks", []):
            if result.get("error") is None:
                key = f"{result['operation']}_{result['adapter_type']}_{result['text_size_kb']:.1f}kb"
                
                if key not in operation_data:
                    operation_data[key] = {
                        "timestamps": [],
                        "processing_times": [],
                        "memory_usage": [],
                        "throughput": []
                    }
                
                operation_data[key]["timestamps"].append(report.get("timestamp", ""))
                operation_data[key]["processing_times"].append(result["processing_time_ms"])
                operation_data[key]["memory_usage"].append(result["memory_used_mb"])
                operation_data[key]["throughput"].append(result["throughput_chars_per_sec"])
    
    # Calculate trends
    for key, data in operation_data.items():
        if len(data["processing_times"]) >= 2:
            # Calculate trend direction and magnitude
            times = data["processing_times"]
            recent_avg = statistics.mean(times[-3:]) if len(times) >= 3 else times[-1]
            older_avg = statistics.mean(times[:3]) if len(times) >= 3 else times[0]
            
            trend_direction = "improving" if recent_avg < older_avg else "degrading" if recent_avg > older_avg else "stable"
            trend_magnitude = abs(recent_avg - older_avg) / older_avg if older_avg > 0 else 0
            
            trends[key] = {
                "direction": trend_direction,
                "magnitude_percent": trend_magnitude * 100,
                "recent_avg_ms": recent_avg,
                "historical_avg_ms": older_avg,
                "data_points": len(times)
            }
    
    return trends


def generate_performance_summary(report: Dict[str, Any]) -> str:
    """Generate human-readable performance summary."""
    summary_lines = [
        "🚀 Performance Benchmark Summary",
        "=" * 40,
        ""
    ]
    
    # Overall statistics
    total_benchmarks = report["summary"]["total_benchmarks"]
    successful = report["summary"]["successful_benchmarks"]
    failed = report["summary"]["failed_benchmarks"]
    compliance_rate = report["summary"]["target_compliance_rate"]
    
    summary_lines.extend([
        f"📊 Overall Results:",
        f"   Total benchmarks: {total_benchmarks}",
        f"   Successful: {successful}",
        f"   Failed: {failed}",
        f"   Target compliance: {compliance_rate:.1%}",
        ""
    ])
    
    # Performance targets
    targets = report["performance_targets"]
    summary_lines.extend([
        f"🎯 Performance Targets:",
        f"   Tokenization (10KB): < {targets['tokenization_10kb_ms']:.0f}ms",
        f"   Chunking (100KB): < {targets['chunking_100kb_ms']:.0f}ms",
        f"   Memory scaling: < {targets['memory_scaling_factor']:.1f}x",
        ""
    ])
    
    # Adapter comparison
    if report["adapter_comparison"]:
        summary_lines.extend([
            f"⚡ Adapter Performance Comparison:",
        ])
        
        for adapter, metrics in report["adapter_comparison"].items():
            avg_time = metrics["avg_processing_time_ms"]
            compliance = metrics["target_compliance_rate"]
            summary_lines.append(f"   {adapter}: {avg_time:.1f}ms avg, {compliance:.1%} compliance")
        
        summary_lines.append("")
    
    # Regression analysis
    regression = report["regression_analysis"]
    if regression["baseline_available"]:
        status = regression["summary"]["overall_status"]
        regressions = regression["summary"]["total_regressions"]
        improvements = regression["summary"]["total_improvements"]
        
        summary_lines.extend([
            f"🔍 Regression Analysis: {status}",
            f"   Regressions detected: {regressions}",
            f"   Improvements detected: {improvements}",
            ""
        ])
        
        if regressions > 0:
            summary_lines.append("⚠️  Regressions:")
            for reg in regression["regressions_detected"][:3]:  # Show top 3
                summary_lines.append(f"   - {reg['operation']} ({reg['adapter']}): +{reg['regression_percent']:.1f}%")
            if len(regression["regressions_detected"]) > 3:
                summary_lines.append(f"   ... and {len(regression['regressions_detected']) - 3} more")
            summary_lines.append("")
        
        if improvements > 0:
            summary_lines.append("🎉 Improvements:")
            for imp in regression["improvements_detected"][:3]:  # Show top 3
                if "improvement_percent" in imp:
                    summary_lines.append(f"   - {imp['operation']} ({imp['adapter']}): -{imp['improvement_percent']:.1f}%")
            summary_lines.append("")
    
    # System info
    system = report["system_info"]
    summary_lines.extend([
        f"💻 System Information:",
        f"   Platform: {system.get('platform', 'unknown')}",
        f"   Python: {system.get('python_version', 'unknown').split()[0]}",
        f"   Memory: {system.get('memory_available', 'unknown')} GB" if isinstance(system.get('memory_available'), (int, float)) else f"   Memory: {system.get('memory_available', 'unknown')}",
        ""
    ])
    
    return "\n".join(summary_lines)