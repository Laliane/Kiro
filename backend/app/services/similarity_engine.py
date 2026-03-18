"""
Similarity Engine for LLM Consultant Advisor.

Generates embeddings for QueryItems and performs ANN search in ChromaDB,
then uses the LLM to explain attribute contributions for each result.

Environment variables:
  LLM_PROVIDER      "openai" or "anthropic" (default: openai)
  LLM_API_KEY       API key for the selected provider
  LLM_MODEL         Model name (default: gpt-4o-mini / claude-3-haiku-20240307)
"""

from __future__ import annotations

import json
import logging
import os

from app.database import get_records_collection
from app.models import (
    AttributeContribution,
    ErrorCode,
    QueryItem,
    Record,
    SimilarityResult,
)
from app.services.embeddings import generate_embedding

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


def _call_llm(prompt: str) -> str:
    """Call the configured LLM with a single user prompt and return the response text."""
    messages = [{"role": "user", "content": prompt}]

    if _LLM_PROVIDER == "openai":
        import openai  # lazy import

        client = openai.OpenAI(api_key=_LLM_API_KEY)
        response = client.chat.completions.create(
            model=_get_model(),
            messages=messages,
        )
        return response.choices[0].message.content or ""

    elif _LLM_PROVIDER == "anthropic":
        import anthropic  # lazy import

        client = anthropic.Anthropic(api_key=_LLM_API_KEY)
        response = client.messages.create(
            model=_get_model(),
            max_tokens=4096,
            messages=messages,
        )
        return response.content[0].text if response.content else ""

    else:
        raise ValueError(
            f"{ErrorCode.LLM_UNAVAILABLE}: Unknown LLM provider '{_LLM_PROVIDER}'. "
            "Set LLM_PROVIDER to 'openai' or 'anthropic'."
        )


# ---------------------------------------------------------------------------
# ChromaDB helpers
# ---------------------------------------------------------------------------


def _chroma_to_record(record_id: str, embedding: list[float], metadata: dict) -> Record:
    """Reconstruct a Record from ChromaDB query result data."""
    from datetime import datetime

    attributes: dict = {}
    source_row_hash = metadata.get("source_row_hash", "")
    created_at = datetime.fromisoformat(
        metadata.get("created_at", datetime.utcnow().isoformat())
    )
    updated_at = datetime.fromisoformat(
        metadata.get("updated_at", datetime.utcnow().isoformat())
    )

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


# ---------------------------------------------------------------------------
# SimilarityEngine
# ---------------------------------------------------------------------------


class SimilarityEngine:
    """
    Executes ANN similarity search against the ChromaDB knowledge base and
    provides LLM-powered attribute contribution explanations.
    """

    def search(
        self,
        query_item: QueryItem,
        top_n: int = 10,
        threshold: float = 0.5,
    ) -> list[SimilarityResult]:
        """
        Search for the top-N most similar Records to the given QueryItem.

        Steps:
        1. Ensure the QueryItem has an embedding (generate one if missing).
        2. Query ChromaDB for the nearest neighbours.
        3. Convert ChromaDB cosine distances to similarity scores: score = 1 - (distance / 2).
        4. Filter out results below the threshold.
        5. Return results sorted by similarity_score descending.

        Raises:
            ValueError with ErrorCode.KB_EMPTY if the knowledge base is empty.

        Returns:
            list[SimilarityResult] — may be empty if no record exceeds the threshold.
        """
        collection = get_records_collection()

        # Guard: KB must not be empty
        if collection.count() == 0:
            raise ValueError(
                f"{ErrorCode.KB_EMPTY}: The knowledge base is empty. "
                "Please upload a CSV file before performing similarity search."
            )

        # Ensure the QueryItem has an embedding
        if query_item.embedding is None:
            logger.info(
                "QueryItem %s has no embedding — generating one now.", query_item.id
            )
            query_item.embedding = generate_embedding(query_item.raw_description)

        # Query ChromaDB — request up to top_n results
        query_result = collection.query(
            query_embeddings=[query_item.embedding],
            n_results=min(top_n, collection.count()),
            include=["embeddings", "metadatas", "distances"],
        )

        ids: list[str] = query_result["ids"][0]
        embeddings: list[list[float]] = query_result["embeddings"][0]
        metadatas: list[dict] = query_result["metadatas"][0]
        distances: list[float] = query_result["distances"][0]

        results: list[SimilarityResult] = []
        for record_id, embedding, metadata, distance in zip(
            ids, embeddings, metadatas, distances
        ):
            # ChromaDB cosine space: distance in [0, 2]; convert to similarity in [0, 1]
            similarity_score = 1.0 - (distance / 2.0)

            if similarity_score < threshold:
                continue  # below threshold — skip

            record = _chroma_to_record(record_id, embedding, metadata)
            results.append(
                SimilarityResult(
                    record=record,
                    similarity_score=similarity_score,
                )
            )

        # Sort descending by similarity_score
        results.sort(key=lambda r: r.similarity_score, reverse=True)

        if not results:
            logger.info(
                "No results above threshold %.2f for QueryItem %s.",
                threshold,
                query_item.id,
            )

        return results

    def explain(
        self,
        query_item: QueryItem,
        record: Record,
    ) -> list[AttributeContribution]:
        """
        Use the LLM to explain which attributes of the QueryItem contributed most
        to the similarity with the given Record.

        Returns a list of AttributeContribution sorted by contribution_score descending.

        Raises ValueError with ErrorCode.LLM_UNAVAILABLE on LLM failure.
        """
        attributes = query_item.extracted_attributes
        if not attributes:
            # Fall back to raw description if no structured attributes are available
            attributes = {"description": query_item.raw_description}

        prompt = (
            "You are an expert at explaining why two items are similar based on their attributes.\n\n"
            "Query Item attributes:\n"
            f"{json.dumps(attributes, ensure_ascii=False, indent=2)}\n\n"
            "Candidate Record attributes:\n"
            f"{json.dumps(record.attributes, ensure_ascii=False, indent=2)}\n\n"
            "For each attribute present in the Query Item, evaluate how much it contributed "
            "to the similarity with the Candidate Record.\n\n"
            "Respond ONLY with a valid JSON array (no markdown, no extra text) where each element has:\n"
            '  "attribute_name": string — the attribute name from the Query Item\n'
            '  "contribution_score": float between 0.0 and 1.0 — how much this attribute contributed\n'
            '  "justification": string — a brief explanation of why this attribute contributed\n\n'
            "Example:\n"
            '[{"attribute_name": "industry", "contribution_score": 0.9, '
            '"justification": "Both items belong to the same industry sector."}]'
        )

        try:
            raw_response = _call_llm(prompt)
        except Exception as exc:
            logger.error("LLM explain call failed: %s", exc)
            raise ValueError(
                f"{ErrorCode.LLM_UNAVAILABLE}: Failed to generate attribute explanation. "
                f"Details: {exc}"
            ) from exc

        # Parse the JSON response
        try:
            parsed = json.loads(raw_response.strip())
        except json.JSONDecodeError:
            # Attempt to extract JSON array from the response if wrapped in markdown
            import re

            match = re.search(r"\[.*\]", raw_response, re.DOTALL)
            if match:
                parsed = json.loads(match.group())
            else:
                logger.error(
                    "LLM returned non-JSON response for explain: %s", raw_response[:200]
                )
                raise ValueError(
                    f"{ErrorCode.LLM_UNAVAILABLE}: LLM returned an invalid JSON response "
                    "for attribute explanation."
                )

        contributions: list[AttributeContribution] = []
        for item in parsed:
            try:
                contributions.append(
                    AttributeContribution(
                        attribute_name=str(item["attribute_name"]),
                        contribution_score=float(item["contribution_score"]),
                        justification=str(item["justification"]),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning("Skipping malformed contribution item %s: %s", item, exc)

        # Sort by contribution_score descending
        contributions.sort(key=lambda c: c.contribution_score, reverse=True)

        return contributions
