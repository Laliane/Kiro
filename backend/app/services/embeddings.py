"""
Shared embedding generation module for LLM Consultant Advisor.

Extracted from chat_orchestrator.py to avoid duplication across services.

Environment variables:
  LLM_PROVIDER      "openai" or "anthropic" (default: openai)
  LLM_API_KEY       API key for the selected provider
  EMBEDDING_MODEL   Embedding model name (default: text-embedding-3-small)
  OPENAI_API_KEY    OpenAI API key used as fallback when provider is Anthropic
"""

from __future__ import annotations

import logging
import os

from app.models import ErrorCode

logger = logging.getLogger(__name__)

_LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "openai").lower()
_LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
_EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
# Fallback OpenAI key used for embeddings when provider is Anthropic
_OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", _LLM_API_KEY)


def generate_embedding(text: str) -> list[float]:
    """
    Generate an embedding vector for the given text using OpenAI's embedding API.

    When LLM_PROVIDER is "anthropic", falls back to OpenAI embeddings using
    OPENAI_API_KEY (or LLM_API_KEY if OPENAI_API_KEY is not set).

    Raises ValueError with ErrorCode.LLM_UNAVAILABLE on failure.
    """
    import openai  # lazy import

    api_key = _OPENAI_API_KEY if _LLM_PROVIDER == "anthropic" else _LLM_API_KEY
    client = openai.OpenAI(api_key=api_key)
    try:
        response = client.embeddings.create(
            model=_EMBEDDING_MODEL,
            input=text,
        )
        return response.data[0].embedding
    except Exception as exc:
        logger.error("Embedding generation failed: %s", exc)
        raise ValueError(
            f"{ErrorCode.LLM_UNAVAILABLE}: Failed to generate embedding. Details: {exc}"
        ) from exc
