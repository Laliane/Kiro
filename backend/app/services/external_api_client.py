"""
External API Client for LLM Consultant Advisor.

Sends selected records (with similarity scores) to a configured external endpoint.
Supports bearer token, API key, and basic auth.

Environment variables:
  EXTERNAL_API_URL          Target endpoint URL
  EXTERNAL_API_AUTH_TYPE    "bearer", "api_key", or "basic"
  EXTERNAL_API_CREDENTIALS  JSON string with credentials
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone

from app.models import ErrorCode, ExternalAPIConfig, SimilarityResult

logger = logging.getLogger(__name__)


@dataclass
class SendResult:
    success: bool
    status_code: int | None
    message: str
    sent_count: int = 0


class ExternalAPIClient:
    """Transmits selected records to an external API endpoint."""

    def send(
        self,
        results: list[SimilarityResult],
        config: ExternalAPIConfig,
        consultant_id: str = "unknown",
    ) -> SendResult:
        """
        Send records to the external API.

        Args:
            results:       SimilarityResult objects to transmit.
            config:        ExternalAPIConfig with endpoint and auth details.
            consultant_id: Used for audit logging.

        Returns:
            SendResult with success flag, HTTP status code, and message.
        """
        import httpx

        headers = self._build_headers(config)
        payload = self._build_payload(results)

        timestamp = datetime.now(tz=timezone.utc).isoformat()

        try:
            with httpx.Client(timeout=config.timeout_seconds) as client:
                response = client.post(
                    config.endpoint_url,
                    json=payload,
                    headers=headers,
                )
            success = response.is_success
            result = SendResult(
                success=success,
                status_code=response.status_code,
                message="Enviado com sucesso." if success else response.text[:500],
                sent_count=len(results),
            )
        except httpx.TimeoutException as exc:
            logger.error("External API timeout | url=%s error=%s", config.endpoint_url, exc)
            result = SendResult(
                success=False,
                status_code=None,
                message=f"{ErrorCode.EXTERNAL_API_TIMEOUT}: Timeout ao conectar com a API externa.",
                sent_count=0,
            )
        except Exception as exc:
            logger.error("External API error | url=%s error=%s", config.endpoint_url, exc)
            result = SendResult(
                success=False,
                status_code=None,
                message=f"{ErrorCode.EXTERNAL_API_ERROR}: Erro ao enviar para API externa. Detalhes: {exc}",
                sent_count=0,
            )

        # Audit log
        logger.info(
            "External API send | timestamp=%s consultant_id=%s records=%d status=%s http_status=%s",
            timestamp,
            consultant_id,
            len(results),
            "success" if result.success else "failure",
            result.status_code,
        )

        return result

    def _build_headers(self, config: ExternalAPIConfig) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        creds = config.credentials

        if config.auth_type == "bearer":
            token = creds.get("token", "")
            headers["Authorization"] = f"Bearer {token}"
        elif config.auth_type == "api_key":
            key_name = creds.get("header_name", "X-API-Key")
            key_value = creds.get("api_key", "")
            headers[key_name] = key_value
        elif config.auth_type == "basic":
            import base64
            username = creds.get("username", "")
            password = creds.get("password", "")
            encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
            headers["Authorization"] = f"Basic {encoded}"

        return headers

    def _build_payload(self, results: list[SimilarityResult]) -> dict:
        records = []
        for r in results:
            records.append({
                "id": r.record.id,
                "similarity_score": r.similarity_score,
                "attributes": r.record.attributes,
                "attribute_contributions": [
                    {
                        "attribute_name": c.attribute_name,
                        "contribution_score": c.contribution_score,
                        "justification": c.justification,
                    }
                    for c in r.attribute_contributions
                ],
            })
        return {"records": records, "total": len(records)}


def get_external_api_config() -> ExternalAPIConfig | None:
    """Build ExternalAPIConfig from environment variables. Returns None if not configured."""
    url = os.environ.get("EXTERNAL_API_URL", "")
    if not url:
        return None

    auth_type = os.environ.get("EXTERNAL_API_AUTH_TYPE", "bearer")
    raw_creds = os.environ.get("EXTERNAL_API_CREDENTIALS", "{}")
    try:
        credentials = json.loads(raw_creds)
    except json.JSONDecodeError:
        credentials = {}

    return ExternalAPIConfig(
        endpoint_url=url,
        auth_type=auth_type,  # type: ignore[arg-type]
        credentials=credentials,
    )
