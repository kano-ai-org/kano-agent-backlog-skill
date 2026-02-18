"""Tests for validation logic."""

from kano_backlog_core.models import BacklogItem, ItemType, ItemState
from kano_backlog_core.validation import is_ready

def create_stub_item(item_type: ItemType, **kwargs) -> BacklogItem:
    """Create a minimal item for testing."""
    defaults = {
        "id": "TEST-001",
        "uid": "00000000-0000-0000-0000-000000000000",
        "type": item_type,
        "title": "Test Item",
        "state": ItemState.PROPOSED,
        "created": "2026-01-01",
        "updated": "2026-01-01",
    }
    defaults.update(kwargs)
    return BacklogItem(**defaults)

def test_task_ready_gate():
    """Test Ready gate validation for Tasks."""
    item = create_stub_item(ItemType.TASK)
    ready, missing = is_ready(item)
    assert not ready
    assert len(missing) == 5
    assert "Context" in missing
    assert "Goal" in missing
    
    item = create_stub_item(
        ItemType.TASK,
        context="Some context",
        goal="Some goal"
    )
    ready, missing = is_ready(item)
    assert not ready
    assert "Approach" in missing
    assert "Context" not in missing
    
    item = create_stub_item(
        ItemType.TASK,
        context="   \n  ",
        goal="Valid goal"
    )
    ready, missing = is_ready(item)
    assert "Context" in missing
    
    item = create_stub_item(
        ItemType.TASK,
        context="Context",
        goal="Goal",
        approach="Approach",
        acceptance_criteria="AC",
        risks="Risks"
    )
    ready, missing = is_ready(item)
    assert ready
    assert len(missing) == 0

def test_bug_ready_gate():
    """Test Ready gate validation for Bugs."""
    item = create_stub_item(ItemType.BUG)
    ready, missing = is_ready(item)
    assert not ready
    assert len(missing) == 5

def test_epic_ready_gate():
    """Test Ready gate validation for Epics."""
    item = create_stub_item(ItemType.EPIC)
    ready, missing = is_ready(item)
    assert not ready
    assert len(missing) == 2
    
    item = create_stub_item(
        ItemType.EPIC,
        context="Strategic context",
        goal="Business goal"
    )
    ready, missing = is_ready(item)
    assert ready
    assert len(missing) == 0

def test_feature_ready_gate():
    """Test Ready gate validation for Features."""
    item = create_stub_item(
        ItemType.FEATURE,
        context="Feature context",
        goal="Feature goal"
    )
    ready, missing = is_ready(item)
    assert not ready
    assert "Acceptance Criteria" in missing
    
    item = create_stub_item(
        ItemType.FEATURE,
        context="Feature context",
        goal="Feature goal",
        acceptance_criteria="AC list"
    )
    ready, missing = is_ready(item)
    assert ready
    assert len(missing) == 0
