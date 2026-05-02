import json

from .models import Manifest


def list_libraries(manifest: Manifest, json_output: bool = False) -> None:
    """List libraries from manifest."""
    if json_output:
        print(json.dumps(manifest.model_dump(), indent=2))
        return

    indexed = [lib for lib in manifest.libraries if lib.indexed]
    print(
        f"Available libraries: {len(indexed)} indexed / {manifest.total_libraries} total"
    )

    for lib in indexed:
        chunks = f" ({lib.chunks} chunks)" if lib.chunks else ""
        print(f"  {lib.id}{chunks}")
