"""
Property-based tests for kano CLI item create command.

Feature: kano-cli-item-create
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from hypothesis import given, strategies as st, settings
from typer.testing import CliRunner
import sys
import os

# Add the src directory to Python path for testing
test_dir = Path(__file__).parent
src_dir = test_dir.parent / "src"
scripts_dir = test_dir.parent / "scripts"
sys.path.insert(0, str(src_dir))
sys.path.insert(0, str(scripts_dir))

from kano_cli.cli import app


class TestCLIItemCreate:
    """Test suite for CLI item create functionality."""
    
    def setup_method(self):
        """Set up test environment for each test."""
        self.runner = CliRunner()
        self.temp_dir = Path(tempfile.mkdtemp())
        
        # Store the original working directory and skill root
        self.original_cwd = os.getcwd()
        self.skill_root = Path(__file__).parent.parent
        
        # Add the scripts/common directory to Python path for testing
        scripts_common = self.skill_root / "scripts" / "common"
        if str(scripts_common) not in sys.path:
            sys.path.insert(0, str(scripts_common))
        
        # Create a minimal backlog structure for testing
        self.backlog_root = self.temp_dir / "_kano" / "backlog"
        self.products_dir = self.backlog_root / "products"
        self.test_product = self.products_dir / "test-product"
        self.items_root = self.test_product / "items"
        
        # Create directory structure
        for item_type in ["epics", "features", "userstories", "tasks", "bugs"]:
            (self.items_root / item_type / "0000").mkdir(parents=True, exist_ok=True)
        
        # Create required product directories for configuration validation
        for required_dir in ["decisions", "views", "_meta"]:
            (self.test_product / required_dir).mkdir(parents=True, exist_ok=True)
        
        # Create minimal config
        config_dir = self.test_product / "_config"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_content = {
            "project": {
                "name": "test-product",
                "prefix": "TE"
            },
            "views": {
                "auto_refresh": True
            },
            "log": {
                "verbosity": "info",
                "debug": False
            }
        }
        import json
        (config_dir / "config.json").write_text(json.dumps(config_content, indent=2))
        
        # Create shared defaults directory
        shared_dir = self.backlog_root / "_shared"
        shared_dir.mkdir(parents=True, exist_ok=True)
        defaults_content = {"default_product": "test-product"}
        (shared_dir / "defaults.json").write_text(json.dumps(defaults_content))
        
        # Set working directory to temp directory
        os.chdir(str(self.temp_dir))
    
    def teardown_method(self):
        """Clean up after each test."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @given(
        item_type=st.sampled_from(["epic", "feature", "userstory", "task", "bug"]),
        title=st.text(min_size=1, max_size=100).filter(lambda x: x.strip() and 
                                                       not any(c in x for c in '<>:"|?*\0')),
        priority=st.sampled_from(["P0", "P1", "P2", "P3", "P4"]),
        tags=st.lists(st.text(min_size=1, max_size=20).filter(
            lambda x: x.strip() and not any(c in x for c in '<>:"|?*\0,')), 
            max_size=5),
        agent=st.text(min_size=1, max_size=50).filter(lambda x: x.strip())
    )
    @settings(max_examples=100)
    def test_argument_acceptance_completeness(self, item_type, title, priority, tags, agent):
        """
        Property 2: Argument Acceptance Completeness
        For any valid combination of supported arguments (--type, --title, --parent, --priority, --tags, --product), 
        the CLI should accept and parse them correctly without errors.
        
        Feature: kano-cli-item-create, Property 2: Argument Acceptance Completeness
        Validates: Requirements 1.2, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6
        """
        # Prepare arguments
        args = [
            "item", "create",
            "--type", item_type,
            "--title", title.strip(),
            "--priority", priority,
            "--agent", agent.strip(),
            "--product", "test-product",
            "--dry-run"  # Use dry-run to avoid actual file creation
        ]
        
        # Add tags if provided
        if tags:
            tag_str = ",".join(tag.strip() for tag in tags if tag.strip())
            if tag_str:
                args.extend(["--tags", tag_str])
        
        # Execute command
        result = self.runner.invoke(app, args)
        
        # Should not fail with argument parsing errors
        # Exit code 0 for dry-run success, or specific validation errors (not argument parsing errors)
        assert result.exit_code in [0, 1], f"Unexpected exit code {result.exit_code}. Output: {result.output}"
        
        # If it failed, it should be due to validation, not argument parsing
        if result.exit_code == 1:
            # Should contain validation error message, not argument parsing error
            assert "Validation error:" in result.output or "Error during validation:" in result.output, \
                f"Expected validation error, got: {result.output}"
        else:
            # Success case - should show what would be created
            assert "Would create:" in result.output, f"Expected dry-run output, got: {result.output}"
            # Check that the item type appears in the output (handle UserStory special case)
            type_in_output = (item_type.upper() in result.output or 
                            item_type.capitalize() in result.output or
                            "UserStory" in result.output)  # Special case for userstory -> UserStory
    @given(
        item_type=st.one_of(
            st.text().filter(lambda x: x.lower() not in ["epic", "feature", "userstory", "task", "bug"]),
            st.sampled_from(["INVALID", "unknown", "123", ""])
        ),
        title=st.one_of(
            st.just(""),  # Empty title
            st.just("   "),  # Whitespace only
            st.text(min_size=201),  # Too long
            st.text().filter(lambda x: any(c in x for c in '<>:"|?*\0'))  # Invalid characters
        ),
        priority=st.one_of(
            st.text().filter(lambda x: x not in ["P0", "P1", "P2", "P3", "P4"]),
            st.sampled_from(["P5", "HIGH", "LOW", ""])
        ),
        tags=st.one_of(
            st.lists(st.text(min_size=51)),  # Tags too long
            st.lists(st.text().filter(lambda x: any(c in x for c in '<>:"|?*\0,')))  # Invalid chars in tags
        ),
        agent=st.one_of(
            st.just(""),  # Empty agent
            st.just("   ")  # Whitespace only agent
        )
    )
    @settings(max_examples=100)
    def test_input_validation_consistency(self, item_type, title, priority, tags, agent):
        """
        Property 3: Input Validation Consistency
        For any invalid input (invalid item type, missing required arguments, invalid product name, 
        non-existent parent, invalid title), the CLI should reject it with appropriate error messages 
        and non-zero exit codes.
        
        Feature: kano-cli-item-create, Property 3: Input Validation Consistency
        Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5
        """
        # Prepare arguments with invalid inputs
        args = [
            "item", "create",
            "--type", item_type,
            "--title", title,
            "--priority", priority,
            "--agent", agent,
            "--product", "test-product",
            "--dry-run"
        ]
        
        # Add tags if provided
        if tags:
            tag_str = ",".join(str(tag) for tag in tags)
            args.extend(["--tags", tag_str])
        
        # Execute command
        result = self.runner.invoke(app, args)
        
        # Should fail with validation error (exit code 1)
        assert result.exit_code == 1, f"Expected validation failure, got exit code {result.exit_code}. Output: {result.output}"
        
        # Should contain validation error message
        assert ("Validation error:" in result.output or 
                "Error during validation:" in result.output or
                "Invalid" in result.output or
                "cannot be empty" in result.output or
                "too long" in result.output), \
            f"Expected validation error message, got: {result.output}"

    @given(
        parent_id=st.text(min_size=1, max_size=20).filter(
            lambda x: x.strip() and 
            not x.startswith("TE-") and 
            not any(c in x for c in '\\/<>:"|?*\0') and  # Avoid path-problematic chars
            x.isalnum() or '-' in x  # Keep it simple - alphanumeric or with dashes
        )
    )
    @settings(max_examples=50)
    def test_parent_validation(self, parent_id):
        """
        Test parent item validation - should fail when parent doesn't exist.
        Part of Property 3: Input Validation Consistency
        """
        args = [
            "item", "create",
            "--type", "task",
            "--title", "Test Task",
            "--priority", "P2",
            "--agent", "test-agent",
            "--product", "test-product",
            "--parent", parent_id,
            "--dry-run"
        ]
        
        result = self.runner.invoke(app, args)
        
        # Should fail because parent doesn't exist
        assert result.exit_code == 1, f"Expected failure for non-existent parent, got: {result.output}"
        assert ("not found" in result.output or 
                "Validation error:" in result.output or
                "Error during validation:" in result.output), \
            f"Expected parent validation error, got: {result.output}"

    def test_invalid_product_validation(self):
        """
        Test product validation - should fail when product doesn't exist.
        Part of Property 3: Input Validation Consistency
        """
        args = [
            "item", "create",
            "--type", "task",
            "--title", "Test Task",
            "--priority", "P2",
            "--agent", "test-agent",
            "--product", "non-existent-product",
            "--dry-run"
        ]
        
        result = self.runner.invoke(app, args)
        
        # Should fail because product doesn't exist
        assert result.exit_code == 1, f"Expected failure for non-existent product, got: {result.output}"
        assert ("not found" in result.output or 
                "Validation error:" in result.output), \
            f"Expected product validation error, got: {result.output}"

    @given(
        config_override=st.dictionaries(
            keys=st.sampled_from([
                "KANO_LOG_VERBOSITY", "KANO_LOG_DEBUG", "KANO_VIEWS_AUTO_REFRESH",
                "KANO_INDEX_ENABLED", "KANO_INDEX_BACKEND", "KANO_PROCESS_PROFILE"
            ]),
            values=st.one_of(
                st.sampled_from(["info", "debug", "warn", "error"]),  # For verbosity
                st.sampled_from(["true", "false", "1", "0"]),  # For boolean values
                st.sampled_from(["sqlite", "postgres"]),  # For backend
                st.text(min_size=1, max_size=50)  # For profile
            ),
            min_size=0,
            max_size=3
        ),
        product_arg=st.one_of(
            st.none(),
            st.just("test-product"),
            st.text(min_size=1, max_size=30).filter(lambda x: x.strip() and x.isalnum())
        )
    )
    @settings(max_examples=100)
    def test_configuration_integration_correctness(self, config_override, product_arg):
        """
        Property 7: Configuration Integration Correctness
        For any valid configuration setup (files, environment variables, product contexts), 
        the CLI should respect and correctly apply the configuration settings.
        
        Feature: kano-cli-item-create, Property 7: Configuration Integration Correctness
        Validates: Requirements 5.3, 6.1, 6.2, 6.3, 6.4, 6.5
        """
        # Set up environment variables for this test
        original_env = {}
        try:
            # Store original environment values
            for key in config_override:
                original_env[key] = os.environ.get(key)
                os.environ[key] = str(config_override[key])
            
            # Create additional config files for testing
            config_dir = self.test_product / "_config"
            config_content = {
                "project": {
                    "name": "test-product",
                    "prefix": "TE"
                },
                "views": {
                    "auto_refresh": True
                },
                "log": {
                    "verbosity": "info",
                    "debug": False
                },
                "process": {
                    "profile": "builtin/azure-boards-agile"
                },
                "index": {
                    "enabled": False,
                    "backend": "sqlite"
                }
            }
            
            import json
            (config_dir / "config.json").write_text(json.dumps(config_content, indent=2))
            
            # Create shared defaults if testing product auto-detection
            if product_arg is None:
                shared_dir = self.backlog_root / "_shared"
                shared_dir.mkdir(parents=True, exist_ok=True)
                defaults_content = {"default_product": "test-product"}
                (shared_dir / "defaults.json").write_text(json.dumps(defaults_content))
            
            # Prepare command arguments
            args = [
                "item", "create",
                "--type", "task",
                "--title", "Configuration Test Task",
                "--priority", "P2",
                "--agent", "test-agent",
                "--dry-run"
            ]
            
            # Add product argument if specified
            if product_arg:
                args.extend(["--product", product_arg])
            
            # Execute command
            result = self.runner.invoke(app, args)
            
            # For valid configurations, should succeed or fail with specific validation errors
            if product_arg == "test-product" or (product_arg is None and 
                (self.backlog_root / "_shared" / "defaults.json").exists()):
                # Should succeed (exit code 0) or fail with validation errors (not config errors)
                assert result.exit_code in [0, 1], f"Unexpected exit code {result.exit_code}. Output: {result.output}"
                
                if result.exit_code == 0:
                    # Success case - verify configuration was applied
                    assert "Would create:" in result.output, f"Expected dry-run success output, got: {result.output}"
                    assert "Product: test-product" in result.output, f"Expected product in output, got: {result.output}"
                    
                    # Check that configuration values are reflected in output
                    if "KANO_PROCESS_PROFILE" in config_override:
                        profile_value = config_override["KANO_PROCESS_PROFILE"]
                        assert f"Config: {profile_value}" in result.output or "Config:" in result.output, \
                            f"Expected config profile in output, got: {result.output}"
                else:
                    # Validation error case - should be specific validation, not config loading error
                    assert ("Validation error:" in result.output or 
                            "Error during validation:" in result.output), \
                        f"Expected validation error, got: {result.output}"
                    
                    # Should not be configuration loading errors
                    assert not any(phrase in result.output.lower() for phrase in [
                        "configuration modules", "config file", "invalid config", "config loading"
                    ]), f"Unexpected configuration error: {result.output}"
            else:
                # Invalid product case - should fail with product validation error
                assert result.exit_code == 1, f"Expected failure for invalid product, got: {result.output}"
                assert ("not found" in result.output or 
                        "Validation error:" in result.output), \
                    f"Expected product validation error, got: {result.output}"
        
        finally:
            # Restore original environment
            for key, original_value in original_env.items():
                if original_value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = original_value

    def test_product_directory_structure_validation(self):
        """
        Test that product directory structure validation works correctly.
        Part of Property 7: Configuration Integration Correctness
        """
        # Create a product with incomplete directory structure
        incomplete_product = self.products_dir / "incomplete-product"
        incomplete_product.mkdir(parents=True, exist_ok=True)
        
        # Only create some directories, not all required ones
        (incomplete_product / "items").mkdir(exist_ok=True)
        (incomplete_product / "_config").mkdir(exist_ok=True)
        # Missing: decisions, views, _meta
        
        args = [
            "item", "create",
            "--type", "task",
            "--title", "Test Task",
            "--priority", "P2",
            "--agent", "test-agent",
            "--product", "incomplete-product",
            "--dry-run"
        ]
        
        result = self.runner.invoke(app, args)
        
        # Should fail due to incomplete directory structure
        assert result.exit_code == 1, f"Expected failure for incomplete structure, got: {result.output}"
        assert ("incomplete" in result.output.lower() or 
                "missing" in result.output.lower() or
                "Validation error:" in result.output), \
            f"Expected structure validation error, got: {result.output}"

    def test_environment_variable_overrides(self):
        """
        Test that environment variables correctly override configuration values.
        Part of Property 7: Configuration Integration Correctness
        """
        # Set specific environment variables
        test_env = {
            "KANO_LOG_VERBOSITY": "debug",
            "KANO_VIEWS_AUTO_REFRESH": "false",
            "KANO_INDEX_ENABLED": "true"
        }
        
        original_env = {}
        try:
            for key, value in test_env.items():
                original_env[key] = os.environ.get(key)
                os.environ[key] = value
            
            args = [
                "item", "create",
                "--type", "task",
                "--title", "Environment Test Task",
                "--priority", "P2",
                "--agent", "test-agent",
                "--product", "test-product",
                "--dry-run"
            ]
            
            result = self.runner.invoke(app, args)
            
            # Should succeed and show that environment overrides were applied
            assert result.exit_code == 0, f"Expected success with env overrides, got: {result.output}"
            assert "Would create:" in result.output, f"Expected dry-run output, got: {result.output}"
            
        finally:
            # Restore original environment
            for key, original_value in original_env.items():
                if original_value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = original_value

    @given(
        item_type=st.sampled_from(["epic", "feature", "userstory", "task", "bug"]),
        title=st.text(min_size=1, max_size=100).filter(lambda x: x.strip() and 
                                                       not any(c in x for c in '<>:"|?*\0')),
        priority=st.sampled_from(["P0", "P1", "P2", "P3", "P4"]),
        tags=st.lists(st.text(min_size=1, max_size=20).filter(
            lambda x: x.strip() and not any(c in x for c in '<>:"|?*\0,')), 
            max_size=5),
        agent=st.text(min_size=1, max_size=50).filter(lambda x: x.strip())
    )
    @settings(max_examples=100)
    def test_backward_compatibility_preservation(self, item_type, title, priority, tags, agent):
        """
        Property 4: Backward Compatibility Preservation
        For any valid input that works with workitem_create.py, the new CLI should produce 
        equivalent results in terms of file structure, metadata format, and file naming.
        
        Feature: kano-cli-item-create, Property 4: Backward Compatibility Preservation
        Validates: Requirements 1.3, 5.1, 5.2, 5.5
        """
        # Prepare arguments for new CLI
        args = [
            "item", "create",
            "--type", item_type,
            "--title", title.strip(),
            "--priority", priority,
            "--agent", agent.strip(),
            "--product", "test-product",
            "--dry-run"
        ]
        
        # Add tags if provided
        if tags:
            tag_str = ",".join(tag.strip() for tag in tags if tag.strip())
            if tag_str:
                args.extend(["--tags", tag_str])
        
        # Execute new CLI command
        result = self.runner.invoke(app, args)
        
        # Should succeed for valid inputs
        assert result.exit_code == 0, f"Expected success for valid input, got: {result.output}"
        assert "Would create:" in result.output, f"Expected dry-run output, got: {result.output}"
        
        # Extract information from dry-run output
        output_lines = result.output.strip().split('\n')
        
        # Verify file structure compatibility
        # Should show path with bucket organization (e.g., items/tasks/0000/)
        path_line = next((line for line in output_lines if "Path:" in line), "")
        assert path_line, f"Expected path in output, got: {result.output}"
        
        # Extract path and verify structure
        path_str = path_line.split("Path:", 1)[1].strip()
        path = Path(path_str)
        
        # Verify bucket organization (should be in format items/{type}s/0000/)
        path_parts = path.parts
        assert "items" in path_parts, f"Expected 'items' in path, got: {path}"
        
        # Find the type folder (should be pluralized)
        type_folder_expected = f"{item_type}s"
        assert type_folder_expected in path_parts, f"Expected '{type_folder_expected}' in path, got: {path}"
        
        # Verify bucket format (should be 0000 for first items)
        bucket_idx = None
        for i, part in enumerate(path_parts):
            if part == type_folder_expected and i + 1 < len(path_parts):
                bucket_idx = i + 1
                break
        
        assert bucket_idx is not None, f"Could not find bucket in path: {path}"
        bucket = path_parts[bucket_idx]
        assert bucket == "0000", f"Expected bucket '0000', got: '{bucket}'"
        
        # Verify file naming convention (ID_slug.md)
        filename = path.name
        assert filename.endswith(".md"), f"Expected .md extension, got: {filename}"
        assert "_" in filename, f"Expected underscore in filename, got: {filename}"
        
        # Verify ID format (PREFIX-TYPE-NNNN)
        id_part = filename.split("_")[0]
        type_code_map = {
            "epic": "EPIC",
            "feature": "FTR", 
            "userstory": "USR",
            "task": "TSK",
            "bug": "BUG"
        }
        expected_type_code = type_code_map[item_type]
        
        # ID should match pattern: PREFIX-TYPECODE-NNNN
        import re
        id_pattern = rf"^[A-Z]{{2,}}-{expected_type_code}-\d{{4}}$"
        assert re.match(id_pattern, id_part), f"ID '{id_part}' doesn't match expected pattern '{id_pattern}'"
        
        # Verify product information is shown
        product_line = next((line for line in output_lines if "Product:" in line), "")
        assert "test-product" in product_line, f"Expected product in output, got: {result.output}"
        
        # Verify type information is shown correctly
        type_line = next((line for line in output_lines if "Type:" in line), "")
        expected_type_label = {
            "epic": "Epic",
            "feature": "Feature",
            "userstory": "UserStory", 
            "task": "Task",
            "bug": "Bug"
        }[item_type]
        assert expected_type_label in type_line, f"Expected type '{expected_type_label}' in output, got: {result.output}"

    @given(
        item_type=st.sampled_from(["epic", "feature", "userstory", "task", "bug"]),
        title=st.text(min_size=1, max_size=100).filter(lambda x: x.strip() and 
                                                       not any(c in x for c in '<>:"|?*\0')),
        priority=st.sampled_from(["P0", "P1", "P2", "P3", "P4"]),
        tags=st.lists(st.text(min_size=1, max_size=20).filter(
            lambda x: x.strip() and not any(c in x for c in '<>:"|?*\0,')), 
            max_size=3),
        agent=st.text(min_size=1, max_size=50).filter(lambda x: x.strip()),
        area=st.text(min_size=1, max_size=30).filter(lambda x: x.strip() and x.isalnum()),
        owner=st.one_of(
            st.none(),
            st.text(min_size=1, max_size=30).filter(lambda x: x.strip() and x.isalnum())
        )
    )
    @settings(max_examples=100)
    def test_success_operation_consistency(self, item_type, title, priority, tags, agent, area, owner):
        """
        Property 5: Success Operation Consistency
        For any successful item creation, the CLI should return exit code 0, display the created item ID, 
        and create the item in the correct file system location.
        
        Feature: kano-cli-item-create, Property 5: Success Operation Consistency
        Validates: Requirements 4.2, 4.3
        """
        # Prepare arguments for successful creation
        args = [
            "item", "create",
            "--type", item_type,
            "--title", title.strip(),
            "--priority", priority,
            "--agent", agent.strip(),
            "--product", "test-product",
            "--area", area
        ]
        
        # Add optional arguments
        if tags:
            tag_str = ",".join(tag.strip() for tag in tags if tag.strip())
            if tag_str:
                args.extend(["--tags", tag_str])
        
        if owner:
            args.extend(["--owner", owner.strip()])
        
        # First test with dry-run to verify success behavior
        dry_run_args = args + ["--dry-run"]
        result = self.runner.invoke(app, dry_run_args)
        
        # Should succeed with exit code 0
        assert result.exit_code == 0, f"Expected success (exit code 0), got {result.exit_code}. Output: {result.output}"
        
        # Should display what would be created
        assert "Would create:" in result.output, f"Expected 'Would create:' in output, got: {result.output}"
        
        # Should display the item ID
        output_lines = result.output.strip().split('\n')
        id_line = next((line for line in output_lines if "Would create:" in line), "")
        assert id_line, f"Expected ID line in output, got: {result.output}"
        
        # Extract and validate the ID format
        item_id = id_line.split("Would create:", 1)[1].strip()
        
        # Verify ID format matches expected pattern
        type_code_map = {
            "epic": "EPIC",
            "feature": "FTR", 
            "userstory": "USR",
            "task": "TSK",
            "bug": "BUG"
        }
        expected_type_code = type_code_map[item_type]
        
        import re
        id_pattern = rf"^[A-Z]{{2,}}-{expected_type_code}-\d{{4}}$"
        assert re.match(id_pattern, item_id), f"ID '{item_id}' doesn't match expected pattern '{id_pattern}'"
        
        # Should display the correct file system path
        path_line = next((line for line in output_lines if "Path:" in line), "")
        assert path_line, f"Expected path in output, got: {result.output}"
        
        # Extract and validate the path
        path_str = path_line.split("Path:", 1)[1].strip()
        path = Path(path_str)
        
        # Verify path structure is correct
        assert path.is_absolute() or str(path).startswith("_kano"), f"Expected absolute or _kano path, got: {path}"
        assert "items" in path.parts, f"Expected 'items' in path, got: {path}"
        assert f"{item_type}s" in path.parts, f"Expected '{item_type}s' in path, got: {path}"
        assert path.name.endswith(".md"), f"Expected .md extension, got: {path.name}"
        assert item_id in path.name, f"Expected item ID '{item_id}' in filename, got: {path.name}"
        
        # Should display product information
        product_line = next((line for line in output_lines if "Product:" in line), "")
        assert "test-product" in product_line, f"Expected product in output, got: {result.output}"
        
        # Should display type information
        type_line = next((line for line in output_lines if "Type:" in line), "")
        expected_type_label = {
            "epic": "Epic",
            "feature": "Feature",
            "userstory": "UserStory", 
            "task": "Task",
            "bug": "Bug"
        }[item_type]
        assert expected_type_label in type_line, f"Expected type '{expected_type_label}' in output, got: {result.output}"
        
        # Should display title
        title_line = next((line for line in output_lines if "Title:" in line), "")
        assert title.strip() in title_line, f"Expected title '{title.strip()}' in output, got: {result.output}"
        
        # Should display priority
        priority_line = next((line for line in output_lines if "Priority:" in line), "")
        assert priority in priority_line, f"Expected priority '{priority}' in output, got: {result.output}"
        
        # Now test actual creation (not dry-run) to verify file creation
        # Create a unique subdirectory for this test to avoid conflicts
        import uuid
        test_subdir = f"test-{uuid.uuid4().hex[:8]}"
        test_product_path = self.products_dir / test_subdir
        
        # Set up the test product structure
        test_items_root = test_product_path / "items"
        for item_type_dir in ["epics", "features", "userstories", "tasks", "bugs"]:
            (test_items_root / item_type_dir / "0000").mkdir(parents=True, exist_ok=True)
        
        # Create required product directories
        for required_dir in ["decisions", "views", "_meta"]:
            (test_product_path / required_dir).mkdir(parents=True, exist_ok=True)
        
        # Create minimal config for the test product
        config_dir = test_product_path / "_config"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_content = {
            "project": {"name": test_subdir, "prefix": "TE"},
            "views": {"auto_refresh": False},  # Disable refresh for testing
            "log": {"verbosity": "info", "debug": False}
        }
        import json
        (config_dir / "config.json").write_text(json.dumps(config_content, indent=2))
        
        # Test actual creation
        create_args = [
            "item", "create",
            "--type", item_type,
            "--title", title.strip(),
            "--priority", priority,
            "--agent", agent.strip(),
            "--product", test_subdir,
            "--area", area
        ]
        
        if tags:
            tag_str = ",".join(tag.strip() for tag in tags if tag.strip())
            if tag_str:
                create_args.extend(["--tags", tag_str])
        
        if owner:
            create_args.extend(["--owner", owner.strip()])
        
        create_result = self.runner.invoke(app, create_args)
        
        # Should succeed with exit code 0
        assert create_result.exit_code == 0, f"Expected creation success (exit code 0), got {create_result.exit_code}. Output: {create_result.output}"
        
        # Should display confirmation with created item ID
        assert "Created:" in create_result.output, f"Expected 'Created:' confirmation in output, got: {create_result.output}"
        
        # Extract the created item ID from output
        create_output_lines = create_result.output.strip().split('\n')
        created_line = next((line for line in create_output_lines if "Created:" in line), "")
        assert created_line, f"Expected creation confirmation line, got: {create_result.output}"
        
        created_id = created_line.split("Created:", 1)[1].strip()
        assert re.match(id_pattern, created_id), f"Created ID '{created_id}' doesn't match expected pattern"
        
        # Verify the file was actually created in the correct location
        created_path_line = next((line for line in create_output_lines if "Path:" in line), "")
        assert created_path_line, f"Expected path in creation output, got: {create_result.output}"
        
        created_path_str = created_path_line.split("Path:", 1)[1].strip()
        created_path = Path(created_path_str)
        
        # File should exist
        assert created_path.exists(), f"Expected created file to exist at: {created_path}"
        
        # File should be in correct location structure
        assert created_path.is_file(), f"Expected created path to be a file: {created_path}"
        assert created_path.suffix == ".md", f"Expected .md file, got: {created_path}"
        
        # Verify file content has correct structure (basic check)
        content = created_path.read_text(encoding="utf-8")
        assert content.startswith("---"), f"Expected YAML frontmatter, got: {content[:50]}"
        assert f"id: {created_id}" in content, f"Expected ID in content, got: {content[:200]}"
        assert f'title: "{title.strip()}"' in content, f"Expected title in content, got: {content[:500]}"
        assert f"priority: {priority}" in content, f"Expected priority in content, got: {content[:500]}"