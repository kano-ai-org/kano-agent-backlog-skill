"""
test_item_state_planned.py - Regression tests for ItemState vocabulary.
"""

from kano_backlog_core.models import ItemState


def test_item_state_accepts_planned() -> None:
    assert ItemState("Planned") == ItemState.PLANNED

