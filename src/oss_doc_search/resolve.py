from rapidfuzz import fuzz, process

from .models import Manifest


def resolve_library_id(library_name: str, manifest: Manifest) -> str | None:
    """Resolve library name to ID using fuzzy matching."""
    library_names = [lib.name for lib in manifest.libraries]
    name_to_id = {lib.name: lib.id for lib in manifest.libraries}

    # Direct match
    if library_name in name_to_id:
        return name_to_id[library_name]

    # Fuzzy match
    result = process.extractOne(
        library_name, library_names, scorer=fuzz.WRatio, score_cutoff=60
    )
    if result:
        matched_name = result[0]
        return name_to_id[matched_name]

    return None
