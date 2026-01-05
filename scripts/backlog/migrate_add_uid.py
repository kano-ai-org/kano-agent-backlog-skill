
import argparse
import sys
from pathlib import Path
from datetime import datetime
from lib.utils import generate_uid, update_frontmatter
from lib.index import BacklogIndex

def main():
    parser = argparse.ArgumentParser(description="Migrate backlog items to include UUIDv7 uid.")
    parser.add_argument("--backlog-root", default="_kano/backlog", help="Path to backlog root")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without applying")
    args = parser.parse_args()

    root = Path(args.backlog_root)
    if not root.exists():
        print(f"Error: Backlog root not found: {root}")
        sys.exit(1)

    print(f"Scanning backlog at {root}...")
    index = BacklogIndex(root)
    
    updated_count = 0
    skipped_count = 0
    
    # Iterate through all items found by index scan
    # Note: index only has items with valid 'id'. If we want raw files, we might need a raw glob.
    # But usually we only care about valid items.
    
    all_items = []
    # Flatten items from index
    seen_paths = set()
    for items in index.items_by_id.values():
        for item in items:
            if item.path in seen_paths:
                continue
            seen_paths.add(item.path)
            all_items.append(item)
            
    print(f"Found {len(all_items)} items.")
    
    for item in all_items:
        if item.uid:
            skipped_count += 1
            if args.dry_run:
                # print(f"[Skip] {item.id} already has uid: {item.uid}")
                pass
            continue
            
        new_uid = generate_uid()
        now_str = datetime.now().strftime("%Y-%m-%d")
        
        updates = {
            "uid": new_uid,
            "updated": now_str
        }
        
        if args.dry_run:
            print(f"[Dry Run] {item.id} -> Add uid: {new_uid}")
            updated_count += 1
        else:
            if update_frontmatter(item.path, updates):
                print(f"[Updated] {item.id} -> Added uid: {new_uid}")
                updated_count += 1
            else:
                print(f"[Warning] Failed to update {item.id}")
                
    print("-" * 40)
    print(f"Migration Complete.")
    print(f"Items Updated: {updated_count}")
    print(f"Items Skipped: {skipped_count}")
    
    if args.dry_run:
        print("\nNOTE: This was a dry run. No files were modified.")
        print("Run without --dry-run to apply changes.")

if __name__ == "__main__":
    main()
