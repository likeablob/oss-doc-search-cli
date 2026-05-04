from rapidfuzz import fuzz, process

from .models import Manifest


def resolve_library_id(
    library_name: str, manifest: Manifest, top_k: int = 3
) -> list[str]:
    """Resolve library name to ID using fuzzy matching. Returns list of candidates."""
    library_names = [lib.name for lib in manifest.libraries]
    name_to_id = {lib.name: lib.id for lib in manifest.libraries}

    # Direct match
    if library_name in name_to_id:
        return [name_to_id[library_name]]

    # Fuzzy match
    results = process.extract(
        library_name, library_names, scorer=fuzz.WRatio, score_cutoff=60, limit=top_k
    )
    if results:
        return [name_to_id[r[0]] for r in results]

    return []
