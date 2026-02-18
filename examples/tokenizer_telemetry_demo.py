#!/usr/bin/env python3
"""Demonstration of tokenizer telemetry and monitoring capabilities.

This script shows how to use the comprehensive telemetry system for tokenizer
adapters, including performance monitoring, error tracking, and reporting.

Usage:
    python examples/tokenizer_telemetry_demo.py
"""

import time
from datetime import datetime
from pathlib import Path

# Add the src directory to the path so we can import the modules
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from kano_backlog_core.tokenizer import TokenizerRegistry
from kano_backlog_core.tokenizer_telemetry import (
    configure_telemetry,
    setup_default_alerting,
    AlertThresholds,
    get_default_collector,
    get_default_monitor
)
from kano_backlog_core.tokenizer_reporting import TelemetryReporter, HealthChecker


def main():
    """Run the telemetry demonstration."""
    print("🔬 Tokenizer Telemetry System Demonstration")
    print("=" * 50)
    
    # Configure telemetry with custom settings
    print("\n1. Configuring Telemetry System...")
    
    custom_thresholds = AlertThresholds(
        max_avg_processing_time_ms=100.0,  # 100ms threshold
        max_error_rate=0.05,  # 5% error rate
        max_fallback_rate=0.20,  # 20% fallback rate
        min_sample_count=5  # Need 5 samples before alerting
    )
    
    collector, monitor = configure_telemetry(
        max_history=1000,
        enable_memory_tracking=True,
        alert_thresholds=custom_thresholds
    )
    
    # Setup default alerting (logs to console)
    setup_default_alerting()
    
    print("✅ Telemetry system configured")
    print(f"   - Max history: 1000 operations")
    print(f"   - Memory tracking: enabled")
    print(f"   - Alert thresholds: {custom_thresholds.max_avg_processing_time_ms}ms avg time")
    
    # Create tokenizer registry
    print("\n2. Setting up Tokenizer Registry...")
    registry = TokenizerRegistry()
    
    # Test different adapters
    adapters_to_test = []
    
    # Always test heuristic (should always work)
    adapters_to_test.append(("heuristic", "test-model"))
    
    # Try to test other adapters if available
    try:
        registry._create_adapter("tiktoken", "gpt-4")
        adapters_to_test.append(("tiktoken", "gpt-4"))
        print("✅ TikToken adapter available")
    except Exception as e:
        print(f"⚠️  TikToken adapter not available: {e}")
    
    try:
        registry._create_adapter("huggingface", "bert-base-uncased")
        adapters_to_test.append(("huggingface", "bert-base-uncased"))
        print("✅ HuggingFace adapter available")
    except Exception as e:
        print(f"⚠️  HuggingFace adapter not available: {e}")
    
    print(f"📊 Testing {len(adapters_to_test)} adapter(s)")
    
    # Generate test data
    print("\n3. Generating Test Operations...")
    
    test_texts = [
        "Short test.",
        "This is a medium-length test text for tokenizer telemetry demonstration.",
        "This is a much longer test text that contains multiple sentences and should generate more tokens. It's designed to test the telemetry system's ability to track processing time, token counts, and other metrics across different text lengths and complexities.",
        "Another test with different characteristics: numbers (123), symbols (!@#$%), and various punctuation marks.",
        "Final test text with mixed content including technical terms like 'tokenization', 'telemetry', and 'monitoring'."
    ]
    
    operation_count = 0
    
    for adapter_name, model_name in adapters_to_test:
        print(f"\n   Testing {adapter_name} adapter with {model_name}...")
        
        try:
            adapter = registry.resolve(
                adapter_name=adapter_name,
                model_name=model_name
            )
            
            for i, text in enumerate(test_texts):
                print(f"     Operation {operation_count + 1}: {len(text)} chars", end="")
                
                start_time = time.perf_counter()
                result = adapter.count_tokens(text)
                end_time = time.perf_counter()
                
                print(f" → {result.count} tokens ({(end_time - start_time) * 1000:.1f}ms)")
                operation_count += 1
                
                # Small delay to spread out operations
                time.sleep(0.01)
                
        except Exception as e:
            print(f"     ❌ Failed: {e}")
    
    print(f"\n✅ Completed {operation_count} tokenization operations")
    
    # Demonstrate telemetry analysis
    print("\n4. Analyzing Telemetry Data...")
    
    # Get recent telemetry
    recent_telemetry = collector.get_recent_telemetry(limit=100)
    print(f"📊 Collected {len(recent_telemetry)} telemetry records")
    
    # Show adapter usage statistics
    adapter_stats = collector.get_adapter_stats()
    print(f"📈 Adapter Usage Statistics:")
    
    for adapter_name, stats in adapter_stats.items():
        print(f"   {adapter_name.upper()}:")
        print(f"     Total operations: {stats.total_operations}")
        print(f"     Success rate: {stats.success_rate:.1%}")
        print(f"     Avg processing time: {stats.avg_processing_time_ms:.1f}ms")
        print(f"     Avg tokens per operation: {stats.avg_tokens_per_operation:.1f}")
        print(f"     Fallback rate: {stats.fallback_rate:.1%}")
    
    # Performance monitoring
    print("\n5. Performance Monitoring...")
    
    # Calculate performance metrics
    metrics = monitor.calculate_metrics(window_minutes=5)
    
    if metrics:
        print("📊 Performance Metrics (last 5 minutes):")
        for adapter_name, adapter_metrics in metrics.items():
            print(f"   {adapter_name.upper()}:")
            print(f"     Avg time: {adapter_metrics.avg_processing_time_ms:.1f}ms")
            print(f"     P95 time: {adapter_metrics.p95_processing_time_ms:.1f}ms")
            print(f"     Throughput: {adapter_metrics.operations_per_second:.1f} ops/sec")
            print(f"     Error rate: {adapter_metrics.error_rate:.1%}")
            print(f"     Sample count: {adapter_metrics.sample_count}")
    else:
        print("⚠️  No performance metrics available (operations too recent)")
    
    # Check for alerts
    print("\n6. Checking for Alerts...")
    alerts = monitor.check_alerts(window_minutes=5)
    
    if alerts:
        print(f"🚨 {len(alerts)} alert(s) detected:")
        for alert in alerts:
            print(f"   {alert['alert_type'].upper()}: {alert['adapter_name']}")
            print(f"     {alert['message']}")
    else:
        print("✅ No alerts detected - all systems operating normally")
    
    # Health assessment
    print("\n7. System Health Assessment...")
    
    health_checker = HealthChecker(collector, monitor)
    health_status = health_checker.check_system_health(window_minutes=5)
    
    status_emoji = {
        "healthy": "✅",
        "warning": "⚠️",
        "critical": "❌"
    }
    
    print(f"🏥 Overall Health: {status_emoji.get(health_status.status, '❓')} {health_status.status.upper()}")
    print(f"📊 Health Score: {health_status.score:.2f}/1.00")
    
    if health_status.issues:
        print("🔍 Issues detected:")
        for issue in health_status.issues:
            print(f"   • {issue}")
    
    if health_status.recommendations:
        print("💡 Recommendations:")
        for rec in health_status.recommendations:
            print(f"   • {rec}")
    
    # Generate comprehensive report
    print("\n8. Generating Telemetry Report...")
    
    reporter = TelemetryReporter(collector, monitor)
    
    # Generate text report
    print("\n" + "=" * 60)
    print("COMPREHENSIVE TELEMETRY REPORT")
    print("=" * 60)
    
    text_report = reporter.generate_text_report(window_hours=1)
    print(text_report)
    
    # Demonstrate export functionality
    print("\n9. Export Capabilities...")
    
    # Export telemetry data
    export_dir = Path("telemetry_exports")
    export_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Export raw telemetry data
    telemetry_export_path = export_dir / f"telemetry_data_{timestamp}.json"
    collector.export_telemetry(telemetry_export_path, format="json")
    print(f"📁 Raw telemetry data exported to: {telemetry_export_path}")
    
    # Export formatted report
    report_export_path = export_dir / f"telemetry_report_{timestamp}.json"
    reporter.export_report(report_export_path, format="json", window_hours=1)
    print(f"📊 Telemetry report exported to: {report_export_path}")
    
    # Show file sizes
    telemetry_size = telemetry_export_path.stat().st_size / 1024
    report_size = report_export_path.stat().st_size / 1024
    print(f"   Telemetry data: {telemetry_size:.1f} KB")
    print(f"   Report data: {report_size:.1f} KB")
    
    # Demonstrate error scenario
    print("\n10. Error Handling Demonstration...")
    
    # Create a failing operation to show error telemetry
    class FailingAdapter:
        def __init__(self, model_name):
            self.model_name = model_name
            self.adapter_id = "failing"
        
        def count_tokens(self, text):
            raise RuntimeError("Simulated adapter failure for demonstration")
        
        def max_tokens(self):
            return 1024
    
    # Use telemetry collector directly to track the failing operation
    with collector.track_operation(
        adapter_name="failing",
        adapter_id="failing:demo",
        model_name="demo-model",
        text="This operation will fail intentionally"
    ) as tracker:
        try:
            # Simulate failure
            raise RuntimeError("Simulated adapter failure for demonstration")
        except Exception as e:
            tracker.set_error(e)
            print(f"❌ Simulated error: {e}")
    
    # Show error telemetry
    error_telemetry = [t for t in collector.get_recent_telemetry(limit=10) if t.error_occurred]
    if error_telemetry:
        print(f"🔍 Error telemetry collected: {len(error_telemetry)} error(s)")
        latest_error = error_telemetry[-1]
        print(f"   Error type: {latest_error.error_type}")
        print(f"   Error message: {latest_error.error_message}")
        print(f"   Processing time: {latest_error.processing_time_ms:.1f}ms")
    
    print("\n" + "=" * 50)
    print("🎉 Telemetry Demonstration Complete!")
    print("=" * 50)
    
    print(f"\nSummary:")
    print(f"• Processed {operation_count} successful operations")
    print(f"• Collected {len(collector.get_recent_telemetry(limit=1000))} telemetry records")
    print(f"• Tested {len(adapters_to_test)} adapter type(s)")
    print(f"• Generated comprehensive reports and exports")
    print(f"• Demonstrated error handling and monitoring")
    
    print(f"\nNext steps:")
    print(f"• Review exported files in: {export_dir}")
    print(f"• Integrate telemetry into your tokenizer workflows")
    print(f"• Set up monitoring dashboards using the JSON reports")
    print(f"• Configure custom alert thresholds for your use case")


if __name__ == "__main__":
    main()