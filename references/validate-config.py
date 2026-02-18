#!/usr/bin/env python3
"""
Validation script for .kano/backlog_config.toml

This script validates the project-level backlog configuration file
and shows the resolved configuration for each product.
"""

import sys
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib  # Fallback for older Python
    except ImportError:
        print("Error: Need tomllib (Python 3.11+) or tomli package")
        sys.exit(1)


def validate_config(config_path: Path) -> bool:
    """Validate the backlog configuration file."""
    if not config_path.exists():
        print(f"❌ Config file not found: {config_path}")
        return False
    
    try:
        with open(config_path, 'rb') as f:
            config = tomllib.load(f)
    except Exception as e:
        print(f"❌ Failed to parse TOML: {e}")
        return False
    
    print(f"✅ Successfully parsed: {config_path}")
    
    # Validate structure
    products = config.get('products', {})
    if not products:
        print("⚠️  No products defined")
        return True
    
    print(f"📦 Found {len(products)} products:")
    
    valid = True
    for product_name, product_config in products.items():
        print(f"\n  🔍 Validating product: {product_name}")
        
        # Check required fields
        required_fields = ['name', 'prefix', 'backlog_root']
        for field in required_fields:
            if field not in product_config:
                print(f"    ❌ Missing required field: {field}")
                valid = False
            else:
                print(f"    ✅ {field}: {product_config[field]}")
        
        # Check backlog_root path
        if 'backlog_root' in product_config:
            backlog_path = Path(product_config['backlog_root'])
            if backlog_path.is_absolute():
                resolved_path = backlog_path
            else:
                resolved_path = config_path.parent.parent / backlog_path
            
            print(f"    📁 Resolved path: {resolved_path}")
            if not resolved_path.exists():
                print(f"    ⚠️  Path does not exist (will be created on init)")
    
    # Show shared config
    shared = config.get('shared', {})
    if shared:
        print(f"\n🔧 Shared configuration:")
        for key, value in shared.items():
            print(f"  {key}: {value}")
    
    # Show defaults
    defaults = config.get('defaults', {})
    if defaults:
        print(f"\n⚙️  Default configuration:")
        for key, value in defaults.items():
            print(f"  {key}: {value}")
    
    return valid


def main():
    """Main validation function."""
    config_path = Path('.kano/backlog_config.toml')
    
    print("🔍 Validating Kano Backlog Configuration")
    print("=" * 50)
    
    if validate_config(config_path):
        print("\n✅ Configuration is valid!")
        return 0
    else:
        print("\n❌ Configuration has errors!")
        return 1


if __name__ == "__main__":
    sys.exit(main())