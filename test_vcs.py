#!/usr/bin/env python3
"""Test VCS metadata functionality."""

import sys
from pathlib import Path

# Add src to path
skill_root = Path(__file__).parent.parent
src_dir = skill_root / "src"
sys.path.insert(0, str(src_dir))

from kano_backlog_core.vcs.detector import detect_vcs_metadata, format_vcs_metadata


def test_vcs_detection():
    """Test VCS metadata detection."""
    print("Testing VCS metadata detection...")
    
    # Test detection
    meta = detect_vcs_metadata()
    print(f"Provider: {meta.provider}")
    print(f"Revision: {meta.revision}")
    print(f"Ref: {meta.ref}")
    print(f"Label: {meta.label}")
    print(f"Dirty: {meta.dirty}")
    
    # Test formatting
    formatted_min = format_vcs_metadata(meta, "min")
    print(f"\nFormatted (min):\n{formatted_min}")
    
    formatted_full = format_vcs_metadata(meta, "full")
    print(f"\nFormatted (full):\n{formatted_full}")
    
    # Verify no timestamps
    assert "Generated:" not in formatted_min
    assert "Generated:" not in formatted_full
    assert "timestamp" not in formatted_min.lower()
    assert "timestamp" not in formatted_full.lower()
    
    print("\n✅ All tests passed!")


if __name__ == "__main__":
    test_vcs_detection()