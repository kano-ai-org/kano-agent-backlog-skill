"""State machine and transition logic for backlog items."""

from typing import Optional, List, Tuple, Dict
from datetime import date, datetime

from .models import BacklogItem, ItemState, ItemType, StateAction


class StateMachine:
    """Enforce state transitions and business rules."""

    # Valid transitions: (from_state, action) → to_state
    TRANSITIONS: Dict[Tuple[ItemState, StateAction], ItemState] = {
        # Propose path
        (ItemState.NEW, StateAction.PROPOSE): ItemState.PROPOSED,
        
        # Ready gate
        (ItemState.PROPOSED, StateAction.READY): ItemState.READY,
        (ItemState.NEW, StateAction.READY): ItemState.READY,
        
        # Start work
        (ItemState.READY, StateAction.START): ItemState.IN_PROGRESS,
        (ItemState.NEW, StateAction.START): ItemState.IN_PROGRESS,
        (ItemState.BLOCKED, StateAction.START): ItemState.IN_PROGRESS,
        
        # Review
        (ItemState.IN_PROGRESS, StateAction.REVIEW): ItemState.REVIEW,
        
        # Complete
        (ItemState.IN_PROGRESS, StateAction.DONE): ItemState.DONE,
        (ItemState.REVIEW, StateAction.DONE): ItemState.DONE,
        (ItemState.READY, StateAction.DONE): ItemState.DONE,
        
        # Block (from any state except Done/Dropped)
        (ItemState.NEW, StateAction.BLOCK): ItemState.BLOCKED,
        (ItemState.PROPOSED, StateAction.BLOCK): ItemState.BLOCKED,
        (ItemState.READY, StateAction.BLOCK): ItemState.BLOCKED,
        (ItemState.IN_PROGRESS, StateAction.BLOCK): ItemState.BLOCKED,
        (ItemState.REVIEW, StateAction.BLOCK): ItemState.BLOCKED,
        
        # Drop (from any state)
        (ItemState.NEW, StateAction.DROP): ItemState.DROPPED,
        (ItemState.PROPOSED, StateAction.DROP): ItemState.DROPPED,
        (ItemState.READY, StateAction.DROP): ItemState.DROPPED,
        (ItemState.IN_PROGRESS, StateAction.DROP): ItemState.DROPPED,
        (ItemState.REVIEW, StateAction.DROP): ItemState.DROPPED,
        (ItemState.BLOCKED, StateAction.DROP): ItemState.DROPPED,
    }

    @staticmethod
    def can_transition(state: ItemState, action: StateAction) -> bool:
        """
        Check if transition is valid (basic check, no Ready gate).

        Args:
            state: Current ItemState
            action: StateAction to perform

        Returns:
            True if transition is allowed
        """
        return (state, action) in StateMachine.TRANSITIONS

    @staticmethod
    def transition(
        item: BacklogItem, 
        action: StateAction, 
        agent: Optional[str] = None, 
        message: Optional[str] = None,
        model: Optional[str] = None,
    ) -> BacklogItem:
        """
        Execute state transition with side effects.

        Args:
            item: BacklogItem to transition (modified in-place)
            action: StateAction to perform
            agent: Agent performing the transition (optional)
            message: Optional worklog message

        Returns:
            Modified BacklogItem

        Raises:
            ValidationError: If transition is not allowed or Ready gate fails
        """
        # Check if transition exists
        key = (item.state, action)
        if key not in StateMachine.TRANSITIONS:
            from .errors import ValidationError
            raise ValidationError([f"Invalid transition: {item.state.value} --{action.value}--> (no target state)"])

        # Check Ready gate for Task/Bug when moving to Ready state
        if action == StateAction.READY and item.type in [ItemType.TASK, ItemType.BUG]:
            errors = ReadyValidator.check(item)
            if errors:
                from .errors import ValidationError
                raise ValidationError([f"Ready gate failed: {', '.join(errors)}"])

        # Execute transition
        old_state = item.state
        new_state = StateMachine.TRANSITIONS[key]
        item.state = new_state
        item.updated = date.today().isoformat()

        # Append worklog entry
        now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d %H:%M")
        state_msg = f"State: {old_state.value} → {new_state.value}"
        if message:
            worklog_text = f"{state_msg}: {message}"
        else:
            worklog_text = state_msg
        
        if agent:
            model_value = (model or "").strip() or "unknown"
            worklog_line = f"{timestamp} [agent={agent}] [model={model_value}] {worklog_text}"
        else:
            worklog_line = f"{timestamp} {worklog_text}"
        
        item.worklog.append(worklog_line)

        return item


class ReadyValidator:
    """Validate Ready gate for Task/Bug items."""

    REQUIRED_SECTIONS = ["context", "goal", "approach", "acceptance_criteria", "risks"]

    @staticmethod
    def check(item: BacklogItem) -> List[str]:
        """
        Check if item passes Ready gate.

        Args:
            item: BacklogItem to validate

        Returns:
            List of error messages (empty if validation passes)
        """
        errors = []

        # Only validate Task and Bug
        if item.type not in [ItemType.TASK, ItemType.BUG]:
            return errors

        # Check required sections are non-empty
        if not item.context or not item.context.strip():
            errors.append("context")
        
        if not item.goal or not item.goal.strip():
            errors.append("goal")
        
        if not item.approach or not item.approach.strip():
            errors.append("approach")
        
        if not item.acceptance_criteria or not item.acceptance_criteria.strip():
            errors.append("acceptance_criteria")
        
        if not item.risks or not item.risks.strip():
            errors.append("risks")

        return errors
