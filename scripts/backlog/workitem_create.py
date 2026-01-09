#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime
import re
import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import List, Optional
from lib.utils import generate_uid

COMMON_DIR = Path(__file__).resolve().parents[1] / "common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))
from config_loader import get_config_value, load_config_with_defaults, validate_config  # noqa: E402
from context import get_context  # noqa: E402

LOGGING_DIR = Path(__file__).resolve().parents[1] / "logging"
if str(LOGGING_DIR) not in sys.path:
    sys.path.insert(0, str(LOGGING_DIR))
from audit_runner import run_with_audit  # noqa: E402

COMMON_DIR = Path(__file__).resolve().parents[1] / "common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))
from product_args import add_product_arguments, get_product_and_sandbox_flags  # noqa: E402


TYPE_MAP = {
    "epic": ("Epic", "EPIC", ("epic", "epics")),
    "feature": ("Feature", "FTR", ("feature", "features")),
    "userstory": ("UserStory", "USR", ("userstory", "userstories")),
    "task": ("Task", "TSK", ("task", "tasks")),
    "bug": ("Bug", "BUG", ("bug", "bugs")),
}


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
    parser = argparse.ArgumentParser(description="Create a backlog work item from a template.")
    parser.add_argument(
        "--items-root",
        default="_kano/backlog/items",
        help="Backlog items root (default: _kano/backlog/items).",
    )
    parser.add_argument(
        "--backlog-root",
        help="Backlog root for index registry (default: parent of items root).",
    )
    parser.add_argument("--type", required=True, help="Epic|Feature|UserStory|Task|Bug (work item type).")
    parser.add_argument("--title", required=True, help="Work item title.")
    parser.add_argument("--parent", help="Parent work item ID.")
    parser.add_argument("--priority", default="P2", help="Priority (default: P2).")
    parser.add_argument("--area", default="general", help="Area (default: general).")
    parser.add_argument("--iteration", default="null", help="Iteration value or null.")
    parser.add_argument("--tags", default="", help="Comma-separated tags.")
    parser.add_argument("--owner", default="null", help="Owner value or null.")
    parser.add_argument("--agent", required=True, help="Worklog agent name (required).")
    parser.add_argument(
        "--config",
        help=(
            "Optional config path override (default: KANO_BACKLOG_CONFIG_PATH or _kano/backlog/_config/config.json). "
            "Used for project.name/prefix defaults."
        ),
    )
    add_product_arguments(parser)
    parser.add_argument("--project-name", help="Project name override.")
    parser.add_argument("--prefix", help="ID prefix override.")
    parser.add_argument(
        "--create-index",
        action="store_true",
        help="Create Epic index file (default for Epic).",
    )
    parser.add_argument(
        "--no-index",
        action="store_true",
        help="Skip Epic index file creation.",
    )
    parser.add_argument(
        "--index-registry",
        help="Path to indexes.md (default: <backlog-root>/_meta/indexes.md). Use 'none' to disable.",
    )
    parser.add_argument(
        "--worklog-message",
        default="Created from template.",
        help="Initial Worklog message.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print target path and exit.")
    parser.add_argument(
        "--no-refresh",
        action="store_true",
        help="Disable automatic dashboard refresh for this invocation.",
    )
    return parser.parse_args()


def normalize_nullable(value: Optional[str]) -> str:
    if value is None:
        return "null"
    trimmed = value.strip()
    if trimmed.lower() in ("", "null", "none"):
        return "null"
    return trimmed


def pick_items_subdir(items_root: Path, candidates: tuple[str, str]) -> str:
    """
    Choose the canonical type folder for the current backlog root.

    - Multi-product layout prefers singular (e.g. items/feature/).
    - Legacy layouts may still use plural (e.g. items/features/).
    - If neither exists yet, return the canonical choice for that layout.
    """
    singular, plural = candidates
    if (items_root / singular).exists():
        return singular
    if (items_root / plural).exists():
        return plural
    parts = items_root.as_posix().split("/")
    if "products" in parts:
        return singular
    return plural


def yaml_list(values: List[str]) -> str:
    if not values:
        return "[]"
    escaped = [v.replace('"', '\\"') for v in values]
    inner = ", ".join(f"\"{v}\"" for v in escaped)
    return f"[{inner}]"


def read_project_name(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("PROJECT_NAME="):
            value = line.split("=", 1)[1].strip()
            if value and value[0] in ('"', "'") and value[-1] == value[0]:
                value = value[1:-1]
            return value
    return None


def split_segments(name: str) -> List[str]:
    parts = re.split(r"[^A-Za-z0-9]+", name)
    segments: List[str] = []
    for part in parts:
        if not part:
            continue
        segments.extend(re.findall(r"[A-Z]+(?=[A-Z][a-z]|[0-9]|$)|[A-Z]?[a-z]+|[0-9]+", part))
    return segments


def derive_prefix(name: str) -> str:
    segments = split_segments(name)
    letters = []
    for seg in segments:
        for ch in seg:
            if ch.isalpha():
                letters.append(ch)
                break
    prefix = "".join(letters)

    if len(prefix) == 1:
        seed = segments[0] if segments else name
        consonant = ""
        for ch in seed[1:]:
            if ch.isalpha() and ch.upper() not in "AEIOU":
                consonant = ch
                break
        if consonant:
            prefix += consonant
        else:
            for ch in seed[1:]:
                if ch.isalpha():
                    prefix += ch
                    break

    if len(prefix) < 2:
        letters = [ch for ch in name if ch.isalpha()]
        if len(letters) >= 2:
            prefix = letters[0] + letters[1]

    if not prefix:
        raise ValueError("Unable to derive prefix. Provide --prefix or --project-name.")

    return prefix.upper()


def slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", ascii_text).strip("-").lower()
    return slug or "untitled"


def read_frontmatter_id(path: Path) -> Optional[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith("id:"):
            return line.split(":", 1)[1].strip().strip('"')
    return None


def find_next_number(root: Path, prefix: str, type_code: str) -> int:
    pattern = re.compile(rf"{re.escape(prefix)}-{type_code}-(\d{{4}})")
    max_num = 0
    if not root.exists():
        return 1
    for path in root.rglob("*.md"):
        if path.name == "README.md" or path.name.endswith(".index.md"):
            continue
        item_id = read_frontmatter_id(path)
        match = pattern.search(item_id or path.name)
        if not match:
            continue
        number = int(match.group(1))
        if number > max_num:
            max_num = number
    return max_num + 1


def build_index_registry_path(backlog_root: Optional[Path], override: Optional[str]) -> Optional[Path]:
    if override:
        if override.lower() == "none":
            return None
        return Path(override)
    if backlog_root:
        return backlog_root / "_meta" / "indexes.md"
    return None


def should_auto_refresh(config: dict) -> bool:
    return bool(get_config_value(config, "views.auto_refresh", True))


def refresh_dashboards(backlog_root: Path, agent: str, config_path: Optional[str]) -> None:
    refresh_script = Path(__file__).resolve().parent / "view_refresh_dashboards.py"
    cmd = [sys.executable, str(refresh_script), "--backlog-root", str(backlog_root), "--agent", agent]
    if config_path:
        cmd.extend(["--config", config_path])
    result = subprocess.run(cmd, text=True, capture_output=True)
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or result.stdout.strip() or "Failed to refresh dashboards.")


def refresh_parent_index(items_root: Path, backlog_root: Path, parent_id: str, agent: str) -> None:
    index_script = Path(__file__).resolve().parent / "workitem_generate_index.py"
    cmd = [
        sys.executable, str(index_script),
        "--root-id", parent_id,
        "--items-root", str(items_root),
        "--backlog-root", str(backlog_root),
        "--agent", agent
    ]
    # Silently attempt refresh; parent might not have an index file or might be external
    subprocess.run(cmd, text=True, capture_output=True)


def update_index_registry(path: Path, item_id: str, index_file: str, updated: str, notes: str) -> None:
    if not path.exists():
        return

    lines = path.read_text(encoding="utf-8").splitlines()
    if any(item_id in line for line in lines):
        return

    header_idx = None
    for idx, line in enumerate(lines):
        if line.strip().startswith("| type |"):
            header_idx = idx
            break

    if header_idx is None:
        lines.extend(["", "| type | item_id | index_file | updated | notes |", "| ---- | ------- | ---------- | ------- | ----- |"])
    elif header_idx + 1 >= len(lines) or "|" not in lines[header_idx + 1]:
        lines.insert(header_idx + 1, "| ---- | ------- | ---------- | ------- | ----- |")

    lines.append(f"| Epic | {item_id} | {index_file} | {updated} | {notes} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def render_item(
    item_id: str,
    uid: str,
    item_type: str,
    title: str,
    priority: str,
    parent: str,
    area: str,
    iteration: str,
    tags: str,
    created: str,
    updated: str,
    owner: str,
    agent: str,
    message: str,
) -> str:
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "---",
        f"id: {item_id}",
        f"uid: {uid}",
        f"type: {item_type}",
        f"title: \"{title}\"",
        "state: Proposed",
        f"priority: {priority}",
        f"parent: {parent}",
        f"area: {area}",
        f"iteration: {iteration}",
        f"tags: {tags}",
        f"created: {created}",
        f"updated: {updated}",
        f"owner: {owner}",
        "external:",
        "  azure_id: null",
        "  jira_key: null",
        "links:",
        "  relates: []",
        "  blocks: []",
        "  blocked_by: []",
        "decisions: []",
        "---",
        "",
        "# Context",
        "",
        "# Goal",
        "",
        "# Non-Goals",
        "",
        "# Approach",
        "",
        "# Alternatives",
        "",
        "# Acceptance Criteria",
        "",
        "# Risks / Dependencies",
        "",
        "# Worklog",
        "",
        f"{timestamp} [agent={agent}] {message}",
    ]
    return "\n".join(lines) + "\n"


def render_index(item_id: str, title: str, updated: str, backlog_root_label: str) -> str:
    lines = [
        "---",
        "type: Index",
        f"for: {item_id}",
        f"title: \"{title} Index\"",
        f"updated: {updated}",
        "---",
        "",
        "# MOC",
        "",
        "## Auto list (Dataview)",
        "",
        "```dataview",
        "table id, state, priority",
        f"from \"{backlog_root_label}/items\"",
        f"where parent = \"{item_id}\"",
        "sort priority asc",
        "```",
        "",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    type_key = args.type.strip().lower()
    if type_key not in TYPE_MAP:
        raise SystemExit(f"Unknown type: {args.type}. Use Epic, Feature, UserStory, Task, or Bug.")

    type_label, type_code, type_folder_candidates = TYPE_MAP[type_key]

    repo_root = Path.cwd().resolve()
    ctx = get_context(product_arg=args.product, repo_root=repo_root)
    product_root = ctx["product_root"]
    product_name = ctx["product_name"]
    # For view rendering we must refresh the product backlog root (not the platform root),
    # otherwise generated dashboards under `products/<product>/views` won't update.
    backlog_root = product_root

    config_path = args.config
    if not config_path:
        default_config = product_root / "_config" / "config.json"
        if default_config.exists():
            config_path = str(default_config)

    config = load_config_with_defaults(repo_root=repo_root, config_path=config_path)
    errors = validate_config(config)
    if errors:
        raise SystemExit("Invalid config:\n- " + "\n- ".join(errors))
    allowed_roots = allowed_roots_for_repo(repo_root)

    # Context already resolved above

    prefix = args.prefix
    if not prefix:
        config_prefix = get_config_value(config, "project.prefix")
        if isinstance(config_prefix, str) and config_prefix.strip():
            prefix = config_prefix.strip()
        else:
            project_name = args.project_name or get_config_value(config, "project.name")
            project_name = project_name or read_project_name(Path("config/profile.env"))
            if not project_name:
                # Use product_name as fallback for deriving prefix
                project_name = product_name
            prefix = derive_prefix(project_name)

    parent = normalize_nullable(args.parent)
    if type_label != "Epic" and parent == "null":
        print("Warning: non-Epic item without --parent.")

    items_root = product_root / "items"
    type_folder = pick_items_subdir(items_root, type_folder_candidates)
    # Numbering must be unique within the product even during migrations where
    # legacy and new folder layouts can coexist (e.g. `items/feature/` vs `items/features/`).
    # Scan the entire items root for this type code to avoid ID collisions.
    next_number = find_next_number(items_root, prefix, type_code)
    bucket = (next_number // 100) * 100
    bucket_str = f"{bucket:04d}"

    slug = slugify(args.title)
    item_id = f"{prefix}-{type_code}-{next_number:04d}"
    file_name = f"{item_id}_{slug}.md"
    item_path = items_root / type_folder / bucket_str / file_name

    if item_path.exists():
        raise SystemExit(f"Item already exists: {item_path}")

    if args.dry_run:
        print(f"ID: {item_id}")
        print(f"Path: {item_path}")
        return 0

    tags = [tag.strip() for tag in args.tags.split(",") if tag.strip()]
    date = datetime.datetime.now().strftime("%Y-%m-%d")

    uid = generate_uid()

    item_body = render_item(
        item_id=item_id,
        uid=uid,
        item_type=type_label,
        title=args.title,
        priority=args.priority,
        parent=parent,
        area=normalize_nullable(args.area),
        iteration=normalize_nullable(args.iteration),
        tags=yaml_list(tags),
        created=date,
        updated=date,
        owner=normalize_nullable(args.owner),
        agent=args.agent,
        message=args.worklog_message,
    )

    item_path.parent.mkdir(parents=True, exist_ok=True)
    item_path.write_text(item_body, encoding="utf-8")
    print(f"Created item: {item_path}")

    create_index = args.create_index or (type_label == "Epic" and not args.no_index)
    if type_label == "Epic" and create_index:
        index_path = item_path.with_suffix(".index.md")
        backlog_label = f"_kano/backlog/products/{product_name}"
        try:
            backlog_label = product_root.relative_to(repo_root).as_posix()
        except ValueError:
            pass
        index_body = render_index(item_id, args.title, date, backlog_label)
        index_path.write_text(index_body, encoding="utf-8")
        print(f"Created index: {index_path}")

        registry_path = product_root / "_meta" / "indexes.md"
        if registry_path:
            registry_path = registry_path.resolve()
            index_rel = index_path
            try:
                index_rel = index_path.relative_to(repo_root)
            except ValueError:
                pass
            update_index_registry(
                registry_path,
                item_id=item_id,
                index_file=index_rel.as_posix(),
                updated=date,
                notes=args.title,
            )

    if backlog_root and not args.no_refresh and should_auto_refresh(config):
        refresh_dashboards(backlog_root=backlog_root, agent=args.agent, config_path=args.config)
        if parent and parent != "null":
            refresh_parent_index(items_root=items_root, backlog_root=product_root, parent_id=parent, agent=args.agent)

    return 0


if __name__ == "__main__":
    raise SystemExit(run_with_audit(main))
