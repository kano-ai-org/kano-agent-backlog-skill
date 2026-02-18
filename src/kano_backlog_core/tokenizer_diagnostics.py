"""Diagnostic utilities for tokenizer adapters.

This module provides diagnostic tools to help users troubleshoot tokenizer
issues, check adapter availability, and get recommendations for their use case.
"""

import logging
import sys
from typing import Any, Dict, List, Optional, Tuple

from .tokenizer import TokenizerRegistry, get_default_registry
from .tokenizer_errors import (
    TokenizerError,
    create_user_friendly_error_message,
)

logger = logging.getLogger(__name__)


class TokenizerDiagnostics:
    """Diagnostic utilities for tokenizer adapters."""
    
    def __init__(self, registry: Optional[TokenizerRegistry] = None):
        self.registry = registry or get_default_registry()
    
    def check_system_requirements(self) -> Dict[str, Any]:
        """Check system requirements for tokenizer adapters.
        
        Returns:
            Dictionary with system information and requirements status
        """
        requirements = {
            "python_version": sys.version,
            "python_version_info": sys.version_info,
            "dependencies": {},
            "adapters": {},
            "recommendations": []
        }
        
        # Check Python version
        if sys.version_info < (3, 8):
            requirements["recommendations"].append(
                "⚠️  Python 3.8+ recommended for best tokenizer support"
            )
        
        # Check optional dependencies
        dependencies_to_check = [
            ("tiktoken", "TikToken adapter for OpenAI models"),
            ("transformers", "HuggingFace adapter for transformer models"),
            ("torch", "PyTorch backend for HuggingFace models"),
            ("sentence_transformers", "Sentence-transformers models"),
        ]
        
        for dep_name, description in dependencies_to_check:
            try:
                __import__(dep_name)
                requirements["dependencies"][dep_name] = {
                    "available": True,
                    "description": description,
                    "version": self._get_package_version(dep_name)
                }
            except ImportError:
                requirements["dependencies"][dep_name] = {
                    "available": False,
                    "description": description,
                    "version": None
                }
        
        # Check adapter availability
        adapter_status = self.registry.get_adapter_status()
        requirements["adapters"] = adapter_status
        
        # Generate recommendations
        recommendations = self._generate_system_recommendations(requirements)
        requirements["recommendations"].extend(recommendations)
        
        return requirements
    
    def _get_package_version(self, package_name: str) -> Optional[str]:
        """Get version of an installed package."""
        try:
            import importlib.metadata
            return importlib.metadata.version(package_name)
        except Exception:
            try:
                # Fallback for older Python versions
                import pkg_resources
                return pkg_resources.get_distribution(package_name).version
            except Exception:
                return "unknown"
    
    def _generate_system_recommendations(self, requirements: Dict[str, Any]) -> List[str]:
        """Generate system-specific recommendations."""
        recommendations = []
        
        deps = requirements["dependencies"]
        adapters = requirements["adapters"]
        
        # Recommend installing missing dependencies
        if not deps.get("tiktoken", {}).get("available", False):
            recommendations.append(
                "💡 Install tiktoken for accurate OpenAI model tokenization: pip install tiktoken"
            )
        
        if not deps.get("transformers", {}).get("available", False):
            recommendations.append(
                "💡 Install transformers for HuggingFace model support: pip install transformers"
            )
        
        # Check for adapter issues
        available_adapters = [name for name, info in adapters.items() if info["available"]]
        if len(available_adapters) == 1 and "heuristic" in available_adapters:
            recommendations.append(
                "⚠️  Only heuristic adapter available. Install tiktoken or transformers for exact tokenization."
            )
        
        if not available_adapters:
            recommendations.append(
                "❌ No adapters available! This indicates a serious configuration issue."
            )
        
        return recommendations
    
    def diagnose_model_compatibility(self, model_name: str) -> Dict[str, Any]:
        """Diagnose compatibility for a specific model.
        
        Args:
            model_name: Model name to diagnose
            
        Returns:
            Dictionary with compatibility information and recommendations
        """
        diagnosis = {
            "model_name": model_name,
            "recommended_adapter": None,
            "compatible_adapters": [],
            "issues": [],
            "recommendations": []
        }
        
        # Get recommended adapter
        try:
            recommended = self.registry.suggest_best_adapter(model_name)
            diagnosis["recommended_adapter"] = recommended
        except Exception as e:
            diagnosis["issues"].append(f"Failed to get adapter recommendation: {e}")
        
        # Test each adapter
        adapter_status = self.registry.get_adapter_status()
        for adapter_name, status in adapter_status.items():
            if status["available"]:
                try:
                    # Try creating adapter for this model
                    test_adapter = self.registry.resolve(
                        adapter_name=adapter_name,
                        model_name=model_name
                    )
                    
                    # Test tokenization
                    test_result = test_adapter.count_tokens("Hello world")
                    
                    diagnosis["compatible_adapters"].append({
                        "adapter": adapter_name,
                        "status": "compatible",
                        "test_tokens": test_result.count,
                        "is_exact": test_result.is_exact,
                        "max_tokens": test_result.model_max_tokens
                    })
                    
                except Exception as e:
                    diagnosis["compatible_adapters"].append({
                        "adapter": adapter_name,
                        "status": "incompatible",
                        "error": str(e)
                    })
        
        # Generate model-specific recommendations
        recommendations = self._generate_model_recommendations(model_name, diagnosis)
        diagnosis["recommendations"] = recommendations
        
        return diagnosis
    
    def _generate_model_recommendations(self, model_name: str, diagnosis: Dict[str, Any]) -> List[str]:
        """Generate model-specific recommendations."""
        recommendations = []
        
        compatible_adapters = [
            adapter for adapter in diagnosis["compatible_adapters"]
            if adapter["status"] == "compatible"
        ]
        
        if not compatible_adapters:
            recommendations.append(
                f"❌ No compatible adapters found for model '{model_name}'"
            )
            recommendations.append(
                "💡 Try using 'auto' adapter selection for automatic fallback"
            )
        else:
            # Recommend exact tokenizers over heuristic
            exact_adapters = [
                adapter for adapter in compatible_adapters
                if adapter.get("is_exact", False)
            ]
            
            if exact_adapters:
                best_exact = exact_adapters[0]["adapter"]
                recommendations.append(
                    f"✅ Use '{best_exact}' adapter for exact tokenization of '{model_name}'"
                )
            else:
                recommendations.append(
                    f"⚠️  Only approximate tokenization available for '{model_name}'"
                )
        
        # Model-specific advice
        if any(openai_indicator in model_name.lower() for openai_indicator in 
               ["gpt", "text-embedding", "davinci"]):
            recommendations.append(
                "💡 For OpenAI models, tiktoken adapter provides the most accurate results"
            )
        
        if any(hf_indicator in model_name.lower() for hf_indicator in 
               ["bert", "roberta", "sentence-transformers"]):
            recommendations.append(
                "💡 For HuggingFace models, huggingface adapter provides the most accurate results"
            )
        
        return recommendations
    
    def test_adapter_chain(self, model_name: str, 
                          fallback_chain: Optional[List[str]] = None) -> Dict[str, Any]:
        """Test a complete adapter fallback chain.
        
        Args:
            model_name: Model name to test
            fallback_chain: Optional custom fallback chain
            
        Returns:
            Dictionary with test results for each adapter in the chain
        """
        if fallback_chain:
            # Temporarily set custom fallback chain
            original_chain = self.registry.get_fallback_chain()
            self.registry.set_fallback_chain(fallback_chain)
        
        try:
            test_results = {
                "model_name": model_name,
                "fallback_chain": fallback_chain or self.registry.get_fallback_chain(),
                "adapter_results": [],
                "final_result": None,
                "recommendations": []
            }
            
            # Test each adapter in the chain
            for adapter_name in test_results["fallback_chain"]:
                try:
                    adapter = self.registry.resolve(
                        adapter_name=adapter_name,
                        model_name=model_name
                    )
                    
                    # Test with sample text
                    test_text = "The quick brown fox jumps over the lazy dog."
                    result = adapter.count_tokens(test_text)
                    
                    test_results["adapter_results"].append({
                        "adapter": adapter_name,
                        "status": "success",
                        "tokens": result.count,
                        "method": result.method,
                        "is_exact": result.is_exact,
                        "tokenizer_id": result.tokenizer_id
                    })
                    
                    # Record first successful adapter
                    if test_results["final_result"] is None:
                        test_results["final_result"] = {
                            "adapter": adapter_name,
                            "tokens": result.count,
                            "is_exact": result.is_exact
                        }
                    
                except Exception as e:
                    test_results["adapter_results"].append({
                        "adapter": adapter_name,
                        "status": "failed",
                        "error": str(e)
                    })
            
            # Generate recommendations based on test results
            recommendations = self._generate_chain_recommendations(test_results)
            test_results["recommendations"] = recommendations
            
            return test_results
            
        finally:
            # Restore original fallback chain if it was modified
            if fallback_chain:
                self.registry.set_fallback_chain(original_chain)
    
    def _generate_chain_recommendations(self, test_results: Dict[str, Any]) -> List[str]:
        """Generate recommendations based on fallback chain test results."""
        recommendations = []
        
        successful_adapters = [
            result for result in test_results["adapter_results"]
            if result["status"] == "success"
        ]
        
        failed_adapters = [
            result for result in test_results["adapter_results"]
            if result["status"] == "failed"
        ]
        
        if not successful_adapters:
            recommendations.append(
                "❌ All adapters in fallback chain failed"
            )
            recommendations.append(
                "💡 Check system requirements and install missing dependencies"
            )
        else:
            first_success = successful_adapters[0]
            if first_success["is_exact"]:
                recommendations.append(
                    f"✅ Fallback chain working well - '{first_success['adapter']}' provides exact tokenization"
                )
            else:
                recommendations.append(
                    f"⚠️  Fallback chain uses approximate tokenization - '{first_success['adapter']}' adapter"
                )
                recommendations.append(
                    "💡 Install tiktoken or transformers for exact tokenization"
                )
        
        if failed_adapters:
            recommendations.append(
                f"ℹ️  {len(failed_adapters)} adapter(s) failed but fallback is working"
            )
        
        return recommendations
    
    def create_diagnostic_report(self, model_name: Optional[str] = None) -> str:
        """Create a comprehensive diagnostic report.
        
        Args:
            model_name: Optional specific model to diagnose
            
        Returns:
            Formatted diagnostic report string
        """
        report_lines = [
            "🔍 Tokenizer Adapter Diagnostic Report",
            "=" * 50,
            ""
        ]
        
        # System requirements check
        system_info = self.check_system_requirements()
        report_lines.extend([
            "📋 System Information:",
            f"   Python: {system_info['python_version_info'][:2]}",
            ""
        ])
        
        # Dependencies status
        report_lines.append("📦 Dependencies:")
        for dep_name, dep_info in system_info["dependencies"].items():
            status = "✅" if dep_info["available"] else "❌"
            version = f" (v{dep_info['version']})" if dep_info["version"] else ""
            report_lines.append(f"   {status} {dep_name}{version}")
        report_lines.append("")
        
        # Adapter status
        report_lines.append("🔧 Adapters:")
        for adapter_name, adapter_info in system_info["adapters"].items():
            status = "✅" if adapter_info["available"] else "❌"
            error_info = f" - {adapter_info['error']}" if adapter_info.get("error") else ""
            report_lines.append(f"   {status} {adapter_name}{error_info}")
        report_lines.append("")
        
        # Model-specific diagnosis
        if model_name:
            model_diagnosis = self.diagnose_model_compatibility(model_name)
            report_lines.extend([
                f"🤖 Model Analysis: {model_name}",
                f"   Recommended: {model_diagnosis['recommended_adapter']}",
                f"   Compatible adapters: {len([a for a in model_diagnosis['compatible_adapters'] if a['status'] == 'compatible'])}",
                ""
            ])
            
            # Add model recommendations
            if model_diagnosis["recommendations"]:
                report_lines.append("💡 Model Recommendations:")
                for rec in model_diagnosis["recommendations"]:
                    report_lines.append(f"   {rec}")
                report_lines.append("")
        
        # System recommendations
        if system_info["recommendations"]:
            report_lines.append("💡 System Recommendations:")
            for rec in system_info["recommendations"]:
                report_lines.append(f"   {rec}")
            report_lines.append("")
        
        # Fallback chain test
        if model_name:
            chain_test = self.test_adapter_chain(model_name)
            report_lines.extend([
                "🔄 Fallback Chain Test:",
                f"   Chain: {' → '.join(chain_test['fallback_chain'])}",
            ])
            
            if chain_test["final_result"]:
                final = chain_test["final_result"]
                exactness = "exact" if final["is_exact"] else "approximate"
                report_lines.append(f"   Result: {final['adapter']} ({exactness})")
            else:
                report_lines.append("   Result: All adapters failed")
            
            report_lines.append("")
        
        return "\n".join(report_lines)


def run_diagnostics(model_name: Optional[str] = None, 
                   registry: Optional[TokenizerRegistry] = None) -> str:
    """Run comprehensive tokenizer diagnostics.
    
    Args:
        model_name: Optional specific model to diagnose
        registry: Optional custom registry to use
        
    Returns:
        Formatted diagnostic report
    """
    diagnostics = TokenizerDiagnostics(registry)
    return diagnostics.create_diagnostic_report(model_name)


def check_adapter_health(adapter_name: str, model_name: str = "test-model",
                        registry: Optional[TokenizerRegistry] = None) -> Dict[str, Any]:
    """Check health of a specific adapter.
    
    Args:
        adapter_name: Name of adapter to check
        model_name: Model name to test with
        registry: Optional custom registry to use
        
    Returns:
        Dictionary with health check results
    """
    registry = registry or get_default_registry()
    
    health_check = {
        "adapter_name": adapter_name,
        "model_name": model_name,
        "healthy": False,
        "error": None,
        "test_results": None,
        "recommendations": []
    }
    
    try:
        # Try to create and test the adapter
        adapter = registry.resolve(
            adapter_name=adapter_name,
            model_name=model_name
        )
        
        # Test with sample text
        test_text = "Hello, world! This is a test."
        result = adapter.count_tokens(test_text)
        
        health_check.update({
            "healthy": True,
            "test_results": {
                "tokens": result.count,
                "method": result.method,
                "is_exact": result.is_exact,
                "tokenizer_id": result.tokenizer_id,
                "max_tokens": result.model_max_tokens
            }
        })
        
        # Add recommendations based on results
        if not result.is_exact:
            health_check["recommendations"].append(
                "Consider using an exact tokenizer for production use"
            )
        
    except TokenizerError as e:
        health_check.update({
            "healthy": False,
            "error": str(e),
            "recommendations": e.recovery_suggestions
        })
        
    except Exception as e:
        health_check.update({
            "healthy": False,
            "error": str(e),
            "recommendations": [
                "Check adapter configuration and dependencies",
                "Try using 'auto' adapter selection for fallback"
            ]
        })
    
    return health_check