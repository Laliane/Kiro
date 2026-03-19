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
from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings

from app.models import ErrorCode

logger = logging.getLogger(__name__)

_LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "openai").lower()
_LLM_API_KEY = os.environ.get("AZURE_OPENAI_API_KEY")
_EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL")

def generate_embedding(text: str) -> list[float]:
    """
    Generate an embedding vector for the given text using AzureOpenAIEmbeddings from langchain.

    Raises ValueError with ErrorCode.LLM_UNAVAILABLE on failure.
    """
    try:
        embeddings = AzureOpenAIEmbeddings(
            azure_deployment=_EMBEDDING_MODEL,
            api_key=_LLM_API_KEY,
            azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT", ""),
            api_version=os.environ.get("AZURE_OPENAI_API_VERSION", ""),
        )
        result = embeddings.embed_query(text)
        return result
    except Exception as exc:
        logger.error("Embedding generation failed: %s", exc)
        raise ValueError(
            f"{ErrorCode.LLM_UNAVAILABLE}: Failed to generate embedding. Details: {exc}"
        ) from exc
