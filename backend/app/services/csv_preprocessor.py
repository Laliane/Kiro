"""
CSV Preprocessor for LLM Consultant Advisor.

Reads, cleans, normalises and vectorises records from a CSV file into ChromaDB.
Supports full load and incremental reload (only new/modified rows are processed).

Responsibilities:
- Deduplication by SHA-256 hash of each row
- Missing-value handling (fill with empty string)
- Whitespace normalisation and lowercase column names
- Embedding generation via the shared embeddings module
- Storage in ChromaDB via database.py CRUD helpers
- Auto-detection of KnowledgeBaseSchema from CSV columns
- Incremental reload: skip unchanged rows, update modified ones, add new ones
- Invalid-record logging (missing required fields) without aborting the batch
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from app.database import add_record, list_records, update_record
from app.models import KnowledgeBaseSchema, Record
from app.services.embeddings import generate_embedding

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Global KB schema — set after the first successful load
# ---------------------------------------------------------------------------

_kb_schema: KnowledgeBaseSchema | None = None


def get_kb_schema() -> KnowledgeBaseSchema | None:
    """Return the KnowledgeBaseSchema detected from the last CSV load, or None."""
    return _kb_schema


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


@dataclass
class PreprocessingResult:
    processed_count: int = 0
    skipped_count: int = 0
    updated_count: int = 0
    error_log: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _row_hash(row_dict: dict[str, Any]) -> str:
    """Compute a deterministic SHA-256 hash for a row dictionary."""
    return hashlib.sha256(
        json.dumps(row_dict, sort_keys=True).encode()
    ).hexdigest()


def _detect_schema(df: pd.DataFrame) -> KnowledgeBaseSchema:
    """
    Auto-detect KnowledgeBaseSchema from a DataFrame.

    - required_fields: columns where fewer than 50 % of values are missing
    - optional_fields: the rest
    - text_fields: all string-typed columns (used for embedding)
    - id_field: first column named 'id' (case-insensitive), else the first column
    """
    columns = list(df.columns)
    missing_ratio = df.isnull().mean()

    required_fields = [c for c in columns if missing_ratio[c] < 0.5]
    optional_fields = [c for c in columns if missing_ratio[c] >= 0.5]

    # Text fields: columns whose dtype is object (string)
    text_fields = [c for c in columns if df[c].dtype == object]

    # id_field: prefer a column literally named 'id', else use the first column
    id_candidates = [c for c in columns if c.lower() == "id"]
    id_field = id_candidates[0] if id_candidates else columns[0]

    return KnowledgeBaseSchema(
        required_fields=required_fields,
        optional_fields=optional_fields,
        text_fields=text_fields,
        id_field=id_field,
    )


def _build_embedding_text(row_dict: dict[str, Any], text_fields: list[str]) -> str:
    """
    Combine text_fields into a single enriched string for embedding generation.

    Format: "field1: value1 | field2: value2 | ..."
    """
    parts = [
        f"{f}: {row_dict.get(f, '')}"
        for f in text_fields
        if row_dict.get(f, "") != ""
    ]
    return " | ".join(parts) if parts else " ".join(str(v) for v in row_dict.values())


def _validate_required_fields(
    row_dict: dict[str, Any],
    required_fields: list[str],
    row_index: int,
) -> list[str]:
    """Return a list of error messages for missing required fields (empty list = valid)."""
    errors: list[str] = []
    for f in required_fields:
        val = row_dict.get(f, "")
        if val == "" or val is None:
            errors.append(
                f"Row {row_index}: missing required field '{f}'"
            )
    return errors


def _read_and_normalise(file_path: str) -> pd.DataFrame:
    """
    Read a CSV file and apply basic normalisation:
    - Lowercase column names
    - Strip leading/trailing whitespace from string values
    - Fill NaN with empty string
    """
    df = pd.read_csv(file_path)
    df.columns = [c.strip().lower() for c in df.columns]
    # Strip whitespace from string columns
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].str.strip()
    df = df.fillna("")
    return df


# ---------------------------------------------------------------------------
# CSVPreprocessor
# ---------------------------------------------------------------------------


class CSVPreprocessor:
    """
    Reads, cleans and vectorises records from a CSV file into ChromaDB.

    Usage:
        preprocessor = CSVPreprocessor()
        result = preprocessor.load("data/knowledge_base.csv")
        result = preprocessor.reload("data/knowledge_base.csv")  # incremental
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, file_path: str) -> PreprocessingResult:
        """
        Full load: read the CSV, deduplicate, generate embeddings and store in ChromaDB.

        Steps:
        1. Read and normalise the CSV.
        2. Detect and store the KnowledgeBaseSchema.
        3. Deduplicate rows by SHA-256 hash (skip duplicate rows within the file).
        4. Validate required fields; log invalid rows and skip them.
        5. Generate embedding for each valid row.
        6. Store each Record in ChromaDB via add_record().

        Returns a PreprocessingResult with counts and error_log.
        """
        global _kb_schema

        result = PreprocessingResult()

        try:
            df = _read_and_normalise(file_path)
        except Exception as exc:
            msg = f"Failed to read CSV '{file_path}': {exc}"
            logger.error(msg)
            result.error_log.append(msg)
            return result

        if df.empty:
            logger.warning("CSV file '%s' is empty — nothing to load.", file_path)
            return result

        schema = _detect_schema(df)
        _kb_schema = schema
        logger.info(
            "KB schema detected | required=%s optional=%s text=%s id_field=%s",
            schema.required_fields,
            schema.optional_fields,
            schema.text_fields,
            schema.id_field,
        )

        seen_hashes: set[str] = set()

        for idx, row in df.iterrows():
            row_dict = row.to_dict()
            row_hash = _row_hash(row_dict)

            # Intra-file deduplication
            if row_hash in seen_hashes:
                result.skipped_count += 1
                logger.debug("Row %s skipped (duplicate within file, hash=%s)", idx, row_hash)
                continue
            seen_hashes.add(row_hash)

            # Validate required fields
            errors = _validate_required_fields(row_dict, schema.required_fields, int(str(idx)))
            if errors:
                for err in errors:
                    result.error_log.append(err)
                    logger.warning(err)
                result.skipped_count += 1
                continue

            # Generate embedding
            try:
                embedding_text = _build_embedding_text(row_dict, schema.text_fields)
                embedding = generate_embedding(embedding_text)
            except Exception as exc:
                msg = f"Row {idx}: embedding generation failed — {exc}"
                result.error_log.append(msg)
                logger.error(msg)
                result.skipped_count += 1
                continue

            # Build and store Record
            now = datetime.now(tz=timezone.utc)
            record = Record(
                id=str(uuid.uuid4()),
                source_row_hash=row_hash,
                attributes=row_dict,
                embedding=embedding,
                created_at=now,
                updated_at=now,
            )
            try:
                add_record(record)
                result.processed_count += 1
            except Exception as exc:
                msg = f"Row {idx}: failed to store record — {exc}"
                result.error_log.append(msg)
                logger.error(msg)
                result.skipped_count += 1

        logger.info(
            "CSV load complete | file=%s processed=%d skipped=%d errors=%d",
            file_path,
            result.processed_count,
            result.skipped_count,
            len(result.error_log),
        )
        return result

    def reload(self, file_path: str) -> PreprocessingResult:
        """
        Incremental reload: process only new or modified rows.

        Steps:
        1. Read and normalise the CSV.
        2. Detect and update the KnowledgeBaseSchema.
        3. Build a map of existing records: {source_row_hash -> Record}.
        4. For each row in the CSV:
           - If hash exists and is unchanged → skip (skipped_count++).
           - If hash is new → generate embedding and add_record() (processed_count++).
           - If hash is modified (same id_field value, different hash) → generate
             embedding and update_record() (updated_count++).
        5. Log invalid rows and continue.

        Returns a PreprocessingResult with counts and error_log.
        """
        global _kb_schema

        result = PreprocessingResult()

        try:
            df = _read_and_normalise(file_path)
        except Exception as exc:
            msg = f"Failed to read CSV '{file_path}': {exc}"
            logger.error(msg)
            result.error_log.append(msg)
            return result

        if df.empty:
            logger.warning("CSV file '%s' is empty — nothing to reload.", file_path)
            return result

        schema = _detect_schema(df)
        _kb_schema = schema

        # Build lookup maps from existing ChromaDB records
        existing_records = list_records()
        # hash → Record (for fast dedup check)
        existing_by_hash: dict[str, Record] = {r.source_row_hash: r for r in existing_records}
        # id_field value → Record (to detect modifications)
        id_field = schema.id_field
        existing_by_id_value: dict[str, Record] = {}
        for r in existing_records:
            id_val = str(r.attributes.get(id_field, ""))
            if id_val:
                existing_by_id_value[id_val] = r

        seen_hashes: set[str] = set()

        for idx, row in df.iterrows():
            row_dict = row.to_dict()
            row_hash = _row_hash(row_dict)

            # Intra-file deduplication
            if row_hash in seen_hashes:
                result.skipped_count += 1
                continue
            seen_hashes.add(row_hash)

            # Validate required fields
            errors = _validate_required_fields(row_dict, schema.required_fields, int(str(idx)))
            if errors:
                for err in errors:
                    result.error_log.append(err)
                    logger.warning(err)
                result.skipped_count += 1
                continue

            # Check if this exact hash already exists → skip
            if row_hash in existing_by_hash:
                result.skipped_count += 1
                logger.debug("Row %s unchanged (hash=%s) — skipped.", idx, row_hash)
                continue

            # Generate embedding for new/modified row
            try:
                embedding_text = _build_embedding_text(row_dict, schema.text_fields)
                embedding = generate_embedding(embedding_text)
            except Exception as exc:
                msg = f"Row {idx}: embedding generation failed — {exc}"
                result.error_log.append(msg)
                logger.error(msg)
                result.skipped_count += 1
                continue

            now = datetime.now(tz=timezone.utc)
            id_val = str(row_dict.get(id_field, ""))

            if id_val and id_val in existing_by_id_value:
                # Modified row: update existing record
                existing = existing_by_id_value[id_val]
                updated = Record(
                    id=existing.id,
                    source_row_hash=row_hash,
                    attributes=row_dict,
                    embedding=embedding,
                    created_at=existing.created_at,
                    updated_at=now,
                )
                try:
                    update_record(updated)
                    result.updated_count += 1
                    logger.debug("Row %s updated (id_val=%s).", idx, id_val)
                except Exception as exc:
                    msg = f"Row {idx}: failed to update record — {exc}"
                    result.error_log.append(msg)
                    logger.error(msg)
                    result.skipped_count += 1
            else:
                # New row: add record
                record = Record(
                    id=str(uuid.uuid4()),
                    source_row_hash=row_hash,
                    attributes=row_dict,
                    embedding=embedding,
                    created_at=now,
                    updated_at=now,
                )
                try:
                    add_record(record)
                    result.processed_count += 1
                    logger.debug("Row %s added (hash=%s).", idx, row_hash)
                except Exception as exc:
                    msg = f"Row {idx}: failed to store record — {exc}"
                    result.error_log.append(msg)
                    logger.error(msg)
                    result.skipped_count += 1

        logger.info(
            "CSV reload complete | file=%s processed=%d updated=%d skipped=%d errors=%d",
            file_path,
            result.processed_count,
            result.updated_count,
            result.skipped_count,
            len(result.error_log),
        )
        return result
