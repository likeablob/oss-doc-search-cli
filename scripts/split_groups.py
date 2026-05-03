#!/usr/bin/env python3
"""
Split changed libraries into groups for parallel reindexing.

Usage:
    python scripts/split_groups.py --update-info ./update_info.json --n-groups 3 --output ./groups.json
"""

import argparse
import json
import sys
from pathlib import Path


def split_groups(changed: list, n_groups: int) -> list[dict]:
    if not changed:
        return [{"id": 0, "changed": []}]

    per_group = max(1, len(changed) // n_groups)
    groups = []
    for i in range(n_groups):
        start = i * per_group
        end = start + per_group if i < n_groups - 1 else len(changed)
        groups.append({"id": i, "changed": changed[start:end]})
    return groups


def main():
    parser = argparse.ArgumentParser(description="Split changed libraries into groups")
    parser.add_argument("--update-info", required=True, help="update_info.json path")
    parser.add_argument("--n-groups", type=int, default=3, help="Number of groups")
    parser.add_argument("--output", default="./groups.json", help="Output JSON path")
    args = parser.parse_args()

    with open(args.update_info) as f:
        update_info = json.load(f)

    changed = update_info.get("changed", [])
    groups = split_groups(changed, args.n_groups)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(groups, f, indent=2)

    print(f"Split {len(changed)} changed into {len(groups)} groups")
    for g in groups:
        print(f"  Group {g['id']}: {len(g['changed'])} libraries")

    return 0


if __name__ == "__main__":
    sys.exit(main())
