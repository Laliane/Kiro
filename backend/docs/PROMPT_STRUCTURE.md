# Estrutura do Prompt do Agente - Sistema RAG

## 📚 Visão Geral

O chat utiliza **RAG (Retrieval-Augmented Generation)** para responder perguntas baseadas na base de conhecimento do ChromaDB.

## 🏗️ Arquitetura da Solução

### 1. Fluxo RAG no `send_message`

```
Pergunta do Usuário
    ↓
Gerar Embedding da Pergunta
    ↓
Buscar Top-K Documentos Similares no ChromaDB
    ↓
Construir Prompt de Sistema com Contexto
    ↓
Enviar ao LLM: [System Prompt + Histórico + Pergunta]
    ↓
Resposta do Agente
```

### 2. Componentes Principais

#### `_retrieve_relevant_context(query, top_k=5)`
**Função**: Busca documentos relevantes no ChromaDB
- Gera embedding da pergunta do usuário
- Busca os top-K documentos mais similares
- Formata o contexto com relevância de cada documento
- Retorna string formatada pronta para o prompt

**Exemplo de Saída**:
```
[Documento 1] (Relevância: 95%)
id: 1, name: Notebook Dell, description: Notebook Dell Inspiron 15..., price: 3500.00

[Documento 2] (Relevância: 87%)
id: 4, name: Monitor LG, description: Monitor LG UltraWide 29 polegadas..., price: 1200.00
```

#### `_build_system_prompt(context)`
**Função**: Constrói o prompt de sistema com instruções
- Define o papel do agente
- Injeta o contexto recuperado
- Especifica regras de comportamento
- Define formato de resposta

**Estrutura do Prompt**:

1. **PAPEL**: Define identidade do agente
   ```
   "Você é um assistente especializado em análise de dados..."
   ```

2. **BASE DE CONHECIMENTO**: Contexto recuperado do ChromaDB
   ```
   "## BASE DE CONHECIMENTO DISPONÍVEL
   [Documentos relevantes formatados]"
   ```

3. **INSTRUÇÕES**: Como se comportar
   - Basear-se sempre nos dados fornecidos
   - Não inventar informações
   - Citar documentos quando responder
   - Ser conciso e objetivo

4. **LIMITAÇÕES**: O que NÃO fazer
   - Não inventar dados
   - Não responder fora do escopo
   - Não fazer suposições sem dados

5. **FORMATO**: Como estruturar respostas
   - Usar listas
   - Destacar informações importantes
   - Ser transparente sobre limitações

## 🎯 Como Funciona no Código

### Localização: `backend/app/services/chat_orchestrator.py`

#### Método `send_message` (modificado)

```python
def send_message(self, session_id: str, message: str, use_rag: bool = True):
    # 1. Valida sessão
    # 2. Recupera contexto do ChromaDB (RAG)
    context = _retrieve_relevant_context(message, top_k=5)
    
    # 3. Constrói prompt de sistema
    system_prompt = _build_system_prompt(context)
    
    # 4. Monta histórico: [System] + [User/Assistant histórico]
    history_with_context = [system_message] + conversation_history
    
    # 5. Chama LLM
    reply = _call_llm(history_with_context)
    
    # 6. Retorna resposta
    return assistant_message
```

## ⚙️ Parâmetros Configuráveis

### 1. `top_k` (padrão: 5)
Número de documentos recuperados do ChromaDB
- **Valor baixo (3-5)**: Respostas mais focadas, menos contexto
- **Valor alto (10-20)**: Mais contexto, pode confundir o modelo

### 2. `use_rag` (padrão: True)
Ativar/desativar RAG por sessão
- **True**: Usa base de conhecimento (recomendado)
- **False**: Chat livre sem contexto específico

### 3. Threshold de Similaridade
Ajustável em `_retrieve_relevant_context`
```python
# Exemplo: filtrar por relevância mínima
if similarity < 0.7:  # Apenas 70%+ de similaridade
    continue
```

## 🔧 Personalizações Possíveis

### 1. Modificar o Prompt de Sistema

Edite a função `_build_system_prompt` em `chat_orchestrator.py`:

```python
def _build_system_prompt(context: str) -> str:
    return f"""Você é um [SEU PAPEL CUSTOMIZADO].
    
## BASE DE CONHECIMENTO
{context}

## SUAS INSTRUÇÕES CUSTOMIZADAS
1. ...
2. ...
"""
```

### 2. Adicionar Filtros ao RAG

Em `_retrieve_relevant_context`, adicione filtros:

```python
results = collection.query(
    query_embeddings=[query_embedding],
    n_results=top_k,
    where={"attr_category": "Eletrônicos"},  # Filtro por categoria
    include=["metadatas", "documents", "distances"]
)
```

### 3. Ajustar Formato da Resposta

Modifique as instruções no prompt de sistema:

```python
## FORMATO DE RESPOSTA
- Use tabelas markdown quando comparar produtos
- Sempre inclua preços formatados
- Adicione emojis para melhor visualização
```

## 📊 Exemplo de Uso

### Entrada do Usuário:
```
"Preciso de um notebook para trabalho, algo em torno de 3500 reais"
```

### Contexto Recuperado (RAG):
```
[Documento 1] (Relevância: 95%)
id: 1, name: Notebook Dell, description: Notebook Dell Inspiron 15 com processador Intel Core i5, price: 3500.00

[Documento 2] (Relevância: 78%)
id: 9, name: Placa de Vídeo, description: Placa de Vídeo NVIDIA GeForce RTX 3060..., price: 2500.00
```

### Resposta do Agente:
```
De acordo com a base de conhecimento, encontrei uma opção que atende exatamente seu orçamento:

**Notebook Dell Inspiron 15** (Documento 1 - Relevância: 95%)
- Preço: R$ 3.500,00
- Processador: Intel Core i5
- Ideal para trabalho

Este produto tem alta relevância com sua busca e está dentro do seu orçamento especificado.
```

## 🚀 Melhorias Futuras

1. **Cache de Embeddings**: Armazenar embeddings de queries frequentes
2. **Re-ranking**: Usar modelo de re-ranking após busca inicial
3. **Prompt Dinâmico**: Adaptar instruções baseado no tipo de pergunta
4. **Multi-turn RAG**: Manter contexto relevante entre turnos
5. **Feedback Loop**: Ajustar relevância baseado em feedback do usuário

## 📝 Notas Técnicas

- **Embeddings**: Gerados via Azure OpenAI (text-embedding-3-small)
- **Similaridade**: Cosine distance convertida em score (0-1)
- **LLM**: Azure GPT-4o via LangChain
- **Armazenamento**: ChromaDB persistente em disco
- **Sistema de Mensagens**: Suporta roles: system, user, assistant
