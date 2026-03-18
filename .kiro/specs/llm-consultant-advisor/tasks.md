# Implementation Plan: LLM Consultant Advisor

## Overview

Implementação incremental da aplicação web LLM Consultant Advisor, composta por backend FastAPI (Python) e frontend React/TypeScript. As tarefas seguem a ordem de dependência: infraestrutura base → autenticação → sessões → Knowledge Base → busca de similaridade → análise LLM → seleção e exportação → integração com API externa.

## Tasks

- [x] 1. Configurar estrutura do projeto e dependências base
  - Criar estrutura de diretórios: `backend/`, `frontend/`, `tests/`
  - Criar `backend/pyproject.toml` com dependências: fastapi, uvicorn, chromadb, openai, anthropic, hypothesis, pytest, python-jose, passlib, reportlab, httpx
  - Criar `frontend/package.json` com dependências: react, typescript, vite, axios, tailwindcss
  - Criar `backend/.env.example` com variáveis: `LLM_PROVIDER`, `LLM_API_KEY`, `EMBEDDING_MODEL`, `JWT_SECRET`, `EXTERNAL_API_URL`, `EXTERNAL_API_AUTH_TYPE`, `EXTERNAL_API_CREDENTIALS`
  - Criar `backend/app/main.py` com app FastAPI e routers registrados
  - _Requirements: 7.1, 9.5_

- [x] 2. Implementar modelos de dados e camada de persistência
  - [x] 2.1 Criar modelos de dados Python em `backend/app/models.py`
    - Implementar dataclasses/Pydantic models: `Session`, `ChatMessage`, `QueryItem`, `Record`, `SimilarityResult`, `AttributeContribution`, `AnalysisReport`, `Recommendation`, `ExternalAPIConfig`, `KnowledgeBaseSchema`, `ErrorCode`
    - _Requirements: 1.4, 2.2, 3.1, 4.2, 5.3, 9.2_

  - [x] 2.2 Criar camada de persistência em `backend/app/database.py`
    - Inicializar ChromaDB client e collection para embeddings
    - Implementar funções CRUD para `Record` no ChromaDB
    - Implementar armazenamento em memória (dict) para `Session` e `ChatMessage` (pode ser substituído por PostgreSQL em etapa futura)
    - _Requirements: 5.4, 7.3_

  - [ ]* 2.3 Escrever property test para round-trip de embeddings (Property 9)
    - **Property 9: Round-trip de armazenamento de embeddings**
    - **Validates: Requirements 5.3, 5.4**

- [x] 3. Implementar Auth Service e middleware de autenticação
  - [x] 3.1 Criar `backend/app/services/auth_service.py`
    - Implementar `AuthService.authenticate(credentials)` retornando `TokenPair` (JWT access + refresh)
    - Implementar `AuthService.validate_token(token)` retornando `ConsultantIdentity`
    - Implementar `AuthService.refresh(refresh_token)` retornando novo `TokenPair`
    - Implementar expiração automática de sessão por inatividade (30 min) em `SessionManager`
    - _Requirements: 7.1, 7.4_

  - [x] 3.2 Criar endpoints de autenticação em `backend/app/routers/auth.py`
    - `POST /auth/login` e `POST /auth/refresh`
    - Criar middleware FastAPI que valida JWT em todos os endpoints protegidos e retorna 401/403 para tokens inválidos
    - _Requirements: 7.1, 7.2_

  - [ ]* 3.3 Escrever property test para rejeição de acesso não autenticado (Property 12)
    - **Property 12: Rejeição de acesso não autenticado**
    - **Validates: Requirements 7.1, 7.2**

  - [ ]* 3.4 Escrever property test para expiração automática de sessões (Property 14)
    - **Property 14: Expiração automática de sessões inativas**
    - **Validates: Requirements 7.4**

  - [ ]* 3.5 Escrever testes unitários para Auth Service
    - Testar login com credenciais válidas e inválidas
    - Testar refresh de token
    - Testar expiração de token
    - _Requirements: 7.1, 7.2, 7.4_

- [x] 4. Checkpoint — Garantir que todos os testes passam
  - Garantir que todos os testes passam, perguntar ao usuário se houver dúvidas.

- [x] 5. Implementar Chat Orchestrator e gerenciamento de sessões
  - [x] 5.1 Criar `backend/app/services/chat_orchestrator.py`
    - Implementar `ChatOrchestrator.create_session(consultant_id)` retornando `Session`
    - Implementar `ChatOrchestrator.close_session(session_id)`
    - Implementar `ChatOrchestrator.get_history(session_id)` retornando `list[ChatMessage]`
    - Implementar `ChatOrchestrator.send_message(session_id, message)` com chamada ao LLM Provider configurado e manutenção do histórico como contexto
    - Registrar log de sessão (consultant_id, timestamps, query_items) conforme `ErrorCode`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 7.3_

  - [x] 5.2 Criar endpoints de sessão e mensagens em `backend/app/routers/sessions.py`
    - `POST /sessions`, `DELETE /sessions/{id}`, `POST /sessions/{id}/messages`, `GET /sessions/{id}/messages`
    - _Requirements: 1.1, 1.6_

  - [ ]* 5.3 Escrever property test para completude do histórico de sessão (Property 1)
    - **Property 1: Completude do histórico de sessão**
    - **Validates: Requirements 1.4**

  - [ ]* 5.4 Escrever property test para isolamento entre sessões (Property 2)
    - **Property 2: Isolamento entre sessões**
    - **Validates: Requirements 1.6, 7.5**

  - [ ]* 5.5 Escrever property test para auditoria de sessões (Property 13)
    - **Property 13: Auditoria de sessões**
    - **Validates: Requirements 7.3**

- [x] 6. Implementar Attribute Extractor
  - [x] 6.1 Criar `backend/app/services/attribute_extractor.py`
    - Implementar `AttributeExtractor.extract(description, schema)` usando LLM para interpretar texto e retornar `ExtractionResult` com `attributes`, `confidence`, `missing_fields`
    - Quando `missing_fields` não estiver vazio, retornar resultado com flag para solicitar informações adicionais ao consultor
    - _Requirements: 2.1, 2.2, 2.4_

  - [x] 6.2 Integrar Attribute Extractor no `ChatOrchestrator.send_message`
    - Detectar quando mensagem contém descrição de Query_Item
    - Chamar `AttributeExtractor.extract` e apresentar atributos extraídos ao consultor para confirmação (mensagem com `metadata.type = "attribute_confirmation"`)
    - Quando confirmado, setar `QueryItem.confirmed = True` e gerar embedding
    - _Requirements: 2.3, 2.5_

  - [ ]* 6.3 Escrever property test para extração de atributos (Property 3)
    - **Property 3: Extração de atributos produz resultado não vazio para descrições válidas**
    - **Validates: Requirements 2.2**

  - [ ]* 6.4 Escrever property test para Query_Item confirmado disponível (Property 4)
    - **Property 4: Query_Item confirmado fica disponível para busca**
    - **Validates: Requirements 2.5**

- [x] 7. Implementar CSV Preprocessor e carga da Knowledge Base
  - [x] 7.1 Criar `backend/app/services/csv_preprocessor.py`
    - Implementar `CSVPreprocessor.load(file_path)` com leitura, limpeza (deduplicação por SHA-256, tratamento de valores ausentes, normalização), geração de embeddings e armazenamento no ChromaDB
    - Implementar `CSVPreprocessor.reload(file_path)` com carga incremental: reprocessar apenas records com `source_row_hash` novo ou modificado
    - Registrar records inválidos (campos obrigatórios ausentes) em log de erros e continuar com os válidos
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_

  - [x] 7.2 Criar endpoints de admin em `backend/app/routers/admin.py`
    - `POST /admin/knowledge-base/upload` e `GET /admin/knowledge-base/status`
    - _Requirements: 5.1, 5.7_

  - [ ]* 7.3 Escrever property test para deduplicação pelo CSV Preprocessor (Property 8)
    - **Property 8: Deduplicação pelo CSV Preprocessor**
    - **Validates: Requirements 5.2**

  - [ ]* 7.4 Escrever property test para carga incremental (Property 10)
    - **Property 10: Carga incremental preserva records não modificados**
    - **Validates: Requirements 5.5**

- [x] 8. Checkpoint — Garantir que todos os testes passam
  - Garantir que todos os testes passam, perguntar ao usuário se houver dúvidas.

- [x] 9. Implementar Similarity Engine
  - [x] 9.1 Criar `backend/app/services/similarity_engine.py`
    - Implementar `SimilarityEngine.search(query_item, top_n, threshold)` gerando embedding do `QueryItem` e executando busca ANN no ChromaDB, retornando `list[SimilarityResult]` ordenada por `similarity_score` decrescente
    - Implementar `SimilarityEngine.explain(query_item, record)` usando LLM para gerar `AttributeContribution` com `contribution_score` e `justification` para cada atributo
    - Quando nenhum result acima do threshold, retornar lista vazia com flag para notificar consultor
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 4.3_

  - [x] 9.2 Integrar Similarity Engine no fluxo do `ChatOrchestrator`
    - Após confirmação do `QueryItem`, chamar `SimilarityEngine.search` e armazenar resultados na sessão
    - Expor resultados via `GET /sessions/{id}/results`
    - _Requirements: 3.1, 3.3_

  - [ ]* 9.3 Escrever property test para ordenação decrescente dos resultados (Property 5)
    - **Property 5: Ordenação decrescente dos resultados de similaridade**
    - **Validates: Requirements 3.2**

  - [ ]* 9.4 Escrever property test para cardinalidade top-N (Property 6)
    - **Property 6: Cardinalidade dos resultados respeita N configurado**
    - **Validates: Requirements 3.3**

- [x] 10. Implementar Report Generator e exportação
  - [x] 10.1 Criar `backend/app/services/report_generator.py`
    - Implementar `ReportGenerator.generate(session_id, format)` que monta `AnalysisReport` com todos os campos obrigatórios (summary, patterns, differences, recommendations com `supporting_record_id`, explainability com `attribute_contributions` ordenadas por `contribution_score` decrescente)
    - Suportar formato `"json"` (serialização fiel) e `"pdf"` (usando reportlab)
    - Se KB insuficiente, preencher `confidence_note`
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 6.1, 6.2, 6.3_

  - [x] 10.2 Criar endpoints de relatório em `backend/app/routers/sessions.py`
    - `POST /sessions/{id}/report` e `POST /sessions/{id}/export`
    - Retornar arquivo para download em até 5s; em caso de erro na geração de PDF, notificar e preservar relatório na sessão
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [ ]* 10.3 Escrever property test para completude estrutural do Analysis_Report (Property 7)
    - **Property 7: Completude estrutural do Analysis_Report**
    - **Validates: Requirements 4.2, 4.3, 4.4**

  - [ ]* 10.4 Escrever property test para round-trip JSON do relatório (Property 11)
    - **Property 11: Exportação JSON é round-trip fiel**
    - **Validates: Requirements 6.2**

- [x] 11. Implementar seleção de records e envio para API externa
  - [x] 11.1 Criar `backend/app/services/selection_manager.py`
    - Implementar lógica de seleção/desseleção de records: atualizar `Session.selected_record_ids` e retornar contagem atual
    - Endpoint `PATCH /sessions/{id}/selections` para atualizar seleção sem recarregar lista
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

  - [x] 11.2 Criar `backend/app/services/external_api_client.py`
    - Implementar `ExternalAPIClient.send(records, config)` que transmite records selecionados com todos os atributos e `similarity_score` para o endpoint configurado via variável de ambiente
    - Suportar `auth_type`: bearer, api_key, basic
    - Em caso de erro/timeout, retornar `SendResult` com `success=False`, `status_code` e `message`
    - Registrar log de cada operação: timestamp, consultant_id, quantidade de records, status HTTP
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

  - [x] 11.3 Criar endpoint de envio externo em `backend/app/routers/sessions.py`
    - `POST /sessions/{id}/send-external`
    - Retornar 400 se `selected_record_ids` estiver vazio
    - _Requirements: 9.1, 9.4_

  - [ ]* 11.4 Escrever property test para consistência do estado de seleção (Property 15)
    - **Property 15: Consistência do estado de seleção**
    - **Validates: Requirements 8.3, 8.4, 8.6**

  - [ ]* 11.5 Escrever property test para disponibilidade de envio condicionada à seleção (Property 16)
    - **Property 16: Disponibilidade da opção de envio condicionada à seleção**
    - **Validates: Requirements 9.1**

  - [ ]* 11.6 Escrever property test para completude do payload enviado (Property 17)
    - **Property 17: Completude do payload enviado para API externa**
    - **Validates: Requirements 9.2**

  - [ ]* 11.7 Escrever property test para auditoria de operações de envio (Property 18)
    - **Property 18: Auditoria de operações de envio externo**
    - **Validates: Requirements 9.6**

- [x] 12. Checkpoint — Garantir que todos os testes passam
  - Garantir que todos os testes passam, perguntar ao usuário se houver dúvidas.

- [x] 13. Implementar frontend React/TypeScript
  - [x] 13.1 Criar estrutura base do frontend em `frontend/src/`
    - Configurar Vite + React + TypeScript + TailwindCSS
    - Criar tipos TypeScript espelhando os modelos do backend: `Session`, `ChatMessage`, `SimilarityResult`, `AnalysisReport`, `Record`
    - Criar `frontend/src/api/client.ts` com funções axios para todos os endpoints REST
    - _Requirements: 1.1, 7.1_

  - [x] 13.2 Implementar tela de autenticação
    - Criar `frontend/src/pages/Login.tsx` com formulário de login
    - Armazenar JWT no `localStorage`, redirecionar para chat após login
    - Redirecionar para login em respostas 401/403
    - _Requirements: 7.1, 7.2_

  - [x] 13.3 Implementar Chat Interface
    - Criar `frontend/src/components/ChatInterface.tsx` com lista de mensagens, input de texto e envio
    - Exibir mensagens de confirmação de atributos com botões "Confirmar" / "Corrigir"
    - Exibir mensagens de erro descritivas retornadas pelo backend
    - _Requirements: 1.1, 1.2, 1.3, 1.5, 2.1, 2.3, 2.4_

  - [x] 13.4 Implementar Record Selector e painel de resultados
    - Criar `frontend/src/components/RecordSelector.tsx` com lista de records similares, checkboxes individuais, indicação visual de selecionados e contador de selecionados
    - Atualizar seleção via `PATCH /sessions/{id}/selections` sem recarregar lista
    - Botão "Enviar para API externa" habilitado apenas quando há records selecionados
    - _Requirements: 3.3, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 9.1_

  - [x] 13.5 Implementar Analysis Report View e exportação
    - Criar `frontend/src/components/AnalysisReport.tsx` exibindo summary, patterns, differences, recommendations e seção de explicabilidade
    - Botões de exportação PDF e JSON com feedback de sucesso/erro
    - _Requirements: 4.1, 4.2, 4.3, 6.1, 6.2, 6.3, 6.4_

- [x] 14. Integração final e wiring
  - [x] 14.1 Conectar todos os componentes no fluxo principal
    - Garantir que o fluxo completo funciona: login → criar sessão → descrever Query_Item → confirmar atributos → ver records similares → selecionar records → gerar relatório → exportar / enviar para API externa
    - Verificar que timeout de inatividade de 30 min encerra sessão e redireciona para login
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.5, 3.1, 4.1, 7.4_

  - [ ]* 14.2 Escrever testes de integração para o fluxo principal
    - Testar fluxo completo via TestClient do FastAPI
    - Testar upload de CSV e busca subsequente sem reinicialização
    - _Requirements: 5.7_

- [x] 15. Checkpoint final — Garantir que todos os testes passam
  - Garantir que todos os testes passam, perguntar ao usuário se houver dúvidas.

## Notes

- Tarefas marcadas com `*` são opcionais e podem ser puladas para um MVP mais rápido
- Cada tarefa referencia requisitos específicos para rastreabilidade
- Os property tests usam a biblioteca `hypothesis` com `@settings(max_examples=100)`
- Cada property test deve incluir o comentário: `# Feature: llm-consultant-advisor, Property {N}: {texto}`
- O LLM Provider e o Embedding Model são configuráveis via variáveis de ambiente — nenhum provider está hardcoded
