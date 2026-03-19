# Kiro - LLM Consultant Advisor

Sistema de análise de dados com LLM e busca por similaridade vetorial.

## Configuração Inicial

### 1. Configurar variáveis de ambiente

Copie o arquivo `.env.example` para `.env` no diretório `backend/`:

```bash
cd backend
cp .env.example .env
```

Edite o arquivo `.env` e configure suas credenciais:
- `AZURE_OPENAI_API_KEY`: Sua chave da Azure OpenAI
- `AZURE_OPENAI_ENDPOINT`: Endpoint do seu recurso Azure
- `AZURE_OPENAI_DEPLOYMENT`: Nome do deployment
- `DEFAULT_KB_CSV_PATH`: Caminho para o CSV da base de conhecimento (opcional)

### 2. Base de Conhecimento (CSV)

O sistema carrega automaticamente a base de conhecimento ao iniciar se você configurar `DEFAULT_KB_CSV_PATH` no arquivo `.env`.

**Opção 1: Carregamento Automático (Recomendado)**
1. Coloque seu arquivo CSV em `backend/data/knowledge_base.csv`
2. Configure no `.env`: `DEFAULT_KB_CSV_PATH=./data/knowledge_base.csv`
3. O CSV será carregado automaticamente ao iniciar o backend

**Opção 2: Upload Manual**
- Use o endpoint `POST /admin/knowledge-base/upload` para fazer upload do CSV
- Útil para atualizar a base de conhecimento sem reiniciar o servidor

## Executar o Projeto

### Backend
```bash
cd backend

# Ativar ambiente virtual (recomendado)
python -m venv venv
source venv/bin/activate  # macOS/Linux
# ou: venv\Scripts\activate  # Windows

# Instalar dependências
pip install -e ".[dev]"

# Executar servidor
uvicorn app.main:app --reload
```

### Frontend
```bash
# Em outro terminal
cd frontend
npm install
npm run dev
```

## Estrutura do Projeto

```
backend/
  app/
    routers/       # Endpoints da API
    services/      # Lógica de negócio
    database.py    # Integração com ChromaDB
    main.py        # Aplicação FastAPI
  data/            # Diretório para arquivos CSV (criar manualmente se necessário)
  chroma_data/     # Dados persistentes do ChromaDB (criado automaticamente)

frontend/
  src/
    components/    # Componentes React
    pages/         # Páginas da aplicação
    api/           # Cliente da API
```

## Funcionalidades Principais

### 🤖 Chat com RAG (Retrieval-Augmented Generation)
O sistema utiliza RAG para responder perguntas baseadas na base de conhecimento:
- Busca automática de documentos relevantes no ChromaDB
- Prompt de sistema com instruções e contexto
- Respostas baseadas em dados reais, não inventadas
- Citação de fontes com nível de relevância

📖 **Documentação completa**: [`backend/docs/PROMPT_STRUCTURE.md`](backend/docs/PROMPT_STRUCTURE.md)

### 📡 Endpoints Principais

- `POST /auth/login` - Autenticação
- `POST /sessions` - Criar sessão de chat
- `POST /sessions/{id}/messages` - Enviar mensagem (com RAG automático)
- `POST /admin/knowledge-base/upload` - Upload de CSV
- `GET /admin/knowledge-base/status` - Status da base de conhecimento

## 📚 Documentação Adicional

- [Estrutura do Prompt e RAG](backend/docs/PROMPT_STRUCTURE.md) - Como funciona o agente conversacional
- [Formato da Base de Conhecimento](backend/data/README.md) - Como preparar seus dados CSV
