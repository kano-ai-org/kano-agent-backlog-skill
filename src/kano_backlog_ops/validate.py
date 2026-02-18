from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional
from datetime import datetime
import fnmatch
import os
import re
import subprocess

from kano_backlog_core.config import ConfigLoader
import frontmatter
from kano_backlog_ops import item_utils, worklog


@dataclass
class UidViolation:
    path: Path
    uid: str
    reason: str


@dataclass
class UidValidationResult:
    product: str
    checked: int
    violations: List[UidViolation]


def validate_uids(product: str | None = None, backlog_root: Path | None = None) -> List[UidValidationResult]:
    """Validate that all items use UUIDv7 UIDs.

    Returns a list of per-product results with violations (empty list if all clean).
    """

    # Resolve target products
    product_roots: list[Path] = []
    if backlog_root:
        backlog_root = Path(backlog_root).resolve()
        if product:
            product_roots.append(backlog_root / "products" / product)
        else:
            products_dir = backlog_root / "products"
            if products_dir.exists():
                product_roots.extend([p for p in products_dir.iterdir() if p.is_dir()])
    else:
        # Resolve from current workspace; product optional
        if product:
            ctx = ConfigLoader.from_path(Path.cwd(), product=product)
            product_roots.append(ctx.product_root)
        else:
            ctx = ConfigLoader.from_path(Path.cwd())
            products_dir = ctx.backlog_root / "products"
            if products_dir.exists():
                product_roots.extend([p for p in products_dir.iterdir() if p.is_dir()])

    v7_pattern = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
    results: list[UidValidationResult] = []

    for root in product_roots:
        violations: list[UidViolation] = []
        checked = 0
        for item_path in (root / "items").rglob("*.md"):
            name = item_path.name.lower()
            if name.startswith("readme") or name.endswith(".index.md"):
                continue
            try:
                post = frontmatter.loads(item_path.read_text(encoding="utf-8"))
            except Exception as exc:  # pragma: no cover - defensive
                violations.append(UidViolation(item_path, "<unreadable>", f"Failed to parse frontmatter: {exc}"))
                continue
            checked += 1
            uid = str(post.get("uid", "")).lower()
            if not uid:
                violations.append(UidViolation(item_path, "<missing>", "Missing uid"))
                continue
            if not v7_pattern.match(uid):
                violations.append(UidViolation(item_path, uid, "UID is not UUIDv7"))
        results.append(UidValidationResult(product=root.name, checked=checked, violations=violations))

    return results


@dataclass
class LinkIssue:
    source_path: Path
    line: int
    column: int
    link_type: str
    link_text: str
    target: str


@dataclass
class LinkValidationResult:
    product: str
    checked_files: int
    issues: List[LinkIssue]


@dataclass
class LinkChange:
    source_path: Path
    line: int
    column: int
    link_type: str
    original: str
    updated: str
    reason: str


@dataclass
class LinkFixResult:
    product: str
    checked_files: int
    updated_files: int
    changes: List[LinkChange]


@dataclass
class LinkRestoreAction:
    source_path: Path
    target: str
    status: str
    candidates: List[str]
    restored_path: Optional[str]


@dataclass
class LinkRestoreResult:
    product: str
    checked_files: int
    actions: List[LinkRestoreAction]


@dataclass
class RefRemapResult:
    old_id: str
    new_id: str
    old_path: Path
    new_path: Path
    updated_files: int


@dataclass
class DuplicateIdConflict:
    id: str
    uid: str
    paths: list[str]
    hashes: list[str]


@dataclass
class DuplicateIdRemap:
    old_id: str
    new_id: str
    uid: str
    old_path: Path
    new_path: Path
    status: str


@dataclass
class DuplicateIdReport:
    product: str
    checked: int
    duplicates: int
    conflicts: list[DuplicateIdConflict]
    remaps: list[DuplicateIdRemap]
    updated_files: int


_MARKDOWN_LINK_RE = re.compile(r"(?<!\!)\[[^\]]+\]\(([^)]+)\)")
_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
_EXTERNAL_PREFIXES = ("http://", "https://", "mailto:", "tel:", "obsidian:", "file:", "vscode:")


def _resolve_product_roots(
    *,
    product: str | None = None,
    backlog_root: Path | None = None,
) -> list[Path]:
    product_roots: list[Path] = []
    if backlog_root:
        backlog_root = Path(backlog_root).resolve()
        if product:
            product_roots.append(backlog_root / "products" / product)
        else:
            products_dir = backlog_root / "products"
            if products_dir.exists():
                product_roots.extend([p for p in products_dir.iterdir() if p.is_dir()])
    else:
        if product:
            ctx = ConfigLoader.from_path(Path.cwd(), product=product)
            product_roots.append(ctx.product_root)
        else:
            ctx = ConfigLoader.from_path(Path.cwd())
            products_dir = ctx.backlog_root / "products"
            if products_dir.exists():
                product_roots.extend([p for p in products_dir.iterdir() if p.is_dir()])
    return product_roots


def _replace_id_tokens(text: str, old_id: str, new_id: str) -> str:
    pattern = re.compile(rf"(?<![A-Z0-9-]){re.escape(old_id)}(?![A-Z0-9-])")
    return pattern.sub(new_id, text)


def _replace_id_tokens_excluding_worklog(text: str, old_id: str, new_id: str) -> str:
    lines = text.splitlines()
    worklog_idx = worklog.find_worklog_section(lines)
    if worklog_idx == -1:
        return _replace_id_tokens(text, old_id, new_id)
    head = "\n".join(lines[:worklog_idx])
    tail = "\n".join(lines[worklog_idx:])
    updated_head = _replace_id_tokens(head, old_id, new_id)
    if head:
        return f"{updated_head}\n{tail}"
    return tail


def replace_id_in_files(
    paths: Iterable[Path],
    *,
    old_id: str,
    new_id: str,
    skip_worklog: bool = True,
    apply: bool = False,
) -> int:
    updated_files = 0
    for path in paths:
        path = path.resolve()
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if skip_worklog:
            updated = _replace_id_tokens_excluding_worklog(text, old_id, new_id)
        else:
            updated = _replace_id_tokens(text, old_id, new_id)
        if updated != text:
            if apply:
                path.write_text(updated, encoding="utf-8")
            updated_files += 1
    return updated_files


def replace_link_targets(
    paths: Iterable[Path],
    *,
    old_id: str,
    new_path: Path,
    apply: bool = False,
) -> int:
    updated_files = 0
    for path in paths:
        path = path.resolve()
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        lines = content.splitlines()
        file_changed = False
        new_rel = _relpath_posix(path.parent, new_path)
        new_stem = new_path.stem

        for idx, line in enumerate(lines):
            def _rewrite_markdown(match: re.Match) -> str:
                nonlocal file_changed
                raw_target = match.group(1)
                target, suffix, is_angle = _split_target_and_suffix(raw_target)
                if old_id not in target:
                    return match.group(0)
                base = _drop_fragment(target)
                fragment = ""
                if "#" in target:
                    fragment = "#" + target.split("#", 1)[1]
                if base == old_id or base.endswith(f"/{old_id}") or base.endswith(f"\\{old_id}") or "/" in base or "\\" in base:
                    new_target = f"{new_rel}{fragment}"
                else:
                    new_target = f"{base.replace(old_id, new_stem)}{fragment}"
                updated_target = _rebuild_target(new_target, suffix, is_angle)
                file_changed = True
                return match.group(0).replace(raw_target, updated_target, 1)

            def _rewrite_wikilink(match: re.Match) -> str:
                nonlocal file_changed
                raw = match.group(1).strip()
                if not raw:
                    return match.group(0)
                parts = raw.split("|", 1)
                target = parts[0].strip()
                alias = parts[1].strip() if len(parts) > 1 else ""
                if old_id not in target:
                    return match.group(0)
                if "/" in target or "\\" in target or target.startswith("."):
                    new_target = new_rel
                else:
                    new_target = new_stem
                new_link = f"[[{new_target}]]"
                if alias:
                    new_link = f"[[{new_target}|{alias}]]"
                file_changed = True
                return new_link

            line = _MARKDOWN_LINK_RE.sub(_rewrite_markdown, line)
            line = _WIKILINK_RE.sub(_rewrite_wikilink, line)
            lines[idx] = line

        if file_changed:
            updated_files += 1
            if apply:
                path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return updated_files


def _next_ref_id(root: Path, prefix: str) -> str:
    pattern = re.compile(rf"{re.escape(prefix)}-(\d{{4}})")
    max_num = 0
    for path in root.glob("*.md"):
        match = pattern.search(path.name)
        if match:
            num = int(match.group(1))
            max_num = max(max_num, num)
    return f"{prefix}-{max_num + 1:04d}"


def _iter_markdown_files(product_root: Path, *, include_views: bool) -> Iterable[Path]:
    roots = [
        product_root / "items",
        product_root / "decisions",
        product_root / "_meta",
    ]
    if include_views:
        roots.append(product_root / "views")

    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.md"):
            if ".cache" in path.parts:
                continue
            if "_analysis" in path.parts and "views" in path.parts:
                continue
            yield path

    readme = product_root / "README.md"
    if readme.exists():
        yield readme


def _iter_canonical_files(product_root: Path) -> Iterable[Path]:
    roots = [
        product_root / "items",
        product_root / "decisions",
    ]
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.md"):
            if ".cache" in path.parts:
                continue
            name = path.name.lower()
            if name.startswith("readme") or name.endswith(".index.md"):
                continue
            yield path


def _hash_text(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _next_item_id(
    items_root: Path,
    prefix: str,
    type_code: str,
    used_ids: set[str],
) -> str:
    next_num = item_utils.find_next_number(items_root, prefix, type_code)
    while True:
        candidate = f"{prefix}-{type_code}-{next_num:04d}"
        if candidate not in used_ids:
            return candidate
        next_num += 1


def _next_ref_id_unique(
    decisions_root: Path,
    prefix: str,
    used_ids: set[str],
) -> str:
    candidate = _next_ref_id(decisions_root, prefix)
    while candidate in used_ids:
        number = int(candidate.split("-")[-1]) + 1
        candidate = f"{prefix}-{number:04d}"
    return candidate


def _decision_suffix(path: Path) -> str:
    if "_" in path.stem:
        return "_" + path.stem.split("_", 1)[1]
    return ""


def _item_slug(path: Path, post: frontmatter.Post) -> str:
    title = str(post.get("title") or "").strip()
    if not title:
        title = path.stem.split("_", 1)[-1]
    return item_utils.slugify(title)


def _load_conflict_policy(product_root: Path) -> tuple[str, str]:
    id_policy = "rename"
    uid_policy = "trash_shorter"
    try:
        _, config = ConfigLoader.load_effective_config(product_root, product=product_root.name)
        policy = config.get("conflict_policy") if isinstance(config, dict) else {}
        if isinstance(policy, dict):
            raw_id = str(policy.get("id_conflict", id_policy)).strip().lower()
            raw_uid = str(policy.get("uid_conflict", uid_policy)).strip().lower()
            id_policy = raw_id or id_policy
            uid_policy = raw_uid or uid_policy
    except Exception:
        pass
    id_policy = id_policy.replace("-", "_")
    uid_policy = uid_policy.replace("-", "_")
    return id_policy, uid_policy


def _trash_duplicate_path(
    path: Path,
    *,
    product_root: Path,
    agent: str,
    model: Optional[str],
    apply: bool,
    reason: str,
) -> tuple[Path, str]:
    if "items" in path.parts:
        from kano_backlog_ops.workitem import trash_item

        backlog_root = product_root.parent.parent
        result = trash_item(
            str(path),
            agent=agent,
            model=model,
            product=product_root.name,
            backlog_root=backlog_root,
            reason=reason,
            apply=apply,
        )
        return result.trashed_path, result.status

    stamp = datetime.now().strftime("%Y%m%d")
    trash_root = product_root / "_trash" / stamp
    try:
        rel_path = path.resolve().relative_to(product_root.resolve())
    except ValueError:
        rel_path = Path(path.name)
    trashed_path = trash_root / rel_path
    status = "would-trash"
    if apply:
        text = path.read_text(encoding="utf-8")
        trashed_path.parent.mkdir(parents=True, exist_ok=True)
        if trashed_path.resolve() != path.resolve():
            try:
                path.replace(trashed_path)
            except PermissionError:
                trashed_path.write_text(text, encoding="utf-8")
                try:
                    path.unlink()
                except PermissionError:
                    pass
        else:
            trashed_path.write_text(text, encoding="utf-8")
        status = "trashed"
    return trashed_path, status


def normalize_duplicate_ids(
    product: str | None = None,
    backlog_root: Path | None = None,
    *,
    agent: str,
    model: Optional[str] = None,
    apply: bool = False,
) -> list[DuplicateIdReport]:
    """Normalize duplicate IDs by UID; conflicts are same UID with differing content."""
    results: list[DuplicateIdReport] = []

    for product_root in _resolve_product_roots(product=product, backlog_root=backlog_root):
        id_policy, uid_policy = _load_conflict_policy(product_root)
        entries: dict[str, list[tuple[Path, str, str]]] = {}
        checked = 0
        used_ids: set[str] = set()

        for path in _iter_canonical_files(product_root):
            try:
                post = frontmatter.load(path)
            except Exception:
                continue
            item_id = str(post.get("id") or "").strip()
            if not item_id:
                continue
            uid = str(post.get("uid") or "").strip() or "<missing>"
            text = path.read_text(encoding="utf-8")
            text_hash = _hash_text(text)
            entries.setdefault(item_id, []).append((path, uid, text_hash))
            used_ids.add(item_id)
            checked += 1

        conflicts: list[DuplicateIdConflict] = []
        remaps: list[DuplicateIdRemap] = []

        for item_id, group in entries.items():
            if len(group) < 2:
                continue
            uid_hashes: dict[str, set[str]] = {}
            for _, uid, text_hash in group:
                uid_hashes.setdefault(uid, set()).add(text_hash)
            conflict_uids = [uid for uid, hashes in uid_hashes.items() if len(hashes) > 1]
            if conflict_uids:
                if uid_policy == "trash_shorter":
                    for conflict_uid in conflict_uids:
                        uid_group = [
                            (path, entry_uid, text_hash)
                            for path, entry_uid, text_hash in group
                            if entry_uid == conflict_uid
                        ]
                        candidates = []
                        for path, _, _ in uid_group:
                            try:
                                length = len(path.read_text(encoding="utf-8"))
                            except Exception:
                                length = 0
                            candidates.append((path, length))
                        candidates_sorted = sorted(candidates, key=lambda entry: (-entry[1], str(entry[0])))
                        if not candidates_sorted:
                            continue
                        keep_path = candidates_sorted[0][0]
                        for path, _ in candidates_sorted[1:]:
                            trashed_path, status = _trash_duplicate_path(
                                path,
                                product_root=product_root,
                                agent=agent,
                                model=model,
                                apply=apply,
                                reason=f"UID conflict for {conflict_uid}; trashed shorter content in favor of {keep_path.name}.",
                            )
                            remaps.append(
                                DuplicateIdRemap(
                                    old_id=item_id,
                                    new_id=item_id,
                                    uid=conflict_uid,
                                    old_path=path,
                                    new_path=trashed_path,
                                    status=status,
                                )
                            )
                    continue
                for uid in conflict_uids:
                    conflicts.append(
                        DuplicateIdConflict(
                            id=item_id,
                            uid=uid,
                            paths=[str(p) for p, u, _ in group if u == uid],
                            hashes=sorted(uid_hashes[uid]),
                        )
                    )
                continue

            group_sorted = sorted(group, key=lambda entry: str(entry[0]))
            canonical_path, _, _ = group_sorted[0]
            if id_policy != "rename":
                for path, uid, _ in group_sorted[1:]:
                    remaps.append(
                        DuplicateIdRemap(
                            old_id=item_id,
                            new_id=item_id,
                            uid=uid,
                            old_path=path,
                            new_path=path,
                            status="skipped",
                        )
                    )
                continue
            for path, uid, _ in group_sorted[1:]:
                new_id = None
                status = "would-remap"
                new_path = path
                if "decisions" in path.parts:
                    new_id = _next_ref_id_unique(product_root / "decisions", "ADR", used_ids)
                    used_ids.add(new_id)
                    new_name = f"{new_id}{_decision_suffix(path)}{path.suffix}"
                    new_path = path.parent / new_name
                else:
                    parts = item_id.split("-")
                    prefix = parts[0] if len(parts) > 0 else "KABSD"
                    type_code = parts[1] if len(parts) > 1 else "TSK"
                    new_id = _next_item_id(product_root / "items", prefix, type_code, used_ids)
                    used_ids.add(new_id)
                    bucket = item_utils.calculate_bucket(int(new_id.split("-")[-1]))
                    subdir = path.parent.parent.name
                    new_dir = product_root / "items" / subdir / bucket
                    slug = _item_slug(path, frontmatter.load(path))
                    new_path = new_dir / f"{new_id}_{slug}{path.suffix}"

                if apply and new_id:
                    content = path.read_text(encoding="utf-8")
                    updated = _replace_id_tokens(content, item_id, new_id)
                    lines = updated.splitlines()
                    if "items" in path.parts:
                        lines = worklog.append_worklog_entry(
                            lines,
                            f"Remapped duplicate ID: {item_id} -> {new_id}.",
                            agent,
                            model=model,
                        )
                    new_text = "\n".join(lines) + "\n"
                    new_path.parent.mkdir(parents=True, exist_ok=True)
                    if new_path.resolve() != path.resolve():
                        try:
                            path.replace(new_path)
                        except PermissionError:
                            new_path.write_text(new_text, encoding="utf-8")
                            try:
                                path.unlink()
                            except PermissionError:
                                pass
                    else:
                        new_path.write_text(new_text, encoding="utf-8")
                    status = "remapped"

                remaps.append(
                    DuplicateIdRemap(
                        old_id=item_id,
                        new_id=new_id or item_id,
                        uid=uid,
                        old_path=path,
                        new_path=new_path,
                        status=status,
                    )
                )

        results.append(
            DuplicateIdReport(
                product=product_root.name,
                checked=checked,
                duplicates=sum(1 for ids in entries.values() if len(ids) > 1),
                conflicts=conflicts,
                remaps=remaps,
                updated_files=sum(1 for remap in remaps if remap.status == "remapped"),
            )
        )

    return results


def remap_reference_id(
    target_path: Path,
    *,
    product: str | None = None,
    backlog_root: Path | None = None,
    prefix: str = "ADR",
    update_refs: bool = True,
    apply: bool = False,
) -> RefRemapResult:
    """Remap a reference ID (e.g., ADR-0004) and update links across the product."""
    target_path = target_path.resolve()
    if not target_path.exists():
        raise FileNotFoundError(f"Target not found: {target_path}")

    product_root = None
    if backlog_root and product:
        product_root = Path(backlog_root).resolve() / "products" / product
    else:
        for parent in target_path.parents:
            if parent.name == "decisions" and parent.parent.name:
                product_root = parent.parent
                break
    if product_root is None or not product_root.exists():
        raise ValueError("Could not resolve product root for reference remap")

    old_id = target_path.stem.split("_", 1)[0]
    new_id = _next_ref_id(product_root / "decisions", prefix)

    suffix = ""
    if "_" in target_path.stem:
        suffix = "_" + target_path.stem.split("_", 1)[1]
    new_name = f"{new_id}{suffix}{target_path.suffix}"
    new_path = target_path.parent / new_name

    updated_files = 0
    if apply:
        content = target_path.read_text(encoding="utf-8")
        content = _replace_id_tokens(content, old_id, new_id)
        new_path.write_text(content, encoding="utf-8")
        if new_path.resolve() != target_path.resolve():
            try:
                target_path.unlink()
            except PermissionError:
                pass
        updated_files += 1

        if update_refs:
            for path in _iter_markdown_files(product_root, include_views=False):
                if path.resolve() == new_path.resolve():
                    continue
                text = path.read_text(encoding="utf-8")
                updated = _replace_id_tokens(text, old_id, new_id)
                if updated != text:
                    path.write_text(updated, encoding="utf-8")
                    updated_files += 1

    return RefRemapResult(
        old_id=old_id,
        new_id=new_id,
        old_path=target_path,
        new_path=new_path,
        updated_files=updated_files,
    )


def _strip_link_target(raw: str) -> str:
    target = raw.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1].strip()
    if " " in target:
        target = target.split(" ", 1)[0].strip()
    return target


def _drop_fragment(target: str) -> str:
    if "#" in target:
        return target.split("#", 1)[0]
    return target


def _is_external(target: str) -> bool:
    lower = target.lower()
    return lower.startswith(_EXTERNAL_PREFIXES)


def _matches_ignore(target: str, ignore_patterns: list[str]) -> bool:
    for pattern in ignore_patterns:
        if fnmatch.fnmatch(target, pattern):
            return True
    return False


def _split_target_and_suffix(raw: str) -> tuple[str, str, bool]:
    raw = raw.strip()
    is_angle = raw.startswith("<") and raw.endswith(">")
    if is_angle:
        raw = raw[1:-1].strip()
    if " " in raw:
        target, suffix = raw.split(" ", 1)
        return target.strip(), f" {suffix.strip()}", is_angle
    return raw, "", is_angle


def _rebuild_target(target: str, suffix: str, is_angle: bool) -> str:
    rebuilt = f"{target}{suffix}"
    if is_angle:
        return f"<{rebuilt}>"
    return rebuilt


def _apply_remap(target: str, remap_roots: list[tuple[str, str]]) -> tuple[str, Optional[str]]:
    for from_root, to_root in remap_roots:
        if target.startswith(from_root):
            return f"{to_root}{target[len(from_root):]}", "remap-root"
        if target.startswith("/" + from_root):
            return f"/{to_root}{target[len(from_root) + 1:]}", "remap-root"
    return target, None


def _relpath_posix(from_path: Path, to_path: Path) -> str:
    rel = Path(os.path.relpath(to_path, start=from_path))
    return rel.as_posix()


def _resolve_target_path(
    target: str,
    *,
    source_path: Path,
    project_root: Path,
    backlog_root: Path,
    product_root: Path,
    name_index: dict[str, list[Path]],
    id_index: dict[str, list[Path]],
) -> Optional[Path]:
    if target.startswith("_kano/backlog/") or target.startswith("_kano\\backlog\\"):
        candidate = project_root / target
        if candidate.exists():
            return candidate
        relative = str(target).replace("\\", "/").split("_kano/backlog/", 1)[-1]
        candidate = backlog_root / "products" / product_root.name / relative
        return candidate if candidate.exists() else None
    if target.startswith("_kano/") or target.startswith("_kano\\"):
        candidate = project_root / target
        return candidate if candidate.exists() else None
    if target.startswith("/"):
        candidate = project_root / target.lstrip("/")
        return candidate if candidate.exists() else None

    candidate = source_path.parent / target
    if candidate.exists():
        return candidate
    if candidate.suffix:
        return None
    md_candidate = candidate.with_suffix(".md")
    if md_candidate.exists():
        return md_candidate
    if "/" not in target and "\\" not in target:
        name = target
        if not name.endswith(".md"):
            name = f"{name}.md"
        if name in name_index:
            return name_index[name][0]
        unique = _unique_id_path(id_index, target)
        if unique:
            return unique
    return None


def _git_repo_root(start_path: Path) -> Optional[Path]:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(start_path),
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    output = result.stdout.strip()
    return Path(output) if output else None


def _git_history_paths(repo_root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "rev-list", "--all", "--objects"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        return []
    paths: list[str] = []
    for line in result.stdout.splitlines():
        parts = line.strip().split(" ", 1)
        if len(parts) == 2:
            paths.append(parts[1].strip())
    return paths


def _git_show_file(repo_root: Path, commit: str, path: str) -> Optional[str]:
    result = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def _git_last_commit_for_path(repo_root: Path, path: str) -> Optional[str]:
    result = subprocess.run(
        ["git", "log", "-n", "1", "--format=%H", "--", path],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        return None
    commit = result.stdout.strip()
    return commit or None


def _normalize_path_fragment(target: str) -> str:
    target = target.strip()
    target = target.replace("\\", "/")
    return target.lstrip("./")


def _apply_remap_to_path(path_value: str, remap_roots: list[tuple[str, str]]) -> str:
    normalized = _normalize_path_fragment(path_value)
    for from_root, to_root in remap_roots:
        from_norm = _normalize_path_fragment(from_root)
        to_norm = _normalize_path_fragment(to_root)
        if normalized.startswith(to_norm):
            return normalized
        if normalized.startswith(from_norm):
            return f"{to_norm}{normalized[len(from_norm):]}"
    return normalized


def _match_history_candidates(target: str, history_paths: list[str]) -> list[str]:
    target = _normalize_path_fragment(target)
    if not target:
        return []
    if "/" in target:
        return [p for p in history_paths if _normalize_path_fragment(p).endswith(target)]
    base = target.split("/")[-1]
    if base.endswith(".md"):
        return [p for p in history_paths if Path(p).name == base]
    return [
        p
        for p in history_paths
        if Path(p).name.startswith(base) and Path(p).name.endswith(".md")
    ]


def _resolve_markdown_target(
    target: str,
    *,
    source_path: Path,
    project_root: Path,
    backlog_root: Path,
    product_root: Path,
    name_index: dict[str, list[Path]],
    id_index: dict[str, list[Path]],
) -> Optional[Path]:
    if target.startswith("_kano/backlog/") or target.startswith("_kano\\backlog\\"):
        candidate = project_root / target
        if candidate.exists():
            return candidate
        relative = str(target).replace("\\", "/").split("_kano/backlog/", 1)[-1]
        candidate = backlog_root / "products" / product_root.name / relative
    elif target.startswith("_kano/") or target.startswith("_kano\\"):
        candidate = project_root / target
    elif target.startswith("/"):
        candidate = project_root / target.lstrip("/")
    else:
        candidate = source_path.parent / target

    if candidate.suffix:
        return candidate if candidate.exists() else None

    md_candidate = candidate.with_suffix(".md")
    if md_candidate.exists():
        return md_candidate
    if candidate.exists():
        return candidate

    if "/" not in target and "\\" not in target:
        name = target
        if not name.endswith(".md"):
            name = f"{name}.md"
        if name in name_index:
            return name_index[name][0]
        unique = _unique_id_path(id_index, target)
        if unique:
            return unique

    return None


def _build_wikilink_index(
    product_root: Path,
    *,
    include_views: bool,
) -> tuple[dict[str, list[Path]], dict[str, list[Path]]]:
    name_index: dict[str, list[Path]] = {}
    id_index: dict[str, list[Path]] = {}
    for path in _iter_markdown_files(product_root, include_views=include_views):
        name = path.name
        name_index.setdefault(name, []).append(path)
        stem = path.stem
        if stem:
            item_id = stem.split("_", 1)[0]
            id_index.setdefault(item_id, []).append(path)
    return name_index, id_index


def _unique_id_path(id_index: dict[str, list[Path]], target: str) -> Optional[Path]:
    matches = id_index.get(target, [])
    if len(matches) == 1:
        return matches[0]
    return None


def _resolve_wikilink_target(
    target: str,
    *,
    source_path: Path,
    project_root: Path,
    backlog_root: Path,
    product_root: Path,
    name_index: dict[str, list[Path]],
    id_index: dict[str, list[Path]],
) -> Optional[Path]:
    if "/" in target or "\\" in target:
        candidate = source_path.parent / target
        if not candidate.suffix:
            candidate = candidate.with_suffix(".md")
        if candidate.exists():
            return candidate
        if target.startswith("_kano/backlog/") or target.startswith("_kano\\backlog\\"):
            relative = str(target).replace("\\", "/").split("_kano/backlog/", 1)[-1]
            candidate = backlog_root / "products" / product_root.name / relative
            if not candidate.suffix:
                candidate = candidate.with_suffix(".md")
            if candidate.exists():
                return candidate
        if target.startswith("_kano/") or target.startswith("_kano\\"):
            candidate = project_root / target
            if not candidate.suffix:
                candidate = candidate.with_suffix(".md")
            return candidate if candidate.exists() else None
        return None

    name = target
    if not name.endswith(".md"):
        name = f"{name}.md"
    matches = name_index.get(name, [])
    if matches:
        return matches[0]
    unique = _unique_id_path(id_index, target)
    if unique:
        return unique
    candidate = product_root / name
    if candidate.exists():
        return candidate
    return None


def validate_links(
    product: str | None = None,
    backlog_root: Path | None = None,
    *,
    include_views: bool = False,
    ignore_targets: Optional[list[str]] = None,
) -> List[LinkValidationResult]:
    """Validate markdown links and wikilinks within backlog content."""
    ignore_targets = ignore_targets or []
    results: list[LinkValidationResult] = []

    for product_root in _resolve_product_roots(product=product, backlog_root=backlog_root):
        backlog_root = product_root.parent.parent
        project_root = backlog_root.parent.parent
        name_index, id_index = _build_wikilink_index(product_root, include_views=include_views)
        issues: list[LinkIssue] = []
        checked_files = 0

        for path in _iter_markdown_files(product_root, include_views=include_views):
            try:
                content = path.read_text(encoding="utf-8")
            except Exception as exc:  # pragma: no cover - defensive
                issues.append(
                    LinkIssue(
                        source_path=path,
                        line=1,
                        column=1,
                        link_type="read-error",
                        link_text=str(exc),
                        target="",
                    )
                )
                continue

            checked_files += 1
            for line_no, line in enumerate(content.splitlines(), start=1):
                for match in _MARKDOWN_LINK_RE.finditer(line):
                    raw_target = _strip_link_target(match.group(1))
                    if not raw_target or raw_target.startswith("#"):
                        continue
                    if _is_external(raw_target) or _matches_ignore(raw_target, ignore_targets):
                        continue
                    target = _drop_fragment(raw_target)
                    resolved = _resolve_markdown_target(
                        target,
                        source_path=path,
                        project_root=project_root,
                        backlog_root=backlog_root,
                        product_root=product_root,
                        name_index=name_index,
                        id_index=id_index,
                    )
                    if resolved is None or not resolved.exists():
                        issues.append(
                            LinkIssue(
                                source_path=path,
                                line=line_no,
                                column=match.start(1) + 1,
                                link_type="markdown",
                                link_text=match.group(0),
                                target=raw_target,
                            )
                        )

                for match in _WIKILINK_RE.finditer(line):
                    raw = match.group(1).strip()
                    if not raw:
                        continue
                    target = raw.split("|", 1)[0].strip()
                    target = _drop_fragment(target)
                    if not target or _matches_ignore(target, ignore_targets):
                        continue
                    resolved = _resolve_wikilink_target(
                        target,
                        source_path=path,
                        project_root=project_root,
                        backlog_root=backlog_root,
                        product_root=product_root,
                        name_index=name_index,
                        id_index=id_index,
                    )
                    if resolved is None or not resolved.exists():
                        issues.append(
                            LinkIssue(
                                source_path=path,
                                line=line_no,
                                column=match.start(0) + 1,
                                link_type="wikilink",
                                link_text=match.group(0),
                                target=target,
                            )
                        )

        results.append(
            LinkValidationResult(
                product=product_root.name,
                checked_files=checked_files,
                issues=issues,
            )
        )

    return results


def fix_links(
    product: str | None = None,
    backlog_root: Path | None = None,
    *,
    include_views: bool = False,
    ignore_targets: Optional[list[str]] = None,
    remap_roots: Optional[list[tuple[str, str]]] = None,
    resolve_ids: bool = False,
    apply: bool = False,
) -> List[LinkFixResult]:
    """Fix markdown links and wikilinks using remap and resolve strategies."""
    ignore_targets = ignore_targets or []
    remap_roots = remap_roots or []
    results: list[LinkFixResult] = []

    for product_root in _resolve_product_roots(product=product, backlog_root=backlog_root):
        backlog_root = product_root.parent.parent
        project_root = backlog_root.parent.parent
        name_index, id_index = _build_wikilink_index(product_root, include_views=include_views)
        checked_files = 0
        updated_files = 0
        changes: list[LinkChange] = []

        for path in _iter_markdown_files(product_root, include_views=include_views):
            try:
                content = path.read_text(encoding="utf-8")
            except Exception as exc:  # pragma: no cover - defensive
                changes.append(
                    LinkChange(
                        source_path=path,
                        line=1,
                        column=1,
                        link_type="read-error",
                        original=str(exc),
                        updated="",
                        reason="read-error",
                    )
                )
                continue

            checked_files += 1
            lines = content.splitlines()
            file_changed = False

            for idx, line in enumerate(lines):
                line_no = idx + 1

                def _rewrite_markdown(match: re.Match) -> str:
                    nonlocal file_changed
                    raw_target = match.group(1)
                    target, suffix, is_angle = _split_target_and_suffix(raw_target)
                    if not target or target.startswith("#"):
                        return match.group(0)
                    if _is_external(target) or _matches_ignore(target, ignore_targets):
                        return match.group(0)

                    base = _drop_fragment(target)
                    fragment = ""
                    if "#" in target:
                        fragment = "#" + target.split("#", 1)[1]

                    remapped, reason = _apply_remap(base, remap_roots)
                    resolved_path = _resolve_target_path(
                        remapped,
                        source_path=path,
                        project_root=project_root,
                        backlog_root=backlog_root,
                        product_root=product_root,
                        name_index=name_index,
                        id_index=id_index,
                    )
                    if resolved_path is None:
                        return match.group(0)

                    new_target = remapped
                    if resolve_ids and _unique_id_path(id_index, base):
                        new_target = _relpath_posix(path.parent, resolved_path)
                        reason = "resolve-id"
                    elif remapped != base:
                        new_target = remapped
                    if new_target == base:
                        return match.group(0)

                    updated_target = _rebuild_target(f"{new_target}{fragment}", suffix, is_angle)
                    file_changed = True
                    changes.append(
                        LinkChange(
                            source_path=path,
                            line=line_no,
                            column=match.start(1) + 1,
                            link_type="markdown",
                            original=raw_target,
                            updated=updated_target,
                            reason=reason or "rewrite",
                        )
                    )
                    return match.group(0).replace(raw_target, updated_target, 1)

                def _rewrite_wikilink(match: re.Match) -> str:
                    nonlocal file_changed
                    raw = match.group(1).strip()
                    if not raw:
                        return match.group(0)
                    parts = raw.split("|", 1)
                    target = parts[0].strip()
                    alias = parts[1].strip() if len(parts) > 1 else ""
                    if not target or _matches_ignore(target, ignore_targets):
                        return match.group(0)

                    base = _drop_fragment(target)
                    fragment = ""
                    if "#" in target:
                        fragment = "#" + target.split("#", 1)[1]

                    remapped, reason = _apply_remap(base, remap_roots)
                    resolved_path = _resolve_target_path(
                        remapped,
                        source_path=path,
                        project_root=project_root,
                        backlog_root=backlog_root,
                        product_root=product_root,
                        name_index=name_index,
                        id_index=id_index,
                    )
                    if resolved_path is None:
                        return match.group(0)

                    new_target = remapped
                    if resolve_ids and _unique_id_path(id_index, base):
                        new_target = _relpath_posix(path.parent, resolved_path)
                        reason = "resolve-id"
                    elif remapped != base:
                        new_target = remapped
                    if new_target == base:
                        return match.group(0)

                    updated_target = f"{new_target}{fragment}"
                    new_link = f"[[{updated_target}]]"
                    if alias:
                        new_link = f"[[{updated_target}|{alias}]]"
                    file_changed = True
                    changes.append(
                        LinkChange(
                            source_path=path,
                            line=line_no,
                            column=match.start(0) + 1,
                            link_type="wikilink",
                            original=match.group(0),
                            updated=new_link,
                            reason=reason or "rewrite",
                        )
                    )
                    return new_link

                line = _MARKDOWN_LINK_RE.sub(_rewrite_markdown, line)
                line = _WIKILINK_RE.sub(_rewrite_wikilink, line)
                lines[idx] = line

            if file_changed:
                updated_files += 1
                if apply:
                    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        results.append(
            LinkFixResult(
                product=product_root.name,
                checked_files=checked_files,
                updated_files=updated_files,
                changes=changes,
            )
        )

    return results


def restore_links_from_vcs(
    product: str | None = None,
    backlog_root: Path | None = None,
    *,
    include_views: bool = False,
    ignore_targets: Optional[list[str]] = None,
    remap_roots: Optional[list[tuple[str, str]]] = None,
    apply: bool = False,
) -> List[LinkRestoreResult]:
    """Restore missing link targets from VCS history when possible."""
    ignore_targets = ignore_targets or []
    remap_roots = remap_roots or []
    results: list[LinkRestoreResult] = []

    for product_root in _resolve_product_roots(product=product, backlog_root=backlog_root):
        backlog_root = product_root.parent.parent
        repo_root = _git_repo_root(backlog_root)
        actions: list[LinkRestoreAction] = []

        issues = validate_links(
            product=product_root.name,
            backlog_root=backlog_root,
            include_views=include_views,
            ignore_targets=ignore_targets,
        )[0].issues

        if repo_root is None:
            for issue in issues:
                actions.append(
                    LinkRestoreAction(
                        source_path=issue.source_path,
                        target=issue.target,
                        status="no-vcs",
                        candidates=[],
                        restored_path=None,
                    )
                )
            results.append(
                LinkRestoreResult(
                    product=product_root.name,
                    checked_files=0,
                    actions=actions,
                )
            )
            continue

        history_paths = _git_history_paths(repo_root)
        checked_files = 0
        for issue in issues:
            checked_files += 1
            target = _normalize_path_fragment(issue.target)
            if not target or _matches_ignore(target, ignore_targets):
                continue

            candidates = _match_history_candidates(target, history_paths)

            if not candidates:
                actions.append(
                    LinkRestoreAction(
                        source_path=issue.source_path,
                        target=issue.target,
                        status="missing",
                        candidates=[],
                        restored_path=None,
                    )
                )
                continue

            unique_candidates = sorted(set(candidates))
            remapped_map: dict[str, list[str]] = {}
            for candidate in unique_candidates:
                remapped = _apply_remap_to_path(candidate, remap_roots)
                remapped_map.setdefault(remapped, []).append(candidate)

            if len(remapped_map) > 1:
                actions.append(
                    LinkRestoreAction(
                        source_path=issue.source_path,
                        target=issue.target,
                        status="ambiguous",
                        candidates=unique_candidates,
                        restored_path=None,
                    )
                )
                continue

            remapped_target = next(iter(remapped_map.keys()))
            original_candidates = remapped_map[remapped_target]
            history_path = original_candidates[0]
            for candidate in original_candidates:
                if _normalize_path_fragment(candidate).startswith(_normalize_path_fragment(remapped_target)):
                    history_path = candidate
                    break
            commit = _git_last_commit_for_path(repo_root, history_path)
            if not commit:
                actions.append(
                    LinkRestoreAction(
                        source_path=issue.source_path,
                        target=issue.target,
                        status="missing",
                        candidates=unique_candidates,
                        restored_path=None,
                    )
                )
                continue

            restored_rel = remapped_target
            restore_path = repo_root / restored_rel
            if restore_path.exists():
                actions.append(
                    LinkRestoreAction(
                        source_path=issue.source_path,
                        target=issue.target,
                        status="exists",
                        candidates=unique_candidates,
                        restored_path=str(restore_path),
                    )
                )
                continue

            file_text = _git_show_file(repo_root, commit, history_path)
            if file_text is None:
                actions.append(
                    LinkRestoreAction(
                        source_path=issue.source_path,
                        target=issue.target,
                        status="missing",
                        candidates=unique_candidates,
                        restored_path=None,
                    )
                )
                continue

            if apply:
                restore_path.parent.mkdir(parents=True, exist_ok=True)
                restore_path.write_text(file_text, encoding="utf-8")
                status = "restored"
            else:
                status = "would-restore"

            actions.append(
                LinkRestoreAction(
                    source_path=issue.source_path,
                    target=issue.target,
                    status=status,
                    candidates=unique_candidates,
                    restored_path=str(restore_path),
                )
            )

        results.append(
            LinkRestoreResult(
                product=product_root.name,
                checked_files=checked_files,
                actions=actions,
            )
        )

    return results
