#!/usr/bin/env python3
"""
Reindex multiple libraries based on update_info.json.

Usage:
    python scripts/reindex_libraries.py --update-info ./update_info.json --output-dir ./indexes
"""

import argparse
import fnmatch
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import duckdb
import numpy as np
import onnxruntime as ort
import yaml
from huggingface_hub import hf_hub_download
from tokenizers import Tokenizer

from oss_doc_search.models import DocSource, Filters, LibraryDefinition

ROOT = Path(__file__).parent.parent
REGISTRY = ROOT / "registry"

MODEL_REPO = "onnx-models/all-MiniLM-L6-v2-onnx"
TOKENIZER_REPO = "sentence-transformers/all-MiniLM-L6-v2"


def load_library_config(library_id: str) -> LibraryDefinition:
    """Load and validate library config from YAML."""
    parts = library_id.strip("/").split("/")
    if len(parts) == 2:
        yaml_path = REGISTRY / parts[0] / f"{parts[1]}.yaml"
    elif len(parts) == 3:
        yaml_path = REGISTRY / parts[0] / f"{parts[1]}-{parts[2]}.yaml"
    else:
        raise ValueError(f"Invalid library_id: {library_id}")

    if not yaml_path.exists():
        raise FileNotFoundError(f"Library config not found: {yaml_path}")

    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    return LibraryDefinition.model_validate(data)


class Embedder:
    def __init__(self):
        cache_dir = Path.home() / ".cache" / "oss-doc-search-cli" / "models"
        model_path = cache_dir / "all-MiniLM-L6-v2" / "model.onnx"
        if not model_path.exists():
            hf_hub_download(
                repo_id=MODEL_REPO,
                filename="model.onnx",
                local_dir=cache_dir / "all-MiniLM-L6-v2",
            )
        self.model_path = model_path

        tokenizer_path = cache_dir / "all-MiniLM-L6-v2-tokenizer" / "tokenizer.json"
        if not tokenizer_path.exists():
            hf_hub_download(
                repo_id=TOKENIZER_REPO,
                filename="tokenizer.json",
                local_dir=cache_dir / "all-MiniLM-L6-v2-tokenizer",
            )
        self.tokenizer = Tokenizer.from_file(str(tokenizer_path))
        self.session = ort.InferenceSession(str(self.model_path))
        self.embedding_dim = 384

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        encoded = self.tokenizer.encode_batch(texts)
        input_ids = np.array([e.ids for e in encoded], dtype=np.int64)
        attention_mask = np.array([e.attention_mask for e in encoded], dtype=np.int64)
        token_type_ids = np.zeros_like(input_ids)

        max_len = input_ids.shape[1]
        if max_len < 128:
            pad_len = 128 - max_len
            input_ids = np.pad(input_ids, ((0, 0), (0, pad_len)), constant_values=0)
            attention_mask = np.pad(
                attention_mask, ((0, 0), (0, pad_len)), constant_values=0
            )
            token_type_ids = np.pad(
                token_type_ids, ((0, 0), (0, pad_len)), constant_values=0
            )

        outputs = self.session.run(
            None,
            {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "token_type_ids": token_type_ids,
            },
        )

        output_array = outputs[0]
        if not isinstance(output_array, np.ndarray):
            output_array = np.array(output_array)
        mask = np.expand_dims(attention_mask, -1).repeat(output_array.shape[-1], -1)
        embeddings = (output_array * mask).sum(1) / np.clip(mask.sum(1), 1e-9, None)
        return embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)


def chunk_text(text: str, max_chunk_size: int = 500, overlap: int = 50) -> list[str]:
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + max_chunk_size, len(words))
        chunks.append(" ".join(words[start:end]))
        if end >= len(words):
            break
        start = end - overlap
    return chunks


def clone_repo(
    repo: str, output_dir: Path, ref: str | None = None, depth: int = 1
) -> Path:
    url = f"https://github.com/{repo}.git"
    if output_dir.exists():
        shutil.rmtree(output_dir)
    if ref:
        subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                str(depth),
                "--branch",
                ref,
                url,
                str(output_dir),
            ],
            check=True,
            capture_output=True,
        )
    else:
        subprocess.run(
            ["git", "clone", "--depth", str(depth), url, str(output_dir)],
            check=True,
            capture_output=True,
        )
    return output_dir


def collect_docs(
    clone_dir: Path, doc_source: DocSource, filters: Filters
) -> list[dict]:
    docs = []
    path = doc_source.path
    extensions = doc_source.extensions
    target_dir = clone_dir / path

    if not target_dir.exists():
        print(f"Warning: {target_dir} does not exist")
        return docs

    for ext in extensions:
        for file in target_dir.rglob(f"*{ext}"):
            rel_path = file.relative_to(clone_dir)
            if _should_exclude(rel_path, filters):
                continue
            content = file.read_text(errors="ignore")
            if len(content.strip()) > 100:
                docs.append(
                    {"path": str(rel_path), "name": file.name, "content": content}
                )
    return docs


def _should_exclude(rel_path: Path, filters: Filters) -> bool:
    path_str = str(rel_path)
    for pattern in filters.exclude:
        if fnmatch.fnmatch(path_str, pattern) or fnmatch.fnmatch(
            path_str.lower(), pattern.lower()
        ):
            return True
    if filters.include:
        for pattern in filters.include:
            if fnmatch.fnmatch(path_str, pattern) or fnmatch.fnmatch(
                path_str.lower(), pattern.lower()
            ):
                return False
        return True
    return False


def create_index(
    docs: list[dict], output_path: Path, embedder: Embedder, batch_size: int = 32
) -> dict:
    chunks = []
    for doc in docs:
        for i, chunk in enumerate(chunk_text(doc["content"])):
            chunks.append(
                {
                    "id": f"{doc['path']}:{i}",
                    "title": doc["name"],
                    "content": chunk,
                    "source": doc["path"],
                    "doc_name": doc["name"],
                }
            )

    print(f"  Creating {len(chunks)} chunks...")

    if output_path.exists():
        output_path.unlink()

    conn = duckdb.connect(str(output_path))
    conn.execute("INSTALL vss")
    conn.execute("LOAD vss")
    conn.execute("SET hnsw_enable_experimental_persistence = true")
    conn.execute(f"""
        CREATE TABLE docs (
            id VARCHAR,
            title VARCHAR,
            content VARCHAR,
            source VARCHAR,
            doc_name VARCHAR,
            embedding FLOAT[{embedder.embedding_dim}]
        )
    """)

    print("  Generating embeddings...")
    for batch_start in range(0, len(chunks), batch_size):
        batch_end = min(batch_start + batch_size, len(chunks))
        batch_chunks = chunks[batch_start:batch_end]
        batch_texts = [c["content"] for c in batch_chunks]
        embeddings = embedder.embed_batch(batch_texts)

        for chunk, emb in zip(batch_chunks, embeddings, strict=True):
            emb_str = "[" + ",".join(str(x) for x in emb) + "]"
            conn.execute(
                f"""
                INSERT INTO docs VALUES (?, ?, ?, ?, ?, {emb_str}::FLOAT[{embedder.embedding_dim}])
            """,
                [
                    chunk["id"],
                    chunk["title"],
                    chunk["content"],
                    chunk["source"],
                    chunk["doc_name"],
                ],
            )

        print(f"    {batch_end}/{len(chunks)} chunks")

    print("  Creating HNSW index...")
    conn.execute(
        "CREATE INDEX docs_idx ON docs USING HNSW (embedding) WITH (metric = 'cosine')"
    )
    conn.close()

    file_size = output_path.stat().st_size
    return {
        "docs": len(docs),
        "chunks": len(chunks),
        "file_size_mb": file_size / 1024 / 1024,
    }


def reindex_library(
    library_id: str, commit_sha: str, output_dir: Path, embedder: Embedder
) -> dict:
    config = load_library_config(library_id)
    doc_source = config.doc_source
    filters = config.filters

    repo = doc_source.repo
    ref = doc_source.ref

    with tempfile.TemporaryDirectory() as tmpdir:
        clone_base = Path(tmpdir)

        clone_dir = clone_base / repo.replace("/", "_")
        print(f"  Cloning {repo}...")
        if ref:
            print(f"    ref: {ref}")
        clone_repo(repo, clone_dir, ref)

        docs = collect_docs(clone_dir, doc_source, filters)
        print(f"    Collected {len(docs)} docs")

        index_name = library_id.strip("/").replace("/", "_")
        index_path = output_dir / f"{index_name}.duckdb"

        stats = create_index(docs, index_path, embedder)

        return {
            "library_id": library_id,
            "commit_sha": commit_sha,
            "chunks": stats["chunks"],
            "index_size_mb": stats["file_size_mb"],
            "index_path": str(index_path),
            "index_filename": index_path.name,
        }


def main():
    parser = argparse.ArgumentParser(description="Reindex changed libraries")
    parser.add_argument("--update-info", required=True, help="update_info.json path")
    parser.add_argument(
        "--output-dir", "-o", default="./indexes", help="Output directory"
    )
    parser.add_argument(
        "--continue-on-error", action="store_true", help="Continue on library errors"
    )
    args = parser.parse_args()

    with open(args.update_info) as f:
        update_info = json.load(f)

    changed = update_info.get("changed", [])
    if not changed:
        print("No libraries to reindex")
        return 0

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    embedder = Embedder()
    print(f"Embedder ready (dim={embedder.embedding_dim})")

    results = []
    failed = []

    for entry in changed:
        library_id = entry["id"]
        commit_sha = entry["commit_sha"]

        index_name = library_id.strip("/").replace("/", "_")
        index_path = output_dir / f"{index_name}.duckdb"

        if index_path.exists():
            print(f"\nSkipping {library_id} (index exists from cache)")
            conn = duckdb.connect(str(index_path))
            result = conn.execute("SELECT COUNT(*) FROM docs").fetchone()
            chunks = result[0] if result else 0
            conn.close()
            size_mb = index_path.stat().st_size / 1024 / 1024
            results.append(
                {
                    "library_id": library_id,
                    "success": True,
                    "commit_sha": commit_sha,
                    "chunks": chunks,
                    "index_size_mb": round(size_mb, 2),
                    "error": None,
                    "index_filename": index_path.name,
                }
            )
            continue

        print(f"\nIndexing {library_id}...")
        try:
            meta = reindex_library(library_id, commit_sha, output_dir, embedder)
            meta["success"] = True
            meta["error"] = None
            results.append(meta)
            print(f"  Done: {meta['chunks']} chunks, {meta['index_size_mb']:.2f} MB")
        except Exception as e:
            print(f"  ERROR: {e}")
            failed.append(library_id)
            results.append(
                {
                    "library_id": library_id,
                    "success": False,
                    "commit_sha": commit_sha,
                    "error": str(e),
                    "index_filename": None,
                }
            )
            if not args.continue_on_error:
                raise

    results_path = output_dir / "index_results.json"
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nResults saved: {results_path}")

    if failed:
        print(f"Failed libraries: {failed}")
        if not args.continue_on_error:
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
