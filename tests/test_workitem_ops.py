import os
import sys
from pathlib import Path

import pytest

test_dir = Path(__file__).parent
src_dir = test_dir.parent / "src"
sys.path.insert(0, str(src_dir))

from kano_backlog_core.models import ItemState, ItemType
from kano_backlog_ops.workitem import create_item, get_item, list_items, update_state
from conftest import write_project_backlog_config


def _scaffold_product(tmp_path: Path, *, name: str = "demo-product", prefix: str = "DE") -> Path:
    backlog_root = tmp_path / "_kano" / "backlog"
    product_root = backlog_root / "products" / name
    items_root = product_root / "items"

    for item_type in ["epic", "feature", "userstory", "task", "bug"]:
        (items_root / item_type / "0000").mkdir(parents=True, exist_ok=True)

    for required_dir in ["decisions", "views", "_meta"]:
        (product_root / required_dir).mkdir(parents=True, exist_ok=True)

    write_project_backlog_config(tmp_path, products={name: (name, prefix)})

    return product_root


def test_get_item_resolves_by_id_uid_and_path(tmp_path: Path):
    product_name = "demo-product"
    _scaffold_product(tmp_path, name=product_name)

    cwd_before = Path.cwd()
    os.chdir(tmp_path)
    try:
        created = create_item(
            item_type=ItemType.TASK,
            title="Test Task",
            product=product_name,
            agent="tester",
            tags=["alpha", "beta"],
        )

        by_id = get_item(created.id, product=product_name)
        assert by_id.id == created.id
        assert by_id.uid == created.uid
        assert set(by_id.tags) >= {"alpha", "beta"}

        by_uid = get_item(created.uid, product=product_name)
        assert by_uid.id == created.id

        by_path = get_item(str(created.path), product=product_name)
        assert by_path.id == created.id
    finally:
        os.chdir(cwd_before)


def test_list_items_filters_and_is_deterministic(tmp_path: Path):
    product_name = "demo-product"
    _scaffold_product(tmp_path, name=product_name)

    cwd_before = Path.cwd()
    os.chdir(tmp_path)
    try:
        t1 = create_item(
            item_type=ItemType.TASK,
            title="Task One",
            product=product_name,
            agent="tester",
            tags=["a", "b"],
        )
        t2 = create_item(
            item_type=ItemType.TASK,
            title="Task Two",
            product=product_name,
            agent="tester",
            tags=["a"],
        )
        b1 = create_item(
            item_type=ItemType.BUG,
            title="Bug One",
            product=product_name,
            agent="tester",
            tags=["b"],
        )

        all_items = list_items(product=product_name)
        assert [i.id for i in all_items] == sorted([i.id for i in all_items])
        assert {t1.id, t2.id, b1.id}.issubset({i.id for i in all_items})

        tasks_only = list_items(product=product_name, item_type=ItemType.TASK)
        assert {i.type for i in tasks_only} == {ItemType.TASK}

        tag_and = list_items(product=product_name, tags=["a", "b"])
        assert [i.id for i in tag_and] == [t1.id]
    finally:
        os.chdir(cwd_before)


def test_update_state_syncs_parent_and_refreshes_dashboards(tmp_path: Path):
    product_name = "demo-product"
    product_root = _scaffold_product(tmp_path, name=product_name)

    cwd_before = Path.cwd()
    os.chdir(tmp_path)
    try:
        parent = create_item(
            item_type=ItemType.FEATURE,
            title="Parent Feature",
            product=product_name,
            agent="tester",
        )
        c1 = create_item(
            item_type=ItemType.TASK,
            title="Child One",
            product=product_name,
            agent="tester",
            parent=parent.id,
            force=True,
        )
        c2 = create_item(
            item_type=ItemType.TASK,
            title="Child Two",
            product=product_name,
            agent="tester",
            parent=parent.id,
            force=True,
        )

        started = update_state(
            item_ref=c1.id,
            new_state=ItemState.IN_PROGRESS,
            agent="tester",
            model="unit-test",
            product=product_name,
            sync_parent=True,
            refresh_dashboards=False,
            force=True,
        )
        assert started.parent_synced is True
        parent_after_start = get_item(parent.id, product=product_name)
        assert parent_after_start.state == ItemState.IN_PROGRESS
        assert any("Auto parent sync:" in line for line in parent_after_start.worklog)

        first_done = update_state(
            item_ref=c1.id,
            new_state=ItemState.DONE,
            agent="tester",
            model="unit-test",
            product=product_name,
            sync_parent=True,
            refresh_dashboards=False,
        )
        assert first_done.parent_synced is False
        parent_mid = get_item(parent.id, product=product_name)
        assert parent_mid.state == ItemState.IN_PROGRESS

        second_done = update_state(
            item_ref=c2.id,
            new_state=ItemState.DONE,
            agent="tester",
            model="unit-test",
            product=product_name,
            sync_parent=True,
            refresh_dashboards=True,
        )
        assert second_done.parent_synced is True
        assert second_done.dashboards_refreshed is True

        parent_final = get_item(parent.id, product=product_name)
        assert parent_final.state == ItemState.DONE

        views_root = product_root / "views"
        assert (views_root / "Dashboard_PlainMarkdown_Active.md").exists()
        assert (views_root / "Dashboard_PlainMarkdown_New.md").exists()
        assert (views_root / "Dashboard_PlainMarkdown_Done.md").exists()
    finally:
        os.chdir(cwd_before)
