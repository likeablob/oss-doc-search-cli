#!/usr/bin/env python3
"""
Generate manifest.json from registry YAML files and existing indexes.

Usage:
    python scripts/generate_manifest.py --indexes ./indexes --output ./manifest.json
    python scripts/generate_manifest.py --indexes ./indexes --output ./manifest.json --with-commit-sha
    python scripts/generate_manifest.py --indexes ./indexes --output ./manifest.json --prev-manifest ./prev_manifest/manifest.json --update-info ./update_info.json
"""

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

import yaml

from oss_doc_search.models import LibraryDefinition

ROOT = Path(__file__).parent.parent
REGISTRY = ROOT / "registry"


def load_registry() -> list[LibraryDefinition]:
    """Load and validate all YAML configs from registry."""
    libraries = []
    for yaml_path in REGISTRY.rglob("*.yaml"):
        with open(yaml_path) as f:
            data = yaml.safe_load(f)
        libraries.append(LibraryDefinition.model_validate(data))
    return libraries


def compute_file_hash(file_path: Path) -> str:
    """Compute SHA256 hash of file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return f"sha256:{sha256.hexdigest()}"


def load_previous_manifest(prev_manifest_path: Path) -> dict | None:
    """Load previous manifest if exists."""
    if prev_manifest_path and prev_manifest_path.exists():
        with open(prev_manifest_path) as f:
            return json.load(f)
    return None


def find_library_in_manifest(manifest: dict, library_id: str) -> dict | None:
    """Find library entry in manifest."""
    for lib in manifest.get("libraries", []):
        if lib["id"] == library_id:
            return lib
    return None


def check_index_exists(library_id: str, indexes_dir: Path) -> dict | None:
    """Check if index file exists and get stats."""
    index_name = library_id.strip("/").replace("/", "_")
    index_path = indexes_dir / f"{index_name}.duckdb"

    if not index_path.exists():
        return None

    import duckdb

    conn = duckdb.connect(str(index_path))
    result = conn.execute("SELECT COUNT(*) FROM docs").fetchone()
    chunks = result[0] if result else 0
    conn.close()

    return {
        "index_path": str(index_path),
        "chunks": chunks,
        "file_size_mb": index_path.stat().st_size / 1024 / 1024,
        "updated_at": datetime.fromtimestamp(index_path.stat().st_mtime).isoformat(),
        "index_filename": f"{index_name}.duckdb",
        "index_hash": compute_file_hash(index_path),
    }


def generate_manifest(
    indexes_dir: Path,
    output_path: Path,
    include_missing: bool = False,
    with_commit_sha: bool = False,
    release_tag: str | None = None,
    prev_manifest: dict | None = None,
    update_info: dict | None = None,
):
    """Generate manifest.json."""
    libraries = load_registry()

    today = datetime.now()
    tag = release_tag or f"v{today.strftime('%Y.%m.%d-%H%M')}"

    import os

    github_repo = os.environ.get("GITHUB_REPOSITORY", "likeablob/oss-doc-search")
    parts = github_repo.split("/")
    owner = parts[0] if len(parts) >= 1 else "likeablob"
    repo_name = parts[1] if len(parts) >= 2 else "oss-doc-search"
    release_base_url = f"https://github.com/{owner}/{repo_name}/releases/download/{tag}"

    changed_dict = {}
    unchanged_set = set()
    if update_info:
        for entry in update_info.get("changed", []):
            changed_dict[entry["id"]] = entry
        for entry in update_info.get("unchanged", []):
            unchanged_set.add(entry["id"])

    manifest = {
        "manifest_version": today.strftime("%Y.%m.%d"),
        "release_tag": tag,
        "release_base_url": release_base_url,
        "generated_at": today.isoformat(),
        "total_libraries": len(libraries),
        "libraries": [],
    }

    indexed_count = 0
    missing_count = 0
    inherited_count = 0
    new_count = 0

    for lib in libraries:
        lib_id = lib.id

        prev_entry = (
            find_library_in_manifest(prev_manifest, lib_id) if prev_manifest else None
        )
        index_info = check_index_exists(lib_id, indexes_dir)

        entry: dict[str, str | bool | int | float] = {
            "id": lib_id,
            "name": lib.name,
            "repo": lib.repo,
            "doc_repo": lib.doc_source.repo,
            "license": lib.license,
            "description": lib.description or "",
        }

        if lib_id in unchanged_set and prev_entry and prev_entry.get("indexed"):
            entry["indexed"] = True
            entry["chunks"] = prev_entry.get("chunks", 0)
            entry["index_size_mb"] = prev_entry.get("index_size_mb", 0)
            entry["updated_at"] = prev_entry.get("updated_at", "")
            entry["index_filename"] = prev_entry.get("index_filename", "")
            entry["index_hash"] = prev_entry.get("index_hash", "")

            prev_index_url = prev_entry.get("index_url", "")
            if prev_index_url:
                entry["index_url"] = prev_index_url
            else:
                prev_base_url = (
                    prev_manifest.get("release_base_url", "") if prev_manifest else ""
                )
                if prev_base_url and entry.get("index_filename"):
                    entry["index_url"] = f"{prev_base_url}/{entry['index_filename']}"
                else:
                    entry["index_url"] = ""

            if with_commit_sha:
                entry["commit_sha"] = prev_entry.get("commit_sha", "")
            entry["inherited"] = True
            indexed_count += 1
            inherited_count += 1

        elif (
            lib_id not in changed_dict
            and prev_entry
            and prev_entry.get("indexed")
            and not index_info
        ):
            entry["indexed"] = True
            entry["chunks"] = prev_entry.get("chunks", 0)
            entry["index_size_mb"] = prev_entry.get("index_size_mb", 0)
            entry["updated_at"] = prev_entry.get("updated_at", "")
            entry["index_filename"] = prev_entry.get("index_filename", "")
            entry["index_hash"] = prev_entry.get("index_hash", "")

            prev_index_url = prev_entry.get("index_url", "")
            if prev_index_url:
                entry["index_url"] = prev_index_url
            else:
                prev_base_url = (
                    prev_manifest.get("release_base_url", "") if prev_manifest else ""
                )
                if prev_base_url and entry.get("index_filename"):
                    entry["index_url"] = f"{prev_base_url}/{entry['index_filename']}"
                else:
                    entry["index_url"] = ""

            if with_commit_sha:
                entry["commit_sha"] = prev_entry.get("commit_sha", "")
            entry["inherited"] = True
            indexed_count += 1
            inherited_count += 1

        elif index_info:
            entry["indexed"] = True
            entry["chunks"] = index_info["chunks"]
            entry["index_size_mb"] = round(index_info["file_size_mb"], 2)
            entry["updated_at"] = index_info["updated_at"]
            entry["index_filename"] = index_info["index_filename"]
            entry["index_hash"] = index_info["index_hash"]
            entry["index_url"] = f"{release_base_url}/{index_info['index_filename']}"

            if with_commit_sha and lib_id in changed_dict:
                entry["commit_sha"] = changed_dict[lib_id]["commit_sha"]

            indexed_count += 1
            new_count += 1
        else:
            entry["indexed"] = False
            missing_count += 1
            if not include_missing:
                continue

        manifest["libraries"].append(entry)

    manifest["indexed_count"] = indexed_count
    manifest["missing_count"] = missing_count
    manifest["inherited_count"] = inherited_count
    manifest["new_count"] = new_count

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"Generated manifest: {output_path}")
    print(f"  Total: {len(libraries)}")
    print(f"  Indexed: {indexed_count}")
    print(f"    Inherited: {inherited_count}")
    print(f"    New: {new_count}")
    print(f"  Missing: {missing_count}")

    return manifest


def main():
    parser = argparse.ArgumentParser(description="Generate manifest.json")
    parser.add_argument(
        "--indexes", "-i", default="./indexes", help="Indexes directory"
    )
    parser.add_argument(
        "--output", "-o", default="./manifest.json", help="Output manifest path"
    )
    parser.add_argument(
        "--include-missing", action="store_true", help="Include non-indexed libraries"
    )
    parser.add_argument(
        "--with-commit-sha",
        action="store_true",
        help="Include commit SHA from index_metadata.json",
    )
    parser.add_argument(
        "--release-tag",
        default=None,
        help="Release tag (default: vYYYY.MM.DD-HHMM)",
    )
    parser.add_argument(
        "--prev-manifest",
        default=None,
        help="Previous manifest path (for inheriting unchanged URLs)",
    )
    parser.add_argument(
        "--update-info",
        default=None,
        help="update_info.json path (changed/unchanged lists)",
    )
    args = parser.parse_args()

    indexes_dir = Path(args.indexes)
    output_path = Path(args.output)
    prev_manifest_path = Path(args.prev_manifest) if args.prev_manifest else None
    update_info_path = Path(args.update_info) if args.update_info else None

    prev_manifest = (
        load_previous_manifest(prev_manifest_path) if prev_manifest_path else None
    )
    update_info = None
    if update_info_path and update_info_path.exists():
        with open(update_info_path) as f:
            update_info = json.load(f)

    generate_manifest(
        indexes_dir,
        output_path,
        args.include_missing,
        args.with_commit_sha,
        args.release_tag,
        prev_manifest,
        update_info,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
