#!/usr/bin/env python3
"""
Validate indexes based on index_results.json.

Usage:
    python scripts/validate_indexes.py --metadata ./index_results.json
    python scripts/validate_indexes.py --metadata ./index_results.json --fail-on-error
"""

import argparse
import json
import sys
from pathlib import Path


def validate_indexes(metadata_path: Path, fail_on_error: bool = False) -> dict:
    """Validate indexes and report results."""
    if not metadata_path.exists():
        print(f"ERROR: Results file not found: {metadata_path}")
        return {"valid": False, "error": "results_not_found"}

    with open(metadata_path) as f:
        results = json.load(f)

    succeeded = []
    failed = []

    for entry in results:
        lib_id = entry.get("library_id", "unknown")
        if entry.get("success", False):
            succeeded.append(lib_id)
        else:
            failed.append(
                {"library_id": lib_id, "error": entry.get("error", "unknown")}
            )

    print("Index validation results:")
    print(f"  Succeeded: {len(succeeded)}")
    for lib in succeeded:
        print(f"    - {lib}")

    print(f"  Failed: {len(failed)}")
    for entry in failed:
        print(f"    - {entry['library_id']}: {entry['error']}")

    result = {
        "valid": len(failed) == 0,
        "succeeded": succeeded,
        "failed": failed,
    }

    if failed and fail_on_error:
        print(f"\nERROR: {len(failed)} libraries failed")
        sys.exit(1)

    return result


def main():
    parser = argparse.ArgumentParser(description="Validate indexes")
    parser.add_argument(
        "--metadata", "-m", required=True, help="index_results.json path"
    )
    parser.add_argument(
        "--fail-on-error",
        action="store_true",
        help="Exit with error if any library failed",
    )
    args = parser.parse_args()

    metadata_path = Path(args.metadata)
    result = validate_indexes(metadata_path, args.fail_on_error)

    return 0 if result["valid"] else 1
