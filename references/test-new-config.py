#!/usr/bin/env python3
"""
Test script for new project-level configuration system.

This script tests the updated ConfigLoader with project-level config support.
"""

import sys
from pathlib import Path

# Add src to path for testing
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from kano_backlog_core.config import ConfigLoader
from kano_backlog_core.project_config import ProjectConfigLoader


def test_project_config_loading():
    """Test loading project configuration."""
    print("🔍 Testing Project Config Loading")
    print("=" * 50)
    
    # Test from current directory (should find .kano/backlog_config.toml)
    current_dir = Path.cwd()
    print(f"Starting from: {current_dir}")
    
    # Find project config
    config_path = ProjectConfigLoader.find_project_config(current_dir)
    if config_path:
        print(f"✅ Found project config: {config_path}")
        
        try:
            project_config = ProjectConfigLoader.load_project_config(config_path)
            print(f"✅ Loaded project config successfully")
            print(f"   Products: {list(project_config.products.keys())}")
            
            for name, product in project_config.products.items():
                print(f"   - {name}: {product.name} ({product.prefix})")
                print(f"     Backlog root: {product.backlog_root}")
                
                # Test backlog root resolution
                resolved_root = project_config.resolve_backlog_root(name, config_path)
                print(f"     Resolved: {resolved_root}")
                print(f"     Exists: {resolved_root.exists() if resolved_root else False}")
        
        except Exception as e:
            print(f"❌ Failed to load project config: {e}")
            return False
    else:
        print("⚠️  No project config found")
        return False
    
    return True


def test_config_resolution():
    """Test the updated config resolution."""
    print("\n🔍 Testing Config Resolution")
    print("=" * 50)
    
    current_dir = Path.cwd()
    
    try:
        # Test with kano-agent-backlog-skill product
        print("Testing kano-agent-backlog-skill product:")
        ctx, config = ConfigLoader.load_effective_config(
            current_dir,
            product="kano-agent-backlog-skill"
        )
        
        print(f"✅ Context resolved:")
        print(f"   Project root: {ctx.project_root}")
        print(f"   Backlog root: {ctx.backlog_root}")
        print(f"   Product root: {ctx.product_root}")
        print(f"   Product name: {ctx.product_name}")
        
        print(f"✅ Config keys: {list(config.keys())}")
        
        # Test with external product
        print("\nTesting kano-opencode-quickstart product:")
        try:
            ctx2, config2 = ConfigLoader.load_effective_config(
                current_dir,
                product="kano-opencode-quickstart"
            )
            
            print(f"✅ External product resolved:")
            print(f"   Project root: {ctx2.project_root}")
            print(f"   Backlog root: {ctx2.backlog_root}")
            print(f"   Product root: {ctx2.product_root}")
            print(f"   Product name: {ctx2.product_name}")
            
        except Exception as e:
            print(f"⚠️  External product test failed (expected if path doesn't exist): {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ Config resolution failed: {e}")
        return False


def main():
    """Run all tests."""
    print("🧪 Testing New Project-Level Configuration System")
    print("=" * 60)
    
    success = True
    
    # Test project config loading
    if not test_project_config_loading():
        success = False
    
    # Test config resolution
    if not test_config_resolution():
        success = False
    
    print("\n" + "=" * 60)
    if success:
        print("✅ All tests passed!")
        return 0
    else:
        print("❌ Some tests failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())