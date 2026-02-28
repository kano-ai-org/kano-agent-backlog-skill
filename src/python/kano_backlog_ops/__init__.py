"""
kano_backlog_ops - Use-case functions for backlog operations.

This package provides the business logic layer for all backlog operations.
CLI commands and future facades (HTTP/MCP) delegate to these functions.

Per ADR-0013, this is an import-only package - never executed directly.

Modules:
    init: Backlog initialization operations
    workitem: Work item CRUD operations
    adr: ADR management operations
    view: View and dashboard generation
    workset: Workset cache management
    index: SQLite index operations
"""

from .init import InitBacklogResult, init_backlog, check_initialized
from .workitem import (
    create_item,
    update_state,
    add_decision_writeback,
    validate_ready,
    list_items,
    get_item,
    DecisionWritebackResult,
)
from .adr import create_adr, list_adrs
from .view import refresh_dashboards, generate_view
from .workset import (
    # Functions
    init_workset,
    refresh_workset,
    get_next_action,
    promote_deliverables,
    cleanup_worksets,
    detect_adr_candidates,
    list_worksets,
    # Directory utilities
    get_workset_cache_root,
    get_item_workset_path,
    get_topic_path,
    ensure_workset_dirs,
    # Data models
    WorksetMetadata,
    WorksetInitResult,
    WorksetRefreshResult,
    WorksetNextResult,
    WorksetPromoteResult,
    WorksetCleanupResult,
    # Errors
    WorksetError,
    ItemNotFoundError as WorksetItemNotFoundError,
    WorksetNotFoundError,
    WorksetValidationError,
)
from .backlog_index import build_index, refresh_index
from .demo import seed_demo, DemoSeedResult
from .persona import generate_summary, generate_report, PersonaSummaryResult, PersonaReportResult
from .sandbox import init_sandbox, SandboxInitResult
from .validate import validate_uids, UidValidationResult, UidViolation
from .topic import (
    # Functions
    create_topic,
    add_item_to_topic,
    pin_document,
    switch_topic,
    get_active_topic,
    export_topic_context,
    list_topics,
    # Shared state functions (KABSD-TSK-0257)
    load_state_index,
    save_state_index,
    load_topic_state,
    save_topic_state,
    generate_topic_id,
    migrate_legacy_active_topics,
    cleanup_legacy_active_topics,
    migrate_topic_state_filenames,
    list_active_topics,
    get_topic_state_by_name,
    update_agent_state,
    update_worksets_after_merge,
    generate_decision_audit_report,
    get_topics_root,
    get_topic_path,
    get_active_topic_path,
    get_state_store_path,
    get_state_topics_dir,
    ensure_topic_dirs,
    validate_topic_name,
    is_valid_topic_name,
    # Data models
    TopicManifest,
    TopicCreateResult,
    TopicAddResult,
    TopicPinResult,
    TopicSwitchResult,
    TopicContextBundle,
    TopicDecisionAuditResult,
    # Shared state data models (KABSD-TSK-0257)
    StateIndex,
    AgentTopicState,
    TopicStateDocument,
    # Errors
    TopicError,
    TopicNotFoundError,
    TopicExistsError,
    TopicValidationError,
)
from .template import (
    # Functions
    create_topic_from_template,
    get_available_templates,
    get_template_info,
    validate_template_by_name,
    # Data models
    TemplateListResult,
    TemplateLoadResult,
    # Errors
    TemplateError,
    TemplateNotFoundError,
    TemplateValidationError,
)

__all__ = [
    # init
    "InitBacklogResult",
    "init_backlog",
    "check_initialized",
    # workitem
    "create_item",
    "update_state",
    "validate_ready",
    "list_items",
    "get_item",
    # adr
    "create_adr",
    "list_adrs",
    # view
    "refresh_dashboards",
    "generate_view",
    # workset - functions
    "init_workset",
    "refresh_workset",
    "get_next_action",
    "promote_deliverables",
    "cleanup_worksets",
    "detect_adr_candidates",
    "list_worksets",
    # workset - directory utilities
    "get_workset_cache_root",
    "get_item_workset_path",
    "get_topic_path",
    "ensure_workset_dirs",
    # workset - data models
    "WorksetMetadata",
    "WorksetInitResult",
    "WorksetRefreshResult",
    "WorksetNextResult",
    "WorksetPromoteResult",
    "WorksetCleanupResult",
    # workset - errors
    "WorksetError",
    "WorksetItemNotFoundError",
    "WorksetNotFoundError",
    "WorksetValidationError",
    # index
    "build_index",
    "refresh_index",
    # demo
    "seed_demo",
    "DemoSeedResult",
    # persona
    "generate_summary",
    "generate_report",
    "PersonaSummaryResult",
    "PersonaReportResult",
    # sandbox
    "init_sandbox",
    "SandboxInitResult",
    # validation
    "validate_uids",
    "UidValidationResult",
    "UidViolation",
    # topic - functions
    "create_topic",
    "add_item_to_topic",
    "pin_document",
    "switch_topic",
    "get_active_topic",
    "export_topic_context",
    "list_topics",
    # topic - shared state functions (KABSD-TSK-0257)
    "load_state_index",
    "save_state_index",
    "load_topic_state",
    "save_topic_state",
    "generate_topic_id",
    "migrate_legacy_active_topics",
    "cleanup_legacy_active_topics",
    "migrate_topic_state_filenames",
    "list_active_topics",
    "get_topic_state_by_name",
    "update_agent_state",
    "update_worksets_after_merge",
    "generate_decision_audit_report",
    # topic - directory utilities
    "get_topics_root",
    "get_topic_path",
    "get_active_topic_path",
    "get_state_store_path",
    "get_state_topics_dir",
    "ensure_topic_dirs",
    "validate_topic_name",
    "is_valid_topic_name",
    # topic - data models
    "TopicManifest",
    "TopicCreateResult",
    "TopicAddResult",
    "TopicPinResult",
    "TopicSwitchResult",
    "TopicContextBundle",
    "TopicDecisionAuditResult",
    # topic - shared state data models (KABSD-TSK-0257)
    "StateIndex",
    "AgentTopicState",
    "TopicStateDocument",
    # topic - errors
    "TopicError",
    "TopicNotFoundError",
    "TopicExistsError",
    "TopicValidationError",
    # template - functions
    "create_topic_from_template",
    "get_available_templates",
    "get_template_info",
    "validate_template_by_name",
    # template - data models
    "TemplateListResult",
    "TemplateLoadResult",
    # template - errors
    "TemplateError",
    "TemplateNotFoundError",
    "TemplateValidationError",
]
