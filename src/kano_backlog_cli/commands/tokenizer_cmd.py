"""CLI commands for tokenizer configuration management."""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer

from ..util import ensure_core_on_path

app = typer.Typer(help="Manage tokenizer adapter configuration")


@app.command("config")
def show_config(
    config_path: Optional[Path] = typer.Option(
        None, 
        "--config", 
        help="Path to configuration file (TOML or JSON)"
    ),
    format: str = typer.Option(
        "json", 
        "--format", 
        help="Output format (json, toml, yaml)"
    ),
) -> None:
    """Show current tokenizer configuration with environment overrides applied."""
    ensure_core_on_path()
    
    try:
        from kano_backlog_core.tokenizer_config import load_tokenizer_config
        
        # Load configuration
        config = load_tokenizer_config(config_path=config_path)
        
        # Output in requested format
        if format.lower() == "json":
            config_dict = config.to_dict()
            typer.echo(json.dumps(config_dict, indent=2))
        elif format.lower() == "toml":
            try:
                import tomli_w
                config_dict = config.to_dict()
                output = tomli_w.dumps(config_dict)
                typer.echo(output)
            except ImportError:
                typer.echo("Error: tomli_w package required for TOML output. Install with: pip install tomli_w", err=True)
                raise typer.Exit(1)
        elif format.lower() == "yaml":
            try:
                import yaml
                config_dict = config.to_dict()
                output = yaml.dump(config_dict, default_flow_style=False, sort_keys=False)
                typer.echo(output)
            except ImportError:
                typer.echo("Error: PyYAML package required for YAML output. Install with: pip install PyYAML", err=True)
                raise typer.Exit(1)
        else:
            typer.echo(f"Error: Unsupported format '{format}'. Use json, toml, or yaml.", err=True)
            raise typer.Exit(1)
            
    except Exception as e:
        typer.echo(f"Error loading tokenizer configuration: {e}", err=True)
        raise typer.Exit(1)


@app.command("validate")
def validate_config(
    config_path: Optional[Path] = typer.Option(
        None, 
        "--config", 
        help="Path to configuration file (TOML or JSON)"
    ),
) -> None:
    """Validate tokenizer configuration."""
    ensure_core_on_path()
    
    try:
        from kano_backlog_core.tokenizer_config import load_tokenizer_config
        
        # Load and validate configuration
        config = load_tokenizer_config(config_path=config_path)
        
        typer.echo("✓ Configuration is valid")
        typer.echo(f"  Adapter: {config.adapter}")
        typer.echo(f"  Model: {config.model}")
        typer.echo(f"  Max tokens: {config.max_tokens or 'auto'}")
        typer.echo(f"  Fallback chain: {' → '.join(config.fallback_chain)}")
        
    except Exception as e:
        typer.echo(f"✗ Configuration validation failed: {e}", err=True)
        raise typer.Exit(1)


@app.command("test")
def test_adapters(
    config_path: Optional[Path] = typer.Option(
        None, 
        "--config", 
        help="Path to configuration file (TOML or JSON)"
    ),
    text: str = typer.Option(
        "This is a test sentence for tokenizer adapter testing.",
        "--text",
        help="Text to use for testing tokenization"
    ),
) -> None:
    """Test tokenizer adapters with sample text."""
    ensure_core_on_path()
    
    try:
        from kano_backlog_core.tokenizer_config import load_tokenizer_config
        from kano_backlog_core.tokenizer import get_default_registry
        
        # Load configuration
        config = load_tokenizer_config(config_path=config_path)
        registry = get_default_registry()
        
        # Set fallback chain
        if config.fallback_chain:
            registry.set_fallback_chain(config.fallback_chain)
        
        typer.echo(f"Testing tokenizers with text: '{text}'")
        typer.echo(f"Text length: {len(text)} characters")
        typer.echo()
        
        # Test each adapter in fallback chain
        for adapter_name in config.fallback_chain:
            try:
                adapter = registry._create_adapter(
                    adapter_name, 
                    config.model, 
                    config.max_tokens,
                    **config.get_adapter_options(adapter_name)
                )
                
                token_count = adapter.count_tokens(text)
                max_tokens = adapter.max_tokens()
                
                typer.echo(f"✓ {adapter_name.upper()} Adapter:")
                typer.echo(f"  Token count: {token_count.count}")
                typer.echo(f"  Method: {token_count.method}")
                typer.echo(f"  Tokenizer ID: {token_count.tokenizer_id}")
                typer.echo(f"  Is exact: {token_count.is_exact}")
                typer.echo(f"  Max tokens: {max_tokens}")
                typer.echo()
                
            except Exception as e:
                typer.echo(f"✗ {adapter_name.upper()} Adapter failed: {e}")
                typer.echo()
        
        # Test primary adapter resolution
        try:
            adapter = registry.resolve(
                adapter_name=config.adapter,
                model_name=config.model,
                max_tokens=config.max_tokens,
                **config.get_adapter_options(config.adapter)
            )
            
            token_count = adapter.count_tokens(text)
            typer.echo(f"Primary adapter resolution ({config.adapter}):")
            typer.echo(f"  Resolved to: {adapter.adapter_id}")
            typer.echo(f"  Token count: {token_count.count}")
            typer.echo(f"  Is exact: {token_count.is_exact}")
            
        except Exception as e:
            typer.echo(f"✗ Primary adapter resolution failed: {e}")
            
    except Exception as e:
        typer.echo(f"Error testing tokenizer adapters: {e}", err=True)
        raise typer.Exit(1)


@app.command("create-example")
def create_example_config(
    output_path: Path = typer.Option(
        Path("tokenizer_config.toml"),
        "--output",
        help="Output path for example configuration file"
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Overwrite existing file"
    ),
) -> None:
    """Create an example tokenizer configuration file."""
    ensure_core_on_path()
    
    if output_path.exists() and not force:
        typer.echo(f"Error: File already exists: {output_path}. Use --force to overwrite.", err=True)
        raise typer.Exit(1)
    
    try:
        from kano_backlog_core.tokenizer_config import create_example_config
        
        example_content = create_example_config()
        
        # Create output directory if needed
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write example configuration
        output_path.write_text(example_content, encoding="utf-8")
        
        typer.echo(f"✓ Created example tokenizer configuration: {output_path}")
        typer.echo()
        typer.echo("Edit the file to customize your tokenizer settings.")
        typer.echo(
            "Use 'kano-backlog tokenizer validate --config <path>' to validate your changes."
        )
        
    except Exception as e:
        typer.echo(f"Error creating example configuration: {e}", err=True)
        raise typer.Exit(1)


@app.command("migrate")
def migrate_config(
    input_path: Path = typer.Argument(..., help="Input configuration file (JSON or TOML)"),
    output_path: Optional[Path] = typer.Option(
        None,
        "--output",
        help="Output TOML file path (defaults to input path with .toml extension)"
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Overwrite existing output file"
    ),
) -> None:
    """Migrate configuration from old format to new TOML format."""
    ensure_core_on_path()
    
    if not input_path.exists():
        typer.echo(f"Error: Input file not found: {input_path}", err=True)
        raise typer.Exit(1)
    
    # Determine output path
    if output_path is None:
        output_path = input_path.with_suffix(".toml")
    
    if output_path.exists() and not force:
        typer.echo(f"Error: Output file already exists: {output_path}. Use --force to overwrite.", err=True)
        raise typer.Exit(1)
    
    try:
        from kano_backlog_core.tokenizer_config import TokenizerConfigMigrator
        
        # Migrate configuration
        TokenizerConfigMigrator.migrate_file(input_path, output_path)
        
        typer.echo(f"✓ Migrated configuration from {input_path} to {output_path}")
        typer.echo()
        typer.echo("Validate the migrated configuration with:")
        typer.echo(f"  kano-backlog tokenizer validate --config {output_path}")
        
    except Exception as e:
        typer.echo(f"Error migrating configuration: {e}", err=True)
        raise typer.Exit(1)


@app.command("diagnose")
def diagnose_tokenizers(
    config_path: Optional[Path] = typer.Option(
        None, 
        "--config", 
        help="Path to configuration file (TOML or JSON)"
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model",
        help="Specific model to diagnose"
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Show detailed diagnostic information"
    ),
) -> None:
    """Run comprehensive tokenizer diagnostics."""
    ensure_core_on_path()
    
    try:
        from kano_backlog_core.tokenizer_config import load_tokenizer_config
        from kano_backlog_core.tokenizer_diagnostics import run_diagnostics
        
        # Load configuration to get model if not specified
        config = load_tokenizer_config(config_path=config_path)
        target_model = model or config.model
        
        # Run diagnostics
        report = run_diagnostics(model_name=target_model)
        typer.echo(report)
        
        if verbose:
            # Show additional recovery statistics
            from kano_backlog_core.tokenizer import get_default_registry
            registry = get_default_registry()
            
            stats = registry.get_recovery_statistics()
            if stats["total_recovery_attempts"] > 0 or stats["total_degradation_events"] > 0:
                typer.echo("\n" + "="*50)
                typer.echo("📊 Recovery Statistics:")
                typer.echo(f"   Total recovery attempts: {stats['total_recovery_attempts']}")
                typer.echo(f"   Active recovery keys: {stats['active_recovery_keys']}")
                typer.echo(f"   Total degradation events: {stats['total_degradation_events']}")
                typer.echo(f"   Recent degradation events: {stats['recent_degradation_events']}")
                
                if stats["most_problematic_adapter"]:
                    typer.echo(f"   Most problematic adapter: {stats['most_problematic_adapter']}")
                
                if stats["degradation_by_adapter"]:
                    typer.echo("\n   Degradation by adapter:")
                    for adapter, counts in stats["degradation_by_adapter"].items():
                        typer.echo(f"     {adapter}: {counts['total_events']} total, {counts['recent_events']} recent")
        
    except Exception as e:
        typer.echo(f"Error running tokenizer diagnostics: {e}", err=True)
        raise typer.Exit(1)


@app.command("health")
def check_adapter_health(
    adapter: str = typer.Argument(..., help="Adapter name to check (heuristic, tiktoken, huggingface)"),
    model: str = typer.Option(
        "test-model",
        "--model",
        help="Model name to test with"
    ),
) -> None:
    """Check health of a specific tokenizer adapter."""
    ensure_core_on_path()
    
    try:
        from kano_backlog_core.tokenizer_diagnostics import check_adapter_health
        
        health_check = check_adapter_health(adapter, model)
        
        if health_check["healthy"]:
            typer.echo(f"✅ {adapter.upper()} adapter is healthy")
            
            if health_check["test_results"]:
                results = health_check["test_results"]
                typer.echo(f"   Token count: {results['tokens']}")
                typer.echo(f"   Method: {results['method']}")
                typer.echo(f"   Is exact: {results['is_exact']}")
                typer.echo(f"   Tokenizer ID: {results['tokenizer_id']}")
                typer.echo(f"   Max tokens: {results['max_tokens']}")
        else:
            typer.echo(f"❌ {adapter.upper()} adapter is unhealthy")
            typer.echo(f"   Error: {health_check['error']}")
            
            if health_check["recommendations"]:
                typer.echo("\n💡 Recommendations:")
                for rec in health_check["recommendations"]:
                    typer.echo(f"   • {rec}")
        
    except Exception as e:
        typer.echo(f"Error checking adapter health: {e}", err=True)
        raise typer.Exit(1)


@app.command("cache-stats")
def show_cache_stats() -> None:
    """Show token count cache statistics."""
    ensure_core_on_path()
    
    try:
        from kano_backlog_core.tokenizer_cache import get_global_cache_stats
        
        stats = get_global_cache_stats()
        
        if stats is None:
            typer.echo("❌ No global cache initialized")
            return
        
        typer.echo("📊 Token Count Cache Statistics:")
        typer.echo()
        typer.echo(f"  Cache Size: {stats.cache_size} / {stats.max_size}")
        typer.echo(f"  Hit Rate: {stats.hit_rate:.2%}")
        typer.echo(f"  Total Requests: {stats.total_requests}")
        typer.echo(f"  Hits: {stats.hits}")
        typer.echo(f"  Misses: {stats.misses}")
        typer.echo(f"  Evictions: {stats.evictions}")
        typer.echo(f"  Memory Usage: {stats.memory_usage_bytes:,} bytes")
        
        if stats.total_requests > 0:
            efficiency = (stats.hits / stats.total_requests) * 100
            if efficiency >= 80:
                typer.echo(f"  ✅ Cache efficiency: {efficiency:.1f}% (Excellent)")
            elif efficiency >= 60:
                typer.echo(f"  ⚠️  Cache efficiency: {efficiency:.1f}% (Good)")
            else:
                typer.echo(f"  ❌ Cache efficiency: {efficiency:.1f}% (Poor)")
        
    except Exception as e:
        typer.echo(f"Error getting cache statistics: {e}", err=True)
        raise typer.Exit(1)


@app.command("accuracy")
def validate_accuracy(
    adapter: Optional[str] = typer.Option(
        None,
        "--adapter",
        help="Specific adapter to validate (default: all available)"
    ),
    model: str = typer.Option(
        "gpt-3.5-turbo",
        "--model",
        help="Model name for validation"
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        help="Output file for detailed report (JSON format)"
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Show detailed results"
    ),
) -> None:
    """Validate tokenizer accuracy against reference test cases."""
    ensure_core_on_path()
    
    try:
        from kano_backlog_core.tokenizer import get_default_registry
        from kano_backlog_core.tokenizer_accuracy import create_default_validator
        
        registry = get_default_registry()
        validator = create_default_validator()
        
        # Get adapters to test
        if adapter:
            # Test specific adapter
            try:
                test_adapter = registry._create_adapter(adapter, model)
                adapters = [test_adapter]
                typer.echo(f"Testing {adapter} adapter with model {model}")
            except Exception as e:
                typer.echo(f"Error creating {adapter} adapter: {e}", err=True)
                raise typer.Exit(1)
        else:
            # Test all available adapters
            adapters = []
            for adapter_name in ["heuristic", "tiktoken", "huggingface"]:
                try:
                    test_adapter = registry._create_adapter(adapter_name, model)
                    adapters.append(test_adapter)
                except Exception as e:
                    typer.echo(f"⚠️  Skipping {adapter_name} adapter: {e}")
            
            if not adapters:
                typer.echo("❌ No adapters available for testing", err=True)
                raise typer.Exit(1)
            
            typer.echo(f"Testing {len(adapters)} adapters with model {model}")
        
        typer.echo()
        
        # Run validation
        with typer.progressbar(adapters, label="Validating adapters") as progress:
            reports = {}
            for test_adapter in progress:
                report = validator.validate_adapter(test_adapter, model)
                reports[test_adapter.adapter_id] = report
        
        # Display results
        typer.echo("\n📊 Accuracy Validation Results:")
        typer.echo("=" * 50)
        
        for adapter_id, report in reports.items():
            grade = report.get_accuracy_grade()
            grade_emoji = {
                "A+": "🏆", "A": "🥇", "B+": "🥈", "B": "🥉", 
                "C": "⚠️", "D": "❌"
            }.get(grade, "❓")
            
            typer.echo(f"\n{grade_emoji} {adapter_id.upper()} - Grade: {grade}")
            typer.echo(f"   Test cases: {report.test_cases_count}")
            typer.echo(f"   Within 1 token: {report.accuracy_within_1_token:.1%}")
            typer.echo(f"   Within 5%: {report.accuracy_within_5_percent:.1%}")
            typer.echo(f"   Within 10%: {report.accuracy_within_10_percent:.1%}")
            typer.echo(f"   Mean absolute error: {report.mean_absolute_error:.2f} tokens")
            typer.echo(f"   Mean relative error: {report.mean_relative_error:.1%}")
            typer.echo(f"   Avg processing time: {report.mean_processing_time_ms:.2f}ms")
            
            if verbose and report.results:
                typer.echo(f"\n   Detailed results (first 5):")
                for i, result in enumerate(report.results[:5]):
                    text_preview = result.test_case.text[:40] + "..." if len(result.test_case.text) > 40 else result.test_case.text
                    rel_error = f"{result.relative_error:.1%}" if result.relative_error != float('inf') else "∞"
                    typer.echo(f"     {i+1}. '{text_preview}'")
                    typer.echo(f"        Expected: {result.test_case.expected_tokens}, Got: {result.predicted_tokens}, Error: {result.absolute_error} ({rel_error})")
        
        # Save detailed report if requested
        if output:
            validator.save_report(reports, output)
            typer.echo(f"\n💾 Detailed report saved to: {output}")
        
        # Summary
        typer.echo(f"\n📋 Summary:")
        best_adapter = min(reports.items(), key=lambda x: x[1].mean_relative_error)
        typer.echo(f"   Best accuracy: {best_adapter[0]} ({best_adapter[1].mean_relative_error:.1%} mean error)")
        
        fastest_adapter = min(reports.items(), key=lambda x: x[1].mean_processing_time_ms)
        typer.echo(f"   Fastest: {fastest_adapter[0]} ({fastest_adapter[1].mean_processing_time_ms:.2f}ms avg)")
        
    except Exception as e:
        typer.echo(f"Error validating accuracy: {e}", err=True)
        raise typer.Exit(1)


@app.command("cache-clear")
def clear_cache(
    confirm: bool = typer.Option(
        False,
        "--confirm",
        help="Skip confirmation prompt"
    ),
) -> None:
    """Clear the token count cache."""
    ensure_core_on_path()
    
    if not confirm:
        confirmed = typer.confirm("Are you sure you want to clear the token count cache?")
        if not confirmed:
            typer.echo("Cache clearing cancelled.")
            return
    
    try:
        from kano_backlog_core.tokenizer_cache import clear_global_cache
        
        clear_global_cache()
        typer.echo("✅ Token count cache cleared successfully")
        
    except Exception as e:
        typer.echo(f"Error clearing cache: {e}", err=True)
        raise typer.Exit(1)


@app.command("env-vars")
def show_environment_variables() -> None:
    """Show available environment variables for tokenizer configuration."""
    typer.echo("Tokenizer Configuration Environment Variables:")
    typer.echo()
    
    env_vars = [
        ("KANO_TOKENIZER_ADAPTER", "Override adapter selection (auto, heuristic, tiktoken, huggingface)"),
        ("KANO_TOKENIZER_MODEL", "Override model name"),
        ("KANO_TOKENIZER_MAX_TOKENS", "Override max tokens (integer)"),
        ("KANO_TOKENIZER_HEURISTIC_CHARS_PER_TOKEN", "Override chars per token ratio (float)"),
        ("KANO_TOKENIZER_TIKTOKEN_ENCODING", "Override TikToken encoding"),
        ("KANO_TOKENIZER_HUGGINGFACE_USE_FAST", "Override use_fast setting (true/false)"),
        ("KANO_TOKENIZER_HUGGINGFACE_TRUST_REMOTE_CODE", "Override trust_remote_code (true/false)"),
    ]
    
    for env_var, description in env_vars:
        current_value = typer.get_text_stream("stdin").isatty() and sys.stdin.isatty()
        import os
        value = os.environ.get(env_var, "not set")
        typer.echo(f"  {env_var}")
        typer.echo(f"    Description: {description}")
        typer.echo(f"    Current value: {value}")
        typer.echo()
    
    typer.echo("Example usage:")
    typer.echo("  export KANO_TOKENIZER_ADAPTER=heuristic")
    typer.echo("  export KANO_TOKENIZER_HEURISTIC_CHARS_PER_TOKEN=3.5")
    typer.echo("  kano-backlog tokenizer test")


@app.command("dependencies")
def check_dependencies(
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Show detailed dependency information"
    ),
    force_refresh: bool = typer.Option(
        False,
        "--refresh",
        help="Force refresh of dependency cache"
    ),
) -> None:
    """Check status of tokenizer dependencies."""
    ensure_core_on_path()
    
    try:
        from kano_backlog_core.tokenizer_dependencies import get_dependency_manager
        
        manager = get_dependency_manager()
        report = manager.check_all_dependencies(force_refresh=force_refresh)
        
        # Show overall health
        health_emoji = {
            "healthy": "✅",
            "degraded": "⚠️",
            "critical": "❌"
        }
        
        typer.echo(f"{health_emoji.get(report.overall_health, '❓')} Overall Health: {report.overall_health.upper()}")
        typer.echo(f"🐍 Python Version: {report.python_version} {'✅' if report.python_compatible else '❌'}")
        typer.echo()
        
        # Show dependency status
        typer.echo("📦 Dependencies:")
        for name, status in report.dependencies.items():
            status_emoji = "✅" if status.available else "❌"
            typer.echo(f"  {status_emoji} {name}")
            
            if status.available:
                typer.echo(f"      Version: {status.version or 'unknown'}")
                if not status.version_compatible:
                    typer.echo(f"      ⚠️  Version issues: {'; '.join(status.version_issues)}")
                if not status.test_passed and status.test_error:
                    typer.echo(f"      ⚠️  Test failed: {status.test_error}")
            else:
                typer.echo(f"      Error: {status.import_error}")
            
            if verbose and status.installation_instructions:
                typer.echo("      Installation:")
                for instruction in status.installation_instructions[:3]:  # Show first 3 instructions
                    if instruction.strip():
                        typer.echo(f"        {instruction}")
        
        typer.echo()
        
        # Show recommendations
        if report.recommendations:
            typer.echo("💡 Recommendations:")
            for rec in report.recommendations:
                typer.echo(f"  • {rec}")
            typer.echo()
        
        # Show missing dependencies
        missing = report.get_missing_dependencies()
        if missing:
            typer.echo(f"❌ Missing Dependencies: {', '.join(missing)}")
            typer.echo(
                "   Use 'kano-backlog tokenizer install-guide' for installation instructions"
            )
            typer.echo()
        
        # Show incompatible dependencies
        incompatible = report.get_incompatible_dependencies()
        if incompatible:
            typer.echo(f"⚠️  Incompatible Dependencies: {', '.join(incompatible)}")
            typer.echo("   Consider updating these packages")
            typer.echo()
        
    except Exception as e:
        typer.echo(f"Error checking dependencies: {e}", err=True)
        raise typer.Exit(1)


@app.command("install-guide")
def show_installation_guide() -> None:
    """Show installation guide for missing dependencies."""
    ensure_core_on_path()
    
    try:
        from kano_backlog_core.tokenizer_dependencies import get_installation_summary
        
        guide = get_installation_summary()
        typer.echo(guide)
        
    except Exception as e:
        typer.echo(f"Error generating installation guide: {e}", err=True)
        raise typer.Exit(1)


@app.command("adapter-status")
def show_adapter_status(
    adapter: Optional[str] = typer.Option(
        None,
        "--adapter",
        help="Show status for specific adapter only"
    ),
) -> None:
    """Show status of tokenizer adapters including dependency checks."""
    ensure_core_on_path()
    
    try:
        from kano_backlog_core.tokenizer import get_default_registry
        
        registry = get_default_registry()
        
        if adapter:
            # Show status for specific adapter
            validation = registry.validate_adapter_dependencies(adapter)
            
            status_emoji = "✅" if validation["valid"] else "❌"
            typer.echo(f"{status_emoji} {adapter.upper()} Adapter")
            
            if validation["valid"]:
                typer.echo("   Status: Ready")
            else:
                typer.echo(f"   Status: Not ready - {validation['error']}")
                
                if validation["missing_dependencies"]:
                    typer.echo(f"   Missing dependencies: {', '.join(validation['missing_dependencies'])}")
                
                if validation["dependency_issues"]:
                    typer.echo("   Dependency issues:")
                    for issue in validation["dependency_issues"]:
                        typer.echo(f"     • {issue}")
                
                if validation["recommendations"]:
                    typer.echo("   Recommendations:")
                    for rec in validation["recommendations"]:
                        typer.echo(f"     • {rec}")
        else:
            # Show status for all adapters
            status = registry.get_adapter_status_with_dependencies()
            
            typer.echo("🔧 Tokenizer Adapter Status:")
            typer.echo()
            
            for adapter_name, info in status.items():
                status_emoji = "✅" if info["available"] else "❌"
                typer.echo(f"  {status_emoji} {adapter_name.upper()}")
                
                if info["available"]:
                    typer.echo(f"      Status: Available")
                    typer.echo(f"      Dependencies: Ready")
                else:
                    typer.echo(f"      Status: Not available")
                    typer.echo(f"      Error: {info['error']}")
                    
                    if info["missing_dependencies"]:
                        typer.echo(f"      Missing deps: {', '.join(info['missing_dependencies'])}")
                    
                    if info["dependency_issues"]:
                        typer.echo(f"      Issues: {'; '.join(info['dependency_issues'][:2])}")
            
            typer.echo()
            
            # Show dependency report summary
            dep_report = registry.get_dependency_report()
            typer.echo(f"📊 Overall Health: {dep_report['overall_health'].upper()}")
            
            if dep_report["missing_dependencies"]:
                typer.echo(f"❌ Missing: {', '.join(dep_report['missing_dependencies'])}")
            
            if dep_report["incompatible_dependencies"]:
                typer.echo(f"⚠️  Incompatible: {', '.join(dep_report['incompatible_dependencies'])}")
        
    except Exception as e:
        typer.echo(f"Error checking adapter status: {e}", err=True)
        raise typer.Exit(1)


@app.command("status")
def show_comprehensive_status(
    config_path: Optional[Path] = typer.Option(
        None, 
        "--config", 
        help="Path to configuration file (TOML or JSON)"
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Show detailed status information"
    ),
    format: str = typer.Option(
        "markdown", 
        "--format", 
        help="Output format (markdown, json)"
    ),
) -> None:
    """Show comprehensive tokenizer system status."""
    ensure_core_on_path()
    
    try:
        from kano_backlog_core.tokenizer_config import load_tokenizer_config
        from kano_backlog_core.tokenizer import get_default_registry
        from kano_backlog_core.tokenizer_dependencies import get_dependency_manager
        
        # Load configuration
        config = load_tokenizer_config(config_path=config_path)
        registry = get_default_registry()
        dependency_manager = get_dependency_manager()
        
        # Get comprehensive status
        adapter_status = registry.get_adapter_status_with_dependencies()
        dependency_report = dependency_manager.check_all_dependencies()
        recovery_stats = registry.get_recovery_statistics()
        
        if format.lower() == "json":
            status_data = {
                "configuration": config.to_dict(),
                "adapters": adapter_status,
                "dependencies": {
                    name: {
                        "available": status.available,
                        "version": status.version,
                        "version_compatible": status.version_compatible,
                        "test_passed": status.test_passed,
                        "installation_instructions": status.installation_instructions[:3] if status.installation_instructions else []
                    }
                    for name, status in dependency_report.dependencies.items()
                },
                "overall_health": dependency_report.overall_health,
                "python_version": dependency_report.python_version,
                "python_compatible": dependency_report.python_compatible,
                "recovery_statistics": recovery_stats,
                "recommendations": dependency_report.recommendations
            }
            typer.echo(json.dumps(status_data, indent=2))
            return
        
        # Markdown format
        typer.echo("# Tokenizer System Status")
        typer.echo()
        
        # Overall health
        health_emoji = {
            "healthy": "✅",
            "degraded": "⚠️",
            "critical": "❌"
        }
        typer.echo(f"**Overall Health:** {health_emoji.get(dependency_report.overall_health, '❓')} {dependency_report.overall_health.upper()}")
        typer.echo(f"**Python Version:** {dependency_report.python_version} {'✅' if dependency_report.python_compatible else '❌'}")
        typer.echo()
        
        # Configuration
        typer.echo("## Configuration")
        typer.echo(f"- **Adapter:** {config.adapter}")
        typer.echo(f"- **Model:** {config.model}")
        typer.echo(f"- **Max Tokens:** {config.max_tokens or 'auto'}")
        typer.echo(f"- **Fallback Chain:** {' → '.join(config.fallback_chain)}")
        typer.echo()
        
        # Adapter Status
        typer.echo("## Adapter Status")
        for adapter_name, info in adapter_status.items():
            status_emoji = "✅" if info["available"] else "❌"
            typer.echo(f"### {status_emoji} {adapter_name.upper()}")
            
            if info["available"]:
                typer.echo(f"- **Status:** Available")
                typer.echo(f"- **Dependencies:** Ready")
            else:
                typer.echo(f"- **Status:** Not available")
                typer.echo(f"- **Error:** {info['error']}")
                
                if info.get("missing_dependencies"):
                    typer.echo(f"- **Missing Dependencies:** {', '.join(info['missing_dependencies'])}")
                
                if info.get("dependency_issues") and verbose:
                    typer.echo(f"- **Issues:** {'; '.join(info['dependency_issues'][:2])}")
            typer.echo()
        
        # Dependencies
        typer.echo("## Dependencies")
        for name, status in dependency_report.dependencies.items():
            status_emoji = "✅" if status.available else "❌"
            typer.echo(f"### {status_emoji} {name}")
            
            if status.available:
                typer.echo(f"- **Version:** {status.version or 'unknown'}")
                if not status.version_compatible:
                    typer.echo(f"- **⚠️ Version Issues:** {'; '.join(status.version_issues)}")
                if not status.test_passed and status.test_error:
                    typer.echo(f"- **⚠️ Test Failed:** {status.test_error}")
            else:
                typer.echo(f"- **Error:** {status.import_error}")
                if verbose and status.installation_instructions:
                    typer.echo("- **Installation:**")
                    for instruction in status.installation_instructions[:3]:
                        if instruction.strip():
                            typer.echo(f"  - {instruction}")
            typer.echo()
        
        # Recovery Statistics (if verbose)
        if verbose and (recovery_stats["total_recovery_attempts"] > 0 or recovery_stats["total_degradation_events"] > 0):
            typer.echo("## Recovery Statistics")
            typer.echo(f"- **Total Recovery Attempts:** {recovery_stats['total_recovery_attempts']}")
            typer.echo(f"- **Active Recovery Keys:** {recovery_stats['active_recovery_keys']}")
            typer.echo(f"- **Total Degradation Events:** {recovery_stats['total_degradation_events']}")
            typer.echo(f"- **Recent Degradation Events:** {recovery_stats['recent_degradation_events']}")
            
            if recovery_stats["most_problematic_adapter"]:
                typer.echo(f"- **Most Problematic Adapter:** {recovery_stats['most_problematic_adapter']}")
            
            if recovery_stats["degradation_by_adapter"]:
                typer.echo("- **Degradation by Adapter:**")
                for adapter, counts in recovery_stats["degradation_by_adapter"].items():
                    typer.echo(f"  - {adapter}: {counts['total_events']} total, {counts['recent_events']} recent")
            typer.echo()
        
        # Recommendations
        if dependency_report.recommendations:
            typer.echo("## Recommendations")
            for rec in dependency_report.recommendations:
                typer.echo(f"- {rec}")
            typer.echo()
        
        # Quick Actions
        typer.echo("## Quick Actions")
        typer.echo("- **Test Adapters:** `kano-backlog tokenizer test`")
        typer.echo("- **Check Dependencies:** `kano-backlog tokenizer dependencies`")
        typer.echo("- **Validate Config:** `kano-backlog tokenizer validate`")
        typer.echo("- **Installation Guide:** `kano-backlog tokenizer install-guide`")
        
    except Exception as e:
        typer.echo(f"Error getting tokenizer status: {e}", err=True)
        raise typer.Exit(1)


@app.command("benchmark")
def benchmark_adapters(
    text: str = typer.Option(
        "This is a sample text for benchmarking tokenizer adapters. It contains various types of content including numbers (123), punctuation (!@#), and different character sets to test tokenization accuracy and performance across different adapter implementations.",
        "--text",
        help="Text to use for benchmarking"
    ),
    iterations: int = typer.Option(
        10,
        "--iterations",
        help="Number of iterations for performance testing"
    ),
    adapters: Optional[str] = typer.Option(
        None,
        "--adapters",
        help="Comma-separated list of adapters to benchmark (default: all available)"
    ),
    model: str = typer.Option(
        "text-embedding-3-small",
        "--model",
        help="Model name to use for benchmarking"
    ),
    format: str = typer.Option(
        "markdown",
        "--format",
        help="Output format (markdown, json, csv)"
    ),
) -> None:
    """Benchmark tokenizer adapter performance and accuracy."""
    ensure_core_on_path()
    
    try:
        from kano_backlog_core.tokenizer import get_default_registry
        import time
        
        registry = get_default_registry()
        
        # Determine which adapters to benchmark
        if adapters:
            adapter_list = [name.strip() for name in adapters.split(",")]
        else:
            # Use all available adapters
            status = registry.get_adapter_status_with_dependencies()
            adapter_list = [name for name, info in status.items() if info["available"]]
        
        if not adapter_list:
            typer.echo("❌ No adapters available for benchmarking", err=True)
            raise typer.Exit(1)
        
        typer.echo(f"🔬 Benchmarking {len(adapter_list)} adapters with {iterations} iterations...")
        typer.echo(f"📝 Text length: {len(text)} characters")
        typer.echo()
        
        results = []
        
        for adapter_name in adapter_list:
            try:
                # Create adapter
                adapter = registry._create_adapter_with_recovery(adapter_name, model)
                
                # Warmup
                adapter.count_tokens("warmup")
                
                # Benchmark
                times = []
                token_counts = []
                
                for i in range(iterations):
                    start_time = time.perf_counter()
                    result = adapter.count_tokens(text)
                    end_time = time.perf_counter()
                    
                    times.append((end_time - start_time) * 1000)  # Convert to ms
                    token_counts.append(result.count)
                
                # Calculate statistics
                avg_time = sum(times) / len(times)
                min_time = min(times)
                max_time = max(times)
                avg_tokens = sum(token_counts) / len(token_counts)
                
                # Check consistency
                consistent = len(set(token_counts)) == 1
                
                results.append({
                    "adapter": adapter_name,
                    "avg_time_ms": avg_time,
                    "min_time_ms": min_time,
                    "max_time_ms": max_time,
                    "avg_tokens": avg_tokens,
                    "consistent": consistent,
                    "is_exact": result.is_exact,
                    "method": result.method,
                    "tokenizer_id": result.tokenizer_id,
                    "success": True,
                    "error": None
                })
                
            except Exception as e:
                results.append({
                    "adapter": adapter_name,
                    "avg_time_ms": None,
                    "min_time_ms": None,
                    "max_time_ms": None,
                    "avg_tokens": None,
                    "consistent": None,
                    "is_exact": None,
                    "method": None,
                    "tokenizer_id": None,
                    "success": False,
                    "error": str(e)
                })
        
        # Output results
        if format.lower() == "json":
            output = {
                "benchmark_config": {
                    "text_length": len(text),
                    "iterations": iterations,
                    "model": model,
                    "adapters_tested": len(adapter_list)
                },
                "results": results
            }
            typer.echo(json.dumps(output, indent=2))
            
        elif format.lower() == "csv":
            import csv
            import io
            
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=[
                "adapter", "avg_time_ms", "min_time_ms", "max_time_ms", 
                "avg_tokens", "consistent", "is_exact", "method", "success", "error"
            ])
            writer.writeheader()
            writer.writerows(results)
            typer.echo(output.getvalue())
            
        else:  # markdown
            typer.echo("# Tokenizer Adapter Benchmark Results")
            typer.echo()
            
            # Summary table
            typer.echo("## Performance Summary")
            typer.echo("| Adapter | Avg Time (ms) | Tokens | Exact | Consistent | Status |")
            typer.echo("|---------|---------------|--------|-------|------------|--------|")
            
            for result in results:
                if result["success"]:
                    status = "✅"
                    avg_time = f"{result['avg_time_ms']:.2f}"
                    tokens = f"{result['avg_tokens']:.0f}"
                    exact = "✅" if result['is_exact'] else "❌"
                    consistent = "✅" if result['consistent'] else "❌"
                else:
                    status = "❌"
                    avg_time = "N/A"
                    tokens = "N/A"
                    exact = "N/A"
                    consistent = "N/A"
                
                typer.echo(f"| {result['adapter']} | {avg_time} | {tokens} | {exact} | {consistent} | {status} |")
            
            typer.echo()
            
            # Detailed results
            typer.echo("## Detailed Results")
            for result in results:
                typer.echo(f"### {result['adapter'].upper()}")
                
                if result["success"]:
                    typer.echo(f"- **Average Time:** {result['avg_time_ms']:.2f} ms")
                    typer.echo(f"- **Time Range:** {result['min_time_ms']:.2f} - {result['max_time_ms']:.2f} ms")
                    typer.echo(f"- **Token Count:** {result['avg_tokens']:.0f}")
                    typer.echo(f"- **Exact Count:** {'Yes' if result['is_exact'] else 'No'}")
                    typer.echo(f"- **Consistent:** {'Yes' if result['consistent'] else 'No'}")
                    typer.echo(f"- **Method:** {result['method']}")
                    typer.echo(f"- **Tokenizer ID:** {result['tokenizer_id']}")
                else:
                    typer.echo(f"- **Status:** Failed")
                    typer.echo(f"- **Error:** {result['error']}")
                
                typer.echo()
            
            # Performance ranking
            successful_results = [r for r in results if r["success"]]
            if len(successful_results) > 1:
                typer.echo("## Performance Ranking")
                
                # Sort by average time
                by_speed = sorted(successful_results, key=lambda x: x["avg_time_ms"])
                typer.echo("**By Speed (fastest first):**")
                for i, result in enumerate(by_speed, 1):
                    typer.echo(f"{i}. {result['adapter']} ({result['avg_time_ms']:.2f} ms)")
                
                typer.echo()
                
                # Sort by accuracy (exact first, then by consistency)
                by_accuracy = sorted(successful_results, key=lambda x: (not x["is_exact"], not x["consistent"]))
                typer.echo("**By Accuracy (most accurate first):**")
                for i, result in enumerate(by_accuracy, 1):
                    accuracy_note = []
                    if result["is_exact"]:
                        accuracy_note.append("exact")
                    if result["consistent"]:
                        accuracy_note.append("consistent")
                    note = f" ({', '.join(accuracy_note)})" if accuracy_note else ""
                    typer.echo(f"{i}. {result['adapter']}{note}")
        
    except Exception as e:
        typer.echo(f"Error running benchmark: {e}", err=True)
        raise typer.Exit(1)


@app.command("compare")
def compare_adapters(
    text: str = typer.Argument(..., help="Text to tokenize and compare"),
    adapters: Optional[str] = typer.Option(
        None,
        "--adapters",
        help="Comma-separated list of adapters to compare (default: all available)"
    ),
    model: str = typer.Option(
        "text-embedding-3-small",
        "--model",
        help="Model name to use for comparison"
    ),
    show_tokens: bool = typer.Option(
        False,
        "--show-tokens",
        help="Show actual token breakdown (for supported adapters)"
    ),
) -> None:
    """Compare tokenization results across different adapters."""
    ensure_core_on_path()
    
    try:
        from kano_backlog_core.tokenizer import get_default_registry
        
        registry = get_default_registry()
        
        # Determine which adapters to compare
        if adapters:
            adapter_list = [name.strip() for name in adapters.split(",")]
        else:
            # Use all available adapters
            status = registry.get_adapter_status_with_dependencies()
            adapter_list = [name for name, info in status.items() if info["available"]]
        
        if not adapter_list:
            typer.echo("❌ No adapters available for comparison", err=True)
            raise typer.Exit(1)
        
        typer.echo(f"# Tokenizer Comparison")
        typer.echo(f"**Text:** {text}")
        typer.echo(f"**Length:** {len(text)} characters")
        typer.echo(f"**Model:** {model}")
        typer.echo()
        
        results = []
        
        for adapter_name in adapter_list:
            try:
                adapter = registry._create_adapter_with_recovery(adapter_name, model)
                result = adapter.count_tokens(text)
                
                results.append({
                    "adapter": adapter_name,
                    "count": result.count,
                    "method": result.method,
                    "tokenizer_id": result.tokenizer_id,
                    "is_exact": result.is_exact,
                    "max_tokens": result.model_max_tokens,
                    "success": True,
                    "error": None
                })
                
            except Exception as e:
                results.append({
                    "adapter": adapter_name,
                    "count": None,
                    "method": None,
                    "tokenizer_id": None,
                    "is_exact": None,
                    "max_tokens": None,
                    "success": False,
                    "error": str(e)
                })
        
        # Display results
        typer.echo("## Results")
        typer.echo("| Adapter | Token Count | Exact | Method | Max Tokens | Status |")
        typer.echo("|---------|-------------|-------|--------|------------|--------|")
        
        for result in results:
            if result["success"]:
                status = "✅"
                count = str(result["count"])
                exact = "✅" if result["is_exact"] else "❌"
                method = result["method"]
                max_tokens = str(result["max_tokens"]) if result["max_tokens"] else "N/A"
            else:
                status = "❌"
                count = "N/A"
                exact = "N/A"
                method = "N/A"
                max_tokens = "N/A"
            
            typer.echo(f"| {result['adapter']} | {count} | {exact} | {method} | {max_tokens} | {status} |")
        
        typer.echo()
        
        # Analysis
        successful_results = [r for r in results if r["success"]]
        if len(successful_results) > 1:
            counts = [r["count"] for r in successful_results]
            min_count = min(counts)
            max_count = max(counts)
            
            typer.echo("## Analysis")
            typer.echo(f"- **Token Count Range:** {min_count} - {max_count}")
            typer.echo(f"- **Variance:** {max_count - min_count} tokens ({((max_count - min_count) / min_count * 100):.1f}%)")
            
            # Find exact adapters
            exact_adapters = [r["adapter"] for r in successful_results if r["is_exact"]]
            if exact_adapters:
                typer.echo(f"- **Exact Adapters:** {', '.join(exact_adapters)}")
            
            # Recommendations
            typer.echo()
            typer.echo("## Recommendations")
            
            if len(exact_adapters) > 0:
                typer.echo(f"- For maximum accuracy, use: **{exact_adapters[0]}**")
            
            # Find fastest (heuristic is typically fastest)
            if "heuristic" in [r["adapter"] for r in successful_results]:
                typer.echo("- For maximum speed, use: **heuristic**")
            
            # Model-specific recommendations
            if "gpt" in model.lower() or "text-embedding" in model.lower():
                if "tiktoken" in [r["adapter"] for r in successful_results]:
                    typer.echo("- For OpenAI models, **tiktoken** is recommended")
            
            if any(hf_indicator in model.lower() for hf_indicator in ["bert", "sentence-transformers"]):
                if "huggingface" in [r["adapter"] for r in successful_results]:
                    typer.echo("- For HuggingFace models, **huggingface** is recommended")
        
        # Show errors
        failed_results = [r for r in results if not r["success"]]
        if failed_results:
            typer.echo()
            typer.echo("## Errors")
            for result in failed_results:
                typer.echo(f"- **{result['adapter']}:** {result['error']}")
        
        # Show token breakdown if requested and supported
        if show_tokens:
            typer.echo()
            typer.echo("## Token Breakdown")
            typer.echo("*(Token breakdown only available for some adapters)*")
            
            for result in successful_results:
                if result["adapter"] == "tiktoken":
                    try:
                        # Try to show tiktoken breakdown
                        adapter = registry._create_adapter_with_recovery("tiktoken", model)
                        if hasattr(adapter, '_encoding'):
                            tokens = adapter._encoding.encode(text)
                            decoded_tokens = [adapter._encoding.decode([token]) for token in tokens]
                            
                            typer.echo(f"### TikToken Breakdown ({len(tokens)} tokens)")
                            for i, (token_id, token_text) in enumerate(zip(tokens, decoded_tokens)):
                                # Show first 20 tokens to avoid overwhelming output
                                if i >= 20:
                                    typer.echo(f"... and {len(tokens) - 20} more tokens")
                                    break
                                typer.echo(f"  {i+1:2d}. {token_id:5d} → '{token_text}'")
                            typer.echo()
                    except Exception as e:
                        typer.echo(f"Could not show tiktoken breakdown: {e}")
        
    except Exception as e:
        typer.echo(f"Error comparing adapters: {e}", err=True)
        raise typer.Exit(1)


@app.command("install")
def install_dependency(
    dependency: str = typer.Argument(..., help="Dependency name to install (tiktoken, transformers, etc.)"),
    method: str = typer.Option(
        "pip",
        "--method",
        help="Installation method (pip or conda)"
    ),
    upgrade: bool = typer.Option(
        False,
        "--upgrade",
        help="Upgrade if already installed"
    ),
) -> None:
    """Install a tokenizer dependency programmatically."""
    ensure_core_on_path()
    
    try:
        from kano_backlog_core.tokenizer_dependencies import get_dependency_manager
        
        manager = get_dependency_manager()
        
        typer.echo(f"Installing {dependency} using {method}...")
        
        success, message = manager.install_dependency(dependency, method, upgrade)
        
        if success:
            typer.echo(f"✅ {message}")
            
            # Verify installation
            typer.echo("Verifying installation...")
            status = manager.check_dependency(dependency, force_refresh=True)
            
            if status.available:
                typer.echo(f"✅ {dependency} is now available (version: {status.version or 'unknown'})")
                if not status.version_compatible:
                    typer.echo("⚠️  Note: Version compatibility issues detected")
                    for issue in status.version_issues:
                        typer.echo(f"   • {issue}")
            else:
                typer.echo(f"❌ {dependency} installation verification failed: {status.import_error}")
        else:
            typer.echo(f"❌ Installation failed: {message}")
            raise typer.Exit(1)
        
    except Exception as e:
        typer.echo(f"Error installing dependency: {e}", err=True)
        raise typer.Exit(1)


@app.command("recommend")
def recommend_adapter(
    model: str = typer.Argument(..., help="Model name to get adapter recommendation for"),
    requirements: Optional[str] = typer.Option(
        None,
        "--requirements",
        help="Requirements as key=value pairs (e.g., 'accuracy=high,speed=medium')"
    ),
) -> None:
    """Get adapter recommendation for a specific model and requirements."""
    ensure_core_on_path()
    
    try:
        from kano_backlog_core.tokenizer import get_default_registry
        
        registry = get_default_registry()
        
        # Parse requirements
        req_dict = {}
        if requirements:
            for pair in requirements.split(","):
                if "=" in pair:
                    key, value = pair.split("=", 1)
                    req_dict[key.strip()] = value.strip()
        
        # Get recommendation
        recommended = registry.suggest_best_adapter(model, req_dict)
        
        typer.echo(f"# Adapter Recommendation for '{model}'")
        typer.echo()
        typer.echo(f"**Recommended Adapter:** {recommended}")
        typer.echo()
        
        # Show reasoning
        typer.echo("## Reasoning")
        
        # Check adapter availability
        status = registry.get_adapter_status_with_dependencies()
        available_adapters = [name for name, info in status.items() if info["available"]]
        
        if recommended not in available_adapters:
            typer.echo(f"⚠️  **Note:** Recommended adapter '{recommended}' is not currently available.")
            typer.echo("   Check dependencies with: `kano-backlog tokenizer dependencies`")
            typer.echo()
        
        # Model-specific reasoning
        if any(openai_model in model.lower() for openai_model in 
               ["gpt", "text-embedding", "davinci", "curie", "babbage", "ada"]):
            typer.echo("- Model appears to be an OpenAI model")
            if recommended == "tiktoken":
                typer.echo("- TikToken provides exact tokenization for OpenAI models")
            else:
                typer.echo(f"- TikToken not available, using fallback: {recommended}")
        
        elif any(hf_indicator in model.lower() for hf_indicator in 
                 ["bert", "roberta", "distil", "sentence-transformers", "t5", "bart"]):
            typer.echo("- Model appears to be a HuggingFace model")
            if recommended == "huggingface":
                typer.echo("- HuggingFace adapter provides exact tokenization for transformer models")
            else:
                typer.echo(f"- HuggingFace adapter not available, using fallback: {recommended}")
        
        else:
            typer.echo("- Model type not specifically recognized")
            typer.echo(f"- Using best available adapter: {recommended}")
        
        # Requirements-based reasoning
        if req_dict:
            typer.echo()
            typer.echo("## Requirements Analysis")
            for key, value in req_dict.items():
                typer.echo(f"- **{key}:** {value}")
                
                if key == "accuracy" and value == "high":
                    if recommended in ["tiktoken", "huggingface"]:
                        typer.echo("  ✅ Exact tokenization adapter selected for high accuracy")
                    else:
                        typer.echo("  ⚠️  Heuristic adapter may not meet high accuracy requirements")
                
                elif key == "speed" and value == "high":
                    if recommended == "heuristic":
                        typer.echo("  ✅ Heuristic adapter selected for high speed")
                    else:
                        typer.echo("  ℹ️  Exact adapters may be slower but more accurate")
        
        # Show alternatives
        typer.echo()
        typer.echo("## Available Alternatives")
        for adapter_name, info in status.items():
            if adapter_name != recommended:
                status_emoji = "✅" if info["available"] else "❌"
                typer.echo(f"- {status_emoji} **{adapter_name}**")
                
                if info["available"]:
                    # Show adapter characteristics
                    if adapter_name == "heuristic":
                        typer.echo("  - Fast approximation, good for development")
                    elif adapter_name == "tiktoken":
                        typer.echo("  - Exact tokenization for OpenAI models")
                    elif adapter_name == "huggingface":
                        typer.echo("  - Exact tokenization for HuggingFace models")
                else:
                    typer.echo(f"  - Not available: {info['error']}")
        
        # Usage example
        typer.echo()
        typer.echo("## Usage Example")
        typer.echo(f"```bash")
        typer.echo(f"# Use recommended adapter in embedding command")
        typer.echo(
            f"kano-backlog embedding build --tokenizer-adapter {recommended} --tokenizer-model {model}"
        )
        typer.echo()
        typer.echo(f"# Test the adapter")
        typer.echo(
            f"kano-backlog tokenizer test --text 'Sample text' --adapter {recommended} --model {model}"
        )
        typer.echo(f"```")
        
    except Exception as e:
        typer.echo(f"Error getting adapter recommendation: {e}", err=True)
        raise typer.Exit(1)


@app.command("list-models")
def list_supported_models(
    adapter: Optional[str] = typer.Option(
        None,
        "--adapter",
        help="Show models for specific adapter only"
    ),
    format: str = typer.Option(
        "markdown",
        "--format",
        help="Output format (markdown, json, csv)"
    ),
) -> None:
    """List supported models and their token limits."""
    ensure_core_on_path()
    
    try:
        from kano_backlog_core.tokenizer import MODEL_MAX_TOKENS, MODEL_TO_ENCODING
        
        # Categorize models
        openai_models = {}
        huggingface_models = {}
        other_models = {}
        
        for model_name, max_tokens in MODEL_MAX_TOKENS.items():
            if any(indicator in model_name.lower() for indicator in 
                   ["gpt", "text-embedding", "davinci", "curie", "babbage", "ada"]):
                openai_models[model_name] = max_tokens
            elif "/" in model_name or any(indicator in model_name.lower() for indicator in 
                                        ["bert", "roberta", "distil", "t5", "bart"]):
                huggingface_models[model_name] = max_tokens
            else:
                other_models[model_name] = max_tokens
        
        # Filter by adapter if specified
        if adapter:
            if adapter.lower() == "tiktoken":
                models_to_show = {"OpenAI Models": openai_models}
            elif adapter.lower() == "huggingface":
                models_to_show = {"HuggingFace Models": huggingface_models}
            elif adapter.lower() == "heuristic":
                models_to_show = {
                    "OpenAI Models": openai_models,
                    "HuggingFace Models": huggingface_models,
                    "Other Models": other_models
                }
            else:
                typer.echo(f"Unknown adapter: {adapter}", err=True)
                raise typer.Exit(1)
        else:
            models_to_show = {
                "OpenAI Models": openai_models,
                "HuggingFace Models": huggingface_models,
                "Other Models": other_models
            }
        
        if format.lower() == "json":
            output = {}
            for category, models in models_to_show.items():
                output[category.lower().replace(" ", "_")] = models
            typer.echo(json.dumps(output, indent=2))
            
        elif format.lower() == "csv":
            import csv
            import io
            
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["Category", "Model", "Max Tokens", "Encoding"])
            
            for category, models in models_to_show.items():
                for model_name, max_tokens in models.items():
                    encoding = MODEL_TO_ENCODING.get(model_name, "N/A")
                    writer.writerow([category, model_name, max_tokens, encoding])
            
            typer.echo(output.getvalue())
            
        else:  # markdown
            typer.echo("# Supported Models")
            typer.echo()
            
            total_models = sum(len(models) for models in models_to_show.values())
            typer.echo(f"**Total Models:** {total_models}")
            if adapter:
                typer.echo(f"**Filtered by Adapter:** {adapter}")
            typer.echo()
            
            for category, models in models_to_show.items():
                if not models:
                    continue
                    
                typer.echo(f"## {category} ({len(models)} models)")
                typer.echo()
                typer.echo("| Model | Max Tokens | Encoding | Recommended Adapter |")
                typer.echo("|-------|------------|----------|-------------------|")
                
                for model_name, max_tokens in sorted(models.items()):
                    encoding = MODEL_TO_ENCODING.get(model_name, "N/A")
                    
                    # Determine recommended adapter
                    if category == "OpenAI Models":
                        recommended = "tiktoken"
                    elif category == "HuggingFace Models":
                        recommended = "huggingface"
                    else:
                        recommended = "heuristic"
                    
                    typer.echo(f"| {model_name} | {max_tokens} | {encoding} | {recommended} |")
                
                typer.echo()
            
            # Usage notes
            typer.echo("## Usage Notes")
            typer.echo("- **Max Tokens:** Maximum context length for the model")
            typer.echo("- **Encoding:** TikToken encoding used (for OpenAI models)")
            typer.echo("- **Recommended Adapter:** Best adapter for accurate tokenization")
            typer.echo()
            typer.echo("### Examples")
            typer.echo("```bash")
            typer.echo("# Use with embedding command")
            typer.echo("kano-backlog embedding build --tokenizer-model text-embedding-3-small")
            typer.echo()
            typer.echo("# Test tokenization")
            typer.echo("kano-backlog tokenizer test --model bert-base-uncased --adapter huggingface")
            typer.echo("```")
        
    except Exception as e:
        typer.echo(f"Error listing models: {e}", err=True)
        raise typer.Exit(1)


# Telemetry and Monitoring Commands
@app.command("telemetry")
def telemetry_status(
    format: str = typer.Option(
        "markdown",
        "--format",
        help="Output format (markdown, json)"
    ),
    window_hours: int = typer.Option(
        24,
        "--window",
        help="Time window in hours for telemetry data"
    ),
) -> None:
    """Show tokenizer telemetry status and recent activity."""
    ensure_core_on_path()
    
    try:
        from kano_backlog_core.tokenizer_telemetry import get_default_collector, get_default_monitor
        from kano_backlog_core.tokenizer_reporting import TelemetryReporter
        
        collector = get_default_collector()
        monitor = get_default_monitor()
        reporter = TelemetryReporter(collector, monitor)
        
        if format.lower() == "json":
            report = reporter.generate_json_report(window_hours)
            typer.echo(json.dumps(report, indent=2))
        else:
            report = reporter.generate_text_report(window_hours)
            typer.echo(report)
        
    except Exception as e:
        typer.echo(f"Error getting telemetry status: {e}", err=True)
        raise typer.Exit(1)


@app.command("telemetry-export")
def export_telemetry(
    output_path: Path = typer.Argument(..., help="Output file path for telemetry export"),
    format: str = typer.Option(
        "json",
        "--format",
        help="Export format (json)"
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Overwrite existing file"
    ),
) -> None:
    """Export telemetry data to file."""
    ensure_core_on_path()
    
    if output_path.exists() and not force:
        typer.echo(f"Error: Output file already exists: {output_path}. Use --force to overwrite.", err=True)
        raise typer.Exit(1)
    
    try:
        from kano_backlog_core.tokenizer_telemetry import get_default_collector
        
        collector = get_default_collector()
        collector.export_telemetry(output_path, format)
        
        typer.echo(f"✅ Telemetry data exported to {output_path}")
        
        # Show summary
        recent_telemetry = collector.get_recent_telemetry(limit=1000)
        adapter_stats = collector.get_adapter_stats()
        
        typer.echo(f"📊 Export Summary:")
        typer.echo(f"   Total operations: {len(recent_telemetry):,}")
        typer.echo(f"   Adapters tracked: {len(adapter_stats)}")
        typer.echo(f"   File size: {output_path.stat().st_size / 1024:.1f} KB")
        
    except Exception as e:
        typer.echo(f"Error exporting telemetry: {e}", err=True)
        raise typer.Exit(1)


@app.command("telemetry-clear")
def clear_telemetry(
    confirm: bool = typer.Option(
        False,
        "--confirm",
        help="Confirm clearing telemetry data"
    ),
) -> None:
    """Clear telemetry history."""
    ensure_core_on_path()
    
    if not confirm:
        typer.echo("⚠️  This will clear all telemetry history.")
        typer.echo("Use --confirm to proceed.")
        raise typer.Exit(1)
    
    try:
        from kano_backlog_core.tokenizer_telemetry import get_default_collector
        
        collector = get_default_collector()
        
        # Get stats before clearing
        recent_telemetry = collector.get_recent_telemetry(limit=10000)
        adapter_stats = collector.get_adapter_stats()
        
        collector.clear_history()
        
        typer.echo("✅ Telemetry history cleared")
        typer.echo(f"📊 Cleared Data:")
        typer.echo(f"   Operations: {len(recent_telemetry):,}")
        typer.echo(f"   Adapters: {len(adapter_stats)}")
        
    except Exception as e:
        typer.echo(f"Error clearing telemetry: {e}", err=True)
        raise typer.Exit(1)


@app.command("monitor")
def monitor_performance(
    window_minutes: int = typer.Option(
        5,
        "--window",
        help="Time window in minutes for performance monitoring"
    ),
    check_alerts: bool = typer.Option(
        True,
        "--alerts",
        help="Check for alert conditions"
    ),
    format: str = typer.Option(
        "markdown",
        "--format",
        help="Output format (markdown, json)"
    ),
) -> None:
    """Monitor tokenizer performance and check for alerts."""
    ensure_core_on_path()
    
    try:
        from kano_backlog_core.tokenizer_telemetry import get_default_monitor
        
        monitor = get_default_monitor()
        
        # Calculate performance metrics
        metrics = monitor.calculate_metrics(window_minutes)
        
        if format.lower() == "json":
            output = {}
            for adapter_name, adapter_metrics in metrics.items():
                output[adapter_name] = {
                    "avg_processing_time_ms": adapter_metrics.avg_processing_time_ms,
                    "p95_processing_time_ms": adapter_metrics.p95_processing_time_ms,
                    "operations_per_second": adapter_metrics.operations_per_second,
                    "tokens_per_second": adapter_metrics.tokens_per_second,
                    "error_rate": adapter_metrics.error_rate,
                    "fallback_rate": adapter_metrics.fallback_rate,
                    "avg_memory_mb": adapter_metrics.avg_memory_mb,
                    "sample_count": adapter_metrics.sample_count,
                    "window_start": adapter_metrics.window_start.isoformat(),
                    "window_end": adapter_metrics.window_end.isoformat()
                }
            
            if check_alerts:
                alerts = monitor.check_alerts(window_minutes)
                output["alerts"] = [
                    {
                        "alert_type": alert["alert_type"],
                        "adapter_name": alert["adapter_name"],
                        "message": alert["message"],
                        "timestamp": alert["timestamp"].isoformat(),
                        "data": alert["data"]
                    }
                    for alert in alerts
                ]
            
            typer.echo(json.dumps(output, indent=2))
            return
        
        # Markdown format
        typer.echo(f"# Tokenizer Performance Monitor")
        typer.echo(f"**Time Window:** {window_minutes} minutes")
        typer.echo(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        typer.echo()
        
        if not metrics:
            typer.echo("📊 No performance data available for the specified time window.")
            typer.echo("   Try increasing the time window or perform some tokenization operations.")
            return
        
        # Performance metrics table
        typer.echo("## Performance Metrics")
        typer.echo("| Adapter | Avg Time (ms) | P95 Time (ms) | Ops/sec | Error Rate | Fallback Rate | Samples |")
        typer.echo("|---------|---------------|---------------|---------|------------|---------------|---------|")
        
        for adapter_name, adapter_metrics in metrics.items():
            typer.echo(
                f"| {adapter_name} | {adapter_metrics.avg_processing_time_ms:.1f} | "
                f"{adapter_metrics.p95_processing_time_ms:.1f} | "
                f"{adapter_metrics.operations_per_second:.1f} | "
                f"{adapter_metrics.error_rate:.1%} | "
                f"{adapter_metrics.fallback_rate:.1%} | "
                f"{adapter_metrics.sample_count} |"
            )
        
        typer.echo()
        
        # Detailed metrics
        typer.echo("## Detailed Metrics")
        for adapter_name, adapter_metrics in metrics.items():
            typer.echo(f"### {adapter_name.upper()}")
            typer.echo(f"- **Processing Time:** {adapter_metrics.avg_processing_time_ms:.1f}ms avg, {adapter_metrics.p95_processing_time_ms:.1f}ms P95")
            typer.echo(f"- **Throughput:** {adapter_metrics.operations_per_second:.1f} ops/sec, {adapter_metrics.tokens_per_second:.0f} tokens/sec")
            typer.echo(f"- **Reliability:** {adapter_metrics.error_rate:.1%} error rate, {adapter_metrics.fallback_rate:.1%} fallback rate")
            
            if adapter_metrics.avg_memory_mb > 0:
                typer.echo(f"- **Memory:** {adapter_metrics.avg_memory_mb:.1f}MB avg, {adapter_metrics.peak_memory_mb:.1f}MB peak")
            
            typer.echo(f"- **Sample Count:** {adapter_metrics.sample_count}")
            typer.echo()
        
        # Check alerts
        if check_alerts:
            alerts = monitor.check_alerts(window_minutes)
            
            if alerts:
                typer.echo("## 🚨 Active Alerts")
                for alert in alerts:
                    typer.echo(f"### {alert['alert_type'].upper()} - {alert['adapter_name']}")
                    typer.echo(f"**Message:** {alert['message']}")
                    typer.echo(f"**Time:** {alert['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
                    
                    if alert.get('data'):
                        data = alert['data']
                        if 'current_value' in data and 'threshold' in data:
                            typer.echo(f"**Current:** {data['current_value']:.2f}, **Threshold:** {data['threshold']:.2f}")
                    typer.echo()
            else:
                typer.echo("## ✅ No Active Alerts")
                typer.echo("All performance metrics are within acceptable thresholds.")
        
    except Exception as e:
        typer.echo(f"Error monitoring performance: {e}", err=True)
        raise typer.Exit(1)


@app.command("health-check")
def health_check(
    window_minutes: int = typer.Option(
        15,
        "--window",
        help="Time window in minutes for health assessment"
    ),
    format: str = typer.Option(
        "markdown",
        "--format",
        help="Output format (markdown, json)"
    ),
) -> None:
    """Perform comprehensive health check of tokenizer system."""
    ensure_core_on_path()
    
    try:
        from kano_backlog_core.tokenizer_telemetry import get_default_collector, get_default_monitor
        from kano_backlog_core.tokenizer_reporting import HealthChecker
        
        collector = get_default_collector()
        monitor = get_default_monitor()
        health_checker = HealthChecker(collector, monitor)
        
        if format.lower() == "json":
            health_summary = health_checker.get_health_summary()
            typer.echo(json.dumps(health_summary, indent=2))
            return
        
        # Perform health check
        health_status = health_checker.check_system_health(window_minutes)
        
        # Display results
        status_emoji = {
            "healthy": "✅",
            "warning": "⚠️",
            "critical": "❌"
        }
        
        typer.echo("# Tokenizer System Health Check")
        typer.echo(f"**Overall Status:** {status_emoji.get(health_status.status, '❓')} {health_status.status.upper()}")
        typer.echo(f"**Health Score:** {health_status.score:.2f}/1.00")
        typer.echo(f"**Last Updated:** {health_status.last_updated.strftime('%Y-%m-%d %H:%M:%S')}")
        typer.echo()
        
        # Component health
        typer.echo("## Component Health")
        components = [
            ("Performance", health_status.performance_health),
            ("Error Handling", health_status.error_health),
            ("Resource Usage", health_status.resource_health)
        ]
        
        for component, status in components:
            emoji = status_emoji.get(status, "❓")
            typer.echo(f"- **{component}:** {emoji} {status}")
        
        typer.echo()
        
        # Adapter health
        if health_status.adapter_health:
            typer.echo("## Adapter Health")
            for adapter_name, status in health_status.adapter_health.items():
                emoji = status_emoji.get(status, "❓")
                typer.echo(f"- **{adapter_name}:** {emoji} {status}")
            typer.echo()
        
        # Issues
        if health_status.issues:
            typer.echo("## 🔍 Issues Detected")
            for issue in health_status.issues:
                typer.echo(f"- {issue}")
            typer.echo()
        
        # Recommendations
        if health_status.recommendations:
            typer.echo("## 💡 Recommendations")
            for rec in health_status.recommendations:
                typer.echo(f"- {rec}")
            typer.echo()
        
        # Detailed diagnostics
        diagnostics = health_checker.diagnose_issues()
        if diagnostics:
            typer.echo("## 🔧 Detailed Diagnostics")
            
            for diagnostic in diagnostics:
                severity_emoji = "🚨" if diagnostic["severity"] == "critical" else "⚠️"
                typer.echo(f"### {severity_emoji} {diagnostic['issue']}")
                typer.echo(f"**Category:** {diagnostic['category']}")
                typer.echo(f"**Severity:** {diagnostic['severity']}")
                
                if diagnostic["recommendations"]:
                    typer.echo("**Recommendations:**")
                    for rec in diagnostic["recommendations"]:
                        typer.echo(f"  - {rec}")
                typer.echo()
        
        # Quick actions
        typer.echo("## Quick Actions")
        if health_status.status == "critical":
            typer.echo("- **Immediate:** Check error logs and fix critical issues")
            typer.echo("- **Monitor:** `kano-backlog tokenizer monitor --window 5`")
            typer.echo("- **Dependencies:** `kano-backlog tokenizer dependencies`")
        elif health_status.status == "warning":
            typer.echo("- **Monitor:** `kano-backlog tokenizer monitor --window 10`")
            typer.echo("- **Performance:** `kano-backlog tokenizer benchmark`")
            typer.echo("- **Status:** `kano-backlog tokenizer status --verbose`")
        else:
            typer.echo("- **Monitor:** `kano-backlog tokenizer telemetry`")
            typer.echo("- **Benchmark:** `kano-backlog tokenizer benchmark`")
            typer.echo("- **Status:** `kano-backlog tokenizer status`")
        
    except Exception as e:
        typer.echo(f"Error performing health check: {e}", err=True)
        raise typer.Exit(1)


@app.command("alerts")
def check_alerts(
    window_minutes: int = typer.Option(
        5,
        "--window",
        help="Time window in minutes for alert checking"
    ),
    format: str = typer.Option(
        "markdown",
        "--format",
        help="Output format (markdown, json)"
    ),
) -> None:
    """Check for active alerts and alert conditions."""
    ensure_core_on_path()
    
    try:
        from kano_backlog_core.tokenizer_telemetry import get_default_monitor
        
        monitor = get_default_monitor()
        alerts = monitor.check_alerts(window_minutes)
        
        if format.lower() == "json":
            output = [
                {
                    "alert_type": alert["alert_type"],
                    "adapter_name": alert["adapter_name"],
                    "message": alert["message"],
                    "timestamp": alert["timestamp"].isoformat(),
                    "data": alert["data"]
                }
                for alert in alerts
            ]
            typer.echo(json.dumps(output, indent=2))
            return
        
        # Markdown format
        typer.echo("# Tokenizer Alerts")
        typer.echo(f"**Time Window:** {window_minutes} minutes")
        typer.echo(f"**Checked:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        typer.echo()
        
        if not alerts:
            typer.echo("✅ **No Active Alerts**")
            typer.echo("All tokenizer adapters are operating within normal parameters.")
            return
        
        typer.echo(f"🚨 **{len(alerts)} Active Alert(s)**")
        typer.echo()
        
        # Group alerts by type
        alert_groups = {}
        for alert in alerts:
            alert_type = alert["alert_type"]
            if alert_type not in alert_groups:
                alert_groups[alert_type] = []
            alert_groups[alert_type].append(alert)
        
        for alert_type, type_alerts in alert_groups.items():
            typer.echo(f"## {alert_type.replace('_', ' ').title()}")
            
            for alert in type_alerts:
                typer.echo(f"### {alert['adapter_name']}")
                typer.echo(f"**Message:** {alert['message']}")
                typer.echo(f"**Time:** {alert['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
                
                if alert.get('data'):
                    data = alert['data']
                    if 'current_value' in data and 'threshold' in data:
                        typer.echo(f"**Current Value:** {data['current_value']:.2f}")
                        typer.echo(f"**Threshold:** {data['threshold']:.2f}")
                typer.echo()
        
        # Recommendations
        typer.echo("## Recommended Actions")
        
        critical_alerts = [a for a in alerts if "critical" in a["alert_type"] or "high" in a["alert_type"]]
        if critical_alerts:
            typer.echo("### Immediate Actions")
            typer.echo("- Investigate critical performance or error issues")
            typer.echo("- Check system resources (CPU, memory)")
            typer.echo("- Review recent error logs")
            typer.echo()
        
        typer.echo("### General Actions")
        typer.echo("- Monitor system performance: `kano-backlog tokenizer monitor`")
        typer.echo("- Check system health: `kano-backlog tokenizer health-check`")
        typer.echo("- Review telemetry data: `kano-backlog tokenizer telemetry`")
        typer.echo("- Benchmark adapters: `kano-backlog tokenizer benchmark`")
        
    except Exception as e:
        typer.echo(f"Error checking alerts: {e}", err=True)
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
