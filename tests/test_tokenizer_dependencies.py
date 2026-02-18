"""Tests for comprehensive dependency management system."""

import sys
import pytest
from unittest.mock import Mock, patch, MagicMock
from packaging import version

from kano_backlog_core.tokenizer_dependencies import (
    DependencyManager,
    DependencyStatus,
    DependencyReport,
    DEPENDENCY_SPECS,
    PYTHON_VERSION_REQUIREMENTS,
    check_dependency,
    check_all_dependencies,
    get_installation_summary,
    check_adapter_readiness,
)


class TestDependencyStatus:
    """Test DependencyStatus dataclass."""
    
    def test_dependency_status_creation(self):
        """Test creating DependencyStatus with default values."""
        status = DependencyStatus(name="tiktoken", available=True)
        
        assert status.name == "tiktoken"
        assert status.available is True
        assert status.version is None
        assert status.version_compatible is True
        assert status.version_issues == []
        assert status.import_error is None
        assert status.installation_instructions == []
        assert status.test_passed is False
        assert status.test_error is None
    
    def test_dependency_status_with_issues(self):
        """Test creating DependencyStatus with version issues."""
        status = DependencyStatus(
            name="transformers",
            available=True,
            version="4.0.0",
            version_compatible=False,
            version_issues=["Version 4.0.0 is below minimum required 4.20.0"]
        )
        
        assert status.name == "transformers"
        assert status.available is True
        assert status.version == "4.0.0"
        assert status.version_compatible is False
        assert len(status.version_issues) == 1


class TestDependencyReport:
    """Test DependencyReport dataclass."""
    
    def test_dependency_report_creation(self):
        """Test creating DependencyReport."""
        dependencies = {
            "tiktoken": DependencyStatus(name="tiktoken", available=True),
            "transformers": DependencyStatus(name="transformers", available=False)
        }
        
        report = DependencyReport(
            dependencies=dependencies,
            python_version="3.9.0",
            python_compatible=True,
            overall_health="degraded",
            recommendations=["Install transformers"]
        )
        
        assert len(report.dependencies) == 2
        assert report.python_version == "3.9.0"
        assert report.python_compatible is True
        assert report.overall_health == "degraded"
        assert len(report.recommendations) == 1
    
    def test_get_missing_dependencies(self):
        """Test getting missing dependencies from report."""
        dependencies = {
            "tiktoken": DependencyStatus(name="tiktoken", available=True),
            "transformers": DependencyStatus(name="transformers", available=False),
            "packaging": DependencyStatus(name="packaging", available=True)
        }
        
        report = DependencyReport(
            dependencies=dependencies,
            python_version="3.9.0",
            python_compatible=True,
            overall_health="degraded",
            recommendations=[]
        )
        
        missing = report.get_missing_dependencies()
        assert missing == ["transformers"]
    
    def test_get_incompatible_dependencies(self):
        """Test getting incompatible dependencies from report."""
        dependencies = {
            "tiktoken": DependencyStatus(name="tiktoken", available=True, version_compatible=True),
            "transformers": DependencyStatus(name="transformers", available=True, version_compatible=False),
            "packaging": DependencyStatus(name="packaging", available=False)  # Not available, so not incompatible
        }
        
        report = DependencyReport(
            dependencies=dependencies,
            python_version="3.9.0",
            python_compatible=True,
            overall_health="degraded",
            recommendations=[]
        )
        
        incompatible = report.get_incompatible_dependencies()
        assert incompatible == ["transformers"]
    
    def test_get_failed_tests(self):
        """Test getting dependencies with failed tests."""
        dependencies = {
            "tiktoken": DependencyStatus(name="tiktoken", available=True, test_passed=True),
            "transformers": DependencyStatus(name="transformers", available=True, test_passed=False),
            "packaging": DependencyStatus(name="packaging", available=False)  # Not available, so no test
        }
        
        report = DependencyReport(
            dependencies=dependencies,
            python_version="3.9.0",
            python_compatible=True,
            overall_health="degraded",
            recommendations=[]
        )
        
        failed = report.get_failed_tests()
        assert failed == ["transformers"]


class TestDependencyManager:
    """Test DependencyManager class."""
    
    def test_dependency_manager_creation(self):
        """Test creating DependencyManager."""
        manager = DependencyManager()
        
        assert manager._dependency_cache == {}
        assert manager._import_cache == {}
        assert manager._last_check_time is None
        assert manager._check_interval == 300
    
    def test_safe_import_success(self):
        """Test successful safe import."""
        manager = DependencyManager()
        
        # Test importing a standard library module
        module = manager._safe_import("sys")
        assert module is not None
        assert module == sys
        
        # Should be cached
        cached_module = manager._safe_import("sys")
        assert cached_module is module
    
    def test_safe_import_failure(self):
        """Test safe import with non-existent module."""
        manager = DependencyManager()
        
        module = manager._safe_import("nonexistent_module_12345")
        assert module is None
    
    def test_get_module_version(self):
        """Test getting module version."""
        manager = DependencyManager()
        
        # Mock module with version
        mock_module = Mock()
        mock_module.__version__ = "1.2.3"
        
        spec = {"version_attr": "__version__", "pip_package": "test"}
        version_str = manager._get_module_version(mock_module, spec)
        assert version_str == "1.2.3"
    
    def test_get_module_version_fallback(self):
        """Test getting module version with fallback methods."""
        manager = DependencyManager()
        
        # Mock module without __version__ but with version
        mock_module = Mock()
        del mock_module.__version__  # Remove __version__
        mock_module.version = "2.0.0"
        
        spec = {"version_attr": "__version__", "pip_package": "test"}
        version_str = manager._get_module_version(mock_module, spec)
        assert version_str == "2.0.0"
    
    def test_check_version_compatibility_valid(self):
        """Test version compatibility check with valid version."""
        manager = DependencyManager()
        
        # Test with tiktoken spec
        is_compatible, issues = manager._check_version_compatibility("tiktoken", "0.5.0")
        assert is_compatible is True
        assert len(issues) == 0
    
    def test_check_version_compatibility_too_old(self):
        """Test version compatibility check with too old version."""
        manager = DependencyManager()
        
        is_compatible, issues = manager._check_version_compatibility("tiktoken", "0.3.0")
        assert is_compatible is False
        assert len(issues) > 0
        assert "below minimum required" in issues[0]
    
    def test_check_version_compatibility_outdated_warning(self):
        """Test version compatibility check with outdated but acceptable version."""
        manager = DependencyManager()
        
        is_compatible, issues = manager._check_version_compatibility("tiktoken", "0.4.5")
        # Should be compatible but with warning about being outdated
        assert is_compatible is False  # Because it's below recommended
        assert len(issues) > 0
        assert "outdated" in issues[0]
    
    def test_test_dependency_functionality_tiktoken(self):
        """Test functionality testing for tiktoken."""
        manager = DependencyManager()
        
        # Mock tiktoken module
        mock_tiktoken = Mock()
        mock_encoding = Mock()
        mock_encoding.encode.return_value = [1, 2, 3]  # Non-empty token list
        mock_tiktoken.get_encoding.return_value = mock_encoding
        
        spec = DEPENDENCY_SPECS["tiktoken"]
        test_passed, error = manager._test_dependency_functionality("tiktoken", mock_tiktoken, spec)
        
        assert test_passed is True
        assert error is None
        mock_tiktoken.get_encoding.assert_called_once_with("cl100k_base")
        mock_encoding.encode.assert_called_once_with("test")
    
    def test_test_dependency_functionality_tiktoken_failure(self):
        """Test functionality testing for tiktoken with failure."""
        manager = DependencyManager()
        
        # Mock tiktoken module that fails
        mock_tiktoken = Mock()
        mock_tiktoken.get_encoding.side_effect = Exception("Encoding not found")
        
        spec = DEPENDENCY_SPECS["tiktoken"]
        test_passed, error = manager._test_dependency_functionality("tiktoken", mock_tiktoken, spec)
        
        assert test_passed is False
        assert "Encoding not found" in error
    
    def test_generate_installation_instructions(self):
        """Test generating installation instructions."""
        manager = DependencyManager()
        
        instructions = manager._generate_installation_instructions("tiktoken")
        
        assert len(instructions) > 0
        assert any("pip install tiktoken" in instr for instr in instructions)
        assert any("conda install" in instr for instr in instructions)
        assert any("import tiktoken" in instr for instr in instructions)
    
    def test_generate_installation_instructions_with_current_version(self):
        """Test generating installation instructions with current version."""
        manager = DependencyManager()
        
        instructions = manager._generate_installation_instructions("tiktoken", current_version="0.3.0")
        
        assert len(instructions) > 0
        assert any("Current version: 0.3.0" in instr for instr in instructions)
        assert any("--upgrade" in instr for instr in instructions)
    
    def test_check_dependency_unknown(self):
        """Test checking unknown dependency."""
        manager = DependencyManager()
        
        status = manager.check_dependency("unknown_dependency")
        
        assert status.name == "unknown_dependency"
        assert status.available is False
        assert "Unknown dependency" in status.import_error
        assert len(status.installation_instructions) > 0
    
    @patch('kano_backlog_core.tokenizer_dependencies.DependencyManager._safe_import')
    def test_check_dependency_import_failure(self, mock_safe_import):
        """Test checking dependency with import failure."""
        mock_safe_import.return_value = None
        
        manager = DependencyManager()
        status = manager.check_dependency("tiktoken")
        
        assert status.name == "tiktoken"
        assert status.available is False
        assert status.import_error is not None
        assert len(status.installation_instructions) > 0
    
    @patch('kano_backlog_core.tokenizer_dependencies.DependencyManager._safe_import')
    @patch('kano_backlog_core.tokenizer_dependencies.DependencyManager._get_module_version')
    @patch('kano_backlog_core.tokenizer_dependencies.DependencyManager._test_dependency_functionality')
    def test_check_dependency_success(self, mock_test_func, mock_get_version, mock_safe_import):
        """Test successful dependency check."""
        # Mock successful import
        mock_module = Mock()
        mock_safe_import.return_value = mock_module
        mock_get_version.return_value = "0.5.0"
        mock_test_func.return_value = (True, None)
        
        manager = DependencyManager()
        status = manager.check_dependency("tiktoken")
        
        assert status.name == "tiktoken"
        assert status.available is True
        assert status.version == "0.5.0"
        assert status.version_compatible is True
        assert status.test_passed is True
        assert status.test_error is None
    
    def test_get_adapter_dependencies(self):
        """Test getting dependencies for specific adapters."""
        manager = DependencyManager()
        
        tiktoken_deps = manager.get_adapter_dependencies("tiktoken")
        assert "tiktoken" in tiktoken_deps
        assert "packaging" in tiktoken_deps  # Required for all
        
        huggingface_deps = manager.get_adapter_dependencies("huggingface")
        assert "transformers" in huggingface_deps
        assert "packaging" in huggingface_deps
    
    @patch('kano_backlog_core.tokenizer_dependencies.DependencyManager.check_dependency')
    def test_check_adapter_readiness_ready(self, mock_check_dep):
        """Test checking adapter readiness when ready."""
        # Mock all dependencies as available and compatible
        def mock_check_side_effect(dep_name):
            return DependencyStatus(
                name=dep_name,
                available=True,
                version_compatible=True,
                test_passed=True
            )
        
        mock_check_dep.side_effect = mock_check_side_effect
        
        manager = DependencyManager()
        is_ready, missing_deps, issues = manager.check_adapter_readiness("tiktoken")
        
        assert is_ready is True
        assert len(missing_deps) == 0
        assert len(issues) == 0
    
    @patch('kano_backlog_core.tokenizer_dependencies.DependencyManager.check_dependency')
    def test_check_adapter_readiness_missing_deps(self, mock_check_dep):
        """Test checking adapter readiness with missing dependencies."""
        def mock_check_side_effect(dep_name):
            if dep_name == "packaging":  # Required dependency
                return DependencyStatus(name=dep_name, available=False)
            else:
                return DependencyStatus(name=dep_name, available=True, version_compatible=True, test_passed=True)
        
        mock_check_dep.side_effect = mock_check_side_effect
        
        manager = DependencyManager()
        is_ready, missing_deps, issues = manager.check_adapter_readiness("tiktoken")
        
        assert is_ready is False
        assert "packaging" in missing_deps
    
    def test_clear_cache(self):
        """Test clearing dependency cache."""
        manager = DependencyManager()
        
        # Add some cached data
        manager._dependency_cache["test"] = DependencyStatus(name="test", available=True)
        manager._import_cache["test"] = Mock()
        manager._last_check_time = 12345.0
        
        manager.clear_cache()
        
        assert len(manager._dependency_cache) == 0
        assert len(manager._import_cache) == 0
        assert manager._last_check_time is None


class TestDependencyManagerIntegration:
    """Integration tests for DependencyManager."""
    
    @patch('kano_backlog_core.tokenizer_dependencies.DependencyManager._safe_import')
    def test_check_all_dependencies_mixed_results(self, mock_safe_import):
        """Test checking all dependencies with mixed results."""
        def import_side_effect(import_name):
            if import_name == "packaging":
                mock_module = Mock()
                mock_module.__version__ = "23.0"
                return mock_module
            elif import_name == "tiktoken":
                return None  # Not available
            elif import_name == "transformers":
                mock_module = Mock()
                mock_module.__version__ = "4.0.0"  # Too old
                return mock_module
            else:
                return None
        
        mock_safe_import.side_effect = import_side_effect
        
        manager = DependencyManager()
        report = manager.check_all_dependencies()
        
        assert isinstance(report, DependencyReport)
        assert len(report.dependencies) == len(DEPENDENCY_SPECS)
        
        # Check specific results
        assert report.dependencies["packaging"].available is True
        assert report.dependencies["tiktoken"].available is False
        assert report.dependencies["transformers"].available is True
        assert report.dependencies["transformers"].version_compatible is False
        
        # Check overall health
        assert report.overall_health in ["degraded", "critical"]
        
        # Check recommendations
        assert len(report.recommendations) > 0
    
    def test_get_installation_summary_format(self):
        """Test installation summary formatting."""
        manager = DependencyManager()
        
        # Mock some missing dependencies
        with patch.object(manager, 'check_all_dependencies') as mock_check_all:
            mock_report = Mock()
            mock_report.get_missing_dependencies.return_value = ["tiktoken", "transformers"]
            mock_report.dependencies = {
                "tiktoken": DependencyStatus(
                    name="tiktoken",
                    available=False,
                    installation_instructions=["pip install tiktoken", "conda install -c conda-forge tiktoken"]
                ),
                "transformers": DependencyStatus(
                    name="transformers",
                    available=False,
                    installation_instructions=["pip install transformers"]
                )
            }
            mock_check_all.return_value = mock_report
            
            summary = manager.get_installation_summary()
            
            assert "📦 Tokenizer Dependencies Installation Guide" in summary
            assert "TIKTOKEN" in summary
            assert "TRANSFORMERS" in summary
            assert "pip install tiktoken" in summary
            assert "pip install transformers" in summary
    
    def test_get_installation_summary_all_available(self):
        """Test installation summary when all dependencies are available."""
        manager = DependencyManager()
        
        with patch.object(manager, 'check_all_dependencies') as mock_check_all:
            mock_report = Mock()
            mock_report.get_missing_dependencies.return_value = []
            mock_check_all.return_value = mock_report
            
            summary = manager.get_installation_summary()
            
            assert "✅ All dependencies are available!" in summary


class TestGlobalFunctions:
    """Test global convenience functions."""
    
    @patch('kano_backlog_core.tokenizer_dependencies._default_dependency_manager')
    def test_check_dependency_global(self, mock_manager):
        """Test global check_dependency function."""
        mock_status = DependencyStatus(name="tiktoken", available=True)
        mock_manager.check_dependency.return_value = mock_status
        
        result = check_dependency("tiktoken")
        
        assert result is mock_status
        mock_manager.check_dependency.assert_called_once_with("tiktoken", False)
    
    @patch('kano_backlog_core.tokenizer_dependencies._default_dependency_manager')
    def test_check_all_dependencies_global(self, mock_manager):
        """Test global check_all_dependencies function."""
        mock_report = Mock()
        mock_manager.check_all_dependencies.return_value = mock_report
        
        result = check_all_dependencies()
        
        assert result is mock_report
        mock_manager.check_all_dependencies.assert_called_once_with(False)
    
    @patch('kano_backlog_core.tokenizer_dependencies._default_dependency_manager')
    def test_get_installation_summary_global(self, mock_manager):
        """Test global get_installation_summary function."""
        mock_summary = "Test summary"
        mock_manager.get_installation_summary.return_value = mock_summary
        
        result = get_installation_summary()
        
        assert result == mock_summary
        mock_manager.get_installation_summary.assert_called_once()
    
    @patch('kano_backlog_core.tokenizer_dependencies._default_dependency_manager')
    def test_check_adapter_readiness_global(self, mock_manager):
        """Test global check_adapter_readiness function."""
        mock_result = (True, [], [])
        mock_manager.check_adapter_readiness.return_value = mock_result
        
        result = check_adapter_readiness("tiktoken")
        
        assert result == mock_result
        mock_manager.check_adapter_readiness.assert_called_once_with("tiktoken")


class TestVersionCompatibility:
    """Test version compatibility checking logic."""
    
    def test_version_parsing_edge_cases(self):
        """Test version parsing with edge cases."""
        manager = DependencyManager()
        
        # Test with pre-release versions
        is_compatible, issues = manager._check_version_compatibility("tiktoken", "0.5.0rc1")
        # Should handle pre-release versions gracefully
        assert isinstance(is_compatible, bool)
        assert isinstance(issues, list)
        
        # Test with development versions
        is_compatible, issues = manager._check_version_compatibility("tiktoken", "0.5.0.dev0")
        assert isinstance(is_compatible, bool)
        assert isinstance(issues, list)
    
    def test_python_version_compatibility(self):
        """Test Python version compatibility checking."""
        manager = DependencyManager()
        
        # Test current Python version (should be compatible)
        is_compatible = manager._check_python_compatibility()
        assert isinstance(is_compatible, bool)
        
        # The actual result depends on the Python version running the tests,
        # but it should not raise an exception


class TestErrorHandling:
    """Test error handling in dependency management."""
    
    def test_malformed_version_handling(self):
        """Test handling of malformed version strings."""
        manager = DependencyManager()
        
        # Test with invalid version string
        is_compatible, issues = manager._check_version_compatibility("tiktoken", "invalid.version")
        assert is_compatible is False
        assert len(issues) > 0
        assert "Failed to parse version" in issues[0]
    
    @patch('kano_backlog_core.tokenizer_dependencies.DependencyManager._safe_import')
    def test_import_exception_handling(self, mock_safe_import):
        """Test handling of unexpected import exceptions."""
        # Mock an unexpected exception during import
        mock_safe_import.side_effect = RuntimeError("Unexpected error")
        
        manager = DependencyManager()
        status = manager.check_dependency("tiktoken")
        
        assert status.available is False
        assert "Unexpected error" in status.import_error
    
    def test_functionality_test_exception_handling(self):
        """Test handling of exceptions during functionality testing."""
        manager = DependencyManager()
        
        # Mock module that raises exception during testing
        mock_module = Mock()
        mock_module.get_encoding.side_effect = RuntimeError("Test error")
        
        spec = DEPENDENCY_SPECS["tiktoken"]
        test_passed, error = manager._test_dependency_functionality("tiktoken", mock_module, spec)
        
        assert test_passed is False
        assert "Test error" in error


class TestPerformanceAndCaching:
    """Test performance characteristics and caching behavior."""
    
    def test_dependency_caching(self):
        """Test that dependency checks are cached."""
        manager = DependencyManager()
        
        with patch.object(manager, '_safe_import') as mock_import:
            mock_import.return_value = None
            
            # First check
            status1 = manager.check_dependency("tiktoken")
            
            # Second check should use cache
            status2 = manager.check_dependency("tiktoken")
            
            # Should only call _safe_import once due to caching
            assert mock_import.call_count == 1
            assert status1 is status2  # Same object from cache
    
    def test_force_refresh_bypasses_cache(self):
        """Test that force_refresh bypasses cache."""
        manager = DependencyManager()
        
        with patch.object(manager, '_safe_import') as mock_import:
            mock_import.return_value = None
            
            # First check
            manager.check_dependency("tiktoken")
            
            # Force refresh should bypass cache
            manager.check_dependency("tiktoken", force_refresh=True)
            
            # Should call _safe_import twice
            assert mock_import.call_count == 2
    
    def test_import_caching(self):
        """Test that successful imports are cached."""
        manager = DependencyManager()
        
        # Import the same module twice
        module1 = manager._safe_import("sys")
        module2 = manager._safe_import("sys")
        
        # Should return the same cached object
        assert module1 is module2
        assert module1 is sys