
import argparse
import sys
import json
from pathlib import Path
from dataclasses import asdict
from datetime import datetime
from lib.index import BacklogIndex

def main():
    parser = argparse.ArgumentParser(description="Report ID collisions in backlog.")
    parser.add_argument("--backlog-root", default="_kano/backlog", help="Path to backlog root")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    parser.add_argument("--collisions-only", action="store_true", help="Only output if collisions exist")
    args = parser.parse_args()

    root = Path(args.backlog_root)
    if not root.exists():
        print(f"Error: Backlog root not found: {root}")
        sys.exit(1)

    index = BacklogIndex(root)
    collisions = index.get_collisions()
    
    # Sort by ID
    sorted_collisions = sorted(collisions.items(), key=lambda x: x[0])
    
    total_items = sum(len(items) for items in index.items_by_id.values())
    
    if args.format == "json":
        out = {
            "generated": datetime.now().isoformat(),
            "total_items": total_items,
            "collision_count": len(sorted_collisions),
            "collisions": []
        }
        for did, items in sorted_collisions:
            item_dicts = []
            for item in items:
                d = asdict(item)
                d['path'] = str(d['path'])
                del d['frontmatter'] # Too verbose
                item_dicts.append(d)
                
            out["collisions"].append({
                "id": did,
                "items": item_dicts
            })
        print(json.dumps(out, indent=2))
        
    else:
        if args.collisions_only and not sorted_collisions:
            return

        print("ID Collision Report")
        print("===================")
        print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"Scanned: {total_items} items")
        print(f"Collisions Found: {len(sorted_collisions)}")
        print()
        
        if sorted_collisions:
            for did, items in sorted_collisions:
                print(f"ID: {did} ({len(items)} items)")
                for i, item in enumerate(items):
                    print(f"  {i+1}. {item.uidshort} | {item.type} | {item.state:<5} | {item.title}")
                    print(f"     Path: {item.path}")
                print(f"  Suggestion: Use {did}@{items[0].uidshort}")
                print()
        else:
            print("No collisions found.")

if __name__ == "__main__":
    main()
