from pathlib import Path

from platformdirs import user_data_dir

CACHE_DIR = Path(user_data_dir("oss-doc-search-cli"))
INDEXES_DIR = CACHE_DIR / "indexes"
CACHE_MANIFEST = CACHE_DIR / "manifest.json"
MODELS_DIR = CACHE_DIR / "models"

# TTL for manifest update (24 hours)
TTL_SECONDS = 86400

CACHE_DIR.mkdir(parents=True, exist_ok=True)
INDEXES_DIR.mkdir(exist_ok=True)
MODELS_DIR.mkdir(exist_ok=True)
