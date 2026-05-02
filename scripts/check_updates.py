#!/usr/bin/env python3
"""
Check which libraries need reindex by comparing commit SHA.

Usage:
    python scripts/check_updates.py                          # All libraries
    python scripts/check_updates.py --libraries "*"          # All libraries
    python scripts/check_updates.py --libraries "/fastify/fastify,/vuejs/vitepress"
    python scripts/check_updates.py --prev-manifest ./prev_manifest/manifest.json
"""

import argparse
import json
import os
import sys
from pathlib import Path

import requests
import yaml

from oss_doc_search.models import LibraryDefinition

ROOT = Path(__file__).parent.parent
REGISTRY = ROOT / "registry"


def load_all_library_ids() -> list[str]:
    """Load all library IDs from registry YAML files."""
    library_ids = []
    for yaml_path in REGISTRY.rglob("*.yaml"):
        with open(yaml_path) as f:
            data = yaml.safe_load(f)
        if data and "id" in data:
            library_ids.append(data["id"])
    return library_ids


def load_library_config(library_id: str) -> LibraryDefinition:
    """Load and validate library config from YAML."""
    parts = library_id.strip("/").split("/")
    if len(parts) == 2:
        yaml_path = REGISTRY / parts[0] / f"{parts[1]}.yaml"
    elif len(parts) == 3:
        yaml_path = REGISTRY / parts[0] / f"{parts[1]}-{parts[2]}.yaml"
    else:
        raise ValueError(f"Invalid library_id: {library_id}")

    if not yaml_path.exists():
        raise FileNotFoundError(f"Library config not found: {yaml_path}")

    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    return LibraryDefinition.model_validate(data)


def get_head_sha(repo: str, ref: str | None = None) -> str:
    """Get SHA from repo. If ref is None, use default branch."""
    url = (
        f"https://api.github.com/repos/{repo}/commits/{ref}"
        if ref
        else f"https://api.github.com/repos/{repo}/commits"
    )
    headers = {"Accept": "application/vnd.github+json"}

    if os.environ.get("GH_TOKEN"):
        headers["Authorization"] = f"token {os.environ['GH_TOKEN']}"

    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()

    data = resp.json()
    if isinstance(data, list):
        return data[0]["sha"]
    return data["sha"]


def find_library_in_manifest(manifest: dict, library_id: str) -> dict | None:
    for lib in manifest.get("libraries", []):
        if lib["id"] == library_id:
            return lib
    return None


def check_updates(
    libraries: list[str], prev_manifest_path: Path | None, force_full: bool = False
) -> dict:
    prev_manifest = None
    if prev_manifest_path and prev_manifest_path.exists():
        with open(prev_manifest_path) as f:
            prev_manifest = json.load(f)

    changed = []
    unchanged = []

    for library_id in libraries:
        config = load_library_config(library_id)
        doc_source = config.doc_source
        repo = doc_source.repo
        ref = doc_source.ref

        prev_lib = (
            find_library_in_manifest(prev_manifest, library_id)
            if prev_manifest
            else None
        )
        prev_sha = prev_lib.get("commit_sha") if prev_lib else None

        if force_full:
            try:
                current_sha = get_head_sha(repo, ref)
            except Exception as e:
                print(f"  {library_id}: ERROR - {e}")
                continue
            changed.append({
                "id": library_id,
                "commit_sha": current_sha,
                "repo": repo,
                "ref": ref,
            })
            print(f"  {library_id}: FORCE_FULL ({current_sha[:7]})")
            continue

        if not prev_sha:
            try:
                current_sha = get_head_sha(repo, ref)
            except Exception as e:
                print(f"  {library_id}: ERROR - {e}")
                continue
            changed.append({
                "id": library_id,
                "commit_sha": current_sha,
                "repo": repo,
                "ref": ref,
            })
            print(f"  {library_id}: NEW ({current_sha[:7]})")
            continue

        try:
            current_sha = get_head_sha(repo, ref)
        except Exception as e:
            print(f"  {library_id}: ERROR - {e}")
            continue

        if current_sha == prev_sha:
            unchanged.append({
                "id": library_id,
                "commit_sha": prev_sha,
            })
            print(f"  {library_id}: UNCHANGED ({current_sha[:7]})")
        else:
            changed.append({
                "id": library_id,
                "commit_sha": current_sha,
                "repo": repo,
                "ref": ref,
            })
            print(f"  {library_id}: CHANGED ({prev_sha[:7]} -> {current_sha[:7]})")

    return {
        "changed": changed,
        "unchanged": unchanged,
        "checked_at": __import__("datetime").datetime.now().isoformat(),
    }


def main():
    parser = argparse.ArgumentParser(description="Check library updates")
    parser.add_argument(
        "--libraries",
        required=False,
        default="",
        help="Library IDs (comma-separated, '*' for all)",
    )
    parser.add_argument("--prev-manifest", default=None, help="Previous manifest path")
    parser.add_argument(
        "--output", "-o", default="./update_info.json", help="Output JSON path"
    )
    parser.add_argument("--force-full", default="false", help="Force full reindex")
    args = parser.parse_args()

    if args.libraries == "" or args.libraries == "*":
        libraries = load_all_library_ids()
        print(f"Loading all libraries from registry: {len(libraries)} found")
    else:
        libraries = [lib.strip() for lib in args.libraries.split(",")]

    prev_manifest_path = Path(args.prev_manifest) if args.prev_manifest else None
    force_full = args.force_full.lower() == "true"

    print(f"Checking {len(libraries)} libraries...")

    result = check_updates(libraries, prev_manifest_path, force_full)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)

    print(
        f"\nResult: {len(result['changed'])} changed, {len(result['unchanged'])} unchanged"
    )
    print(f"Output: {output_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
