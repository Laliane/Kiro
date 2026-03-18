"""
Chat Orchestrator for LLM Consultant Advisor.

Manages session lifecycle and routes messages to the configured LLM provider,
maintaining full conversation history as context.

Environment variables:
  LLM_PROVIDER      "openai" or "anthropic" (default: openai)
  LLM_API_KEY       API key for the selected provider (required)
  LLM_MODEL         Model name (default: gpt-4o-mini for OpenAI, claude-3-haiku-20240307 for Anthropic)
  EMBEDDING_MODEL   Embedding model name (default: text-embedding-3-small)
  OPENAI_API_KEY    OpenAI API key used as fallback for embeddings when provider is Anthropic
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone

from app.database import messages_store, sessions_store
from app.models import ChatMessage, ErrorCode, KnowledgeBaseSchema, QueryItem, Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM provider configuration
# ---------------------------------------------------------------------------

_LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "openai").lower()
_LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
_LLM_MODEL = os.environ.get("LLM_MODEL", "")

_DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-haiku-20240307",
}


def _get_model() -> str:
    return _LLM_MODEL or _DEFAULT_MODELS.get(_LLM_PROVIDER, "gpt-4o-mini")


# ---------------------------------------------------------------------------
# Default Knowledge Base schema (used when no schema is loaded from CSV)
# ---------------------------------------------------------------------------

_DEFAULT_SCHEMA = KnowledgeBaseSchema(
    required_fields=[],
    optional_fields=[],
    text_fields=[],
    id_field="id",
)


# ---------------------------------------------------------------------------
# Internal LLM call helpers
# ---------------------------------------------------------------------------


def _call_openai(messages: list[dict]) -> str:
    """Call OpenAI chat completions API and return the assistant reply."""
    import openai  # lazy import — only required when provider is openai

    client = openai.OpenAI(api_key=_LLM_API_KEY)
    response = client.chat.completions.create(
        model=_get_model(),
        messages=messages,
    )
    return response.choices[0].message.content or ""


def _call_anthropic(messages: list[dict]) -> str:
    """Call Anthropic messages API and return the assistant reply."""
    import anthropic  # lazy import — only required when provider is anthropic

    # Anthropic separates system messages from the conversation turns
    system_parts = [m["content"] for m in messages if m["role"] == "system"]
    conversation = [m for m in messages if m["role"] != "system"]

    client = anthropic.Anthropic(api_key=_LLM_API_KEY)
    kwargs: dict = {
        "model": _get_model(),
        "max_tokens": 4096,
        "messages": conversation,
    }
    if system_parts:
        kwargs["system"] = "\n\n".join(system_parts)

    response = client.messages.create(**kwargs)
    return response.content[0].text if response.content else ""


def _call_llm(history: list[ChatMessage]) -> str:
    """
    Convert ChatMessage history to provider format and call the LLM.

    Raises ValueError with ErrorCode.LLM_UNAVAILABLE if the provider is unknown.
    Propagates provider exceptions to the caller for error handling.
    """
    messages = [{"role": msg.role, "content": msg.content} for msg in history]

    if _LLM_PROVIDER == "openai":
        return _call_openai(messages)
    elif _LLM_PROVIDER == "anthropic":
        return _call_anthropic(messages)
    else:
        raise ValueError(
            f"{ErrorCode.LLM_UNAVAILABLE}: Unknown LLM provider '{_LLM_PROVIDER}'. "
            "Set LLM_PROVIDER to 'openai' or 'anthropic'."
        )


# ---------------------------------------------------------------------------
# Embedding helper
# ---------------------------------------------------------------------------


def _generate_embedding(text: str) -> list[float]:
    """
    Generate an embedding vector for the given text.

    Delegates to the shared embeddings module to avoid duplication.
    """
    from app.services.embeddings import generate_embedding  # shared module

    return generate_embedding(text)


# ---------------------------------------------------------------------------
# ChatOrchestrator
# ---------------------------------------------------------------------------


class ChatOrchestrator:
    """
    Central component that coordinates the conversational flow.

    Maintains session state and message history, and routes messages to the
    configured LLM provider.
    """

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def create_session(self, consultant_id: str) -> Session:
        """
        Create a new active session for the given consultant.

        Returns the created Session and logs the event.
        """
        now = datetime.now(tz=timezone.utc)
        session = Session(
            id=str(uuid.uuid4()),
            consultant_id=consultant_id,
            created_at=now,
            last_activity_at=now,
            status="active",
        )
        sessions_store[session.id] = session
        messages_store[session.id] = []

        logger.info(
            "Session created | session_id=%s consultant_id=%s created_at=%s",
            session.id,
            consultant_id,
            now.isoformat(),
        )
        return session

    def close_session(self, session_id: str) -> None:
        """
        Mark a session as closed.

        Logs the closure with consultant_id, timestamps, and query_items used.
        Silently ignores unknown session IDs.
        """
        session = sessions_store.get(session_id)
        if session is None:
            logger.warning("close_session called for unknown session_id=%s", session_id)
            return

        session.status = "closed"
        now = datetime.now(tz=timezone.utc)

        query_items = []
        if session.query_item is not None:
            query_items.append(session.query_item.id)

        logger.info(
            "Session closed | session_id=%s consultant_id=%s "
            "created_at=%s closed_at=%s query_items=%s",
            session_id,
            session.consultant_id,
            session.created_at.isoformat(),
            now.isoformat(),
            query_items,
        )

    def get_history(self, session_id: str) -> list[ChatMessage]:
        """
        Return the full message history for a session in chronological order.

        Returns an empty list if the session has no messages yet.
        Raises ValueError if the session does not exist.
        """
        if session_id not in sessions_store:
            raise ValueError(
                f"{ErrorCode.SESSION_EXPIRED}: Session '{session_id}' not found."
            )
        return list(messages_store.get(session_id, []))

    # ------------------------------------------------------------------
    # Messaging
    # ------------------------------------------------------------------

    def send_message(self, session_id: str, message: str) -> ChatMessage:
        """
        Send a user message to the LLM and return the assistant's reply.

        Steps:
        1. Validate session exists and is active.
        2. Update last_activity_at.
        3. Append user message to history.
        4. Call LLM with full history as context.
        5. Append assistant reply to history.
        6. Return the assistant ChatMessage.

        Raises ValueError with appropriate ErrorCode if the session is not
        active or does not exist.
        """
        session = sessions_store.get(session_id)

        if session is None:
            raise ValueError(
                f"{ErrorCode.SESSION_EXPIRED}: Session '{session_id}' not found."
            )

        if session.status == "expired":
            raise ValueError(
                f"{ErrorCode.SESSION_EXPIRED}: Session '{session_id}' has expired "
                "due to inactivity. Please start a new session."
            )

        if session.status == "closed":
            raise ValueError(
                f"{ErrorCode.SESSION_EXPIRED}: Session '{session_id}' is closed."
            )

        # Update activity timestamp
        session.last_activity_at = datetime.now(tz=timezone.utc)
        # Append user message
        user_msg = ChatMessage(
            id=str(uuid.uuid4()),
            session_id=session_id,
            role="user",
            content=message,
            timestamp=datetime.now(tz=timezone.utc),
        )
        messages_store[session_id].append(user_msg)

        # Call LLM with full history as context
        try:
            reply_content = _call_llm(messages_store[session_id])
        except Exception as exc:
            logger.error(
                "LLM call failed | session_id=%s error=%s",
                session_id,
                str(exc),
            )
            raise ValueError(
                f"{ErrorCode.LLM_UNAVAILABLE}: The LLM provider is currently unavailable. "
                f"Details: {exc}"
            ) from exc

        # Append assistant reply
        assistant_msg = ChatMessage(
            id=str(uuid.uuid4()),
            session_id=session_id,
            role="assistant",
            content=reply_content,
            timestamp=datetime.now(tz=timezone.utc),
        )
        messages_store[session_id].append(assistant_msg)

        return assistant_msg

    # ------------------------------------------------------------------
    # Query Item flow
    # ------------------------------------------------------------------

    def submit_query_item(
        self,
        session_id: str,
        description: str,
        schema: KnowledgeBaseSchema | None = None,
    ) -> ChatMessage:
        """
        Interpret a natural language description as a Query_Item.

        Steps:
        1. Validate session is active.
        2. Call AttributeExtractor.extract(description, schema).
        3. Create a QueryItem with the extracted attributes.
        4. If needs_more_info=True, return a chat message asking for more details.
        5. If needs_more_info=False, store the QueryItem on the session and return
           a confirmation message (metadata.type = "attribute_confirmation").

        Args:
            session_id:   Active session id.
            description:  Natural language description of the item.
            schema:       Optional KnowledgeBaseSchema; falls back to _DEFAULT_SCHEMA.

        Returns:
            An assistant ChatMessage (either asking for more info or presenting
            extracted attributes for confirmation).
        """
        from app.services.attribute_extractor import AttributeExtractor  # avoid circular import

        session = self._get_active_session(session_id)
        session.last_activity_at = datetime.now(tz=timezone.utc)

        effective_schema = schema or _DEFAULT_SCHEMA

        # Run extraction
        extractor = AttributeExtractor()
        try:
            result = extractor.extract(description, effective_schema)
        except Exception as exc:
            logger.error(
                "AttributeExtractor failed | session_id=%s error=%s", session_id, exc
            )
            raise ValueError(
                f"{ErrorCode.LLM_UNAVAILABLE}: Attribute extraction failed. Details: {exc}"
            ) from exc

        # Build a pending QueryItem (not yet confirmed)
        query_item = QueryItem(
            id=str(uuid.uuid4()),
            session_id=session_id,
            raw_description=description,
            extracted_attributes=result.attributes,
            confirmed=False,
            embedding=None,
        )

        if result.needs_more_info:
            # Ask the consultant for the missing fields — do NOT store the item yet
            missing = ", ".join(result.missing_fields)
            content = (
                f"Para prosseguir com a busca, preciso de mais informações sobre os "
                f"seguintes campos obrigatórios: {missing}. "
                f"Por favor, forneça esses detalhes na sua próxima mensagem."
            )
            msg = ChatMessage(
                id=str(uuid.uuid4()),
                session_id=session_id,
                role="assistant",
                content=content,
                timestamp=datetime.now(tz=timezone.utc),
                metadata={"type": "needs_more_info", "missing_fields": result.missing_fields},
            )
            messages_store[session_id].append(msg)
            return msg

        # Store the pending QueryItem on the session (not confirmed yet)
        session.query_item = query_item

        # Present extracted attributes for confirmation
        attrs_text = "\n".join(
            f"  - {k}: {v}" for k, v in result.attributes.items()
        )
        content = (
            f"Extraí os seguintes atributos da sua descrição:\n{attrs_text}\n\n"
            f"Confiança: {result.confidence:.0%}\n\n"
            f"Por favor, confirme se esses atributos estão corretos para prosseguir "
            f"com a busca de similaridade."
        )
        msg = ChatMessage(
            id=str(uuid.uuid4()),
            session_id=session_id,
            role="assistant",
            content=content,
            timestamp=datetime.now(tz=timezone.utc),
            metadata={
                "type": "attribute_confirmation",
                "query_item_id": query_item.id,
                "extracted_attributes": result.attributes,
                "confidence": result.confidence,
            },
        )
        messages_store[session_id].append(msg)
        return msg

    def confirm_query_item(self, session_id: str) -> ChatMessage:
        """
        Confirm the pending QueryItem for the session and generate its embedding.

        Steps:
        1. Validate session is active and has a pending (unconfirmed) QueryItem.
        2. Generate embedding from the raw_description via the embedding API.
        3. Set QueryItem.confirmed = True and store the embedding.
        4. Return a confirmation ChatMessage.

        Raises ValueError if the session is not active or has no pending QueryItem.
        """
        session = self._get_active_session(session_id)

        if session.query_item is None:
            raise ValueError(
                f"{ErrorCode.EXTRACTION_INSUFFICIENT}: Session '{session_id}' has no "
                "pending Query_Item to confirm. Call submit_query_item first."
            )

        if session.query_item.confirmed:
            raise ValueError(
                f"{ErrorCode.EXTRACTION_INSUFFICIENT}: Query_Item for session "
                f"'{session_id}' is already confirmed."
            )

        session.last_activity_at = datetime.now(tz=timezone.utc)

        # Generate embedding from the raw description
        try:
            embedding = _generate_embedding(session.query_item.raw_description)
        except Exception as exc:
            logger.error(
                "Embedding generation failed | session_id=%s error=%s", session_id, exc
            )
            raise ValueError(
                f"{ErrorCode.LLM_UNAVAILABLE}: Failed to generate embedding for Query_Item. "
                f"Details: {exc}"
            ) from exc

        session.query_item.embedding = embedding
        session.query_item.confirmed = True

        logger.info(
            "QueryItem confirmed | session_id=%s query_item_id=%s",
            session_id,
            session.query_item.id,
        )

        content = (
            "Query_Item confirmado com sucesso. O embedding foi gerado e o item está "
            "pronto para a busca de similaridade."
        )
        msg = ChatMessage(
            id=str(uuid.uuid4()),
            session_id=session_id,
            role="assistant",
            content=content,
            timestamp=datetime.now(tz=timezone.utc),
            metadata={
                "type": "query_item_confirmed",
                "query_item_id": session.query_item.id,
            },
        )
        messages_store[session_id].append(msg)
        return msg

    # ------------------------------------------------------------------
    # Similarity search
    # ------------------------------------------------------------------

    def run_similarity_search(
        self,
        session_id: str,
        top_n: int = 10,
        threshold: float = 0.5,
    ) -> list:
        """
        Execute similarity search for the confirmed QueryItem of the session.

        Steps:
        1. Validate session is active and has a confirmed QueryItem.
        2. Call SimilarityEngine.search(query_item, top_n, threshold).
        3. For each result, call SimilarityEngine.explain and populate attribute_contributions.
        4. Store results in session.similarity_results.
        5. Return the list of SimilarityResult.

        Raises ValueError with appropriate ErrorCode if:
        - Session not found / not active
        - No confirmed QueryItem
        - KB is empty (propagated from SimilarityEngine)
        """
        from app.services.similarity_engine import SimilarityEngine  # avoid circular import
        from app.models import SimilarityResult

        session = self._get_active_session(session_id)

        if session.query_item is None:
            raise ValueError(
                f"{ErrorCode.EXTRACTION_INSUFFICIENT}: Session '{session_id}' has no "
                "Query_Item. Call submit_query_item first."
            )

        if not session.query_item.confirmed:
            raise ValueError(
                f"{ErrorCode.EXTRACTION_INSUFFICIENT}: Query_Item for session "
                f"'{session_id}' is not confirmed yet. Call confirm_query_item first."
            )

        session.last_activity_at = datetime.now(tz=timezone.utc)

        engine = SimilarityEngine()

        try:
            results = engine.search(session.query_item, top_n=top_n, threshold=threshold)
        except ValueError as exc:
            # KB_EMPTY or other known errors — propagate as-is
            raise

        # Populate attribute_contributions for each result
        enriched: list[SimilarityResult] = []
        for result in results:
            try:
                contributions = engine.explain(session.query_item, result.record)
                enriched.append(
                    SimilarityResult(
                        record=result.record,
                        similarity_score=result.similarity_score,
                        attribute_contributions=contributions,
                    )
                )
            except Exception as exc:
                logger.warning(
                    "explain failed for record %s | session_id=%s error=%s",
                    result.record.id,
                    session_id,
                    exc,
                )
                # Keep result without contributions rather than failing entirely
                enriched.append(result)

        session.similarity_results = enriched

        logger.info(
            "Similarity search completed | session_id=%s results=%d top_n=%d threshold=%.2f",
            session_id,
            len(enriched),
            top_n,
            threshold,
        )

        return enriched

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_active_session(self, session_id: str) -> Session:
        """Return the session if it exists and is active; raise ValueError otherwise."""
        session = sessions_store.get(session_id)

        if session is None:
            raise ValueError(
                f"{ErrorCode.SESSION_EXPIRED}: Session '{session_id}' not found."
            )
        if session.status == "expired":
            raise ValueError(
                f"{ErrorCode.SESSION_EXPIRED}: Session '{session_id}' has expired "
                "due to inactivity. Please start a new session."
            )
        if session.status == "closed":
            raise ValueError(
                f"{ErrorCode.SESSION_EXPIRED}: Session '{session_id}' is closed."
            )
        return session
