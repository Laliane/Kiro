"""
Report Generator for LLM Consultant Advisor.

Generates AnalysisReport from session data and exports to JSON or PDF.

Environment variables:
  LLM_PROVIDER  "openai" or "anthropic" (default: openai)
  LLM_API_KEY   API key for the selected provider
  LLM_MODEL     Model name
"""

from __future__ import annotations

import io
import json
import logging
import os
import uuid
from datetime import datetime, timezone

from app.database import get_records_collection, sessions_store
from app.models import (
    AnalysisReport,
    ErrorCode,
    Recommendation,
    SimilarityResult,
)

logger = logging.getLogger(__name__)

_LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "openai").lower()
_LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
_LLM_MODEL = os.environ.get("LLM_MODEL", "")

_DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-haiku-20240307",
}

_MIN_KB_SIZE_FOR_CONFIDENCE = 10  # below this, add a confidence note


def _get_model() -> str:
    return _LLM_MODEL or _DEFAULT_MODELS.get(_LLM_PROVIDER, "gpt-4o-mini")


def _call_llm(prompt: str) -> str:
    messages = [{"role": "user", "content": prompt}]
    if _LLM_PROVIDER == "openai":
        import openai
        client = openai.OpenAI(api_key=_LLM_API_KEY)
        response = client.chat.completions.create(model=_get_model(), messages=messages)
        return response.choices[0].message.content or ""
    elif _LLM_PROVIDER == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=_LLM_API_KEY)
        response = client.messages.create(
            model=_get_model(), max_tokens=4096, messages=messages
        )
        return response.content[0].text if response.content else ""
    else:
        raise ValueError(
            f"{ErrorCode.LLM_UNAVAILABLE}: Unknown LLM provider '{_LLM_PROVIDER}'."
        )


def _build_analysis_prompt(
    query_description: str,
    results: list[SimilarityResult],
) -> str:
    results_text = ""
    for i, r in enumerate(results, 1):
        attrs = json.dumps(r.record.attributes, ensure_ascii=False)
        contribs = ", ".join(
            f"{c.attribute_name}({c.contribution_score:.2f})"
            for c in r.attribute_contributions
        )
        results_text += (
            f"\n{i}. Record ID: {r.record.id} | Score: {r.similarity_score:.3f}\n"
            f"   Atributos: {attrs}\n"
            f"   Contribuições: {contribs}\n"
        )

    return (
        "Você é um consultor especialista. Analise os resultados de similaridade abaixo "
        "e gere um relatório estruturado em JSON com os campos:\n"
        '  "summary": string — resumo executivo da análise\n'
        '  "patterns": array de strings — padrões identificados nos registros similares\n'
        '  "differences": array de strings — principais diferenças entre o item consultado e os registros\n'
        '  "recommendations": array de objetos com "text" e "supporting_record_id"\n\n'
        f"Item consultado: {query_description}\n\n"
        f"Registros similares encontrados:{results_text}\n\n"
        "Responda APENAS com JSON válido, sem markdown."
    )


class ReportGenerator:
    """Generates AnalysisReport from session similarity results."""

    def generate(self, session_id: str, format: str = "json") -> tuple[AnalysisReport, bytes]:
        """
        Build an AnalysisReport for the session and serialize it.

        Args:
            session_id: Active session id.
            format: "json" or "pdf".

        Returns:
            Tuple of (AnalysisReport, bytes) — the report object and its serialized form.

        Raises:
            ValueError with appropriate ErrorCode on failure.
        """
        session = sessions_store.get(session_id)
        if session is None:
            raise ValueError(
                f"{ErrorCode.SESSION_EXPIRED}: Session '{session_id}' not found."
            )

        results = session.similarity_results
        query_item = session.query_item

        if query_item is None:
            raise ValueError(
                f"{ErrorCode.EXTRACTION_INSUFFICIENT}: Session '{session_id}' has no "
                "Query_Item. Run similarity search first."
            )

        kb_size = get_records_collection().count()

        # Build LLM-generated analysis
        prompt = _build_analysis_prompt(query_item.raw_description, results)
        try:
            raw = _call_llm(prompt)
            analysis = json.loads(raw.strip())
        except json.JSONDecodeError:
            import re
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                analysis = json.loads(match.group())
            else:
                logger.error("LLM returned non-JSON for report: %s", raw[:200])
                analysis = {
                    "summary": "Análise não disponível.",
                    "patterns": [],
                    "differences": [],
                    "recommendations": [],
                }
        except Exception as exc:
            logger.error("LLM call failed for report generation: %s", exc)
            raise ValueError(
                f"{ErrorCode.LLM_UNAVAILABLE}: Falha ao gerar análise LLM. Detalhes: {exc}"
            ) from exc

        # Build recommendations — ensure supporting_record_id is always set
        recommendations: list[Recommendation] = []
        for rec in analysis.get("recommendations", []):
            supporting_id = rec.get("supporting_record_id", "")
            if not supporting_id and results:
                supporting_id = results[0].record.id
            recommendations.append(
                Recommendation(text=rec.get("text", ""), supporting_record_id=supporting_id)
            )

        confidence_note: str | None = None
        if kb_size < _MIN_KB_SIZE_FOR_CONFIDENCE:
            confidence_note = (
                f"A base de conhecimento contém apenas {kb_size} registro(s). "
                "Os resultados podem não ser representativos."
            )

        report = AnalysisReport(
            id=str(uuid.uuid4()),
            session_id=session_id,
            generated_at=datetime.now(tz=timezone.utc),
            summary=analysis.get("summary", ""),
            patterns=analysis.get("patterns", []),
            differences=analysis.get("differences", []),
            recommendations=recommendations,
            explainability=results,
            knowledge_base_size=kb_size,
            confidence_note=confidence_note,
        )

        # Serialize
        if format == "pdf":
            data = self._to_pdf(report)
        else:
            data = report.model_dump_json(indent=2).encode("utf-8")

        return report, data

    def _to_pdf(self, report: AnalysisReport) -> bytes:
        """Render the AnalysisReport as a PDF using reportlab."""
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib.units import cm
            from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
        except ImportError as exc:
            raise ValueError(
                f"{ErrorCode.EXPORT_FAILED}: reportlab não está instalado. "
                f"Detalhes: {exc}"
            ) from exc

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2 * cm, leftMargin=2 * cm,
                                topMargin=2 * cm, bottomMargin=2 * cm)
        styles = getSampleStyleSheet()
        story = []

        def h1(text: str) -> Paragraph:
            return Paragraph(f"<b>{text}</b>", styles["Heading1"])

        def h2(text: str) -> Paragraph:
            return Paragraph(f"<b>{text}</b>", styles["Heading2"])

        def body(text: str) -> Paragraph:
            return Paragraph(text, styles["Normal"])

        story.append(h1("Relatório de Análise — LLM Consultant Advisor"))
        story.append(body(f"Sessão: {report.session_id}"))
        story.append(body(f"Gerado em: {report.generated_at.strftime('%d/%m/%Y %H:%M:%S')}"))
        story.append(Spacer(1, 0.5 * cm))

        story.append(h2("Resumo"))
        story.append(body(report.summary or "—"))
        story.append(Spacer(1, 0.3 * cm))

        if report.patterns:
            story.append(h2("Padrões Identificados"))
            for p in report.patterns:
                story.append(body(f"• {p}"))
            story.append(Spacer(1, 0.3 * cm))

        if report.differences:
            story.append(h2("Diferenças"))
            for d in report.differences:
                story.append(body(f"• {d}"))
            story.append(Spacer(1, 0.3 * cm))

        if report.recommendations:
            story.append(h2("Recomendações"))
            for rec in report.recommendations:
                story.append(body(f"• {rec.text} (Ref: {rec.supporting_record_id})"))
            story.append(Spacer(1, 0.3 * cm))

        if report.explainability:
            story.append(h2("Explicabilidade"))
            for sr in report.explainability:
                story.append(body(
                    f"<b>Record {sr.record.id}</b> — Score: {sr.similarity_score:.3f}"
                ))
                for c in sr.attribute_contributions:
                    story.append(body(
                        f"&nbsp;&nbsp;• {c.attribute_name}: {c.contribution_score:.2f} — {c.justification}"
                    ))
            story.append(Spacer(1, 0.3 * cm))

        if report.confidence_note:
            story.append(h2("Nota de Confiança"))
            story.append(body(report.confidence_note))

        doc.build(story)
        return buffer.getvalue()
