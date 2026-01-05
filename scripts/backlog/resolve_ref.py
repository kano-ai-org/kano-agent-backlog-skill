
import argparse
import sys
import json
from pathlib import Path
from dataclasses import asdict
from lib.index import BacklogIndex, BacklogItem

def resolve_ref(ref: str, index: BacklogIndex):
    # 1. Full UID
    if len(ref) == 36 and "-" in ref:
        item = index.get_by_uid(ref)
        if item:
            return [item]
            
    # 2. id@uidshort
    if "@" in ref:
        did, short = ref.split("@", 1)
        candidates = index.get_by_id(did)
        matches = [c for c in candidates if c.uidshort.startswith(short)]
        return matches
        
    # 3. uidshort (8 chars hex)
    # Simple heuristic: 8 chars hex could be short uid
    if len(ref) == 8 and all(c in "0123456789abcdefABCDEF" for c in ref):
        matches = index.get_by_uidshort(ref)
        if matches:
            return matches
            
    # 4. Display ID
    return index.get_by_id(ref)

def print_item(item: BacklogItem, fmt: str):
    if fmt == "json":
        # Can't directly serialize Path object
        d = asdict(item)
        d['path'] = str(d['path'])
        print(json.dumps(d, indent=2))
    elif fmt == "path":
        print(str(item.path))
    elif fmt == "uid":
        print(item.uid)
    else:
        print(f"Resolved: {item.id}")
        print(f"  UID:      {item.uid}")
        print(f"  Type:     {item.type}")
        print(f"  State:    {item.state}")
        print(f"  Title:    {item.title}")
        print(f"  Path:     {item.path}")
        print("-" * 40)

def main():
    parser = argparse.ArgumentParser(description="Resolve reference to backlog item.")
    parser.add_argument("ref", help="Reference string (id, uid, uidshort, or id@uidshort)")
    parser.add_argument("--backlog-root", default="_kano/backlog", help="Path to backlog root")
    parser.add_argument("--interactive", action="store_true", help="Prompt for selection if ambiguous")
    parser.add_argument("--format", choices=["text", "json", "path", "uid"], default="text", help="Output format")
    args = parser.parse_args()

    root = Path(args.backlog_root)
    if not root.exists():
        print(f"Error: Backlog root not found: {root}")
        sys.exit(1)

    index = BacklogIndex(root)
    matches = resolve_ref(args.ref, index)
    
    if not matches:
        print(f"Error: No matches found for '{args.ref}'")
        sys.exit(1)
        
    if len(matches) == 1:
        print_item(matches[0], args.format)
        sys.exit(0)
        
    # Multiple matches
    if args.interactive:
        print(f"Ambiguous: {len(matches)} items match '{args.ref}'")
        print(f"{'#':<3} | {'UID (short)':<12} | {'Type':<10} | {'State':<10} | {'Title'}")
        print("-" * 60)
        for i, m in enumerate(matches):
            print(f"{i+1:<3} | {m.uidshort:<12} | {m.type:<10} | {m.state:<10} | {m.title}")
            
        try:
            choice = input("\nEnter number to select (or 'q' to quit): ")
            if choice.lower() == 'q':
                sys.exit(0)
            idx = int(choice) - 1
            if 0 <= idx < len(matches):
                print_item(matches[idx], args.format)
            else:
                print("Invalid selection.")
                sys.exit(1)
        except ValueError:
            print("Invalid input.")
            sys.exit(1)
    else:
        if args.format == "json":
            # List all matches
            out = []
            for m in matches:
                d = asdict(m)
                d['path'] = str(d['path'])
                out.append(d)
            print(json.dumps(out, indent=2))
        else:
            print(f"Ambiguous: {len(matches)} items match '{args.ref}'. Use --interactive to select.")
            for m in matches:
                print(f"- {m.id}@{m.uidshort} ({m.state}) {m.title}")
            sys.exit(1)

if __name__ == "__main__":
    main()
