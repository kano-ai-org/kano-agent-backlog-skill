#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import datetime
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

LOGGING_DIR = Path(__file__).resolve().parents[1] / "logging"
if str(LOGGING_DIR) not in sys.path:
    sys.path.insert(0, str(LOGGING_DIR))
from audit_runner import run_with_audit  # noqa: E402

COMMON_DIR = Path(__file__).resolve().parents[1] / "common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))
from product_args import add_product_arguments, get_product_and_sandbox_flags  # noqa: E402
from config_loader import get_config_value, load_config_with_defaults, resolve_allowed_root, validate_config  # noqa: E402
from context import get_context  # noqa: E402


TYPE_ORDER = ["Feature", "UserStory", "Task", "Bug"]


@dataclass(frozen=True)
class Item:
    item_id: str
    item_type: str
    title: str
    state: str
    parent: str
    path: Path


def allowed_roots_for_repo(repo_root: Path) -> List[Path]:
    return [
        (repo_root / "_kano" / "backlog").resolve(),
        (repo_root / "_kano" / "backlog_sandbox").resolve(),
    ]


def resolve_allowed_root(path: Path, allowed_roots: List[Path]) -> Optional[Path]:
    resolved = path.resolve()
    for root in allowed_roots:
        try:
            resolved.relative_to(root)
            return root
        except ValueError:
            continue
    return None


def ensure_under_allowed(path: Path, allowed_roots: List[Path], label: str) -> Path:
    root = resolve_allowed_root(path, allowed_roots)
    if root is None:
        allowed = " or ".join(str(root) for root in allowed_roots)
        raise SystemExit(f"{label} must be under {allowed}: {path}")
    return root


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a .index.md for any root item with state annotations."
    )
    parser.add_argument(
        "--items-root",
        default="_kano/backlog/items",
        help="Backlog items root (default: _kano/backlog/items).",
    )
    parser.add_argument(
        "--root-id",
        help="Root item ID to render (Epic/Feature/UserStory).",
    )
    parser.add_argument(
        "--root-path",
        help="Optional root item path to disambiguate duplicate IDs.",
    )
    parser.add_argument(
        "--index-path",
        help="Optional output path for the index file (default: adjacent to the root item).",
    )
    parser.add_argument(
        "--backlog-root",
        help="Backlog root for Dataview label (default: parent of items root).",
    )
    parser.add_argument(
        "--no-dataview",
        action="store_true",
        help="Skip the Dataview auto list section.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print output to stdout instead of writing the file.",
    )
    parser.add_argument(
        "--agent",
        help="Agent identity (used for audit and optional dashboard refresh).",
    )
    parser.add_argument(
        "--config",
        help="Optional config path override for auto-refresh behavior.",
    )
    parser.add_argument(
        "--no-refresh",
        action="store_true",
        help="Disable automatic dashboard refresh after writing index.",
    )
    add_product_arguments(parser)
    return parser.parse_args()


def strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("\"", "'"):
        return value[1:-1]
    return value


def parse_frontmatter(path: Path) -> Dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    data: Dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        data[key.strip()] = strip_quotes(raw)
    return data


def collect_items(root: Path) -> List[Item]:
    items: List[Item] = []
    for path in root.rglob("*.md"):
        if path.name == "README.md" or path.name.endswith(".index.md"):
            continue
        data = parse_frontmatter(path)
        item_id = data.get("id", "").strip()
        if not item_id:
            continue
        items.append(
            Item(
                item_id=item_id,
                item_type=data.get("type", "").strip(),
                title=data.get("title", "").strip(),
                state=data.get("state", "").strip(),
                parent=data.get("parent", "").strip(),
                path=path,
            )
        )
    return items


def build_child_map(items: List[Item]) -> Dict[str, List[Item]]:
    children: Dict[str, List[Item]] = {}
    for item in items:
        if not item.parent or item.parent.lower() == "null":
            continue
        children.setdefault(item.parent, []).append(item)
    return children


def sort_key(item: Item) -> tuple:
    type_rank = TYPE_ORDER.index(item.item_type) if item.item_type in TYPE_ORDER else len(TYPE_ORDER)
    return (type_rank, item.item_id)


def format_link(item: Item) -> str:
    label = f"{item.item_id} {item.title}".strip()
    return f"[[{item.path.stem}|{label}]]"


def render_tree(
    parent_id: str,
    children_map: Dict[str, List[Item]],
    visited: set,
    indent: str = "",
) -> List[str]:
    lines: List[str] = []
    children = sorted(children_map.get(parent_id, []), key=sort_key)
    for child in children:
        if child.item_id in visited:
            continue
        visited.add(child.item_id)
        line = f"{indent}- {format_link(child)}"
        if child.state:
            line += f" (state: {child.state})"
        else:
            line += " (state: unknown)"
        lines.append(line)
        lines.extend(render_tree(child.item_id, children_map, visited, indent + "  "))
    return lines


def render_index(
    root_item: Item,
    children_map: Dict[str, List[Item]],
    backlog_label: str,
    include_dataview: bool,
) -> List[str]:
    updated = datetime.datetime.now().strftime("%Y-%m-%d")
    lines = [
        "---",
        "type: Index",
        f"for: {root_item.item_id}",
        f"title: \"{root_item.title} Index\"",
        f"updated: {updated}",
        "---",
        "",
        "# MOC",
        "",
    ]

    visited = {root_item.item_id}
    tree_lines = render_tree(root_item.item_id, children_map, visited)
    if tree_lines:
        lines.extend(tree_lines)
    else:
        lines.append("- _No items._")

    if include_dataview:
        lines.extend(
            [
                "",
                "## Auto list (Dataview)",
                "",
                "```dataview",
                "table id, state, priority",
                f"from \"{backlog_label}/items\"",
                f"where parent = \"{root_item.item_id}\"",
                "sort priority asc",
                "```",
                "",
            ]
        )
    else:
        lines.append("")

    return lines


def resolve_backlog_label(repo_root: Path, backlog_root: Optional[Path], items_root: Path) -> str:
    if backlog_root is None and items_root.name == "items":
        backlog_root = items_root.parent
    if backlog_root is None:
        return "_kano/backlog"
    try:
        return backlog_root.relative_to(repo_root).as_posix()
    except ValueError:
        return backlog_root.as_posix()


def main() -> int:
    args = parse_args()
    repo_root = Path.cwd().resolve()
    allowed_roots = allowed_roots_for_repo(repo_root)

    product_name, use_sandbox = get_product_and_sandbox_flags(args)
    if use_sandbox and not product_name:
        raise SystemExit("--sandbox requires --product.")

    root_id = args.root_id
    root_path_arg = args.root_path
    if not root_id and not root_path_arg:
        raise SystemExit("Provide --root-id or --root-path.")

    items_root_arg = (args.items_root or "").strip() or "_kano/backlog/items"
    items_root: Path
    if product_name and items_root_arg == "_kano/backlog/items":
        ctx = get_context(product_arg=product_name, repo_root=repo_root)
        product_root = ctx["sandbox_root"] if use_sandbox else ctx["product_root"]
        if product_root is None:
            raise SystemExit(f"Sandbox root not found for product: {product_name}")
        items_root = (Path(product_root) / "items").resolve()
    else:
        items_root = Path(items_root_arg)
        if not items_root.is_absolute():
            items_root = (repo_root / items_root).resolve()
    items_root_root = ensure_under_allowed(items_root, allowed_roots, "items-root")

    backlog_root = None
    if args.backlog_root:
        backlog_root = Path(args.backlog_root)
        if not backlog_root.is_absolute():
            backlog_root = (repo_root / backlog_root).resolve()
    elif product_name and items_root.name == "items":
        backlog_root = items_root.parent

    backlog_label = resolve_backlog_label(repo_root, backlog_root, items_root)
    items = collect_items(items_root)
    items_by_id: Dict[str, List[Item]] = {}
    for item in items:
        items_by_id.setdefault(item.item_id, []).append(item)

    root_item: Optional[Item] = None
    if root_path_arg:
        root_path = Path(root_path_arg)
        if not root_path.is_absolute():
            root_path = (repo_root / root_path).resolve()
        ensure_under_allowed(root_path, allowed_roots, "root-path")
        for item in items:
            if item.path.resolve() == root_path:
                root_item = item
                break
        if root_item is None:
            raise SystemExit(f"Root path not found in items: {root_path}")
        if root_id and root_item.item_id != root_id:
            raise SystemExit("root-id does not match root-path item id.")
    else:
        matches = items_by_id.get(root_id or "", [])
        if not matches:
            raise SystemExit(f"Root item not found: {root_id}")
        if len(matches) != 1:
            raise SystemExit(
                f"Ambiguous id {root_id}. Provide --root-path to disambiguate."
            )
        root_item = matches[0]

    index_path = Path(args.index_path) if args.index_path else root_item.path.with_suffix(".index.md")
    if not index_path.is_absolute():
        index_path = (repo_root / index_path).resolve()
    index_root = ensure_under_allowed(index_path, allowed_roots, "index-path")
    if index_root != items_root_root:
        raise SystemExit("items-root and index-path must share the same root.")

    children_map = build_child_map(items)
    output_lines = render_index(root_item, children_map, backlog_label, not args.no_dataview)
    output_text = "\n".join(output_lines) + "\n"

    if args.dry_run:
        print(output_text)
        return 0

    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(output_text, encoding="utf-8")
    print(f"Updated index: {index_path}")
    # Optional: refresh dashboards if enabled
    if not args.no_refresh:
        # Load config to check auto-refresh
        config_path = args.config
        if not config_path and backlog_root is not None:
            candidate = backlog_root / "_config" / "config.json"
            if candidate.exists():
                config_path = str(candidate)
        config = load_config_with_defaults(repo_root=repo_root, config_path=config_path)
        errors = validate_config(config)
        if errors:
            print("Invalid config:\n- " + "\n- ".join(errors))
            return 0
        if bool(get_config_value(config, "views.auto_refresh", True)):
            if backlog_root is None:
                backlog_root = (repo_root / "_kano" / "backlog").resolve()
            if resolve_allowed_root(backlog_root, allowed_roots) is None:
                print(f"Skip refresh: backlog root not under allowed: {backlog_root}")
                return 0

            refresh_script = Path(__file__).resolve().parents[1] / "backlog" / "view_refresh_dashboards.py"
            cmd = [sys.executable, str(refresh_script), "--backlog-root", str(backlog_root)]
            cmd.extend(["--agent", args.agent or "system"])
            if config_path:
                cmd.extend(["--config", config_path])
            result = subprocess.run(cmd, text=True, capture_output=True)
            if result.returncode != 0:
                err = result.stderr.strip() or result.stdout.strip() or "Failed to refresh dashboards."
                print(err)
    return 0


if __name__ == "__main__":
    raise SystemExit(run_with_audit(main))
