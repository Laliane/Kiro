# 🔧 Correção de Erro - Embeddings do Azure

## ❌ Erro Original
```
embedding generation failed — ErrorCode.LLM_UNAVAILABLE: Failed to generate embedding. 
Details: Error code: 400 - {'error': {'message': "Missing required parameter: 'messages'
```

## ✅ Problema Identificado
O código estava tentando usar a API de **chat** para gerar embeddings, mas embeddings requerem um **deployment específico** no Azure.

## 🔧 Solução Aplicada

### 1. Corrigido `embeddings.py`
- ✅ Validação de variáveis de ambiente obrigatórias
- ✅ Logs detalhados para debug
- ✅ Uso correto do `AzureOpenAIEmbeddings` do LangChain
- ✅ Documentação atualizada

### 2. Variáveis de Ambiente Necessárias

No seu arquivo `.env`, configure:

```bash
# Azure OpenAI - Configuração Geral
AZURE_OPENAI_API_KEY=sua_chave_azure_aqui
AZURE_OPENAI_ENDPOINT=https://seu-recurso.cognitiveservices.azure.com/
AZURE_OPENAI_API_VERSION=2024-08-01-preview

# Deployment para Chat (GPT-4)
AZURE_OPENAI_DEPLOYMENT=inic1537_gpt-4o_dev

# Deployment para Embeddings (IMPORTANTE!)
AZURE_OPENAI_EMBEDDING_MODEL=nome_do_seu_deployment_de_embedding
```

## 📝 Como Encontrar o Nome do Deployment de Embedding

### Opção 1: Via Portal Azure
1. Acesse o [Portal Azure](https://portal.azure.com)
2. Vá para seu recurso Azure OpenAI
3. Clique em "Deployments" no menu lateral
4. Procure por um deployment que use o modelo:
   - `text-embedding-ada-002` (modelo antigo)
   - `text-embedding-3-small` (recomendado)
   - `text-embedding-3-large` (mais preciso)
5. Copie o **nome do deployment** (não o nome do modelo)

### Opção 2: Via Azure CLI
```bash
az cognitiveservices account deployment list \
  --resource-group seu-resource-group \
  --name seu-recurso-openai \
  --query "[?properties.model.name contains(@, 'embedding')]"
```

## 🎯 Exemplo de Configuração Completa

```bash
# .env
AZURE_OPENAI_API_KEY=abc123def456...
AZURE_OPENAI_ENDPOINT=https://inic1537-dev-resource.cognitiveservices.azure.com/
AZURE_OPENAI_API_VERSION=2024-08-01-preview

# Chat (GPT-4)
AZURE_OPENAI_DEPLOYMENT=inic1537_gpt-4o_dev

# Embeddings (text-embedding-3-small)
AZURE_OPENAI_EMBEDDING_MODEL=inic1537_embedding_dev

# Base de conhecimento
DEFAULT_KB_CSV_PATH=./data/knowledge_base_example.csv
```

## 🚀 Testar a Correção

### 1. Reinicie o servidor
```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload
```

### 2. Verifique os logs
Ao iniciar, você deve ver:
```
INFO: Iniciando verificação da base de conhecimento...
INFO: Base de conhecimento vazia. Tentando carregar CSV padrão...
INFO: Carregando CSV da base de conhecimento: ./data/knowledge_base_example.csv
DEBUG: Generating embedding | deployment=inic1537_embedding_dev endpoint=https://...
DEBUG: Embedding generated successfully | length=1536
INFO: Base de conhecimento carregada com sucesso! Processados: 10
```

### 3. Se ainda houver erro
- Verifique se o deployment de embedding existe no Azure
- Confirme que o nome do deployment está correto (case-sensitive)
- Teste a API diretamente:

```bash
curl https://seu-endpoint.openai.azure.com/openai/deployments/seu-deployment-embedding/embeddings?api-version=2024-08-01-preview \
  -H "Content-Type: application/json" \
  -H "api-key: sua-chave" \
  -d '{"input": "teste"}'
```

## ⚠️ Caso Não Tenha Deployment de Embedding

Se você não tem um deployment de embedding criado no Azure:

### 1. Criar Deployment via Portal Azure
1. Acesse seu recurso Azure OpenAI
2. Clique em "Deployments" > "Create new deployment"
3. Selecione modelo: `text-embedding-3-small` (recomendado)
4. Dê um nome (ex: `embedding-deployment`)
5. Clique em "Create"

### 2. Ou use a Azure CLI
```bash
az cognitiveservices account deployment create \
  --resource-group seu-resource-group \
  --name seu-recurso-openai \
  --deployment-name embedding-deployment \
  --model-name text-embedding-3-small \
  --model-version "1" \
  --model-format OpenAI \
  --sku-capacity 120 \
  --sku-name Standard
```

## 📊 Verificar se está Funcionando

Depois de configurar, teste gerando um embedding:

```python
from app.services.embeddings import generate_embedding

text = "Este é um teste"
embedding = generate_embedding(text)
print(f"Embedding gerado com sucesso! Dimensão: {len(embedding)}")
# Saída esperada: Embedding gerado com sucesso! Dimensão: 1536
```

## 🔍 Debug Adicional

Se o erro persistir, ative logs detalhados:

```python
# No início do main.py
import logging
logging.basicConfig(level=logging.DEBUG)
```

Isso mostrará todos os detalhes da chamada à API do Azure.

## ✅ Checklist Final

- [ ] Variável `AZURE_OPENAI_API_KEY` está configurada
- [ ] Variável `AZURE_OPENAI_ENDPOINT` está configurada (com https://)
- [ ] Variável `AZURE_OPENAI_EMBEDDING_MODEL` tem o nome correto do deployment
- [ ] Deployment de embedding existe no Azure OpenAI
- [ ] Servidor foi reiniciado após mudanças no `.env`
- [ ] Logs mostram "Embedding generated successfully"

## 📞 Problemas Comuns

| Erro | Causa | Solução |
|------|-------|---------|
| `Missing required parameter: 'messages'` | Usando deployment de chat para embeddings | Configure `AZURE_OPENAI_EMBEDDING_MODEL` com deployment correto |
| `Deployment not found` | Nome do deployment incorreto | Verifique nome exato no Azure Portal |
| `401 Unauthorized` | API key incorreta ou expirada | Regenere a chave no Azure |
| `429 Rate limit` | Muitas requisições | Aguarde ou aumente quota no Azure |
| `AZURE_OPENAI_ENDPOINT is not set` | Variável não configurada | Configure todas variáveis obrigatórias |
