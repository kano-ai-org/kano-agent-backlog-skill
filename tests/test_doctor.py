"""
Tests for the doctor command.

Feature: release-0-1-0-beta
"""

import sys
from unittest.mock import patch, MagicMock

import pytest

from kano_backlog_cli.commands.doctor import check_python_version, check_sqlite_availability


class TestPythonVersionCheck:
    """Tests for Python version checking."""

    def test_python_version_meets_requirements(self):
        """Test that current Python version passes the check."""
        # Current Python should be >= 3.8 if tests are running
        result = check_python_version()
        
        assert result.name == "Python Version"
        assert result.passed is True
        assert "meets requirements" in result.message
        assert ">= 3.8" in result.message

    def test_python_version_below_minimum(self):
        """Test that Python version below 3.8 fails the check."""
        # Mock sys.version_info to simulate Python 3.7
        with patch.object(sys, 'version_info', (3, 7, 0, 'final', 0)):
            result = check_python_version()
            
            assert result.name == "Python Version"
            assert result.passed is False
            assert "below minimum required version" in result.message
            assert "Current: Python 3.7" in result.details
            assert "Required: Python 3.8+" in result.details

    def test_python_version_exactly_minimum(self):
        """Test that Python 3.8 exactly passes the check."""
        # Mock sys.version_info to simulate Python 3.8
        with patch.object(sys, 'version_info', (3, 8, 0, 'final', 0)):
            result = check_python_version()
            
            assert result.name == "Python Version"
            assert result.passed is True
            assert "Python 3.8 meets requirements" in result.message

    def test_python_version_above_minimum(self):
        """Test that Python versions above 3.8 pass the check."""
        # Mock sys.version_info to simulate Python 3.12
        with patch.object(sys, 'version_info', (3, 12, 0, 'final', 0)):
            result = check_python_version()
            
            assert result.name == "Python Version"
            assert result.passed is True
            assert "Python 3.12 meets requirements" in result.message

    def test_python_version_reports_current_and_required(self):
        """Test that the check reports both current and required versions."""
        result = check_python_version()
        
        # Should contain version information
        current_version = f"{sys.version_info[0]}.{sys.version_info[1]}"
        assert current_version in result.message
        assert "3.8" in result.message



class TestSQLiteAvailabilityCheck:
    """Tests for SQLite availability checking."""

    def test_sqlite_available_and_meets_requirements(self):
        """Test that SQLite is available and meets version requirements."""
        # Current environment should have SQLite >= 3.8.0
        result = check_sqlite_availability()
        
        assert result.name == "SQLite Availability"
        assert result.passed is True
        assert "available" in result.message
        assert ">= 3.8.0" in result.message

    def test_sqlite_missing(self):
        """Test that missing SQLite is detected."""
        # Mock ImportError when importing sqlite3
        with patch('builtins.__import__', side_effect=ImportError("No module named 'sqlite3'")):
            result = check_sqlite_availability()
            
            assert result.name == "SQLite Availability"
            assert result.passed is False
            assert "not available" in result.message
            assert "required for ID sequence management" in result.details

    def test_sqlite_version_below_minimum(self):
        """Test that SQLite version below 3.8.0 fails the check."""
        # Mock sqlite3 module with old version
        mock_sqlite3 = MagicMock()
        mock_sqlite3.sqlite_version = "3.7.5"
        
        with patch.dict('sys.modules', {'sqlite3': mock_sqlite3}):
            result = check_sqlite_availability()
            
            assert result.name == "SQLite Availability"
            assert result.passed is False
            assert "below minimum required version" in result.message
            assert "Current: SQLite 3.7.5" in result.details
            assert "Required: SQLite 3.8.0+" in result.details

    def test_sqlite_version_exactly_minimum(self):
        """Test that SQLite 3.8.0 exactly passes the check."""
        # Mock sqlite3 module with minimum version
        mock_sqlite3 = MagicMock()
        mock_sqlite3.sqlite_version = "3.8.0"
        
        with patch.dict('sys.modules', {'sqlite3': mock_sqlite3}):
            result = check_sqlite_availability()
            
            assert result.name == "SQLite Availability"
            assert result.passed is True
            assert "SQLite 3.8.0 available" in result.message

    def test_sqlite_version_above_minimum(self):
        """Test that SQLite versions above 3.8.0 pass the check."""
        # Mock sqlite3 module with newer version
        mock_sqlite3 = MagicMock()
        mock_sqlite3.sqlite_version = "3.35.5"
        
        with patch.dict('sys.modules', {'sqlite3': mock_sqlite3}):
            result = check_sqlite_availability()
            
            assert result.name == "SQLite Availability"
            assert result.passed is True
            assert "SQLite 3.35.5 available" in result.message

    def test_sqlite_version_check_error(self):
        """Test that errors during version checking are handled."""
        # Mock sqlite3 module that raises an error when accessing version
        mock_sqlite3 = MagicMock()
        mock_sqlite3.sqlite_version = property(lambda self: (_ for _ in ()).throw(RuntimeError("Version error")))
        
        with patch.dict('sys.modules', {'sqlite3': mock_sqlite3}):
            result = check_sqlite_availability()
            
            assert result.name == "SQLite Availability"
            assert result.passed is False
            assert "Failed to check SQLite version" in result.message

    def test_sqlite_version_parsing_handles_short_versions(self):
        """Test that version parsing handles versions with fewer parts."""
        # Mock sqlite3 module with short version string
        mock_sqlite3 = MagicMock()
        mock_sqlite3.sqlite_version = "3.35"
        
        with patch.dict('sys.modules', {'sqlite3': mock_sqlite3}):
            result = check_sqlite_availability()
            
            assert result.name == "SQLite Availability"
            assert result.passed is True
            assert "SQLite 3.35 available" in result.message


class TestBacklogStructureCheck:
    """Tests for backlog structure checking."""

    def test_backlog_root_not_found(self, tmp_path):
        """Test that missing backlog root is detected."""
        from kano_backlog_cli.commands.doctor import check_backlog_structure
        
        nonexistent = tmp_path / "nonexistent"
        result = check_backlog_structure(backlog_root=nonexistent)
        
        assert result.name == "Backlog Structure"
        assert result.passed is False
        assert "not found" in result.message.lower()
        assert "kano-backlog admin init" in result.details

    def test_missing_products_directory(self, tmp_path):
        """Test that missing products directory is detected."""
        from kano_backlog_cli.commands.doctor import check_backlog_structure
        
        backlog_root = tmp_path / "backlog"
        backlog_root.mkdir()
        
        result = check_backlog_structure(backlog_root=backlog_root)
        
        assert result.name == "Backlog Structure"
        assert result.passed is False
        assert "products" in result.message.lower()
        assert "missing required directories" in result.message.lower()

    def test_empty_products_directory(self, tmp_path):
        """Test that empty products directory is detected."""
        from kano_backlog_cli.commands.doctor import check_backlog_structure
        
        backlog_root = tmp_path / "backlog"
        backlog_root.mkdir()
        (backlog_root / "products").mkdir()
        
        result = check_backlog_structure(backlog_root=backlog_root)
        
        assert result.name == "Backlog Structure"
        assert result.passed is False
        assert "no products" in result.message.lower()
        assert "kano-backlog admin init" in result.details

    def test_product_missing_items_directory(self, tmp_path):
        """Test that product missing items directory is detected."""
        from kano_backlog_cli.commands.doctor import check_backlog_structure
        
        backlog_root = tmp_path / "backlog"
        backlog_root.mkdir()
        products_dir = backlog_root / "products"
        products_dir.mkdir()
        product_dir = products_dir / "test-product"
        product_dir.mkdir()
        (product_dir / "decisions").mkdir()
        (product_dir / "_meta").mkdir()
        
        result = check_backlog_structure(backlog_root=backlog_root)
        
        assert result.name == "Backlog Structure"
        assert result.passed is False
        assert "missing directories" in result.message.lower()
        assert "items" in result.message.lower()

    def test_product_missing_decisions_directory(self, tmp_path):
        """Test that product missing decisions directory is detected."""
        from kano_backlog_cli.commands.doctor import check_backlog_structure
        
        backlog_root = tmp_path / "backlog"
        backlog_root.mkdir()
        products_dir = backlog_root / "products"
        products_dir.mkdir()
        product_dir = products_dir / "test-product"
        product_dir.mkdir()
        (product_dir / "items").mkdir()
        (product_dir / "_meta").mkdir()
        
        result = check_backlog_structure(backlog_root=backlog_root)
        
        assert result.name == "Backlog Structure"
        assert result.passed is False
        assert "missing directories" in result.message.lower()
        assert "decisions" in result.message.lower()

    def test_product_missing_meta_directory(self, tmp_path):
        """Test that product missing _meta directory is detected."""
        from kano_backlog_cli.commands.doctor import check_backlog_structure
        
        backlog_root = tmp_path / "backlog"
        backlog_root.mkdir()
        products_dir = backlog_root / "products"
        products_dir.mkdir()
        product_dir = products_dir / "test-product"
        product_dir.mkdir()
        (product_dir / "items").mkdir()
        (product_dir / "decisions").mkdir()
        
        result = check_backlog_structure(backlog_root=backlog_root)
        
        assert result.name == "Backlog Structure"
        assert result.passed is False
        assert "missing directories" in result.message.lower()
        assert "_meta" in result.message.lower()

    def test_product_missing_multiple_directories(self, tmp_path):
        """Test that product missing multiple directories is detected."""
        from kano_backlog_cli.commands.doctor import check_backlog_structure
        
        backlog_root = tmp_path / "backlog"
        backlog_root.mkdir()
        products_dir = backlog_root / "products"
        products_dir.mkdir()
        product_dir = products_dir / "test-product"
        product_dir.mkdir()
        
        result = check_backlog_structure(backlog_root=backlog_root)
        
        assert result.name == "Backlog Structure"
        assert result.passed is False
        assert "missing directories" in result.message.lower()
        # Should mention all three missing directories
        assert "items" in result.message.lower()
        assert "decisions" in result.message.lower()
        assert "_meta" in result.message.lower()

    def test_valid_backlog_structure_single_product(self, tmp_path):
        """Test that valid backlog structure with one product passes."""
        from kano_backlog_cli.commands.doctor import check_backlog_structure
        
        backlog_root = tmp_path / "backlog"
        backlog_root.mkdir()
        products_dir = backlog_root / "products"
        products_dir.mkdir()
        product_dir = products_dir / "test-product"
        product_dir.mkdir()
        (product_dir / "items").mkdir()
        (product_dir / "decisions").mkdir()
        (product_dir / "_meta").mkdir()
        
        result = check_backlog_structure(backlog_root=backlog_root)
        
        assert result.name == "Backlog Structure"
        assert result.passed is True
        assert "valid" in result.message.lower()
        assert "1 product" in result.message.lower()
        assert "test-product" in result.message

    def test_valid_backlog_structure_multiple_products(self, tmp_path):
        """Test that valid backlog structure with multiple products passes."""
        from kano_backlog_cli.commands.doctor import check_backlog_structure
        
        backlog_root = tmp_path / "backlog"
        backlog_root.mkdir()
        products_dir = backlog_root / "products"
        products_dir.mkdir()
        
        # Create two products
        for product_name in ["product-a", "product-b"]:
            product_dir = products_dir / product_name
            product_dir.mkdir()
            (product_dir / "items").mkdir()
            (product_dir / "decisions").mkdir()
            (product_dir / "_meta").mkdir()
        
        result = check_backlog_structure(backlog_root=backlog_root)
        
        assert result.name == "Backlog Structure"
        assert result.passed is True
        assert "valid" in result.message.lower()
        assert "2 product" in result.message.lower()

    def test_ignores_hidden_directories_in_products(self, tmp_path):
        """Test that hidden directories (starting with _) are ignored."""
        from kano_backlog_cli.commands.doctor import check_backlog_structure
        
        backlog_root = tmp_path / "backlog"
        backlog_root.mkdir()
        products_dir = backlog_root / "products"
        products_dir.mkdir()
        
        # Create a hidden directory (should be ignored)
        (products_dir / "_hidden").mkdir()
        
        # Create a valid product
        product_dir = products_dir / "test-product"
        product_dir.mkdir()
        (product_dir / "items").mkdir()
        (product_dir / "decisions").mkdir()
        (product_dir / "_meta").mkdir()
        
        result = check_backlog_structure(backlog_root=backlog_root)
        
        assert result.name == "Backlog Structure"
        assert result.passed is True
        assert "1 product" in result.message.lower()
        assert "_hidden" not in result.message

    def test_provides_fix_command_in_details(self, tmp_path):
        """Test that error messages provide actionable fix commands."""
        from kano_backlog_cli.commands.doctor import check_backlog_structure
        
        backlog_root = tmp_path / "backlog"
        backlog_root.mkdir()
        products_dir = backlog_root / "products"
        products_dir.mkdir()
        product_dir = products_dir / "test-product"
        product_dir.mkdir()
        
        result = check_backlog_structure(backlog_root=backlog_root)
        
        assert result.name == "Backlog Structure"
        assert result.passed is False
        assert result.details is not None
        assert "kano-backlog admin init" in result.details
        assert "--force" in result.details
        assert "test-product" in result.details


class TestConfigurationValidityCheck:
    """Tests for configuration validity checking."""

    def test_no_backlog_root_skips_check(self, tmp_path):
        """Test that missing backlog root skips the check."""
        from kano_backlog_cli.commands.doctor import check_configuration_validity
        
        nonexistent = tmp_path / "nonexistent"
        result = check_configuration_validity(backlog_root=nonexistent)
        
        assert result.name == "Configuration Validity"
        assert result.passed is True
        assert "skipping" in result.message.lower()

    def test_valid_toml_defaults_passes(self, tmp_path):
        """Test that valid TOML defaults file passes."""
        from kano_backlog_cli.commands.doctor import check_configuration_validity
        
        backlog_root = tmp_path / "backlog"
        backlog_root.mkdir()
        shared_dir = backlog_root / "_shared"
        shared_dir.mkdir()
        
        # Create valid TOML defaults
        defaults_toml = shared_dir / "defaults.toml"
        defaults_toml.write_text('[log]\nverbosity = "info"\n', encoding="utf-8")
        
        # Create minimal project config
        project_root = backlog_root.parent.parent
        kano_dir = project_root / ".kano"
        kano_dir.mkdir(parents=True, exist_ok=True)
        project_config = kano_dir / "backlog_config.toml"
        project_config.write_text(
            '[products.test]\nname = "test"\nprefix = "TST"\nbacklog_root = "_kano/backlog/products/test"\n',
            encoding="utf-8"
        )
        
        result = check_configuration_validity(backlog_root=backlog_root)
        
        assert result.name == "Configuration Validity"
        assert result.passed is True
        assert "valid" in result.message.lower()

    def test_invalid_toml_syntax_fails(self, tmp_path):
        """Test that invalid TOML syntax is detected."""
        from kano_backlog_cli.commands.doctor import check_configuration_validity
        
        backlog_root = tmp_path / "backlog"
        backlog_root.mkdir()
        shared_dir = backlog_root / "_shared"
        shared_dir.mkdir()
        
        # Create invalid TOML
        defaults_toml = shared_dir / "defaults.toml"
        defaults_toml.write_text('[log\nverbosity = "info"\n', encoding="utf-8")  # Missing closing bracket
        
        # Create minimal project config
        project_root = backlog_root.parent.parent
        kano_dir = project_root / ".kano"
        kano_dir.mkdir(parents=True, exist_ok=True)
        project_config = kano_dir / "backlog_config.toml"
        project_config.write_text(
            '[products.test]\nname = "test"\nprefix = "TST"\nbacklog_root = "_kano/backlog/products/test"\n',
            encoding="utf-8"
        )
        
        result = check_configuration_validity(backlog_root=backlog_root)
        
        assert result.name == "Configuration Validity"
        assert result.passed is False
        assert "error" in result.message.lower()
        assert "defaults.toml" in result.details
        assert "Invalid TOML syntax" in result.details

    def test_invalid_json_syntax_fails(self, tmp_path):
        """Test that invalid JSON syntax is detected."""
        from kano_backlog_cli.commands.doctor import check_configuration_validity
        
        backlog_root = tmp_path / "backlog"
        backlog_root.mkdir()
        shared_dir = backlog_root / "_shared"
        shared_dir.mkdir()
        
        # Create invalid JSON
        defaults_json = shared_dir / "defaults.json"
        defaults_json.write_text('{"log": {"verbosity": "info"', encoding="utf-8")  # Missing closing braces
        
        # Create minimal project config
        project_root = backlog_root.parent.parent
        kano_dir = project_root / ".kano"
        kano_dir.mkdir(parents=True, exist_ok=True)
        project_config = kano_dir / "backlog_config.toml"
        project_config.write_text(
            '[products.test]\nname = "test"\nprefix = "TST"\nbacklog_root = "_kano/backlog/products/test"\n',
            encoding="utf-8"
        )
        
        result = check_configuration_validity(backlog_root=backlog_root)
        
        assert result.name == "Configuration Validity"
        assert result.passed is False
        assert "error" in result.message.lower()
        assert "defaults.json" in result.details
        assert "Invalid JSON syntax" in result.details
        assert "line" in result.details

    def test_json_config_shows_deprecation_warning(self, tmp_path):
        """Test that JSON config shows deprecation warning."""
        from kano_backlog_cli.commands.doctor import check_configuration_validity
        
        backlog_root = tmp_path / "backlog"
        backlog_root.mkdir()
        shared_dir = backlog_root / "_shared"
        shared_dir.mkdir()
        
        # Create valid JSON
        defaults_json = shared_dir / "defaults.json"
        defaults_json.write_text('{"log": {"verbosity": "info"}}', encoding="utf-8")
        
        # Create minimal project config
        project_root = backlog_root.parent.parent
        kano_dir = project_root / ".kano"
        kano_dir.mkdir(parents=True, exist_ok=True)
        project_config = kano_dir / "backlog_config.toml"
        project_config.write_text(
            '[products.test]\nname = "test"\nprefix = "TST"\nbacklog_root = "_kano/backlog/products/test"\n',
            encoding="utf-8"
        )
        
        result = check_configuration_validity(backlog_root=backlog_root)
        
        assert result.name == "Configuration Validity"
        assert result.passed is True
        assert "warning" in result.message.lower()
        assert "deprecated" in result.details.lower()

    def test_missing_project_config_fails(self, tmp_path):
        """Test that missing project config is detected."""
        from kano_backlog_cli.commands.doctor import check_configuration_validity
        
        # Create proper structure: tmp_path/_kano/backlog
        backlog_root = tmp_path / "_kano" / "backlog"
        backlog_root.mkdir(parents=True)
        
        result = check_configuration_validity(backlog_root=backlog_root)
        
        assert result.name == "Configuration Validity"
        assert result.passed is False
        assert "error" in result.message.lower()
        assert "backlog_config.toml" in result.details
        assert "not found" in result.details

    def test_project_config_missing_products_table_fails(self, tmp_path):
        """Test that project config without products table fails."""
        from kano_backlog_cli.commands.doctor import check_configuration_validity
        
        backlog_root = tmp_path / "backlog"
        backlog_root.mkdir()
        
        # Create project config without products table
        project_root = backlog_root.parent.parent
        kano_dir = project_root / ".kano"
        kano_dir.mkdir(parents=True, exist_ok=True)
        project_config = kano_dir / "backlog_config.toml"
        project_config.write_text('[log]\nverbosity = "info"\n', encoding="utf-8")
        
        result = check_configuration_validity(backlog_root=backlog_root)
        
        assert result.name == "Configuration Validity"
        assert result.passed is False
        assert "error" in result.message.lower()
        assert "products" in result.details.lower()

    def test_product_missing_required_fields_fails(self, tmp_path):
        """Test that product missing required fields fails."""
        from kano_backlog_cli.commands.doctor import check_configuration_validity
        
        backlog_root = tmp_path / "backlog"
        backlog_root.mkdir()
        
        # Create project config with incomplete product
        project_root = backlog_root.parent.parent
        kano_dir = project_root / ".kano"
        kano_dir.mkdir(parents=True, exist_ok=True)
        project_config = kano_dir / "backlog_config.toml"
        project_config.write_text(
            '[products.test]\nname = "test"\n',  # Missing prefix and backlog_root
            encoding="utf-8"
        )
        
        result = check_configuration_validity(backlog_root=backlog_root)
        
        assert result.name == "Configuration Validity"
        assert result.passed is False
        assert "error" in result.message.lower()
        assert "prefix" in result.details.lower()
        assert "backlog_root" in result.details.lower()

    def test_product_config_json_shows_deprecation_warning(self, tmp_path):
        """Test that product-specific config.json shows deprecation warning."""
        from kano_backlog_cli.commands.doctor import check_configuration_validity
        
        backlog_root = tmp_path / "backlog"
        backlog_root.mkdir()
        products_dir = backlog_root / "products"
        products_dir.mkdir()
        product_dir = products_dir / "test-product"
        product_dir.mkdir()
        config_dir = product_dir / "_config"
        config_dir.mkdir()
        
        # Create product config.json
        config_json = config_dir / "config.json"
        config_json.write_text(
            '{"project": {"name": "test-product", "prefix": "TST"}}',
            encoding="utf-8"
        )
        
        # Create minimal project config
        project_root = backlog_root.parent.parent
        kano_dir = project_root / ".kano"
        kano_dir.mkdir(parents=True, exist_ok=True)
        project_config = kano_dir / "backlog_config.toml"
        project_config.write_text(
            '[products.test]\nname = "test"\nprefix = "TST"\nbacklog_root = "_kano/backlog/products/test"\n',
            encoding="utf-8"
        )
        
        result = check_configuration_validity(backlog_root=backlog_root)
        
        assert result.name == "Configuration Validity"
        assert result.passed is True
        assert "warning" in result.message.lower()
        assert "deprecated" in result.details.lower()
        assert "migrate" in result.details.lower()

    def test_product_config_json_missing_required_fields_fails(self, tmp_path):
        """Test that product config.json missing required fields fails."""
        from kano_backlog_cli.commands.doctor import check_configuration_validity
        
        backlog_root = tmp_path / "backlog"
        backlog_root.mkdir()
        products_dir = backlog_root / "products"
        products_dir.mkdir()
        product_dir = products_dir / "test-product"
        product_dir.mkdir()
        config_dir = product_dir / "_config"
        config_dir.mkdir()
        
        # Create incomplete product config.json
        config_json = config_dir / "config.json"
        config_json.write_text(
            '{"project": {"name": "test-product"}}',  # Missing prefix
            encoding="utf-8"
        )
        
        # Create minimal project config
        project_root = backlog_root.parent.parent
        kano_dir = project_root / ".kano"
        kano_dir.mkdir(parents=True, exist_ok=True)
        project_config = kano_dir / "backlog_config.toml"
        project_config.write_text(
            '[products.test]\nname = "test"\nprefix = "TST"\nbacklog_root = "_kano/backlog/products/test"\n',
            encoding="utf-8"
        )
        
        result = check_configuration_validity(backlog_root=backlog_root)
        
        assert result.name == "Configuration Validity"
        assert result.passed is False
        assert "error" in result.message.lower()
        assert "prefix" in result.details.lower()

    def test_multiple_errors_reported(self, tmp_path):
        """Test that multiple configuration errors are reported."""
        from kano_backlog_cli.commands.doctor import check_configuration_validity
        
        backlog_root = tmp_path / "backlog"
        backlog_root.mkdir()
        shared_dir = backlog_root / "_shared"
        shared_dir.mkdir()
        
        # Create invalid TOML
        defaults_toml = shared_dir / "defaults.toml"
        defaults_toml.write_text('[log\n', encoding="utf-8")  # Invalid syntax
        
        # Create invalid JSON
        defaults_json = shared_dir / "defaults.json"
        defaults_json.write_text('{"invalid"', encoding="utf-8")  # Invalid syntax
        
        # Create minimal project config
        project_root = backlog_root.parent.parent
        kano_dir = project_root / ".kano"
        kano_dir.mkdir(parents=True, exist_ok=True)
        project_config = kano_dir / "backlog_config.toml"
        project_config.write_text(
            '[products.test]\nname = "test"\nprefix = "TST"\nbacklog_root = "_kano/backlog/products/test"\n',
            encoding="utf-8"
        )
        
        result = check_configuration_validity(backlog_root=backlog_root)
        
        assert result.name == "Configuration Validity"
        assert result.passed is False
        assert "2" in result.message or "error" in result.message.lower()
        assert "defaults.toml" in result.details
        assert "defaults.json" in result.details



class TestPermissionsCheck:
    """Tests for permissions checking."""

    def test_no_backlog_root_skips_check(self, tmp_path):
        """Test that missing backlog root skips the check."""
        from kano_backlog_cli.commands.doctor import check_permissions
        
        nonexistent = tmp_path / "nonexistent"
        result = check_permissions(backlog_root=nonexistent)
        
        assert result.name == "Permissions"
        assert result.passed is True
        assert "skipping" in result.message.lower()

    def test_writable_backlog_root_passes(self, tmp_path):
        """Test that writable backlog root passes."""
        from kano_backlog_cli.commands.doctor import check_permissions
        
        backlog_root = tmp_path / "backlog"
        backlog_root.mkdir()
        
        result = check_permissions(backlog_root=backlog_root)
        
        assert result.name == "Permissions"
        assert result.passed is True
        assert "OK" in result.message or "ok" in result.message.lower()

    def test_writable_products_directory_passes(self, tmp_path):
        """Test that writable products directory passes."""
        from kano_backlog_cli.commands.doctor import check_permissions
        
        backlog_root = tmp_path / "backlog"
        backlog_root.mkdir()
        products_dir = backlog_root / "products"
        products_dir.mkdir()
        
        result = check_permissions(backlog_root=backlog_root)
        
        assert result.name == "Permissions"
        assert result.passed is True
        assert "2 directories" in result.message or "2 director" in result.message

    def test_writable_product_directories_pass(self, tmp_path):
        """Test that writable product directories pass."""
        from kano_backlog_cli.commands.doctor import check_permissions
        
        backlog_root = tmp_path / "backlog"
        backlog_root.mkdir()
        products_dir = backlog_root / "products"
        products_dir.mkdir()
        product_dir = products_dir / "test-product"
        product_dir.mkdir()
        (product_dir / "items").mkdir()
        (product_dir / "decisions").mkdir()
        (product_dir / "_meta").mkdir()
        
        result = check_permissions(backlog_root=backlog_root)
        
        assert result.name == "Permissions"
        assert result.passed is True
        # Should check: backlog_root, products, product, items, decisions, _meta = 6 directories
        assert "6 directories" in result.message or "6 director" in result.message

    def test_multiple_products_all_checked(self, tmp_path):
        """Test that multiple products are all checked."""
        from kano_backlog_cli.commands.doctor import check_permissions
        
        backlog_root = tmp_path / "backlog"
        backlog_root.mkdir()
        products_dir = backlog_root / "products"
        products_dir.mkdir()
        
        # Create two products
        for product_name in ["product-a", "product-b"]:
            product_dir = products_dir / product_name
            product_dir.mkdir()
            (product_dir / "items").mkdir()
            (product_dir / "decisions").mkdir()
            (product_dir / "_meta").mkdir()
        
        result = check_permissions(backlog_root=backlog_root)
        
        assert result.name == "Permissions"
        assert result.passed is True
        # Should check: backlog_root, products, 2 products, 6 subdirs = 10 directories
        assert "10 directories" in result.message or "10 director" in result.message

    def test_ignores_hidden_directories(self, tmp_path):
        """Test that hidden directories (starting with _) are ignored."""
        from kano_backlog_cli.commands.doctor import check_permissions
        
        backlog_root = tmp_path / "backlog"
        backlog_root.mkdir()
        products_dir = backlog_root / "products"
        products_dir.mkdir()
        
        # Create a hidden directory (should be ignored)
        (products_dir / "_hidden").mkdir()
        
        # Create a valid product
        product_dir = products_dir / "test-product"
        product_dir.mkdir()
        (product_dir / "items").mkdir()
        (product_dir / "decisions").mkdir()
        (product_dir / "_meta").mkdir()
        
        result = check_permissions(backlog_root=backlog_root)
        
        assert result.name == "Permissions"
        assert result.passed is True
        # Should check: backlog_root, products, product, items, decisions, _meta = 6 directories
        # _hidden should be ignored
        assert "6 directories" in result.message or "6 director" in result.message

    def test_read_only_directory_fails(self, tmp_path):
        """Test that read-only directory is detected."""
        from kano_backlog_cli.commands.doctor import check_permissions
        import os
        import stat
        import sys
        
        # Skip on Windows as chmod doesn't work the same way
        if sys.platform == "win32":
            pytest.skip("chmod-based permission tests don't work reliably on Windows")
        
        backlog_root = tmp_path / "backlog"
        backlog_root.mkdir()
        
        # Make directory read-only
        try:
            # Remove write permissions
            current_mode = os.stat(backlog_root).st_mode
            os.chmod(backlog_root, current_mode & ~stat.S_IWUSR & ~stat.S_IWGRP & ~stat.S_IWOTH)
            
            result = check_permissions(backlog_root=backlog_root)
            
            assert result.name == "Permissions"
            assert result.passed is False
            assert "permission" in result.message.lower()
            assert "Backlog root" in result.details
            
        finally:
            # Restore write permissions for cleanup
            try:
                os.chmod(backlog_root, current_mode)
            except:
                pass

    def test_permission_error_provides_recommendations(self, tmp_path):
        """Test that permission errors provide actionable recommendations."""
        from kano_backlog_cli.commands.doctor import check_permissions
        import os
        import stat
        import sys
        
        # Skip on Windows as chmod doesn't work the same way
        if sys.platform == "win32":
            pytest.skip("chmod-based permission tests don't work reliably on Windows")
        
        backlog_root = tmp_path / "backlog"
        backlog_root.mkdir()
        
        # Make directory read-only
        try:
            current_mode = os.stat(backlog_root).st_mode
            os.chmod(backlog_root, current_mode & ~stat.S_IWUSR & ~stat.S_IWGRP & ~stat.S_IWOTH)
            
            result = check_permissions(backlog_root=backlog_root)
            
            assert result.name == "Permissions"
            assert result.passed is False
            assert result.details is not None
            assert "Recommendations" in result.details
            assert "chmod" in result.details or "permissions" in result.details.lower()
            
        finally:
            # Restore write permissions for cleanup
            try:
                os.chmod(backlog_root, current_mode)
            except:
                pass

    def test_partial_permission_issues_reported(self, tmp_path):
        """Test that partial permission issues are reported correctly."""
        from kano_backlog_cli.commands.doctor import check_permissions
        import os
        import stat
        import sys
        
        # Skip on Windows as chmod doesn't work the same way
        if sys.platform == "win32":
            pytest.skip("chmod-based permission tests don't work reliably on Windows")
        
        backlog_root = tmp_path / "backlog"
        backlog_root.mkdir()
        products_dir = backlog_root / "products"
        products_dir.mkdir()
        product_dir = products_dir / "test-product"
        product_dir.mkdir()
        items_dir = product_dir / "items"
        items_dir.mkdir()
        
        # Make only items directory read-only
        try:
            current_mode = os.stat(items_dir).st_mode
            os.chmod(items_dir, current_mode & ~stat.S_IWUSR & ~stat.S_IWGRP & ~stat.S_IWOTH)
            
            result = check_permissions(backlog_root=backlog_root)
            
            assert result.name == "Permissions"
            assert result.passed is False
            assert "1 directory" in result.message or "1 director" in result.message
            assert "items" in result.details.lower()
            
        finally:
            # Restore write permissions for cleanup
            try:
                os.chmod(items_dir, current_mode)
            except:
                pass

    def test_reports_directory_paths_in_errors(self, tmp_path):
        """Test that error messages include directory paths."""
        from kano_backlog_cli.commands.doctor import check_permissions
        import os
        import stat
        import sys
        
        # Skip on Windows as chmod doesn't work the same way
        if sys.platform == "win32":
            pytest.skip("chmod-based permission tests don't work reliably on Windows")
        
        backlog_root = tmp_path / "backlog"
        backlog_root.mkdir()
        
        # Make directory read-only
        try:
            current_mode = os.stat(backlog_root).st_mode
            os.chmod(backlog_root, current_mode & ~stat.S_IWUSR & ~stat.S_IWGRP & ~stat.S_IWOTH)
            
            result = check_permissions(backlog_root=backlog_root)
            
            assert result.name == "Permissions"
            assert result.passed is False
            assert str(backlog_root) in result.details
            
        finally:
            # Restore write permissions for cleanup
            try:
                os.chmod(backlog_root, current_mode)
            except:
                pass



class TestOptionalDependenciesCheck:
    """Tests for optional dependencies checking."""

    def test_all_groups_installed(self):
        """Test when all optional dependency groups are installed."""
        from kano_backlog_cli.commands.doctor import check_optional_dependencies
        from unittest.mock import patch
        
        # Mock all packages as installed
        def mock_import(name):
            if name in ["pytest", "black", "mypy", "isort", "sentence_transformers", "faiss"]:
                return MagicMock()
            raise ImportError(f"No module named '{name}'")
        
        with patch('builtins.__import__', side_effect=mock_import):
            result = check_optional_dependencies()
            
            assert result.name == "Optional Dependencies"
            assert result.passed is True
            assert "all optional groups installed" in result.message.lower()
            assert "dev" in result.message
            assert "vector" in result.message

    def test_no_groups_installed(self):
        """Test when no optional dependency groups are installed."""
        from kano_backlog_cli.commands.doctor import check_optional_dependencies
        from unittest.mock import patch
        
        # Mock all packages as not installed
        def mock_import(name):
            raise ImportError(f"No module named '{name}'")
        
        with patch('builtins.__import__', side_effect=mock_import):
            result = check_optional_dependencies()
            
            assert result.name == "Optional Dependencies"
            assert result.passed is True  # Informational, not a failure
            assert "no optional dependency groups installed" in result.message.lower()
            assert result.details is not None
            assert "[dev]" in result.details
            assert "[vector]" in result.details
            assert "pip install" in result.details

    def test_dev_group_only(self):
        """Test when only dev group is installed."""
        from kano_backlog_cli.commands.doctor import check_optional_dependencies
        from unittest.mock import patch
        
        # Mock only dev packages as installed
        def mock_import(name):
            if name in ["pytest", "black", "mypy", "isort"]:
                return MagicMock()
            raise ImportError(f"No module named '{name}'")
        
        with patch('builtins.__import__', side_effect=mock_import):
            result = check_optional_dependencies()
            
            assert result.name == "Optional Dependencies"
            assert result.passed is True
            assert "installed: dev" in result.message.lower()
            assert "not installed: vector" in result.message.lower()

    def test_vector_group_only(self):
        """Test when only vector group is installed."""
        from kano_backlog_cli.commands.doctor import check_optional_dependencies
        from unittest.mock import patch
        
        # Mock only vector packages as installed
        def mock_import(name):
            if name in ["sentence_transformers", "faiss"]:
                return MagicMock()
            raise ImportError(f"No module named '{name}'")
        
        with patch('builtins.__import__', side_effect=mock_import):
            result = check_optional_dependencies()
            
            assert result.name == "Optional Dependencies"
            assert result.passed is True
            assert "installed: vector" in result.message.lower()
            assert "not installed: dev" in result.message.lower()

    def test_partially_installed_dev_group(self):
        """Test when dev group is partially installed."""
        from kano_backlog_cli.commands.doctor import check_optional_dependencies
        from unittest.mock import patch
        
        # Mock only some dev packages as installed
        def mock_import(name):
            if name in ["pytest", "black"]:
                return MagicMock()
            raise ImportError(f"No module named '{name}'")
        
        with patch('builtins.__import__', side_effect=mock_import):
            result = check_optional_dependencies()
            
            assert result.name == "Optional Dependencies"
            assert result.passed is True
            assert "partially installed: dev" in result.message.lower()
            assert result.details is not None
            assert "mypy" in result.details
            assert "isort" in result.details

    def test_partially_installed_vector_group(self):
        """Test when vector group is partially installed."""
        from kano_backlog_cli.commands.doctor import check_optional_dependencies
        from unittest.mock import patch
        
        # Mock only some vector packages as installed
        def mock_import(name):
            if name == "sentence_transformers":
                return MagicMock()
            raise ImportError(f"No module named '{name}'")
        
        with patch('builtins.__import__', side_effect=mock_import):
            result = check_optional_dependencies()
            
            assert result.name == "Optional Dependencies"
            assert result.passed is True
            assert "partially installed: vector" in result.message.lower()
            assert result.details is not None
            assert "faiss-cpu" in result.details

    def test_mixed_installation_status(self):
        """Test when groups have mixed installation status."""
        from kano_backlog_cli.commands.doctor import check_optional_dependencies
        from unittest.mock import patch
        
        # Mock dev fully installed, vector partially installed
        def mock_import(name):
            if name in ["pytest", "black", "mypy", "isort", "sentence_transformers"]:
                return MagicMock()
            raise ImportError(f"No module named '{name}'")
        
        with patch('builtins.__import__', side_effect=mock_import):
            result = check_optional_dependencies()
            
            assert result.name == "Optional Dependencies"
            assert result.passed is True
            assert "installed: dev" in result.message.lower()
            assert "partially installed: vector" in result.message.lower()
            assert result.details is not None
            assert "faiss-cpu" in result.details

    def test_provides_installation_instructions(self):
        """Test that installation instructions are provided."""
        from kano_backlog_cli.commands.doctor import check_optional_dependencies
        from unittest.mock import patch
        
        # Mock no packages installed
        def mock_import(name):
            raise ImportError(f"No module named '{name}'")
        
        with patch('builtins.__import__', side_effect=mock_import):
            result = check_optional_dependencies()
            
            assert result.name == "Optional Dependencies"
            assert result.passed is True
            assert result.details is not None
            assert "pip install kano-agent-backlog-skill[dev]" in result.details
            assert "[vector]" in result.details

    def test_describes_group_contents(self):
        """Test that group contents are described."""
        from kano_backlog_cli.commands.doctor import check_optional_dependencies
        from unittest.mock import patch
        
        # Mock no packages installed
        def mock_import(name):
            raise ImportError(f"No module named '{name}'")
        
        with patch('builtins.__import__', side_effect=mock_import):
            result = check_optional_dependencies()
            
            assert result.name == "Optional Dependencies"
            assert result.passed is True
            assert result.details is not None
            assert "Development tools" in result.details or "pytest" in result.details
            assert "Vector search" in result.details or "sentence-transformers" in result.details

    def test_check_always_passes(self):
        """Test that the check always passes (informational only)."""
        from kano_backlog_cli.commands.doctor import check_optional_dependencies
        from unittest.mock import patch
        
        # Test with various scenarios - all should pass
        scenarios = [
            # All installed
            lambda name: MagicMock() if name in ["pytest", "black", "mypy", "isort", "sentence_transformers", "faiss"] else (_ for _ in ()).throw(ImportError()),
            # None installed
            lambda name: (_ for _ in ()).throw(ImportError()),
            # Partially installed
            lambda name: MagicMock() if name in ["pytest", "black"] else (_ for _ in ()).throw(ImportError()),
        ]
        
        for mock_import in scenarios:
            with patch('builtins.__import__', side_effect=mock_import):
                result = check_optional_dependencies()
                assert result.passed is True, "Optional dependencies check should always pass"



# Property-Based Tests

from hypothesis import given, strategies as st, settings, assume
from hypothesis import HealthCheck
from typing import Dict, Any, List


class TestDoctorEnvironmentDetectionProperty:
    """Property-based tests for doctor environment detection.
    
    Feature: release-0-1-0-beta, Property 4: Doctor Environment Detection
    
    For any environment configuration (Python version, missing dependencies, 
    invalid backlog structure, permission issues), when `kano-backlog doctor` 
    is run, it should detect and report the issue with actionable recommendations.
    
    Validates: Requirements 7.1, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7
    """

    @given(
        python_major=st.integers(min_value=2, max_value=4),
        python_minor=st.integers(min_value=0, max_value=15),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=100)
    def test_python_version_detection_property(self, python_major: int, python_minor: int):
        """Property: Doctor detects Python version issues across all version combinations.
        
        For any Python version, doctor should:
        - Pass if version >= 3.8
        - Fail if version < 3.8
        - Report current and required versions
        """
        from kano_backlog_cli.commands.doctor import check_python_version
        
        # Mock the Python version
        with patch.object(sys, 'version_info', (python_major, python_minor, 0, 'final', 0)):
            result = check_python_version()
            
            # Property: Check name is always consistent
            assert result.name == "Python Version"
            
            # Property: Pass/fail based on version comparison
            is_valid = (python_major, python_minor) >= (3, 8)
            assert result.passed == is_valid, \
                f"Python {python_major}.{python_minor} should {'pass' if is_valid else 'fail'}"
            
            # Property: Message always contains version information
            assert f"{python_major}.{python_minor}" in result.message
            
            # Property: Version requirement info is in message or details
            if is_valid:
                assert "3.8" in result.message
            else:
                # Failed checks provide details with version info
                assert result.details is not None
                assert "Current:" in result.details
                assert "Required:" in result.details
                assert "3.8" in result.details

    @given(
        sqlite_major=st.integers(min_value=2, max_value=4),
        sqlite_minor=st.integers(min_value=0, max_value=40),
        sqlite_patch=st.integers(min_value=0, max_value=20),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=100)
    def test_sqlite_version_detection_property(
        self, 
        sqlite_major: int, 
        sqlite_minor: int, 
        sqlite_patch: int
    ):
        """Property: Doctor detects SQLite version issues across all version combinations.
        
        For any SQLite version, doctor should:
        - Pass if version >= 3.8.0
        - Fail if version < 3.8.0
        - Report current and required versions
        """
        from kano_backlog_cli.commands.doctor import check_sqlite_availability
        
        version_str = f"{sqlite_major}.{sqlite_minor}.{sqlite_patch}"
        
        # Mock sqlite3 module with the generated version
        mock_sqlite3 = MagicMock()
        mock_sqlite3.sqlite_version = version_str
        
        with patch.dict('sys.modules', {'sqlite3': mock_sqlite3}):
            result = check_sqlite_availability()
            
            # Property: Check name is always consistent
            assert result.name == "SQLite Availability"
            
            # Property: Pass/fail based on version comparison
            is_valid = (sqlite_major, sqlite_minor, sqlite_patch) >= (3, 8, 0)
            assert result.passed == is_valid, \
                f"SQLite {version_str} should {'pass' if is_valid else 'fail'}"
            
            # Property: Message always contains version information
            assert version_str in result.message
            
            # Property: Version requirement info is in message or details
            if is_valid:
                assert "3.8.0" in result.message or "3.8" in result.message
            else:
                # Failed checks provide details with version info
                assert result.details is not None
                assert "Current:" in result.details
                assert "Required:" in result.details
                assert "3.8" in result.details

    @given(
        has_products_dir=st.booleans(),
        num_products=st.integers(min_value=0, max_value=5),
        missing_items=st.booleans(),
        missing_decisions=st.booleans(),
        missing_meta=st.booleans(),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=100)
    def test_backlog_structure_detection_property(
        self,
        tmp_path,
        has_products_dir: bool,
        num_products: int,
        missing_items: bool,
        missing_decisions: bool,
        missing_meta: bool,
    ):
        """Property: Doctor detects backlog structure issues across all configurations.
        
        For any backlog structure configuration, doctor should:
        - Fail if products directory is missing
        - Fail if no products exist
        - Fail if any product is missing required directories
        - Pass if structure is valid
        - Provide actionable recommendations for failures
        """
        from kano_backlog_cli.commands.doctor import check_backlog_structure
        import shutil
        
        # Create backlog root (clean up first to avoid state from previous runs)
        backlog_root = tmp_path / "backlog"
        if backlog_root.exists():
            shutil.rmtree(backlog_root)
        backlog_root.mkdir()
        
        # Create products directory if specified
        if has_products_dir:
            products_dir = backlog_root / "products"
            products_dir.mkdir()
            
            # Create products
            for i in range(num_products):
                product_dir = products_dir / f"product-{i}"
                product_dir.mkdir()
                
                # Create required directories based on flags
                if not missing_items:
                    (product_dir / "items").mkdir()
                if not missing_decisions:
                    (product_dir / "decisions").mkdir()
                if not missing_meta:
                    (product_dir / "_meta").mkdir()
        
        result = check_backlog_structure(backlog_root=backlog_root)
        
        # Property: Check name is always consistent
        assert result.name == "Backlog Structure"
        
        # Property: Determine expected pass/fail
        should_pass = (
            has_products_dir and 
            num_products > 0 and 
            not missing_items and 
            not missing_decisions and 
            not missing_meta
        )
        
        assert result.passed == should_pass, \
            f"Structure (products_dir={has_products_dir}, products={num_products}, " \
            f"missing_items={missing_items}, missing_decisions={missing_decisions}, " \
            f"missing_meta={missing_meta}) should {'pass' if should_pass else 'fail'}"
        
        # Property: Failed checks provide details with recommendations
        if not should_pass:
            assert result.details is not None
            assert "kano-backlog" in result.details.lower()

    @given(
        has_toml=st.booleans(),
        toml_valid=st.booleans(),
        has_json=st.booleans(),
        json_valid=st.booleans(),
        has_project_config=st.booleans(),
        project_config_valid=st.booleans(),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=100)
    def test_configuration_validity_detection_property(
        self,
        tmp_path,
        has_toml: bool,
        toml_valid: bool,
        has_json: bool,
        json_valid: bool,
        has_project_config: bool,
        project_config_valid: bool,
    ):
        """Property: Doctor detects configuration issues across all configurations.
        
        For any configuration setup, doctor should:
        - Detect invalid TOML syntax
        - Detect invalid JSON syntax
        - Detect missing project config
        - Detect invalid project config
        - Pass if all configs are valid
        - Provide actionable error messages
        """
        from kano_backlog_cli.commands.doctor import check_configuration_validity
        import shutil
        
        # Create backlog root (clean up first to avoid state from previous runs)
        backlog_root = tmp_path / "backlog"
        if backlog_root.exists():
            shutil.rmtree(backlog_root)
        backlog_root.mkdir()
        shared_dir = backlog_root / "_shared"
        shared_dir.mkdir()
        
        # Create TOML config if specified
        if has_toml:
            defaults_toml = shared_dir / "defaults.toml"
            if toml_valid:
                defaults_toml.write_text('[log]\nverbosity = "info"\n', encoding="utf-8")
            else:
                defaults_toml.write_text('[log\nverbosity = "info"\n', encoding="utf-8")  # Invalid
        
        # Create JSON config if specified
        if has_json:
            defaults_json = shared_dir / "defaults.json"
            if json_valid:
                defaults_json.write_text('{"log": {"verbosity": "info"}}', encoding="utf-8")
            else:
                defaults_json.write_text('{"log": {"verbosity"', encoding="utf-8")  # Invalid
        
        # Create project config if specified
        project_root = backlog_root.parent.parent
        kano_dir = project_root / ".kano"
        if kano_dir.exists():
            shutil.rmtree(kano_dir)
        kano_dir.mkdir(parents=True)
        project_config = kano_dir / "backlog_config.toml"
        
        if has_project_config:
            if project_config_valid:
                project_config.write_text(
                    '[products.test]\nname = "test"\nprefix = "TST"\nbacklog_root = "_kano/backlog/products/test"\n',
                    encoding="utf-8"
                )
            else:
                project_config.write_text('[products.test]\nname = "test"\n', encoding="utf-8")  # Missing required fields
        
        result = check_configuration_validity(backlog_root=backlog_root)
        
        # Property: Check name is always consistent
        assert result.name == "Configuration Validity"
        
        # Property: Determine expected pass/fail
        # Project config is required, so missing it is an error
        has_invalid_toml = has_toml and not toml_valid
        has_invalid_json = has_json and not json_valid
        has_invalid_project = not has_project_config or (has_project_config and not project_config_valid)
        
        should_pass = not (has_invalid_toml or has_invalid_json or has_invalid_project)
        
        assert result.passed == should_pass, \
            f"Config (toml={has_toml}/{toml_valid}, json={has_json}/{json_valid}, " \
            f"project={has_project_config}/{project_config_valid}) should {'pass' if should_pass else 'fail'}"
        
        # Property: Failed checks provide details
        if not should_pass:
            assert result.details is not None

    @given(
        num_writable_dirs=st.integers(min_value=0, max_value=5),
        num_readonly_dirs=st.integers(min_value=0, max_value=3),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=50)
    def test_permissions_detection_property(
        self,
        tmp_path,
        num_writable_dirs: int,
        num_readonly_dirs: int,
    ):
        """Property: Doctor detects permission issues across all configurations.
        
        For any permission configuration, doctor should:
        - Pass if all directories are writable
        - Fail if any directory is not writable
        - Report which directories lack permissions
        - Provide actionable recommendations
        """
        import sys
        
        # Skip on Windows as chmod doesn't work the same way
        if sys.platform == "win32":
            pytest.skip("chmod-based permission tests don't work reliably on Windows")
        
        from kano_backlog_cli.commands.doctor import check_permissions
        import os
        import stat
        
        # Assume at least one directory exists
        assume(num_writable_dirs + num_readonly_dirs > 0)
        
        # Create backlog root
        backlog_root = tmp_path / "backlog"
        backlog_root.mkdir()
        products_dir = backlog_root / "products"
        products_dir.mkdir()
        
        # Create writable directories
        writable_dirs = []
        for i in range(num_writable_dirs):
            product_dir = products_dir / f"writable-{i}"
            product_dir.mkdir()
            (product_dir / "items").mkdir()
            writable_dirs.append(product_dir / "items")
        
        # Create readonly directories
        readonly_dirs = []
        for i in range(num_readonly_dirs):
            product_dir = products_dir / f"readonly-{i}"
            product_dir.mkdir()
            items_dir = product_dir / "items"
            items_dir.mkdir()
            readonly_dirs.append(items_dir)
        
        try:
            # Make directories read-only
            for dir_path in readonly_dirs:
                current_mode = os.stat(dir_path).st_mode
                os.chmod(dir_path, current_mode & ~stat.S_IWUSR & ~stat.S_IWGRP & ~stat.S_IWOTH)
            
            result = check_permissions(backlog_root=backlog_root)
            
            # Property: Check name is always consistent
            assert result.name == "Permissions"
            
            # Property: Pass/fail based on readonly directories
            should_pass = num_readonly_dirs == 0
            assert result.passed == should_pass, \
                f"Permissions (writable={num_writable_dirs}, readonly={num_readonly_dirs}) " \
                f"should {'pass' if should_pass else 'fail'}"
            
            # Property: Failed checks provide details with recommendations
            if not should_pass:
                assert result.details is not None
                assert "Recommendations" in result.details or "chmod" in result.details.lower()
            
        finally:
            # Restore write permissions for cleanup
            for dir_path in readonly_dirs:
                try:
                    current_mode = os.stat(dir_path).st_mode
                    os.chmod(dir_path, current_mode | stat.S_IWUSR)
                except:
                    pass

    @given(
        dev_packages=st.lists(
            st.sampled_from(["pytest", "black", "mypy", "isort"]),
            min_size=0,
            max_size=4,
            unique=True
        ),
        vector_packages=st.lists(
            st.sampled_from(["sentence_transformers", "faiss"]),
            min_size=0,
            max_size=2,
            unique=True
        ),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=100)
    def test_optional_dependencies_detection_property(
        self,
        dev_packages: List[str],
        vector_packages: List[str],
    ):
        """Property: Doctor detects optional dependency status across all configurations.
        
        For any optional dependency configuration, doctor should:
        - Always pass (informational check)
        - Report which groups are installed/partially installed/not installed
        - Provide installation instructions for missing packages
        """
        from kano_backlog_cli.commands.doctor import check_optional_dependencies
        
        installed_packages = set(dev_packages + vector_packages)
        
        # Mock package imports
        def mock_import(name):
            if name in installed_packages:
                return MagicMock()
            raise ImportError(f"No module named '{name}'")
        
        with patch('builtins.__import__', side_effect=mock_import):
            result = check_optional_dependencies()
            
            # Property: Check name is always consistent
            assert result.name == "Optional Dependencies"
            
            # Property: Check always passes (informational only)
            assert result.passed is True
            
            # Property: Message reflects installation status
            dev_all = {"pytest", "black", "mypy", "isort"}
            vector_all = {"sentence_transformers", "faiss"}
            
            dev_installed = set(dev_packages)
            vector_installed = set(vector_packages)
            
            # Check message content based on installation status
            if dev_installed == dev_all and vector_installed == vector_all:
                assert "all optional groups installed" in result.message.lower()
            elif not dev_installed and not vector_installed:
                assert "no optional dependency groups installed" in result.message.lower()
            else:
                # Partial installation - message should mention specific groups
                assert result.message is not None

    @given(
        issue_type=st.sampled_from([
            "python_old",
            "sqlite_missing",
            "sqlite_old",
            "no_products",
            "missing_dirs",
            "invalid_config",
            "no_permissions",
        ])
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=50)
    def test_doctor_provides_actionable_recommendations_property(
        self,
        tmp_path,
        issue_type: str,
    ):
        """Property: Doctor always provides actionable recommendations for issues.
        
        For any detected issue, doctor should:
        - Provide clear error message
        - Include actionable recommendations in details
        - Suggest specific commands or actions to fix the issue
        """
        import sys
        import os
        import stat
        
        if issue_type == "python_old":
            from kano_backlog_cli.commands.doctor import check_python_version
            with patch.object(sys, 'version_info', (3, 7, 0, 'final', 0)):
                result = check_python_version()
                
        elif issue_type == "sqlite_missing":
            from kano_backlog_cli.commands.doctor import check_sqlite_availability
            with patch('builtins.__import__', side_effect=ImportError("No module named 'sqlite3'")):
                result = check_sqlite_availability()
                
        elif issue_type == "sqlite_old":
            from kano_backlog_cli.commands.doctor import check_sqlite_availability
            mock_sqlite3 = MagicMock()
            mock_sqlite3.sqlite_version = "3.7.0"
            with patch.dict('sys.modules', {'sqlite3': mock_sqlite3}):
                result = check_sqlite_availability()
                
        elif issue_type == "no_products":
            from kano_backlog_cli.commands.doctor import check_backlog_structure
            backlog_root = tmp_path / "backlog"
            backlog_root.mkdir()
            (backlog_root / "products").mkdir()
            result = check_backlog_structure(backlog_root=backlog_root)
            
        elif issue_type == "missing_dirs":
            from kano_backlog_cli.commands.doctor import check_backlog_structure
            backlog_root = tmp_path / "backlog"
            backlog_root.mkdir()
            products_dir = backlog_root / "products"
            products_dir.mkdir()
            product_dir = products_dir / "test-product"
            product_dir.mkdir()
            result = check_backlog_structure(backlog_root=backlog_root)
            
        elif issue_type == "invalid_config":
            from kano_backlog_cli.commands.doctor import check_configuration_validity
            backlog_root = tmp_path / "backlog"
            backlog_root.mkdir()
            shared_dir = backlog_root / "_shared"
            shared_dir.mkdir()
            defaults_toml = shared_dir / "defaults.toml"
            defaults_toml.write_text('[log\n', encoding="utf-8")  # Invalid
            project_root = backlog_root.parent.parent
            kano_dir = project_root / ".kano"
            kano_dir.mkdir(parents=True, exist_ok=True)
            project_config = kano_dir / "backlog_config.toml"
            project_config.write_text(
                '[products.test]\nname = "test"\nprefix = "TST"\nbacklog_root = "_kano/backlog/products/test"\n',
                encoding="utf-8"
            )
            result = check_configuration_validity(backlog_root=backlog_root)
            
        elif issue_type == "no_permissions":
            if sys.platform == "win32":
                pytest.skip("chmod-based permission tests don't work reliably on Windows")
            
            from kano_backlog_cli.commands.doctor import check_permissions
            backlog_root = tmp_path / "backlog"
            backlog_root.mkdir()
            
            try:
                current_mode = os.stat(backlog_root).st_mode
                os.chmod(backlog_root, current_mode & ~stat.S_IWUSR & ~stat.S_IWGRP & ~stat.S_IWOTH)
                result = check_permissions(backlog_root=backlog_root)
            finally:
                try:
                    os.chmod(backlog_root, current_mode)
                except:
                    pass
        
        # Property: Failed checks always have details with recommendations
        assert result.passed is False
        assert result.details is not None
        assert len(result.details) > 0
        
        # Property: Details should contain actionable information
        # (commands, file paths, or specific instructions)
        details_lower = result.details.lower()
        has_actionable_info = (
            "kano-backlog" in details_lower or
            "pip install" in details_lower or
            "chmod" in details_lower or
            "python" in details_lower or
            "sqlite" in details_lower or
            ".toml" in details_lower or
            ".json" in details_lower or
            "init" in details_lower or
            "install" in details_lower
        )
        assert has_actionable_info, \
            f"Details should contain actionable information: {result.details}"
