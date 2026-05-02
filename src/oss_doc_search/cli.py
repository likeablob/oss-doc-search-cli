import argparse
import json
import sys

from .config import CACHE_MANIFEST, INDEXES_DIR
from .list import list_libraries
from .models import Manifest
from .query import query_docs
from .resolve import resolve_library_id
from .update import show_status, update_all, update_index, update_manifest


def load_manifest() -> Manifest:
    """Load manifest, auto-download if missing."""
    if CACHE_MANIFEST.exists():
        with open(CACHE_MANIFEST) as f:
            data = json.load(f)
        return Manifest.model_validate(data)

    print("Manifest not found. Downloading...")
    try:
        update_manifest(force=True)
        with open(CACHE_MANIFEST) as f:
            data = json.load(f)
        return Manifest.model_validate(data)
    except Exception as e:
        raise FileNotFoundError(
            f"Failed to download manifest: {e}\n"
            f"Please check OSSDS_REPO and GH_TOKEN environment variables.\n"
            f"Or manually place manifest.json in: {CACHE_MANIFEST}"
        ) from e


def print_results(results: list[dict]) -> None:
    for r in results:
        print(f"[{r['distance']:.4f}] {r['id']}")
        print(f"  Title: {r['title']}")
        print(f"  Source: {r['source']}")
        print(f"  Content: {r['content'][:200].strip()}...")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="ossds",
        description="OSS documentation search with vector embeddings",
    )
    subparsers = parser.add_subparsers(dest="command")

    # resolve
    resolve_parser = subparsers.add_parser("resolve", help="Resolve library name to ID")
    resolve_parser.add_argument("library_name", help="Library name (fuzzy match)")
    resolve_parser.add_argument("--query", "-q", help="Search query for context")

    # query
    query_parser = subparsers.add_parser("query", help="Query library documentation")
    query_parser.add_argument("library_id", help="Library ID (e.g., /vercel/next.js)")
    query_parser.add_argument("query", help="Search query")
    query_parser.add_argument(
        "--k", "-k", type=int, default=8, help="Number of results"
    )

    # list
    list_parser = subparsers.add_parser("list", help="List available libraries")
    list_parser.add_argument("--json", action="store_true", help="JSON output")

    # update
    update_parser = subparsers.add_parser("update", help="Update manifest and indexes")
    update_parser.add_argument(
        "library_id", nargs="?", help="Library ID to update (optional)"
    )
    update_parser.add_argument("--all", action="store_true", help="Update all indexes")
    update_parser.add_argument("--force", action="store_true", help="Force re-download")
    update_parser.add_argument(
        "--status", action="store_true", help="Show cache status"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # update command (doesn't need manifest)
    if args.command == "update":
        if args.status:
            show_status()
        elif args.all:
            update_all(force=args.force)
        elif args.library_id:
            update_index(args.library_id, force=args.force)
        else:
            update_manifest(force=args.force)
        return

    # Other commands need manifest
    try:
        manifest = load_manifest()
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)

    if args.command == "resolve":
        library_id = resolve_library_id(args.library_name, manifest)
        if library_id:
            print(library_id)
        else:
            print(f"Library not found: {args.library_name}")
            sys.exit(1)

    elif args.command == "query":
        try:
            results = query_docs(args.library_id, args.query, args.k)
            print(f"\nQuery: {args.query}")
            print(f"Top {args.k} results:\n")
            print_results(results)
        except FileNotFoundError as e:
            print(f"Error: {e}")
            print(f"Please run: ossds update {args.library_id}")
            print(f"Or manually place index in: {INDEXES_DIR}")
            sys.exit(1)

    elif args.command == "list":
        list_libraries(manifest, args.json)


if __name__ == "__main__":
    main()
