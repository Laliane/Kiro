"""
Attribute Extractor for LLM Consultant Advisor.

Uses the configured LLM provider to interpret a natural language description
and extract structured attributes matching the Knowledge Base schema.

Environment variables (same as ChatOrchestrator):
  LLM_PROVIDER   "openai" or "anthropic" (default: openai)
  LLM_API_KEY    API key for the selected provider (required)
  LLM_MODEL      Model name (default: gpt-4o-mini / claude-3-haiku-20240307)
"""

from __future__ import annotations

import json
import logging
import os

from pydantic import BaseModel, Field

from app.models import ErrorCode, KnowledgeBaseSchema

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM provider configuration (mirrors chat_orchestrator.py)
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
# Result model
# ---------------------------------------------------------------------------


class ExtractionResult(BaseModel):
    """Result of attribute extraction from a natural language description."""

    attributes: dict = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    missing_fields: list[str] = Field(default_factory=list)
    needs_more_info: bool = False


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are an attribute extraction assistant. Your task is to extract structured \
attributes from a natural language description provided by a consultant.

You will receive:
1. A natural language description of a consultant item (Query_Item).
2. A schema defining the required and optional fields of the Knowledge Base.

Your response MUST be a valid JSON object with exactly these keys:
- "attributes": an object containing only the fields present in the schema \
that you could extract from the description (use the exact field names from the schema).
- "confidence": a float between 0.0 and 1.0 representing your overall confidence \
in the extraction.
- "missing_fields": a list of required field names that were NOT found in the description.

Rules:
- Only include fields that are defined in the schema (required_fields + optional_fields).
- Do NOT invent or hallucinate values — only extract what is explicitly or clearly \
implied in the description.
- If a required field is absent from the description, add it to "missing_fields".
- Do NOT include optional fields in "missing_fields" even if absent.
- Return ONLY the JSON object, no markdown, no explanation.
"""


def _build_user_prompt(description: str, schema: KnowledgeBaseSchema) -> str:
    return (
        f"Description:\n{description}\n\n"
        f"Schema:\n"
        f"  required_fields: {schema.required_fields}\n"
        f"  optional_fields: {schema.optional_fields}\n"
    )


# ---------------------------------------------------------------------------
# LLM call helpers
# ---------------------------------------------------------------------------


def _call_openai_json(system: str, user: str) -> str:
    """Call OpenAI with JSON mode enabled."""
    import openai  # lazy import

    client = openai.OpenAI(api_key=_LLM_API_KEY)
    response = client.chat.completions.create(
        model=_get_model(),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
    )
    return response.choices[0].message.content or "{}"


def _call_anthropic_json(system: str, user: str) -> str:
    """Call Anthropic and request a JSON response."""
    import anthropic  # lazy import

    client = anthropic.Anthropic(api_key=_LLM_API_KEY)
    response = client.messages.create(
        model=_get_model(),
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return response.content[0].text if response.content else "{}"


def _call_llm_for_extraction(system: str, user: str) -> str:
    """Dispatch to the configured LLM provider and return raw JSON string."""
    if _LLM_PROVIDER == "openai":
        return _call_openai_json(system, user)
    elif _LLM_PROVIDER == "anthropic":
        return _call_anthropic_json(system, user)
    else:
        raise ValueError(
            f"{ErrorCode.LLM_UNAVAILABLE}: Unknown LLM provider '{_LLM_PROVIDER}'. "
            "Set LLM_PROVIDER to 'openai' or 'anthropic'."
        )


# ---------------------------------------------------------------------------
# AttributeExtractor
# ---------------------------------------------------------------------------


class AttributeExtractor:
    """
    Interprets a natural language description and extracts structured attributes
    that match the Knowledge Base schema using the configured LLM provider.
    """

    def extract(self, description: str, schema: KnowledgeBaseSchema) -> ExtractionResult:
        """
        Extract attributes from a natural language description.

        Args:
            description: Natural language text describing the Query_Item.
            schema: Knowledge Base schema defining required and optional fields.

        Returns:
            ExtractionResult with:
              - attributes: dict of extracted field → value pairs
              - confidence: float 0–1
              - missing_fields: required fields absent from the description
              - needs_more_info: True when missing_fields is non-empty

        Raises:
            ValueError with ErrorCode.LLM_UNAVAILABLE if the LLM call fails.
        """
        system_prompt = _SYSTEM_PROMPT
        user_prompt = _build_user_prompt(description, schema)

        try:
            raw = _call_llm_for_extraction(system_prompt, user_prompt)
        except Exception as exc:
            logger.error("AttributeExtractor LLM call failed: %s", exc)
            raise ValueError(
                f"{ErrorCode.LLM_UNAVAILABLE}: LLM unavailable during attribute extraction. "
                f"Details: {exc}"
            ) from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error("AttributeExtractor: LLM returned invalid JSON: %s", raw)
            raise ValueError(
                f"{ErrorCode.LLM_UNAVAILABLE}: LLM returned non-JSON response during extraction."
            ) from exc

        attributes: dict = data.get("attributes", {})
        confidence: float = float(data.get("confidence", 0.0))
        missing_fields: list[str] = data.get("missing_fields", [])

        # Clamp confidence to [0, 1]
        confidence = max(0.0, min(1.0, confidence))

        needs_more_info = len(missing_fields) > 0

        result = ExtractionResult(
            attributes=attributes,
            confidence=confidence,
            missing_fields=missing_fields,
            needs_more_info=needs_more_info,
        )

        logger.info(
            "AttributeExtractor: extracted %d attributes, confidence=%.2f, "
            "missing_fields=%s, needs_more_info=%s",
            len(attributes),
            confidence,
            missing_fields,
            needs_more_info,
        )

        return result
