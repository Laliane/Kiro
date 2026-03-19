"""
Shared embedding generation module for LLM Consultant Advisor.

Extracted from chat_orchestrator.py to avoid duplication across services.

Environment variables:
  AZURE_OPENAI_API_KEY          Azure OpenAI API key (required)
  AZURE_OPENAI_ENDPOINT         Azure OpenAI endpoint URL (required)
  AZURE_OPENAI_EMBEDDING_MODEL  Azure deployment name for embeddings (required)
  AZURE_OPENAI_API_VERSION      API version (default: 2024-08-01-preview)
"""

from __future__ import annotations

import logging
import os
from langchain_openai import AzureOpenAIEmbeddings

from app.models import ErrorCode

logger = logging.getLogger(__name__)

# Azure OpenAI configuration for embeddings
_AZURE_API_KEY = os.environ.get("AZURE_OPENAI_API_KEY")
_AZURE_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT")
_AZURE_EMBEDDING_DEPLOYMENT = os.environ.get("AZURE_OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
_AZURE_API_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")


def generate_embedding(text: str) -> list[float]:
    """
    Generate an embedding vector for the given text using Azure OpenAI Embeddings.

    Args:
        text: The text to generate an embedding for.

    Returns:
        A list of floats representing the embedding vector.

    Raises:
        ValueError with ErrorCode.LLM_UNAVAILABLE if the API call fails or
        required environment variables are missing.
    """
    # Validate required environment variables
    if not _AZURE_API_KEY:
        raise ValueError(
            f"{ErrorCode.LLM_UNAVAILABLE}: AZURE_OPENAI_API_KEY environment variable is not set."
        )
    if not _AZURE_ENDPOINT:
        raise ValueError(
            f"{ErrorCode.LLM_UNAVAILABLE}: AZURE_OPENAI_ENDPOINT environment variable is not set."
        )
    
    try:
        logger.debug(
            "Generating embedding | deployment=%s endpoint=%s",
            _AZURE_EMBEDDING_DEPLOYMENT,
            _AZURE_ENDPOINT
        )
        
        embeddings = AzureOpenAIEmbeddings(
            azure_deployment=_AZURE_EMBEDDING_DEPLOYMENT,
            api_key=_AZURE_API_KEY,
            azure_endpoint=_AZURE_ENDPOINT,
            api_version=_AZURE_API_VERSION,
        )
        
        result = embeddings.embed_query(text)
        logger.debug("Embedding generated successfully | length=%d", len(result))
        return result
        
    except Exception as exc:
        logger.error(
            "Embedding generation failed | deployment=%s error=%s",
            _AZURE_EMBEDDING_DEPLOYMENT,
            exc
        )
        raise ValueError(
            f"{ErrorCode.LLM_UNAVAILABLE}: Failed to generate embedding. Details: {exc}"
        ) from exc
