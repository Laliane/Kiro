"""
Admin endpoints for LLM Consultant Advisor.

Routes:
  POST /admin/knowledge-base/upload  — upload a CSV file and load it into ChromaDB
  GET  /admin/knowledge-base/status  — return KB status (record count, schema, readiness)
"""

from __future__ import annotations

import logging
import tempfile
import os
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse

from app.database import list_records
from app.dependencies import get_current_consultant
from app.services.auth_service import ConsultantIdentity
from app.services.csv_preprocessor import CSVPreprocessor, PreprocessingResult, get_kb_schema

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# POST /admin/knowledge-base/upload
# ---------------------------------------------------------------------------


@router.post(
    "/knowledge-base/upload",
    summary="Upload a CSV file to populate the Knowledge Base",
    status_code=status.HTTP_200_OK,
)
async def upload_knowledge_base(
    file: UploadFile,
    _consultant: ConsultantIdentity = Depends(get_current_consultant),
) -> dict[str, Any]:
    """
    Receive a CSV file via multipart/form-data, save it temporarily,
    run CSVPreprocessor.load() and return the PreprocessingResult.

    Requirements: 5.1, 5.7
    """
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV files are accepted.",
        )

    # Save the uploaded file to a temporary location
    try:
        contents = await file.read()
    except Exception as exc:
        logger.error("Failed to read uploaded file: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read uploaded file: {exc}",
        ) from exc

    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=".csv", mode="wb"
        ) as tmp_file:
            tmp_file.write(contents)
            tmp_path = tmp_file.name

        preprocessor = CSVPreprocessor()
        result: PreprocessingResult = preprocessor.load(tmp_path)

    except Exception as exc:
        logger.error("CSV preprocessing failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"CSV preprocessing failed: {exc}",
        ) from exc
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    return {
        "processed_count": result.processed_count,
        "skipped_count": result.skipped_count,
        "updated_count": result.updated_count,
        "error_log": result.error_log,
    }


# ---------------------------------------------------------------------------
# GET /admin/knowledge-base/status
# ---------------------------------------------------------------------------


@router.get(
    "/knowledge-base/status",
    summary="Return the current Knowledge Base status",
    status_code=status.HTTP_200_OK,
)
def get_knowledge_base_status(
    _consultant: ConsultantIdentity = Depends(get_current_consultant),
) -> dict[str, Any]:
    """
    Return KB status:
    - total_records: number of records stored in ChromaDB
    - schema: detected KnowledgeBaseSchema (or null if KB was never loaded)
    - ready: True when total_records > 0 and schema is available

    Requirements: 5.1, 5.7
    """
    try:
        records = list_records()
        total_records = len(records)
    except Exception as exc:
        logger.error("Failed to list records from ChromaDB: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve KB records: {exc}",
        ) from exc

    schema = get_kb_schema()
    schema_dict = schema.model_dump() if schema is not None else None
    ready = total_records > 0 and schema is not None

    return {
        "total_records": total_records,
        "schema": schema_dict,
        "ready": ready,
    }
