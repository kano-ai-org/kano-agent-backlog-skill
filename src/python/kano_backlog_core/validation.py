"""Validation logic for backlog items."""

from typing import List, Tuple
from .models import BacklogItem, ItemType

def is_ready(item: BacklogItem) -> Tuple[bool, List[str]]:
    """
    Check if item meets Ready gate criteria tailored by item type.
    
    Requirements:
    - Epic: Context, Goal
    - Feature/UserStory: Context, Goal, Acceptance Criteria
    - Task/Bug: Context, Goal, Approach, Acceptance Criteria, Risks
    
    Args:
        item: The backlog item to validate
        
    Returns:
        Tuple of (is_valid, missing_fields)
    """
    # Define required fields per type
    # Using tuple of (attribute_name, display_name)
    type_requirements = {
        ItemType.EPIC: [
            ("context", "Context"),
            ("goal", "Goal"),
        ],
        ItemType.FEATURE: [
            ("context", "Context"),
            ("goal", "Goal"),
            ("acceptance_criteria", "Acceptance Criteria"),
        ],
        ItemType.USER_STORY: [
            ("context", "Context"),
            ("goal", "Goal"),
            ("acceptance_criteria", "Acceptance Criteria"),
        ],
        ItemType.TASK: [
            ("context", "Context"),
            ("goal", "Goal"),
            ("approach", "Approach"),
            ("acceptance_criteria", "Acceptance Criteria"),
            ("risks", "Risks / Dependencies"),
        ],
        ItemType.BUG: [
            ("context", "Context"),
            ("goal", "Goal"),
            ("approach", "Approach"),
            ("acceptance_criteria", "Acceptance Criteria"),
            ("risks", "Risks / Dependencies"),
        ],
    }
    
    required_fields = type_requirements.get(item.type, [])
    
    missing = []
    
    for field_attr, field_name in required_fields:
        value = getattr(item, field_attr, None)
        
        # Check if value is None or empty string (whitespace only)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field_name)
            
    return len(missing) == 0, missing
