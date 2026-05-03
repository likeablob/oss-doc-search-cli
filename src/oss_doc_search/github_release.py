import os

import requests


def get_repo_config() -> tuple[str, str]:
    """Get repository owner and name from environment or default."""
    repo = os.environ.get("OSSDS_REPO", "likeablob/oss-doc-search-cli")
    parts = repo.split("/")
    if len(parts) >= 2:
        return parts[0], parts[1]
    return "likeablob", "oss-doc-search-cli"


GITHUB_API_URL = "https://api.github.com/repos/{owner}/{repo}/releases/latest"
GITHUB_RELEASE_API_URL = (
    "https://api.github.com/repos/{owner}/{repo}/releases/tags/{tag}"
)


def get_release_by_tag(
    tag: str, owner: str | None = None, repo: str | None = None
) -> dict:
    """Get release info by tag name."""
    if owner is None or repo is None:
        owner, repo = get_repo_config()

    url = GITHUB_RELEASE_API_URL.format(owner=owner, repo=repo, tag=tag)
    headers = get_auth_headers(json_api=True)

    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()

    return resp.json()


def parse_index_url(index_url: str) -> dict | None:
    """Parse index_url to extract owner, repo, tag, filename."""
    import re

    pattern = r"https://github\.com/([^/]+)/([^/]+)/releases/download/([^/]+)/([^/?]+)"
    match = re.match(pattern, index_url)

    if match:
        return {
            "owner": match.group(1),
            "repo": match.group(2),
            "tag": match.group(3),
            "filename": match.group(4),
        }
    return None


def get_auth_headers(json_api: bool = True) -> dict:
    """Get GitHub API headers with optional authentication."""
    if json_api:
        headers = {"Accept": "application/vnd.github+json"}
    else:
        headers = {"Accept": "application/octet-stream"}
    if os.environ.get("GH_TOKEN"):
        headers["Authorization"] = f"token {os.environ['GH_TOKEN']}"
    return headers


def get_latest_release_info(owner: str | None = None, repo: str | None = None) -> dict:
    """Get latest release info from GitHub API."""
    if owner is None or repo is None:
        owner, repo = get_repo_config()

    url = GITHUB_API_URL.format(owner=owner, repo=repo)
    headers = get_auth_headers(json_api=True)

    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()

    return resp.json()


def get_asset_download_info(asset_name: str, release_info: dict) -> dict:
    """Get asset download info (api_url) for private repo support."""
    for asset in release_info.get("assets", []):
        if asset["name"] == asset_name:
            api_url = asset.get("url")
            asset_id = asset.get("id")

            if api_url and api_url.startswith("https://api.github.com"):
                return {"url": api_url, "use_api": True}

            if asset_id:
                owner, repo = get_repo_config()
                constructed_url = f"https://api.github.com/repos/{owner}/{repo}/releases/assets/{asset_id}"
                return {"url": constructed_url, "use_api": True}

            browser_url = asset.get("browser_download_url")
            if browser_url:
                return {"url": browser_url, "use_api": False}

            return {"url": None, "use_api": False}

    raise FileNotFoundError(f"Asset not found: {asset_name}")


def download_asset(
    asset_name: str, release_info: dict, output_path, show_progress: bool = True
) -> None:
    """Download asset from GitHub release with private repo support."""
    from pathlib import Path

    asset_info = get_asset_download_info(asset_name, release_info)
    url = asset_info["url"]
    use_api = asset_info["use_api"]

    if not url:
        raise FileNotFoundError(f"No download URL for asset: {asset_name}")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    headers = get_auth_headers(json_api=not use_api)
    resp = requests.get(url, headers=headers, stream=True, timeout=30)
    resp.raise_for_status()

    total_size = int(resp.headers.get("content-length", 0))

    if show_progress and total_size > 0:
        from tqdm import tqdm

        with tqdm(total=total_size, unit="B", unit_scale=True) as pbar:
            with open(output_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
                    pbar.update(len(chunk))
    else:
        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)


def download_file(url: str, output_path, show_progress: bool = True) -> None:
    """Download file from URL with optional progress bar."""
    from pathlib import Path

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    headers = get_auth_headers(json_api=False)
    resp = requests.get(url, headers=headers, stream=True, timeout=30)
    resp.raise_for_status()

    total_size = int(resp.headers.get("content-length", 0))

    if show_progress and total_size > 0:
        from tqdm import tqdm

        with tqdm(total=total_size, unit="B", unit_scale=True) as pbar:
            with open(output_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
                    pbar.update(len(chunk))
    else:
        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)


def check_github_release_exists() -> bool:
    """Check if GitHub release exists (for Phase 1 validation)."""
    try:
        get_latest_release_info()
        return True
    except Exception:
        return False
