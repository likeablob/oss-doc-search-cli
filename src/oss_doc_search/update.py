import hashlib
import json
import time
from pathlib import Path

from .config import (
    CACHE_DIR,
    CACHE_MANIFEST,
    INDEXES_DIR,
)
from .github_release import (
    check_github_release_exists,
    download_asset,
    get_latest_release_info,
    get_release_by_tag,
    parse_index_url,
)
from .models import Manifest


def compute_file_hash(file_path: Path) -> str:
    """Compute sha256 hash of file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return f"sha256:{sha256.hexdigest()}"


def get_cached_manifest_version() -> str | None:
    """Get release tag from cached manifest."""
    if not CACHE_MANIFEST.exists():
        return None
    with open(CACHE_MANIFEST) as f:
        data = json.load(f)
    return data.get("release_tag") or data.get("manifest_version")


def load_cached_manifest() -> dict | None:
    """Load cached manifest without auto-update (no network)."""
    if not CACHE_MANIFEST.exists():
        return None
    with open(CACHE_MANIFEST) as f:
        return json.load(f)


def save_cached_version(version: str) -> None:
    """Save version info to cache."""
    version_path = CACHE_DIR / "version.json"
    with open(version_path, "w") as f:
        json.dump({"cached_version": version, "cached_at": time.time()}, f)


def update_manifest() -> None:
    """Download latest manifest (TTL ignored, always fetches)."""
    if not check_github_release_exists():
        raise RuntimeError(
            "GitHub Releases not available.\n"
            "Please check OSSDS_REPO and GH_TOKEN environment variables."
        )

    release_info = get_latest_release_info()

    print(f"Downloading manifest ({release_info['tag_name']})...")
    download_asset("manifest.json", release_info, CACHE_MANIFEST)

    save_cached_version(release_info["tag_name"])
    print(f"Manifest updated: {CACHE_MANIFEST}")


def _index_path(library_id: str) -> Path:
    """Get local index path for a library ID."""
    index_name = library_id.strip("/").replace("/", "_")
    return INDEXES_DIR / f"{index_name}.duckdb"


def need_download_index(library_id: str, manifest: Manifest | None = None) -> bool:
    """Check if index needs update based on hash comparison."""
    from .cli import load_manifest

    index_path = _index_path(library_id)
    if not index_path.exists():
        return True

    if manifest is None:
        manifest = load_manifest()
    lib_entry = next((lib for lib in manifest.libraries if lib.id == library_id), None)
    if not lib_entry:
        return False

    cached_hash = compute_file_hash(index_path)
    expected_hash = lib_entry.index_hash or ""

    return cached_hash != expected_hash


def _download_index(library_id: str) -> bool:
    """Download index for a library. Returns True on success."""
    from .cli import load_manifest

    if not check_github_release_exists():
        return False

    index_path = _index_path(library_id)
    manifest = load_manifest()
    lib_entry = next((lib for lib in manifest.libraries if lib.id == library_id), None)
    if not lib_entry:
        print(f"  Library not found in manifest: {library_id}")
        return False

    index_url = lib_entry.index_url
    if not index_url:
        print(f"  No index_url for: {library_id}")
        return False

    url_info = parse_index_url(index_url)
    if not url_info:
        print(f"  Invalid index_url: {index_url}")
        return False

    release_info = get_release_by_tag(
        url_info["tag"], url_info["owner"], url_info["repo"]
    )
    download_asset(url_info["filename"], release_info, index_path)
    return True


def update_index(
    library_id: str, force: bool = False, manifest: Manifest | None = None
) -> None:
    """Download specific index. Skip hash check if force."""
    index_path = _index_path(library_id)

    if not force and not need_download_index(library_id, manifest):
        print(f"Index cached: {library_id}")
        return

    print(f"Downloading index: {library_id}...")
    if _download_index(library_id):
        print(f"Index updated: {index_path}")


def refresh_cached_indexes() -> None:
    """Hash-compare all cached indexes, download mismatched ones."""
    from .cli import load_manifest

    print("Checking cached indexes...")
    manifest = load_manifest()
    refreshed = 0
    unchanged = 0
    missing = 0

    for lib in manifest.libraries:
        index_path = _index_path(lib.id)
        if not index_path.exists():
            missing += 1
            continue

        if need_download_index(lib.id, manifest):
            print(f"  Hash mismatch: {lib.id}, downloading...")
            if _download_index(lib.id):
                refreshed += 1
            else:
                print(f"  Failed to download: {lib.id}")
        else:
            unchanged += 1

    print(f"Refreshed {refreshed}, Unchanged {unchanged}, Missing {missing}")


def download_all_indexes() -> None:
    """Download ALL indexes from manifest (no hash check)."""
    from .cli import load_manifest

    print("Downloading all indexes...")
    manifest = load_manifest()
    success = 0
    failed = 0

    for lib in manifest.libraries:
        print(f"  Downloading {lib.id}...")
        if _download_index(lib.id):
            print(f"    Done: {_index_path(lib.id)}")
            success += 1
        else:
            print("    Failed")
            failed += 1

    print(f"Downloaded {success} index(es), {failed} failed")


def show_status() -> None:
    """Show cache status (no network activity)."""
    print("Cache Status:")
    print(f"  Cache dir: {CACHE_DIR}")

    cached_version = get_cached_manifest_version()
    if cached_version:
        print(f"  Manifest: cached ({cached_version})")
    else:
        print("  Manifest: not cached")

    manifest_data = load_cached_manifest()
    if not manifest_data:
        print("\n  Indexes: no manifest available")
        return

    libraries = manifest_data.get("libraries", [])
    print(f"\n  Indexes ({len(libraries)} libraries):")

    cached_count = 0
    missing_count = 0

    for lib in libraries:
        lib_id = lib.get("id", "")
        index_path = _index_path(lib_id)

        if index_path.exists():
            cached_hash = compute_file_hash(index_path)
            expected_hash = lib.get("index_hash", "") or ""
            status = "OK" if cached_hash == expected_hash else "~"
            cached_count += 1
        else:
            status = "--"
            missing_count += 1

        print(f"    {status} {lib_id}")

    print(f"\n  Cached: {cached_count}, Missing: {missing_count}")
