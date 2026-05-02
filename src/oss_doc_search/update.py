import hashlib
import json
import time
from pathlib import Path

from .config import (
    CACHE_DIR,
    CACHE_MANIFEST,
    INDEXES_DIR,
    TTL_SECONDS,
)
from .github_release import (
    check_github_release_exists,
    download_asset,
    get_latest_release_info,
    get_release_by_tag,
    parse_index_url,
)


def compute_file_hash(file_path: Path) -> str:
    """Compute sha256 hash of file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return f"sha256:{sha256.hexdigest()}"


def get_cached_manifest_version() -> str | None:
    """Get version from cached manifest."""
    if not CACHE_MANIFEST.exists():
        return None
    with open(CACHE_MANIFEST) as f:
        data = json.load(f)
    return data.get("manifest_version")


def save_cached_version(version: str) -> None:
    """Save version info to cache."""
    version_path = CACHE_DIR / "version.json"
    with open(version_path, "w") as f:
        json.dump({"cached_version": version, "cached_at": time.time()}, f)


def update_manifest(force: bool = False) -> None:
    """Download latest manifest if TTL expired or force."""
    if not check_github_release_exists():
        raise RuntimeError(
            "GitHub Releases not available.\n"
            "Please check OSSDS_REPO and GH_TOKEN environment variables."
        )

    # TTL check
    if not force and CACHE_MANIFEST.exists():
        age_hours = (time.time() - CACHE_MANIFEST.stat().st_mtime) / 3600
        if age_hours < TTL_SECONDS / 3600:
            print(
                f"Manifest cached ({age_hours:.1f}h old, TTL: {TTL_SECONDS / 3600:.0f}h)"
            )
            return

    # Download
    release_info = get_latest_release_info()

    print(f"Downloading manifest ({release_info['tag_name']})...")
    download_asset("manifest.json", release_info, CACHE_MANIFEST)

    save_cached_version(release_info["tag_name"])
    print(f"Manifest updated: {CACHE_MANIFEST}")


def need_download_index(library_id: str) -> bool:
    """Check if index needs download."""
    from .cli import load_manifest

    index_name = library_id.strip("/").replace("/", "_")
    index_path = INDEXES_DIR / f"{index_name}.duckdb"

    if not index_path.exists():
        return True

    # Hash comparison
    manifest = load_manifest()
    lib_entry = next((lib for lib in manifest.libraries if lib.id == library_id), None)
    if not lib_entry:
        return False

    cached_hash = compute_file_hash(index_path)
    expected_hash = lib_entry.index_hash or ""

    return cached_hash != expected_hash


def update_index(library_id: str, force: bool = False) -> None:
    """Download index if hash mismatch or force."""
    from .cli import load_manifest

    if not check_github_release_exists():
        raise RuntimeError(
            "GitHub Releases not available.\n"
            "Please check OSSDS_REPO and GH_TOKEN environment variables."
        )

    index_name = library_id.strip("/").replace("/", "_")
    index_path = INDEXES_DIR / f"{index_name}.duckdb"

    if not force and not need_download_index(library_id):
        print(f"Index cached: {library_id}")
        return

    # Get index_url from manifest
    manifest = load_manifest()
    lib_entry = next((lib for lib in manifest.libraries if lib.id == library_id), None)
    if not lib_entry:
        print(f"Library not found in manifest: {library_id}")
        return

    index_url = lib_entry.index_url
    if not index_url:
        print(f"No index_url for: {library_id}")
        return

    # Parse URL and get release info
    url_info = parse_index_url(index_url)
    if not url_info:
        print(f"Invalid index_url: {index_url}")
        return

    release_info = get_release_by_tag(
        url_info["tag"], url_info["owner"], url_info["repo"]
    )

    print(f"Downloading index: {library_id} ({url_info['tag']})...")
    download_asset(url_info["filename"], release_info, index_path)

    print(f"Index updated: {index_path}")


def update_all(force: bool = False) -> None:
    """Pre-download all indexes."""
    from .cli import load_manifest

    print("Updating all indexes...")
    update_manifest(force=force)

    manifest = load_manifest()
    for lib in manifest.libraries:
        try:
            update_index(lib.id, force=force)
        except Exception as e:
            print(f"Error updating {lib.id}: {e}")


def show_status() -> None:
    """Show cache status."""
    from .cli import load_manifest

    print("Cache Status:")
    print(f"  Cache dir: {CACHE_DIR}")

    # Manifest status
    if CACHE_MANIFEST.exists():
        cached_version = get_cached_manifest_version()
        print(f"  Manifest: cached ({cached_version})")
    else:
        print("  Manifest: not cached")

    # Index status
    manifest = load_manifest()
    print(f"\n  Indexes ({len(manifest.libraries)} libraries):")

    cached_count = 0
    missing_count = 0

    for lib in manifest.libraries:
        index_name = lib.id.strip("/").replace("/", "_")
        index_path = INDEXES_DIR / f"{index_name}.duckdb"

        if index_path.exists():
            cached_hash = compute_file_hash(index_path)
            expected_hash = lib.index_hash or ""
            status = "OK" if cached_hash == expected_hash else "~"
            cached_count += 1
        else:
            status = "--"
            missing_count += 1

        print(f"    {status} {lib.id}")

    print(f"\n  Cached: {cached_count}, Missing: {missing_count}")
