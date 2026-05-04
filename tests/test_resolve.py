from oss_doc_search.resolve import resolve_library_id


def test_resolve_exact_match(sample_manifest):
    assert resolve_library_id("Next.js", sample_manifest) == ["/vercel/next.js"]


def test_resolve_case_insensitive(sample_manifest):
    assert resolve_library_id("next.js", sample_manifest) == ["/vercel/next.js"]


def test_resolve_fuzzy_match(sample_manifest):
    assert resolve_library_id("fasti", sample_manifest) == ["/fastify/fastify"]


def test_resolve_abbreviation(sample_manifest):
    assert resolve_library_id("vue", sample_manifest) == ["/vuejs/vue"]


def test_resolve_id_partial_match(sample_manifest):
    assert resolve_library_id("next.js", sample_manifest) == ["/vercel/next.js"]


def test_resolve_no_match(sample_manifest):
    assert resolve_library_id("unknown-lib", sample_manifest) == []
