import duckdb

from .config import INDEXES_DIR
from .embedder import get_embedder


def query_docs(library_id: str, query: str, k: int = 8) -> list[dict]:
    index_name = library_id.strip("/").replace("/", "_")
    index_path = INDEXES_DIR / f"{index_name}.duckdb"

    if not index_path.exists():
        raise FileNotFoundError(f"Index not found: {library_id}")

    embedder = get_embedder()
    query_emb = embedder.embed(query)

    conn = duckdb.connect(str(index_path))
    conn.execute("LOAD vss")

    emb_str = "[" + ",".join(str(x) for x in query_emb) + "]"
    results = conn.execute(f"""
        SELECT id, title, content, source,
               array_cosine_distance(embedding, {emb_str}::FLOAT[384]) as distance
        FROM docs
        ORDER BY distance
        LIMIT {k}
    """).fetchall()

    conn.close()

    return [
        {"id": r[0], "title": r[1], "content": r[2], "source": r[3], "distance": r[4]}
        for r in results
    ]
