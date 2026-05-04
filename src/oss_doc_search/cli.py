import argparse
import json
import sys
import time
from pathlib import Path

from . import __version__
from .config import CACHE_MANIFEST, TTL_SECONDS
from .list import list_libraries
from .models import LibraryManifestEntry, Manifest
from .query import query_docs
from .resolve import resolve_library_id
from .update import (
    download_all_indexes,
    refresh_cached_indexes,
    show_status,
    update_index,
    update_manifest,
)


def load_manifest() -> Manifest:
    """Load manifest, auto-update if TTL expired, auto-download if missing."""
    if CACHE_MANIFEST.exists():
        age_hours = (time.time() - CACHE_MANIFEST.stat().st_mtime) / 3600
        if age_hours < TTL_SECONDS / 3600:
            with open(CACHE_MANIFEST) as f:
                data = json.load(f)
            return Manifest.model_validate(data)

        # TTL expired, try update (requests timeout=10 already set)
        try:
            update_manifest()
        except Exception:
            print("Warning: Manifest auto-update failed. Using cached version.")
            print("         Run `ossds update` to force sync.")

        with open(CACHE_MANIFEST) as f:
            data = json.load(f)
        return Manifest.model_validate(data)

    print("Manifest not found. Downloading...")
    try:
        update_manifest()
        with open(CACHE_MANIFEST) as f:
            data = json.load(f)
        return Manifest.model_validate(data)
    except Exception as e:
        raise FileNotFoundError(
            f"Failed to download manifest: {e}\n"
            f"Please check OSSDS_REPO and GH_TOKEN environment variables.\n"
            f"Or manually place manifest.json in: {CACHE_MANIFEST}"
        ) from e


def find_library_entry(
    manifest: Manifest, library_id: str
) -> LibraryManifestEntry | None:
    """Find library entry in manifest."""
    for lib in manifest.libraries:
        if lib.id == library_id:
            return lib
    return None


def build_raw_url(repo: str, commit_sha: str, source: str) -> str:
    """Build raw.githubusercontent.com URL."""
    return f"https://raw.githubusercontent.com/{repo}/{commit_sha}/{source.lstrip('/')}"


def install_skills_action(args):
    """Install skill files for coding agents."""
    from .skills import install_skills as _install_skills

    agents = args.agent or ["claude-code"]
    installed = _install_skills(agents=agents, target=args.target)

    if installed:
        print(f"Installed skill to {len(installed)} location(s)")
        for path in installed:
            print(f"  {path}/SKILL.md")
    else:
        print("Failed to install skill")
        sys.exit(1)


def resolve_action(args):
    """Resolve library name to ID."""
    try:
        manifest = load_manifest()
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)

    library_ids = resolve_library_id(args.library_name, manifest, top_k=args.k)
    if library_ids:
        for lib_id in library_ids:
            print(lib_id)
    else:
        print(f"Library not found: {args.library_name}")
        sys.exit(1)


def query_action(args):
    """Query library documentation."""
    try:
        manifest = load_manifest()
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)

    try:
        library_entry = find_library_entry(manifest, args.library_id)
        results = query_docs(args.library_id, args.query, args.k, manifest)
        print(f"\nQuery: {args.query}")
        print(f"Top {args.k} results:\n")
        print_results(results, library_entry, show_full=args.full)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)


def list_action(args):
    """List available libraries."""
    try:
        manifest = load_manifest()
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)

    list_libraries(manifest, args.json)


def update_action(args):
    """Sync manifest and indexes."""
    if args.status:
        show_status()
    elif args.download_all_indexes:
        update_manifest()
        download_all_indexes()
    elif args.manifest_only:
        update_manifest()
    elif args.index_only:
        refresh_cached_indexes()
    elif args.library_id:
        update_index(args.library_id, force=args.force)
    else:
        update_manifest()
        refresh_cached_indexes()


def print_results(
    results: list[dict],
    library_entry: LibraryManifestEntry | None,
    show_full: bool = False,
) -> None:
    for r in results:
        print(f"[{r['distance']:.4f}] {r['id']}")
        print(f"  Title: {r['title']}")

        if library_entry and library_entry.commit_sha:
            repo = library_entry.doc_repo or library_entry.repo
            raw_url = build_raw_url(repo, library_entry.commit_sha, r["source"])
            print(f"  Raw URL: {raw_url}")

        if show_full:
            print(f"  Content:\n{r['content']}")
        else:
            print(f"  Content: {r['content'][:200].strip()}...")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="ossds",
        description="OSS documentation search with vector embeddings",
    )
    parser.add_argument("--version", action="version", version=f"ossds {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    # resolve
    resolve_parser = subparsers.add_parser("resolve", help="Resolve library name to ID")
    resolve_parser.add_argument("library_name", help="Library name (fuzzy match)")
    resolve_parser.add_argument(
        "--k", "-k", type=int, default=3, help="Number of candidates (default: 3)"
    )
    resolve_parser.set_defaults(func=resolve_action)

    # query
    query_parser = subparsers.add_parser("query", help="Query library documentation")
    query_parser.add_argument("library_id", help="Library ID (e.g., /vercel/next.js)")
    query_parser.add_argument("query", help="Search query")
    query_parser.add_argument(
        "--k", "-k", type=int, default=8, help="Number of results"
    )
    query_parser.add_argument(
        "--full", "-f", action="store_true", help="Show full content"
    )
    query_parser.set_defaults(func=query_action)

    # list
    list_parser = subparsers.add_parser("list", help="List available libraries")
    list_parser.add_argument("--json", action="store_true", help="JSON output")
    list_parser.set_defaults(func=list_action)

    # update
    update_parser = subparsers.add_parser("update", help="Sync manifest and indexes")
    update_parser.add_argument(
        "library_id", nargs="?", help="Library ID to update (optional)"
    )
    update_parser.add_argument(
        "--manifest-only",
        action="store_true",
        help="Update manifest only (TTL ignored)",
    )
    update_parser.add_argument(
        "--index-only", action="store_true", help="Refresh cached indexes (hash check)"
    )
    update_parser.add_argument(
        "--download-all-indexes",
        action="store_true",
        help="Download ALL indexes from manifest (WARNING: downloads ~85 libraries, use sparingly)",
    )
    update_parser.add_argument(
        "--force",
        action="store_true",
        help="Skip hash check when updating specific index",
    )
    update_parser.add_argument(
        "--status", action="store_true", help="Show cache status"
    )
    update_parser.set_defaults(func=update_action)

    install_parser = subparsers.add_parser(
        "install-skills", help="Install skill files for coding agents"
    )
    install_parser.add_argument(
        "-a",
        "--agent",
        action="append",
        choices=["opencode", "claude-code"],
        help="Agent type (default: claude-code, can specify multiple)",
    )
    install_parser.add_argument(
        "-t", "--target", type=Path, help="Custom installation path"
    )
    install_parser.set_defaults(func=install_skills_action)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
