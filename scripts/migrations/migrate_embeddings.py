#!/usr/bin/env python3
"""
Embedding model migration script for Emily.

Re-embeds all Qdrant collections when switching from one embedding model
to another (e.g. BGE-M3 1024-dim -> nomic-embed-text 768-dim).

Usage:
    python scripts/migrations/migrate_embeddings.py \\
        --new-model nomic-embed-text \\
        --new-dim 768

    python scripts/migrations/migrate_embeddings.py --dry-run

The script:
 1. Connects to Qdrant and reads all payloads from each collection.
 2. In --dry-run mode, reports counts and exits.
 3. Re-embeds every stored text using the new model via Ollama.
 4. Recreates each collection with the new vector dimension.
 5. Re-inserts all points with fresh embeddings.

Memory and persona data (SQLite, JSON, networkx) are NOT affected.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

_ALL_COLLECTIONS = [
    "emily_semantic",
    "emily_entities",
    "emily_facts",
    "emily_events",
    "emily_knowledge",
]

_EMBED_BATCH_SIZE = 32


async def _get_all_points(
    client: Any,
    collection: str,
) -> list[dict[str, Any]]:
    """Scroll all points from *collection*, returning payload + id pairs."""
    points: list[dict[str, Any]] = []
    offset = None
    while True:
        result = await client.scroll(
            collection_name=collection,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        batch, next_offset = result
        for pt in batch:
            points.append(
                {
                    "id": pt.id,
                    "payload": pt.payload,
                }
            )
        if next_offset is None:
            break
        offset = next_offset
    return points


async def _embed_texts(
    ollama_url: str,
    model: str,
    texts: list[str],
) -> list[list[float]]:
    """Embed a batch of texts via the Ollama REST API."""
    import httpx

    vectors: list[list[float]] = []
    async with httpx.AsyncClient(timeout=120) as http:
        for i in range(0, len(texts), _EMBED_BATCH_SIZE):
            chunk = texts[i : i + _EMBED_BATCH_SIZE]
            resp = await http.post(
                f"{ollama_url}/api/embed",
                json={"model": model, "input": chunk},
            )
            resp.raise_for_status()
            data = resp.json()
            vectors.extend(data["embeddings"])
    return vectors


async def run(
    new_model: str,
    new_dim: int,
    qdrant_url: str,
    ollama_url: str,
    dry_run: bool,
) -> None:
    """Execute the migration."""
    from qdrant_client import AsyncQdrantClient
    from qdrant_client.models import Distance, PointStruct, VectorParams

    client = AsyncQdrantClient(url=qdrant_url)

    collections_resp = await client.get_collections()
    existing = {c.name for c in collections_resp.collections}

    for coll_name in _ALL_COLLECTIONS:
        if coll_name not in existing:
            print(f"  [{coll_name}] does not exist — skipping")
            continue

        points = await _get_all_points(client, coll_name)
        texts = [
            p["payload"].get("content", "") or p["payload"].get("description", "") for p in points
        ]
        non_empty = sum(1 for t in texts if t.strip())

        print(f"  [{coll_name}] {len(points)} points, {non_empty} with text content")

        if dry_run:
            continue

        if not non_empty:
            print("    -> no text content to re-embed, recreating empty collection")
            await client.delete_collection(coll_name)
            await client.create_collection(
                collection_name=coll_name,
                vectors_config=VectorParams(size=new_dim, distance=Distance.COSINE),
            )
            continue

        print(f"    -> embedding {non_empty} texts with {new_model} ...")
        vectors = await _embed_texts(ollama_url, new_model, texts)

        if len(vectors) != len(points):
            print(f"    ERROR: got {len(vectors)} vectors for {len(points)} points")
            sys.exit(1)

        print(f"    -> recreating collection with dim={new_dim} ...")
        await client.delete_collection(coll_name)
        await client.create_collection(
            collection_name=coll_name,
            vectors_config=VectorParams(size=new_dim, distance=Distance.COSINE),
        )

        new_points = []
        for pt, vec in zip(points, vectors, strict=False):
            new_points.append(
                PointStruct(
                    id=pt["id"],
                    vector=vec,
                    payload=pt["payload"],
                )
            )

        for i in range(0, len(new_points), 128):
            batch = new_points[i : i + 128]
            await client.upsert(collection_name=coll_name, points=batch)
        print(f"    -> inserted {len(new_points)} points")

    await client.close()
    if dry_run:
        print("\n  Dry run complete — no changes made.")
    else:
        print("\n  Migration complete.")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Re-embed all Qdrant collections for a new embedding model.",
    )
    parser.add_argument(
        "--new-model",
        required=True,
        help="Ollama model name for the new embeddings (e.g. nomic-embed-text).",
    )
    parser.add_argument(
        "--new-dim",
        type=int,
        required=True,
        help="Embedding dimension of the new model (e.g. 768).",
    )
    parser.add_argument(
        "--qdrant-url",
        default="http://localhost:6333",
        help="Qdrant server URL (default: http://localhost:6333).",
    )
    parser.add_argument(
        "--ollama-url",
        default="http://localhost:11434",
        help="Ollama server URL (default: http://localhost:11434).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without modifying anything.",
    )
    args = parser.parse_args()

    print(f"Embedding migration: {args.new_model} (dim={args.new_dim})")
    print(f"  Qdrant: {args.qdrant_url}")
    print(f"  Ollama: {args.ollama_url}")
    if args.dry_run:
        print("  Mode: DRY RUN\n")
    else:
        print("  Mode: LIVE\n")

    asyncio.run(
        run(
            new_model=args.new_model,
            new_dim=args.new_dim,
            qdrant_url=args.qdrant_url,
            ollama_url=args.ollama_url,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    main()
