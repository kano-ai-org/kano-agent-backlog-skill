"""Comprehensive dependency management for tokenizer adapters.

This module provides enhanced dependency detection, version compatibility checking,
and installation guidance for optional tokenizer dependencies.

Features:
- Optional dependency detection and safe loading
- Version compatibility checking with detailed requirements
- Clear installation instructions with multiple package managers
- Dependency isolation to prevent system-wide failures
- Runtime dependency health monitoring
"""

import importlib
import logging
import sys
import warnings
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union
from packaging import version
import subprocess

logger = logging.getLogger(__name__)

# Dependency specifications with version requirements
DEPENDENCY_SPECS = {
    "tiktoken": {
        "min_version": "0.4.0",
        "recommended_version": "0.5.0",
        "max_version": None,
        "pip_package": "tiktoken",
        "conda_package": "tiktoken",
        "conda_channel": "conda-forge",
        "description": "OpenAI's tiktoken library for exact tokenization of GPT models",
        "adapters": ["tiktoken"],
        "optional": True,
        "import_name": "tiktoken",
        "version_attr": "__version__",
        "test_import": "tiktoken.get_encoding",
    },
    "transformers": {
        "min_version": "4.20.0",
        "recommended_version": "4.35.0",
        "max_version": None,
        "pip_package": "transformers",
        "conda_package": "transformers",
        "conda_channel": "huggingface",
        "description": "HuggingFace transformers library for transformer model tokenizers",
        "adapters": ["huggingface"],
        "optional": True,
        "import_name": "transformers",
        "version_attr": "__version__",
        "test_import": "transformers.AutoTokenizer",
    },
    "sentence-transformers": {
        "min_version": "2.2.0",
        "recommended_version": "2.2.2",
        "max_version": None,
        "pip_package": "sentence-transformers",
        "conda_package": "sentence-transformers",
        "conda_channel": "conda-forge",
        "description": "Sentence transformers library for semantic similarity models",
        "adapters": ["huggingface"],
        "optional": True,
        "import_name": "sentence_transformers",
        "version_attr": "__version__",
        "test_import": "sentence_transformers.SentenceTransformer",
    },
    "torch": {
        "min_version": "1.9.0",
        "recommended_version": "2.0.0",
        "max_version": None,
        "pip_package": "torch",
        "conda_package": "pytorch",
        "conda_channel": "pytorch",
        "description": "PyTorch deep learning framework (required by transformers)",
        "adapters": ["huggingface"],
        "optional": True,
        "import_name": "torch",
        "version_attr": "__version__",
        "test_import": "torch.tensor",
    },
    "packaging": {
        "min_version": "20.0",
        "recommended_version": "23.0",
        "max_version": None,
        "pip_package": "packaging",
        "conda_package": "packaging",
        "conda_channel": "conda-forge",
        "description": "Core utilities for Python packages (required for version checking)",
        "adapters": ["all"],
        "optional": False,  # Required for version checking
        "import_name": "packaging",
        "version_attr": "__version__",
        "test_import": "packaging.version.parse",
    }
}

# Python version compatibility
PYTHON_VERSION_REQUIREMENTS = {
    "tiktoken": {"min": "3.8", "max": None},
    "transformers": {"min": "3.8", "max": None},
    "sentence-transformers": {"min": "3.8", "max": None},
    "torch": {"min": "3.8", "max": None},
}


@dataclass
class DependencyStatus:
    """Status information for a dependency."""
    
    name: str
    available: bool
    version: Optional[str] = None
    version_compatible: bool = True
    version_issues: List[str] = None
    import_error: Optional[str] = None
    installation_instructions: List[str] = None
    test_passed: bool = False
    test_error: Optional[str] = None
    
    def __post_init__(self):
        if self.version_issues is None:
            self.version_issues = []
        if self.installation_instructions is None:
            self.installation_instructions = []


@dataclass
class DependencyReport:
    """Comprehensive dependency report."""
    
    dependencies: Dict[str, DependencyStatus]
    python_version: str
    python_compatible: bool
    overall_health: str  # "healthy", "degraded", "critical"
    recommendations: List[str]
    
    def get_missing_dependencies(self) -> List[str]:
        """Get list of missing dependencies."""
        return [name for name, status in self.dependencies.items() 
                if not status.available]
    
    def get_incompatible_dependencies(self) -> List[str]:
        """Get list of dependencies with version compatibility issues."""
        return [name for name, status in self.dependencies.items() 
                if status.available and not status.version_compatible]
    
    def get_failed_tests(self) -> List[str]:
        """Get list of dependencies that failed functionality tests."""
        return [name for name, status in self.dependencies.items() 
                if status.available and not status.test_passed]


class DependencyManager:
    """Manages optional dependencies for tokenizer adapters."""
    
    def __init__(self):
        self._dependency_cache: Dict[str, DependencyStatus] = {}
        self._import_cache: Dict[str, Any] = {}
        self._last_check_time: Optional[float] = None
        self._check_interval = 300  # 5 minutes
    
    def check_dependency(self, dependency_name: str, force_refresh: bool = False) -> DependencyStatus:
        """Check status of a specific dependency.
        
        Args:
            dependency_name: Name of the dependency to check
            force_refresh: Force refresh of cached status
            
        Returns:
            DependencyStatus with detailed information
        """
        if not force_refresh and dependency_name in self._dependency_cache:
            return self._dependency_cache[dependency_name]
        
        if dependency_name not in DEPENDENCY_SPECS:
            return DependencyStatus(
                name=dependency_name,
                available=False,
                import_error=f"Unknown dependency: {dependency_name}",
                installation_instructions=[f"Dependency '{dependency_name}' is not recognized"]
            )
        
        spec = DEPENDENCY_SPECS[dependency_name]
        status = DependencyStatus(name=dependency_name, available=False)
        
        try:
            # Try to import the module
            module = self._safe_import(spec["import_name"])
            if module is None:
                status.import_error = f"Failed to import {spec['import_name']}"
                status.installation_instructions = self._generate_installation_instructions(dependency_name)
                self._dependency_cache[dependency_name] = status
                return status
            
            # Module imported successfully
            status.available = True
            
            # Check version compatibility
            status.version = self._get_module_version(module, spec)
            if status.version:
                status.version_compatible, status.version_issues = self._check_version_compatibility(
                    dependency_name, status.version
                )
            
            # Test functionality
            status.test_passed, status.test_error = self._test_dependency_functionality(
                dependency_name, module, spec
            )
            
            # Generate recommendations if needed
            if not status.version_compatible or not status.test_passed:
                status.installation_instructions = self._generate_installation_instructions(
                    dependency_name, current_version=status.version
                )
            
        except Exception as e:
            status.import_error = str(e)
            status.installation_instructions = self._generate_installation_instructions(dependency_name)
            logger.debug(f"Dependency check failed for {dependency_name}: {e}")
        
        self._dependency_cache[dependency_name] = status
        return status
    
    def _safe_import(self, import_name: str) -> Optional[Any]:
        """Safely import a module without raising exceptions.
        
        Args:
            import_name: Name of the module to import
            
        Returns:
            Imported module or None if import failed
        """
        if import_name in self._import_cache:
            return self._import_cache[import_name]
        
        try:
            module = importlib.import_module(import_name)
            self._import_cache[import_name] = module
            return module
        except ImportError as e:
            logger.debug(f"Failed to import {import_name}: {e}")
            return None
        except Exception as e:
            logger.warning(f"Unexpected error importing {import_name}: {e}")
            return None
    
    def _get_module_version(self, module: Any, spec: Dict[str, Any]) -> Optional[str]:
        """Get version of an imported module.
        
        Args:
            module: Imported module
            spec: Dependency specification
            
        Returns:
            Version string or None if not available
        """
        try:
            version_attr = spec.get("version_attr", "__version__")
            if hasattr(module, version_attr):
                return getattr(module, version_attr)
            
            # Fallback version detection methods
            if hasattr(module, "version"):
                return module.version
            if hasattr(module, "VERSION"):
                return module.VERSION
            
            # Try importlib.metadata for newer Python versions
            try:
                import importlib.metadata
                return importlib.metadata.version(spec["pip_package"])
            except Exception:
                pass
            
            return None
        except Exception as e:
            logger.debug(f"Failed to get version for {spec['import_name']}: {e}")
            return None
    
    def _check_version_compatibility(self, dependency_name: str, current_version: str) -> Tuple[bool, List[str]]:
        """Check if current version meets requirements.
        
        Args:
            dependency_name: Name of the dependency
            current_version: Current installed version
            
        Returns:
            Tuple of (is_compatible, list_of_issues)
        """
        spec = DEPENDENCY_SPECS[dependency_name]
        issues = []
        
        try:
            current_ver = version.parse(current_version)
            
            # Check minimum version
            if spec["min_version"]:
                min_ver = version.parse(spec["min_version"])
                if current_ver < min_ver:
                    issues.append(f"Version {current_version} is below minimum required {spec['min_version']}")
            
            # Check maximum version
            if spec["max_version"]:
                max_ver = version.parse(spec["max_version"])
                if current_ver > max_ver:
                    issues.append(f"Version {current_version} is above maximum supported {spec['max_version']}")
            
            # Check Python version compatibility
            if dependency_name in PYTHON_VERSION_REQUIREMENTS:
                python_req = PYTHON_VERSION_REQUIREMENTS[dependency_name]
                current_python = version.parse(f"{sys.version_info.major}.{sys.version_info.minor}")
                
                if python_req["min"]:
                    min_python = version.parse(python_req["min"])
                    if current_python < min_python:
                        issues.append(f"Requires Python {python_req['min']}+, current: {current_python}")
                
                if python_req["max"]:
                    max_python = version.parse(python_req["max"])
                    if current_python > max_python:
                        issues.append(f"Not compatible with Python {current_python}, max: {python_req['max']}")
            
            # Warn about outdated versions
            if spec["recommended_version"]:
                recommended_ver = version.parse(spec["recommended_version"])
                if current_ver < recommended_ver:
                    issues.append(f"Version {current_version} is outdated, recommended: {spec['recommended_version']}")
            
        except Exception as e:
            issues.append(f"Failed to parse version {current_version}: {e}")
        
        return len(issues) == 0, issues
    
    def _test_dependency_functionality(self, dependency_name: str, module: Any, spec: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Test basic functionality of a dependency.
        
        Args:
            dependency_name: Name of the dependency
            module: Imported module
            spec: Dependency specification
            
        Returns:
            Tuple of (test_passed, error_message)
        """
        try:
            test_import = spec.get("test_import")
            if not test_import:
                return True, None
            
            # Parse nested attribute access (e.g., "transformers.AutoTokenizer")
            parts = test_import.split(".")
            obj = module
            
            for part in parts[1:]:  # Skip the module name itself
                if hasattr(obj, part):
                    obj = getattr(obj, part)
                else:
                    return False, f"Missing attribute: {test_import}"
            
            # Additional specific tests
            if dependency_name == "tiktoken":
                # Test tiktoken encoding loading
                encoding = module.get_encoding("cl100k_base")
                test_tokens = encoding.encode("test")
                if len(test_tokens) == 0:
                    return False, "tiktoken encoding test failed"
            
            elif dependency_name == "transformers":
                # Test AutoTokenizer import and basic functionality
                from transformers import AutoTokenizer
                # Don't actually load a model in tests, just verify the class exists
                if not hasattr(AutoTokenizer, 'from_pretrained'):
                    return False, "AutoTokenizer.from_pretrained not available"
            
            elif dependency_name == "sentence-transformers":
                # Test SentenceTransformer import
                from sentence_transformers import SentenceTransformer
                if not hasattr(SentenceTransformer, 'encode'):
                    return False, "SentenceTransformer.encode not available"
            
            return True, None
            
        except Exception as e:
            return False, str(e)
    
    def _generate_installation_instructions(self, dependency_name: str, current_version: Optional[str] = None) -> List[str]:
        """Generate installation instructions for a dependency.
        
        Args:
            dependency_name: Name of the dependency
            current_version: Current version if available
            
        Returns:
            List of installation instruction strings
        """
        if dependency_name not in DEPENDENCY_SPECS:
            return [f"Unknown dependency: {dependency_name}"]
        
        spec = DEPENDENCY_SPECS[dependency_name]
        instructions = []
        
        # Basic installation instructions
        if current_version:
            instructions.append(f"Current version: {current_version}")
            if spec["recommended_version"]:
                instructions.append(f"Recommended version: {spec['recommended_version']}")
        
        instructions.append(f"Description: {spec['description']}")
        instructions.append("")
        
        # Pip installation
        pip_cmd = f"pip install {spec['pip_package']}"
        if spec["recommended_version"] and not current_version:
            pip_cmd += f">={spec['recommended_version']}"
        elif current_version and spec["recommended_version"]:
            pip_cmd += f" --upgrade"
        
        instructions.extend([
            "Installation options:",
            f"  • pip: {pip_cmd}",
        ])
        
        # Conda installation
        if spec["conda_package"]:
            conda_cmd = f"conda install -c {spec['conda_channel']} {spec['conda_package']}"
            instructions.append(f"  • conda: {conda_cmd}")
        
        # Verification command
        instructions.extend([
            "",
            "Verify installation:",
            f"  python -c \"import {spec['import_name']}; print({spec['import_name']}.{spec['version_attr']})\""
        ])
        
        # Special instructions for specific packages
        if dependency_name == "transformers":
            instructions.extend([
                "",
                "For sentence-transformers models:",
                "  pip install sentence-transformers",
                "",
                "For GPU support (optional):",
                "  pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118"
            ])
        
        elif dependency_name == "tiktoken":
            instructions.extend([
                "",
                "Note: tiktoken provides exact tokenization for OpenAI models",
                "Alternative: Use 'heuristic' adapter for approximate tokenization"
            ])
        
        return instructions
    
    def check_all_dependencies(self, force_refresh: bool = False) -> DependencyReport:
        """Check status of all known dependencies.
        
        Args:
            force_refresh: Force refresh of all cached statuses
            
        Returns:
            Comprehensive dependency report
        """
        import time
        
        # Check if we need to refresh based on time interval
        current_time = time.time()
        if (not force_refresh and 
            self._last_check_time and 
            current_time - self._last_check_time < self._check_interval):
            # Use cached results if available
            if len(self._dependency_cache) == len(DEPENDENCY_SPECS):
                return self._create_report_from_cache()
        
        dependencies = {}
        for dep_name in DEPENDENCY_SPECS:
            dependencies[dep_name] = self.check_dependency(dep_name, force_refresh)
        
        self._last_check_time = current_time
        
        # Check Python version compatibility
        python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        python_compatible = self._check_python_compatibility()
        
        # Determine overall health
        missing_required = [name for name, status in dependencies.items() 
                          if not DEPENDENCY_SPECS[name]["optional"] and not status.available]
        missing_optional = [name for name, status in dependencies.items() 
                          if DEPENDENCY_SPECS[name]["optional"] and not status.available]
        incompatible = [name for name, status in dependencies.items() 
                       if status.available and not status.version_compatible]
        
        if missing_required:
            overall_health = "critical"
        elif incompatible or len(missing_optional) == len([n for n in DEPENDENCY_SPECS if DEPENDENCY_SPECS[n]["optional"]]):
            overall_health = "degraded"
        else:
            overall_health = "healthy"
        
        # Generate recommendations
        recommendations = self._generate_recommendations(dependencies, python_compatible)
        
        return DependencyReport(
            dependencies=dependencies,
            python_version=python_version,
            python_compatible=python_compatible,
            overall_health=overall_health,
            recommendations=recommendations
        )
    
    def _create_report_from_cache(self) -> DependencyReport:
        """Create dependency report from cached data."""
        python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        python_compatible = self._check_python_compatibility()
        
        # Determine overall health from cache
        missing_required = [name for name, status in self._dependency_cache.items() 
                          if not DEPENDENCY_SPECS[name]["optional"] and not status.available]
        missing_optional = [name for name, status in self._dependency_cache.items() 
                          if DEPENDENCY_SPECS[name]["optional"] and not status.available]
        incompatible = [name for name, status in self._dependency_cache.items() 
                       if status.available and not status.version_compatible]
        
        if missing_required:
            overall_health = "critical"
        elif incompatible or len(missing_optional) == len([n for n in DEPENDENCY_SPECS if DEPENDENCY_SPECS[n]["optional"]]):
            overall_health = "degraded"
        else:
            overall_health = "healthy"
        
        recommendations = self._generate_recommendations(self._dependency_cache, python_compatible)
        
        return DependencyReport(
            dependencies=self._dependency_cache.copy(),
            python_version=python_version,
            python_compatible=python_compatible,
            overall_health=overall_health,
            recommendations=recommendations
        )
    
    def _check_python_compatibility(self) -> bool:
        """Check if current Python version is compatible with dependencies."""
        current_python = version.parse(f"{sys.version_info.major}.{sys.version_info.minor}")
        
        for dep_name, python_req in PYTHON_VERSION_REQUIREMENTS.items():
            if python_req["min"]:
                min_python = version.parse(python_req["min"])
                if current_python < min_python:
                    return False
            
            if python_req["max"]:
                max_python = version.parse(python_req["max"])
                if current_python > max_python:
                    return False
        
        return True
    
    def _generate_recommendations(self, dependencies: Dict[str, DependencyStatus], python_compatible: bool) -> List[str]:
        """Generate recommendations based on dependency status.
        
        Args:
            dependencies: Dictionary of dependency statuses
            python_compatible: Whether Python version is compatible
            
        Returns:
            List of recommendation strings
        """
        recommendations = []
        
        if not python_compatible:
            recommendations.append(
                f"⚠️  Python {sys.version_info.major}.{sys.version_info.minor} may not be compatible with all dependencies"
            )
        
        # Missing required dependencies
        missing_required = [name for name, status in dependencies.items() 
                          if not DEPENDENCY_SPECS[name]["optional"] and not status.available]
        if missing_required:
            recommendations.append(
                f"🚨 Critical: Install required dependencies: {', '.join(missing_required)}"
            )
        
        # Missing optional dependencies
        missing_optional = [name for name, status in dependencies.items() 
                          if DEPENDENCY_SPECS[name]["optional"] and not status.available]
        if missing_optional:
            recommendations.append(
                f"💡 Optional: Install for enhanced functionality: {', '.join(missing_optional)}"
            )
        
        # Version compatibility issues
        incompatible = [name for name, status in dependencies.items() 
                       if status.available and not status.version_compatible]
        if incompatible:
            recommendations.append(
                f"🔄 Update for compatibility: {', '.join(incompatible)}"
            )
        
        # Failed functionality tests
        failed_tests = [name for name, status in dependencies.items() 
                       if status.available and not status.test_passed]
        if failed_tests:
            recommendations.append(
                f"🔧 Functionality issues detected: {', '.join(failed_tests)}"
            )
        
        # Adapter-specific recommendations
        tiktoken_status = dependencies.get("tiktoken")
        transformers_status = dependencies.get("transformers")
        
        if tiktoken_status and not tiktoken_status.available:
            recommendations.append(
                "📝 For OpenAI models: Install tiktoken for exact tokenization"
            )
        
        if transformers_status and not transformers_status.available:
            recommendations.append(
                "🤗 For HuggingFace models: Install transformers for exact tokenization"
            )
        
        if not any(status.available for status in dependencies.values() if DEPENDENCY_SPECS[status.name]["optional"]):
            recommendations.append(
                "⚡ Using heuristic tokenization only. Install tiktoken or transformers for better accuracy."
            )
        
        return recommendations
    
    def get_adapter_dependencies(self, adapter_name: str) -> List[str]:
        """Get list of dependencies required for a specific adapter.
        
        Args:
            adapter_name: Name of the tokenizer adapter
            
        Returns:
            List of dependency names required for the adapter
        """
        dependencies = []
        
        for dep_name, spec in DEPENDENCY_SPECS.items():
            if adapter_name in spec["adapters"] or "all" in spec["adapters"]:
                dependencies.append(dep_name)
        
        return dependencies
    
    def check_adapter_readiness(self, adapter_name: str) -> Tuple[bool, List[str], List[str]]:
        """Check if an adapter has all required dependencies available.
        
        Args:
            adapter_name: Name of the tokenizer adapter
            
        Returns:
            Tuple of (is_ready, missing_dependencies, issues)
        """
        required_deps = self.get_adapter_dependencies(adapter_name)
        missing_deps = []
        issues = []
        
        for dep_name in required_deps:
            if not DEPENDENCY_SPECS[dep_name]["optional"]:  # Only check required deps
                status = self.check_dependency(dep_name)
                if not status.available:
                    missing_deps.append(dep_name)
                elif not status.version_compatible:
                    issues.extend(status.version_issues)
                elif not status.test_passed and status.test_error:
                    issues.append(f"{dep_name}: {status.test_error}")
        
        is_ready = len(missing_deps) == 0 and len(issues) == 0
        return is_ready, missing_deps, issues
    
    def install_dependency(self, dependency_name: str, method: str = "pip", upgrade: bool = False) -> Tuple[bool, str]:
        """Attempt to install a dependency programmatically.
        
        Args:
            dependency_name: Name of the dependency to install
            method: Installation method ("pip" or "conda")
            upgrade: Whether to upgrade if already installed
            
        Returns:
            Tuple of (success, output_message)
        """
        if dependency_name not in DEPENDENCY_SPECS:
            return False, f"Unknown dependency: {dependency_name}"
        
        spec = DEPENDENCY_SPECS[dependency_name]
        
        try:
            if method == "pip":
                package = spec["pip_package"]
                cmd = [sys.executable, "-m", "pip", "install"]
                if upgrade:
                    cmd.append("--upgrade")
                cmd.append(package)
                
                if spec["recommended_version"] and not upgrade:
                    cmd[-1] += f">={spec['recommended_version']}"
            
            elif method == "conda":
                if not spec["conda_package"]:
                    return False, f"Conda installation not available for {dependency_name}"
                
                package = spec["conda_package"]
                channel = spec["conda_channel"]
                cmd = ["conda", "install", "-c", channel, package, "-y"]
            
            else:
                return False, f"Unknown installation method: {method}"
            
            # Execute installation command
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode == 0:
                # Clear cache to force re-check
                self._dependency_cache.pop(dependency_name, None)
                self._import_cache.pop(spec["import_name"], None)
                
                # Verify installation
                status = self.check_dependency(dependency_name, force_refresh=True)
                if status.available:
                    return True, f"Successfully installed {dependency_name} {status.version or ''}"
                else:
                    return False, f"Installation completed but {dependency_name} still not available: {status.import_error}"
            else:
                return False, f"Installation failed: {result.stderr}"
        
        except subprocess.TimeoutExpired:
            return False, f"Installation timed out after 5 minutes"
        except Exception as e:
            return False, f"Installation error: {e}"
    
    def clear_cache(self) -> None:
        """Clear all cached dependency information."""
        self._dependency_cache.clear()
        self._import_cache.clear()
        self._last_check_time = None
    
    def get_installation_summary(self) -> str:
        """Get a formatted summary of installation instructions for all missing dependencies.
        
        Returns:
            Formatted installation summary string
        """
        report = self.check_all_dependencies()
        missing_deps = report.get_missing_dependencies()
        
        if not missing_deps:
            return "✅ All dependencies are available!"
        
        summary_parts = [
            "📦 Tokenizer Dependencies Installation Guide",
            "=" * 50,
            ""
        ]
        
        for dep_name in missing_deps:
            status = report.dependencies[dep_name]
            spec = DEPENDENCY_SPECS[dep_name]
            
            summary_parts.extend([
                f"📋 {dep_name.upper()}",
                f"   {spec['description']}",
                f"   Required for: {', '.join(spec['adapters'])} adapter(s)",
                ""
            ])
            
            for instruction in status.installation_instructions:
                if instruction.strip():
                    summary_parts.append(f"   {instruction}")
            
            summary_parts.append("")
        
        summary_parts.extend([
            "🔄 After installation, restart your Python session",
            "✅ Verify with: python -c \"from kano_backlog_core.tokenizer_dependencies import DependencyManager; print(DependencyManager().check_all_dependencies().overall_health)\"",
            ""
        ])
        
        return "\n".join(summary_parts)


# Global dependency manager instance
_default_dependency_manager = DependencyManager()


def get_dependency_manager() -> DependencyManager:
    """Get the default dependency manager instance."""
    return _default_dependency_manager


def check_dependency(dependency_name: str, force_refresh: bool = False) -> DependencyStatus:
    """Check status of a specific dependency using the default manager."""
    return _default_dependency_manager.check_dependency(dependency_name, force_refresh)


def check_all_dependencies(force_refresh: bool = False) -> DependencyReport:
    """Check status of all dependencies using the default manager."""
    return _default_dependency_manager.check_all_dependencies(force_refresh)


def get_installation_summary() -> str:
    """Get installation summary using the default manager."""
    return _default_dependency_manager.get_installation_summary()


def check_adapter_readiness(adapter_name: str) -> Tuple[bool, List[str], List[str]]:
    """Check if an adapter has all required dependencies available."""
    return _default_dependency_manager.check_adapter_readiness(adapter_name)