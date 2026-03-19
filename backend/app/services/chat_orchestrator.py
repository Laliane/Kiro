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
from dotenv import load_dotenv
from datetime import datetime, timezone

from app.database import messages_store, sessions_store
from app.models import ChatMessage, ErrorCode, KnowledgeBaseSchema, QueryItem, Session
from langchain_openai import AzureChatOpenAI

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM provider configuration
# ---------------------------------------------------------------------------

# Carrega a chave da OpenAI do arquivo .env
load_dotenv()


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
# RAG (Retrieval-Augmented Generation) helpers
# ---------------------------------------------------------------------------


def _retrieve_relevant_context(query: str, top_k: int = 5) -> str:
    """
    Busca contexto relevante no ChromaDB para a query do usuário.
    
    Args:
        query: Pergunta ou mensagem do usuário
        top_k: Número máximo de documentos relevantes a recuperar
    
    Returns:
        String formatada com o contexto relevante ou mensagem de base vazia
    """
    from app.database import get_records_collection
    
    try:
        collection = get_records_collection()
        
        # Verifica se há documentos na base
        if collection.count() == 0:
            return "⚠️ Base de conhecimento vazia. Configure DEFAULT_KB_CSV_PATH ou faça upload de um CSV."
        
        # Gera embedding da query
        query_embedding = _generate_embedding(query)
        
        # Busca documentos similares
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, collection.count()),
            include=["metadatas", "documents", "distances"]
        )
        
        if not results["ids"][0]:
            return "Nenhum documento relevante encontrado na base de conhecimento."
        
        # Formata o contexto
        context_parts = []
        for idx, (metadata, distance) in enumerate(zip(results["metadatas"][0], results["distances"][0]), 1):
            # Converte distância em similaridade (0-1)
            similarity = 1.0 - (distance / 2.0)
            
            # Filtra campos relevantes do metadata
            attrs = {k.replace("attr_", ""): v for k, v in metadata.items() if k.startswith("attr_")}
            
            # Formata cada documento
            attrs_str = ", ".join(f"{k}: {v}" for k, v in attrs.items() if v)
            context_parts.append(f"[Documento {idx}] (Relevância: {similarity:.0%})\n{attrs_str}")
        
        return "\n\n".join(context_parts)
        
    except Exception as exc:
        logger.warning(f"Erro ao recuperar contexto do ChromaDB: {exc}")
        return "Erro ao acessar a base de conhecimento."


def _build_system_prompt(context: str) -> str:
    """
    Constrói o prompt de sistema com instruções e contexto para o agente.
    
    Args:
        context: Contexto relevante recuperado do ChromaDB
    
    Returns:
        Prompt de sistema formatado
    """
    return f"""Você é um assistente especializado em análise de dados e consulta de base de conhecimento.

## PERSONA E AUTORIDADE
Você é o Estrategista de Expansão Sênior de um ecossistema de beleza líder no mercado. Sua especialidade é o método de "Loja Espelho" (Twin-Store Analysis): identificar o sucesso de uma nova área (Setor Censitário) comparando-a com o desempenho histórico e as características socioeconômicas de lojas já consolidadas no parque.

## BASE DE CONHECIMENTO DISPONÍVEL
{context}

## CONTEXTO E OBJETIVO
Sua missão é mitigar riscos financeiros e operacionais. Uma sugestão assertiva de "Loja Espelho" permite prever o sucesso de uma nova abertura.
**Raciocínio Crítico:** Se a loja espelho (existente) tem alta performance em um contexto socioeconômico similar ao potencial, a viabilidade é alta.
**Risco:** Se a similaridade for baixa ou a loja espelho tiver performance ruim, o risco de recompra da franquia pelo franqueador aumenta.

## DIRETRIZES DE ANÁLISE
Ao receber os dados da Loja Potencial (Alvo), você deve realizar a comparação cruzada baseando-se em dois pilares contidos na base vetorial:

**Pilar A: Atributos do PDV (Ponto de Venda)**
Tipologia: (Rua, Shopping, Hipermercado, Smart, Híbrida).
Porte: Metragem quadrada (nr_metragem).
Modelo de Operação: (Franqueado, Própria, Digital).

**Pilar B: Ecossistema Socioeconômico (Entorno)**
Perfil de Renda: Renda per capita e Classe Social predominante (FGV).
Densidade e Público: População total e População em Idade Ativa.
Comportamento de Consumo: Gastos médios em Higiene, Perfumaria e Cuidados Capilares.

## WORKFLOW DE RESPOSTA
Consolidação do Perfil Alvo: Resuma os dados da loja potencial recebida, confirmando que entendeu o perfil (ex: "Loja Smart de Rua em área Classe B"). As informações da loja recebida devem conter, no mínimo, a localização da loja para fins de comparação.
Recuperação Vetorial: Identifique na base as lojas que possuem a menor distância vetorial (maior similaridade) combinando os pilares A e B.
Justificativa Técnica: Para cada loja sugerida, explique o "porquê" da similaridade.
Exemplo: "A Loja X foi selecionada porque, embora esteja em outra cidade, possui o mesmo gasto per capita em perfumaria e a mesma metragem da loja alvo."
Indicador de Confiança: Atribua um nível de similaridade (Baixa, Média, Alta) baseado na convergência dos dados.

## INSTRUÇÕES DE COMPORTAMENTO
1. **Baseie-se SEMPRE nos dados fornecidos acima** - Não invente informações
2. **Se a resposta não estiver na base de conhecimento**, diga claramente que não tem essa informação
4. **Seja conciso e objetivo** - Respostas diretas e úteis
5. **Use linguagem profissional** mas amigável


## O QUE NÃO FAZER
❌ Não invente dados que não estão na base de conhecimento
❌ Não responda sobre tópicos fora do escopo da base de dados
❌ Não faça suposições sem dados concretos
❌ Não ignore o contexto fornecido

## REGRAS DE OURO (RESTRIÇÕES)
Fidelidade aos Dados: Utilize apenas os atributos presentes na base de dados (conforme o dicionário de campos: vlr_renda_per_capita, des_classe_predom_regiao_fgv, vlr_desp_higiene_perfume, etc.).
Filtro de Ruído: Se o usuário mencionar variáveis subjetivas ou fora da lista padrão (ex: "cor da fachada", "clima"), informe gentilmente: "A variável [X] não faz parte dos parâmetros técnicos de expansão e não será considerada na busca por similaridade."
bjetividade: O foco é técnico. Evite adjetivos desnecessários; foque em dados demográficos e operacionais.

Lembre-se: Você é um assistente confiável - a precisão é mais importante que ter uma resposta para tudo."""


# ---------------------------------------------------------------------------
# Internal LLM call helpers
# ---------------------------------------------------------------------------


def _call_openai(messages: list[dict]) -> str:
    """Call OpenAI chat completions API via AzureChatOpenAI and return the assistant reply."""
    llm = AzureChatOpenAI(
        azure_deployment="inic1537_gpt-4o_dev",
        azure_endpoint="https://inic1537-dev-resource.cognitiveservices.azure.com/",
        api_version="2024-08-01-preview",
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        temperature=0.7
    )
    response = llm.invoke(messages)
    return response.content if hasattr(response, "content") else str(response)


def _call_llm(history: list[ChatMessage]) -> str:
    """
    Convert ChatMessage history to provider format and call the LLM.
    
    Supports system, user, and assistant roles.

    Raises ValueError with ErrorCode.LLM_UNAVAILABLE if the provider is unknown.
    Propagates provider exceptions to the caller for error handling.
    """
    messages = [{"role": msg.role, "content": msg.content} for msg in history]

    return _call_openai(messages)
    


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

    def send_message(self, session_id: str, message: str, use_rag: bool = True) -> ChatMessage:
        """
        Send a user message to the LLM and return the assistant's reply.

        Steps:
        1. Validate session exists and is active.
        2. Update last_activity_at.
        3. (RAG) Retrieve relevant context from ChromaDB based on the user's message.
        4. Build system prompt with instructions and context.
        5. Append user message to history.
        6. Call LLM with system prompt and full history as context.
        7. Append assistant reply to history.
        8. Return the assistant ChatMessage.

        Args:
            session_id: The session ID
            message: User's message
            use_rag: If True, retrieves context from ChromaDB (default: True)

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

        # RAG: Retrieve relevant context from ChromaDB
        context = ""
        if use_rag:
            try:
                context = _retrieve_relevant_context(message, top_k=5)
                logger.info(f"RAG context retrieved for session {session_id}")
            except Exception as exc:
                logger.warning(f"RAG context retrieval failed: {exc}")
                context = "Base de conhecimento não disponível no momento."

        # Build conversation history with system prompt
        history_with_context = []
        
        # Add system prompt as first message (only if using RAG and we have context)
        if use_rag and context:
            system_prompt = _build_system_prompt(context)
            history_with_context.append(
                ChatMessage(
                    id="system",
                    session_id=session_id,
                    role="system",
                    content=system_prompt,
                    timestamp=datetime.now(tz=timezone.utc),
                )
            )
        
        # Add existing conversation history
        history_with_context.extend(messages_store[session_id])

        # Call LLM with system prompt + full history as context
        try:
            reply_content = _call_llm(history_with_context)
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
