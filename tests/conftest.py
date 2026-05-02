import pytest

from oss_doc_search.models import LibraryManifestEntry, Manifest


@pytest.fixture
def sample_manifest() -> Manifest:
    return Manifest(
        manifest_version="2026.01.01",
        release_tag="v2026.01.01",
        release_base_url="https://example.com",
        generated_at="2026-01-01T00:00:00",
        total_libraries=3,
        libraries=[
            LibraryManifestEntry(
                id="/vercel/next.js",
                name="Next.js",
                repo="vercel/next.js",
                license="MIT",
                indexed=True,
                chunks=945,
            ),
            LibraryManifestEntry(
                id="/fastify/fastify",
                name="Fastify",
                repo="fastify/fastify",
                license="MIT",
                indexed=True,
                chunks=182,
            ),
            LibraryManifestEntry(
                id="/vuejs/vue",
                name="Vue",
                repo="vuejs/vue",
                license="MIT",
                indexed=True,
                chunks=345,
            ),
        ],
    )
