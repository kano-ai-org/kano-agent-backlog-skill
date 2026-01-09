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
        
        # Create a minimal backlog structure for testing
        self.backlog_root = self.temp_dir / "_kano" / "backlog"
        self.products_dir = self.backlog_root / "products"
        self.test_product = self.products_dir / "test-product"
        self.items_root = self.test_product / "items"
        
        # Create directory structure
        for item_type in ["epics", "features", "userstories", "tasks", "bugs"]:
            (self.items_root / item_type / "0000").mkdir(parents=True, exist_ok=True)
        
        # Create minimal config
        config_dir = self.test_product / "_config"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.json").write_text('{"product_name": "test-product"}')
        
        # Set working directory to temp directory
        self.original_cwd = os.getcwd()
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
            assert item_type.upper() in result.output or item_type.capitalize() in result.output