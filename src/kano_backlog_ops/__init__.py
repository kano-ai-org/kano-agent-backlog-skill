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

from .init import init_backlog, check_initialized
from .workitem import (
    create_item,
    update_state,
    validate_ready,
    list_items,
    get_item,
)
from .adr import create_adr, list_adrs
from .view import refresh_dashboards, generate_view
from .workset import init_workset, refresh_workset, get_next_item, promote_item
from .index import build_index, refresh_index

__all__ = [
    # init
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
    # workset
    "init_workset",
    "refresh_workset",
    "get_next_item",
    "promote_item",
    # index
    "build_index",
    "refresh_index",
]
