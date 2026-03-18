"""
Persistence layer for LLM Consultant Advisor.

- ChromaDB: stores Record embeddings and metadata (persistent on disk)
- In-memory dicts: stores Session and ChatMessage objects (singletons)

Environment variables:
  CHROMA_PATH  Path for ChromaDB persistent storage (default: ./chroma_data)
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import chromadb
from chromadb import Collection

from app.models import ChatMessage, Record, Session

# ---------------------------------------------------------------------------
# ChromaDB initialisation
# ---------------------------------------------------------------------------

_CHROMA_PATH = os.environ.get("CHROMA_PATH", "./chroma_data")
_COLLECTION_NAME = "records"

_chroma_client: chromadb.PersistentClient | None = None
_records_collection: Collection | None = None


def get_chroma_client() -> chromadb.PersistentClient:
    """Return (or lazily create) the singleton ChromaDB persistent client."""
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path=_CHROMA_PATH)
    return _chroma_client


def get_records_collection() -> Collection:
    """Return (or lazily create) the 'records' collection."""
    global _records_collection
    if _records_collection is None:
        client = get_chroma_client()
        _records_collection = client.get_or_create_collection(
            name=_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
    return _records_collection


# ---------------------------------------------------------------------------
# In-memory stores for Session and ChatMessage
# ---------------------------------------------------------------------------

# { session_id: Session }
sessions_store: dict[str, Session] = {}

# { session_id: list[ChatMessage] }
messages_store: dict[str, list[ChatMessage]] = {}


# ---------------------------------------------------------------------------
# Record CRUD — ChromaDB
# ---------------------------------------------------------------------------


def _record_to_chroma(record: Record) -> dict[str, Any]:
    """Convert a Record's attributes to a flat ChromaDB metadata dict."""
    metadata: dict[str, Any] = {
        "source_row_hash": record.source_row_hash,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
    }
    # Flatten attributes into metadata (all values must be str/int/float/bool)
    for key, value in record.attributes.items():
        if isinstance(value, (str, int, float, bool)):
            metadata[f"attr_{key}"] = value
        else:
            metadata[f"attr_{key}"] = str(value)
    return metadata


def _chroma_to_record(
    record_id: str,
    embedding: list[float],
    metadata: dict[str, Any],
) -> Record:
    """Reconstruct a Record from ChromaDB data."""
    attributes: dict[str, Any] = {}
    source_row_hash = metadata.get("source_row_hash", "")
    created_at = datetime.fromisoformat(metadata.get("created_at", datetime.utcnow().isoformat()))
    updated_at = datetime.fromisoformat(metadata.get("updated_at", datetime.utcnow().isoformat()))

    for key, value in metadata.items():
        if key.startswith("attr_"):
            attributes[key[5:]] = value  # strip "attr_" prefix

    return Record(
        id=record_id,
        source_row_hash=source_row_hash,
        attributes=attributes,
        embedding=embedding,
        created_at=created_at,
        updated_at=updated_at,
    )


def add_record(record: Record) -> None:
    """Add a Record to ChromaDB. Raises if the id already exists."""
    collection = get_records_collection()
    collection.add(
        ids=[record.id],
        embeddings=[record.embedding],
        metadatas=[_record_to_chroma(record)],
    )


def get_record(record_id: str) -> Record | None:
    """Retrieve a Record by id. Returns None if not found."""
    collection = get_records_collection()
    result = collection.get(
        ids=[record_id],
        include=["embeddings", "metadatas"],
    )
    if not result["ids"]:
        return None
    return _chroma_to_record(
        record_id=result["ids"][0],
        embedding=result["embeddings"][0],
        metadata=result["metadatas"][0],
    )


def update_record(record: Record) -> None:
    """Update an existing Record in ChromaDB (upsert semantics)."""
    collection = get_records_collection()
    collection.update(
        ids=[record.id],
        embeddings=[record.embedding],
        metadatas=[_record_to_chroma(record)],
    )


def delete_record(record_id: str) -> None:
    """Delete a Record from ChromaDB by id."""
    collection = get_records_collection()
    collection.delete(ids=[record_id])


def list_records() -> list[Record]:
    """Return all Records stored in ChromaDB."""
    collection = get_records_collection()
    result = collection.get(include=["embeddings", "metadatas"])
    records: list[Record] = []
    for rid, emb, meta in zip(result["ids"], result["embeddings"], result["metadatas"]):
        records.append(_chroma_to_record(record_id=rid, embedding=emb, metadata=meta))
    return records
