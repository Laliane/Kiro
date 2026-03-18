"""
Session and messaging endpoints for LLM Consultant Advisor.

POST   /sessions                    — create a new session for the authenticated consultant
DELETE /sessions/{session_id}       — close a session
POST   /sessions/{session_id}/messages — send a message and get LLM response
GET    /sessions/{session_id}/messages — retrieve message history
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel

from app.dependencies import get_current_consultant
from app.models import AnalysisReport, ChatMessage, KnowledgeBaseSchema, Session, SimilarityResult
from app.services.auth_service import ConsultantIdentity
from app.services.chat_orchestrator import ChatOrchestrator
from app.services.report_generator import ReportGenerator

router = APIRouter(prefix="/sessions", tags=["sessions"])

_orchestrator = ChatOrchestrator()


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class SendMessageRequest(BaseModel):
    message: str


class SubmitQueryItemRequest(BaseModel):
    description: str
    schema_: KnowledgeBaseSchema | None = None  # optional; uses default schema if omitted


class SearchRequest(BaseModel):
    top_n: int = 10
    threshold: float = 0.5


class ExportRequest(BaseModel):
    format: str = "json"  # "json" or "pdf"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=Session, status_code=status.HTTP_201_CREATED)
def create_session(
    current: ConsultantIdentity = Depends(get_current_consultant),
) -> Session:
    """Create a new active session for the authenticated consultant."""
    return _orchestrator.create_session(current.consultant_id)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def close_session(
    session_id: str,
    current: ConsultantIdentity = Depends(get_current_consultant),
) -> None:
    """Close (end) an existing session."""
    _orchestrator.close_session(session_id)


@router.post(
    "/{session_id}/messages",
    response_model=ChatMessage,
    status_code=status.HTTP_200_OK,
)
def send_message(
    session_id: str,
    body: SendMessageRequest,
    current: ConsultantIdentity = Depends(get_current_consultant),
) -> ChatMessage:
    """Send a user message and receive the LLM assistant reply."""
    try:
        return _orchestrator.send_message(session_id, body.message)
    except ValueError as exc:
        msg = str(exc)
        # SESSION_EXPIRED / not found → 404; other ValueErrors → 400
        if "not found" in msg or "SESSION_EXPIRED" in msg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=msg,
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg,
        ) from exc


@router.get(
    "/{session_id}/messages",
    response_model=list[ChatMessage],
    status_code=status.HTTP_200_OK,
)
def get_messages(
    session_id: str,
    current: ConsultantIdentity = Depends(get_current_consultant),
) -> list[ChatMessage]:
    """Return the full message history for a session in chronological order."""
    try:
        return _orchestrator.get_history(session_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    "/{session_id}/query-item",
    response_model=ChatMessage,
    status_code=status.HTTP_200_OK,
)
def submit_query_item(
    session_id: str,
    body: SubmitQueryItemRequest,
    current: ConsultantIdentity = Depends(get_current_consultant),
) -> ChatMessage:
    """
    Submit a natural language description as a Query_Item.

    The Attribute Extractor interprets the description and returns either:
    - A message asking for more information (metadata.type = "needs_more_info")
    - A confirmation message with extracted attributes (metadata.type = "attribute_confirmation")
    """
    try:
        return _orchestrator.submit_query_item(
            session_id, body.description, body.schema_
        )
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg or "SESSION_EXPIRED" in msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from exc


@router.post(
    "/{session_id}/query-item/confirm",
    response_model=ChatMessage,
    status_code=status.HTTP_200_OK,
)
def confirm_query_item(
    session_id: str,
    current: ConsultantIdentity = Depends(get_current_consultant),
) -> ChatMessage:
    """
    Confirm the pending Query_Item for the session.

    Sets QueryItem.confirmed = True and generates the embedding via the
    embedding API. The item is then ready for similarity search.
    """
    try:
        return _orchestrator.confirm_query_item(session_id)
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg or "SESSION_EXPIRED" in msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from exc


@router.post(
    "/{session_id}/search",
    response_model=list[SimilarityResult],
    status_code=status.HTTP_200_OK,
)
def run_search(
    session_id: str,
    body: SearchRequest = SearchRequest(),
    current: ConsultantIdentity = Depends(get_current_consultant),
) -> list[SimilarityResult]:
    """
    Trigger similarity search for the confirmed Query_Item of the session.

    Accepts optional `top_n` (default 10) and `threshold` (default 0.5) in the request body.
    Returns the list of SimilarityResult sorted by similarity_score descending.
    If the knowledge base is empty or no results exceed the threshold, returns an empty list
    with a descriptive message in the response headers.
    """
    try:
        return _orchestrator.run_similarity_search(
            session_id, top_n=body.top_n, threshold=body.threshold
        )
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg or "SESSION_EXPIRED" in msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from exc
        if "KB_001" in msg:
            # KB empty — return empty list with descriptive detail instead of 500
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=msg,
            ) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from exc


@router.get(
    "/{session_id}/results",
    response_model=list[SimilarityResult],
    status_code=status.HTTP_200_OK,
)
def get_results(
    session_id: str,
    current: ConsultantIdentity = Depends(get_current_consultant),
) -> list[SimilarityResult]:
    """
    Return the stored similarity results for a session.

    Results are populated by POST /sessions/{id}/search.
    Returns an empty list if no search has been performed yet.
    """
    from app.database import sessions_store
    from app.models import ErrorCode

    session = sessions_store.get(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{ErrorCode.SESSION_EXPIRED}: Session '{session_id}' not found.",
        )
    return session.similarity_results


_report_generator = ReportGenerator()


@router.post(
    "/{session_id}/report",
    response_model=AnalysisReport,
    status_code=status.HTTP_200_OK,
)
def generate_report(
    session_id: str,
    current: ConsultantIdentity = Depends(get_current_consultant),
) -> AnalysisReport:
    """
    Generate an AnalysisReport for the session.

    Calls the LLM to produce summary, patterns, differences, recommendations
    and explainability from the stored similarity results.
    """
    try:
        report, _ = _report_generator.generate(session_id, format="json")
        return report
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg or "SESSION_EXPIRED" in msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from exc


@router.post(
    "/{session_id}/export",
    status_code=status.HTTP_200_OK,
)
def export_report(
    session_id: str,
    body: ExportRequest = ExportRequest(),
    current: ConsultantIdentity = Depends(get_current_consultant),
) -> Response:
    """
    Export the AnalysisReport as JSON or PDF for download.

    Returns the file as a binary response with appropriate Content-Type and
    Content-Disposition headers.
    """
    fmt = body.format.lower()
    if fmt not in ("json", "pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Formato inválido. Use 'json' ou 'pdf'.",
        )
    try:
        _, data = _report_generator.generate(session_id, format=fmt)
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg or "SESSION_EXPIRED" in msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from exc

    if fmt == "pdf":
        media_type = "application/pdf"
        filename = f"relatorio_{session_id}.pdf"
    else:
        media_type = "application/json"
        filename = f"relatorio_{session_id}.json"

    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


_selection_manager = None  # lazy import to avoid circular deps


def _get_selection_manager():
    from app.services.selection_manager import SelectionManager
    return SelectionManager()


class UpdateSelectionsRequest(BaseModel):
    add_ids: list[str] = []
    remove_ids: list[str] = []


@router.patch(
    "/{session_id}/selections",
    status_code=status.HTTP_200_OK,
)
def update_selections(
    session_id: str,
    body: UpdateSelectionsRequest,
    current: ConsultantIdentity = Depends(get_current_consultant),
) -> dict:
    """
    Add or remove record IDs from the session's selection without reloading the list.

    Returns the updated list of selected_record_ids and the current count.
    """
    try:
        selected = _get_selection_manager().update_selections(
            session_id, add_ids=body.add_ids, remove_ids=body.remove_ids
        )
        return {"selected_record_ids": selected, "count": len(selected)}
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg or "SESSION_EXPIRED" in msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from exc


@router.post(
    "/{session_id}/send-external",
    status_code=status.HTTP_200_OK,
)
def send_external(
    session_id: str,
    current: ConsultantIdentity = Depends(get_current_consultant),
) -> dict:
    """
    Send the selected records to the configured external API.

    Returns 400 if no records are selected.
    Returns the SendResult with success flag, status_code, and message.
    """
    from app.database import sessions_store
    from app.models import ErrorCode
    from app.services.external_api_client import ExternalAPIClient, get_external_api_config

    session = sessions_store.get(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{ErrorCode.SESSION_EXPIRED}: Session '{session_id}' not found.",
        )

    if not session.selected_record_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nenhum record selecionado. Selecione ao menos um record antes de enviar.",
        )

    config = get_external_api_config()
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="API externa não configurada. Defina EXTERNAL_API_URL nas variáveis de ambiente.",
        )

    # Filter similarity results to only selected records
    selected_set = set(session.selected_record_ids)
    selected_results = [r for r in session.similarity_results if r.record.id in selected_set]

    client = ExternalAPIClient()
    result = client.send(selected_results, config, consultant_id=current.consultant_id)

    return {
        "success": result.success,
        "status_code": result.status_code,
        "message": result.message,
        "sent_count": result.sent_count,
    }
