"""CLI commands for performance benchmarking and analysis.

This module provides CLI commands for:
- Running performance benchmarks
- Generating performance reports
- Managing performance baselines
- Analyzing performance trends and regressions
"""

import click
import json
import sys
from pathlib import Path
from typing import Optional

from kano_backlog_core.config import get_config


@click.group()
def performance():
    """Performance benchmarking and analysis commands."""
    pass


@performance.command()
@click.option(
    "--output", "-o",
    type=click.Path(path_type=Path),
    default="performance_report.json",
    help="Output file for performance report"
)
@click.option(
    "--baseline", "-b",
    type=click.Path(exists=True, path_type=Path),
    help="Baseline file for regression detection"
)
@click.option(
    "--save-baseline",
    type=str,
    help="Save results as baseline with given version name"
)
@click.option(
    "--format", "output_format",
    type=click.Choice(["json", "summary", "both"]),
    default="both",
    help="Output format"
)
@click.option(
    "--quick",
    is_flag=True,
    help="Run quick benchmarks (subset of tests)"
)
def benchmark(
    output: Path,
    baseline: Optional[Path],
    save_baseline: Optional[str],
    output_format: str,
    quick: bool
):
    """Run comprehensive performance benchmarks.
    
    This command runs the full performance benchmark suite including:
    - Tokenization performance across different text sizes
    - Chunking pipeline performance end-to-end  
    - Memory usage profiling for large documents
    - Comparison benchmarks between adapter types
    
    Performance targets are validated and regression detection is performed
    if a baseline file is provided.
    """
    try:
        # Import here to avoid import issues if dependencies are missing
        from tests.test_tokenizer_performance_benchmarks import PerformanceBenchmarkSuite
        from tests.performance_utils import BaselineManager, generate_performance_summary
        
        click.echo("🚀 Starting performance benchmark suite...")
        
        # Initialize benchmark suite
        suite = PerformanceBenchmarkSuite()
        
        # Modify test documents for quick mode
        if quick:
            click.echo("⚡ Quick mode: Running subset of benchmarks")
            original_docs = suite.test_documents
            suite.test_documents = {
                "1kb_english": original_docs["1kb_english"],
                "10kb_english": original_docs["10kb_english"],
                "10kb_mixed": original_docs["10kb_mixed"]
            }
        
        # Generate performance report
        report = suite.generate_performance_report(output if output_format in ["json", "both"] else None)
        
        # Save baseline if requested
        if save_baseline:
            baseline_manager = BaselineManager()
            baseline_file = baseline_manager.save_baseline(report.__dict__, save_baseline)
            click.echo(f"💾 Baseline saved: {baseline_file}")
        
        # Output results
        if output_format in ["summary", "both"]:
            summary = generate_performance_summary(report.__dict__)
            click.echo("\n" + summary)
        
        if output_format == "json":
            click.echo(f"📄 Full report saved to: {output}")
        elif output_format == "both":
            click.echo(f"📄 Full report saved to: {output}")
        
        # Check for failures and set exit code
        failed_benchmarks = report.summary["failed_benchmarks"]
        regression_status = report.regression_analysis["summary"]["overall_status"]
        
        if failed_benchmarks > 0:
            click.echo(f"\n❌ {failed_benchmarks} benchmarks failed", err=True)
            sys.exit(1)
        elif regression_status == "FAIL":
            click.echo(f"\n⚠️  Performance regressions detected", err=True)
            sys.exit(1)
        else:
            click.echo(f"\n✅ All benchmarks passed")
            
    except ImportError as e:
        click.echo(f"❌ Missing dependencies for performance benchmarks: {e}", err=True)
        click.echo("Install with: pip install psutil", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"❌ Benchmark execution failed: {e}", err=True)
        sys.exit(1)


@performance.command()
@click.argument("report_files", nargs=-1, type=click.Path(exists=True, path_type=Path))
@click.option(
    "--output", "-o",
    type=click.Path(path_type=Path),
    default="performance_trends.json",
    help="Output file for trend analysis"
)
def analyze_trends(report_files: tuple[Path, ...], output: Path):
    """Analyze performance trends across multiple benchmark reports.
    
    Provide multiple performance report JSON files to analyze trends over time.
    This helps identify performance improvements or degradations across versions.
    """
    if len(report_files) < 2:
        click.echo("❌ Need at least 2 report files for trend analysis", err=True)
        sys.exit(1)
    
    try:
        from tests.performance_utils import analyze_performance_trends
        
        click.echo(f"📈 Analyzing trends across {len(report_files)} reports...")
        
        # Load all reports
        reports = []
        for report_file in report_files:
            with open(report_file, 'r') as f:
                reports.append(json.load(f))
        
        # Analyze trends
        trends = analyze_performance_trends(reports)
        
        if "error" in trends:
            click.echo(f"❌ {trends['error']}", err=True)
            sys.exit(1)
        
        # Save detailed analysis
        with open(output, 'w') as f:
            json.dump(trends, f, indent=2)
        
        # Display summary
        click.echo(f"\n📊 Performance Trends Summary:")
        click.echo(f"   Operations analyzed: {len(trends)}")
        
        improving = sum(1 for t in trends.values() if t["direction"] == "improving")
        degrading = sum(1 for t in trends.values() if t["direction"] == "degrading")
        stable = sum(1 for t in trends.values() if t["direction"] == "stable")
        
        click.echo(f"   Improving: {improving}")
        click.echo(f"   Degrading: {degrading}")
        click.echo(f"   Stable: {stable}")
        
        # Show top improvements and degradations
        if improving > 0:
            click.echo(f"\n🎉 Top Improvements:")
            improvements = [(k, v) for k, v in trends.items() if v["direction"] == "improving"]
            improvements.sort(key=lambda x: x[1]["magnitude_percent"], reverse=True)
            for op, trend in improvements[:3]:
                click.echo(f"   {op}: -{trend['magnitude_percent']:.1f}%")
        
        if degrading > 0:
            click.echo(f"\n⚠️  Top Degradations:")
            degradations = [(k, v) for k, v in trends.items() if v["direction"] == "degrading"]
            degradations.sort(key=lambda x: x[1]["magnitude_percent"], reverse=True)
            for op, trend in degradations[:3]:
                click.echo(f"   {op}: +{trend['magnitude_percent']:.1f}%")
        
        click.echo(f"\n📄 Detailed analysis saved to: {output}")
        
    except Exception as e:
        click.echo(f"❌ Trend analysis failed: {e}", err=True)
        sys.exit(1)


@performance.command()
@click.option(
    "--version", "-v",
    default="current",
    help="Baseline version name"
)
@click.option(
    "--list", "list_baselines",
    is_flag=True,
    help="List available baselines"
)
def baseline(version: str, list_baselines: bool):
    """Manage performance baselines for regression detection.
    
    Baselines are used to detect performance regressions by comparing
    current benchmark results with historical performance data.
    """
    try:
        from tests.performance_utils import BaselineManager
        
        manager = BaselineManager()
        
        if list_baselines:
            baseline_files = list(manager.baseline_dir.glob("baseline_*.json"))
            if baseline_files:
                click.echo("📋 Available baselines:")
                for baseline_file in sorted(baseline_files):
                    version_name = baseline_file.stem.replace("baseline_", "")
                    try:
                        baseline = manager.load_baseline(version_name)
                        if baseline:
                            click.echo(f"   {version_name}: {baseline.timestamp} ({len(baseline.benchmarks)} benchmarks)")
                        else:
                            click.echo(f"   {version_name}: (corrupted)")
                    except Exception:
                        click.echo(f"   {version_name}: (error loading)")
            else:
                click.echo("📋 No baselines found")
            return
        
        # Load and display baseline
        baseline = manager.load_baseline(version)
        if baseline:
            click.echo(f"📊 Baseline '{version}':")
            click.echo(f"   Timestamp: {baseline.timestamp}")
            click.echo(f"   Version: {baseline.version}")
            click.echo(f"   Benchmarks: {len(baseline.benchmarks)}")
            click.echo(f"   System: {baseline.system_info.get('platform', 'unknown')}")
            
            # Show sample benchmarks
            if baseline.benchmarks:
                click.echo(f"\n📈 Sample benchmarks:")
                for i, (key, metrics) in enumerate(list(baseline.benchmarks.items())[:5]):
                    click.echo(f"   {key}: {metrics['processing_time_ms']:.1f}ms")
                if len(baseline.benchmarks) > 5:
                    click.echo(f"   ... and {len(baseline.benchmarks) - 5} more")
        else:
            click.echo(f"❌ Baseline '{version}' not found", err=True)
            sys.exit(1)
            
    except Exception as e:
        click.echo(f"❌ Baseline management failed: {e}", err=True)
        sys.exit(1)


@performance.command()
@click.option(
    "--adapter", "-a",
    multiple=True,
    help="Test specific adapter types (can be used multiple times)"
)
@click.option(
    "--size", "-s",
    type=click.Choice(["1kb", "10kb", "100kb", "all"]),
    default="all",
    help="Test specific document sizes"
)
@click.option(
    "--operation", "-op",
    type=click.Choice(["tokenization", "chunking", "memory", "all"]),
    default="all",
    help="Test specific operations"
)
def validate_targets(adapter: tuple[str, ...], size: str, operation: str):
    """Validate that performance targets are being met.
    
    This command runs targeted performance tests to validate that
    the system meets its performance targets:
    - Tokenization: < 100ms for 10KB documents
    - Chunking: < 500ms for 100KB documents
    - Memory usage: Linear scaling with document size
    """
    try:
        from tests.test_tokenizer_performance_benchmarks import (
            TestTokenizationPerformance,
            TestChunkingPerformance,
            TestMemoryUsage
        )
        
        click.echo("🎯 Validating performance targets...")
        
        # Run targeted tests based on options
        test_results = []
        
        if operation in ["tokenization", "all"]:
            click.echo("  📊 Testing tokenization performance...")
            test_instance = TestTokenizationPerformance()
            test_instance.setup_method()
            
            try:
                test_instance.test_tokenization_performance_targets()
                test_results.append(("Tokenization targets", "PASS"))
            except AssertionError as e:
                test_results.append(("Tokenization targets", f"FAIL: {e}"))
            except Exception as e:
                test_results.append(("Tokenization targets", f"ERROR: {e}"))
            
            try:
                test_instance.test_tokenization_scaling()
                test_results.append(("Tokenization scaling", "PASS"))
            except AssertionError as e:
                test_results.append(("Tokenization scaling", f"FAIL: {e}"))
            except Exception as e:
                test_results.append(("Tokenization scaling", f"ERROR: {e}"))
        
        if operation in ["chunking", "all"]:
            click.echo("  🔧 Testing chunking performance...")
            test_instance = TestChunkingPerformance()
            test_instance.setup_method()
            
            try:
                test_instance.test_chunking_performance_targets()
                test_results.append(("Chunking targets", "PASS"))
            except AssertionError as e:
                test_results.append(("Chunking targets", f"FAIL: {e}"))
            except Exception as e:
                test_results.append(("Chunking targets", f"ERROR: {e}"))
        
        if operation in ["memory", "all"]:
            click.echo("  💾 Testing memory usage...")
            test_instance = TestMemoryUsage()
            test_instance.setup_method()
            
            try:
                test_instance.test_memory_scaling_linearity()
                test_results.append(("Memory scaling", "PASS"))
            except AssertionError as e:
                test_results.append(("Memory scaling", f"FAIL: {e}"))
            except Exception as e:
                test_results.append(("Memory scaling", f"ERROR: {e}"))
            
            try:
                test_instance.test_memory_usage_reasonable()
                test_results.append(("Memory usage", "PASS"))
            except AssertionError as e:
                test_results.append(("Memory usage", f"FAIL: {e}"))
            except Exception as e:
                test_results.append(("Memory usage", f"ERROR: {e}"))
        
        # Display results
        click.echo(f"\n📋 Performance Target Validation Results:")
        passed = 0
        failed = 0
        
        for test_name, result in test_results:
            if result == "PASS":
                click.echo(f"   ✅ {test_name}: {result}")
                passed += 1
            else:
                click.echo(f"   ❌ {test_name}: {result}")
                failed += 1
        
        click.echo(f"\n📊 Summary: {passed} passed, {failed} failed")
        
        if failed > 0:
            sys.exit(1)
        else:
            click.echo("🎉 All performance targets validated successfully!")
            
    except ImportError as e:
        click.echo(f"❌ Missing dependencies: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"❌ Target validation failed: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    performance()