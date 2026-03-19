# 🧪 Guia de Teste - Chat com RAG

## 🚀 Iniciando o Sistema

### 1. Preparar o Ambiente

```bash
# Terminal 1 - Backend
cd backend
source venv/bin/activate
export DEFAULT_KB_CSV_PATH=./data/knowledge_base_example.csv
uvicorn app.main:app --reload
```

Você deve ver nos logs:
```
INFO: Iniciando verificação da base de conhecimento...
INFO: Base de conhecimento vazia. Tentando carregar CSV padrão...
INFO: Carregando CSV da base de conhecimento: ./data/knowledge_base_example.csv
INFO: Base de conhecimento carregada com sucesso! Processados: 10, Ignorados: 0
```

### 2. Testar Endpoints

## 📋 Exemplos de Perguntas e Respostas Esperadas

### Exemplo 1: Busca por Produto Específico

**Pergunta:**
```json
{
  "message": "Preciso de um notebook para trabalho, algo em torno de 3500 reais"
}
```

**Comportamento Esperado:**
1. Sistema gera embedding da pergunta
2. Busca no ChromaDB produtos similares
3. Encontra "Notebook Dell" (preço 3500, relevância alta)
4. Constrói prompt com contexto
5. LLM responde citando o documento

**Resposta Esperada:**
```
De acordo com a base de conhecimento, encontrei uma opção que atende exatamente seu orçamento:

**Notebook Dell Inspiron 15** (Documento 1 - Relevância: 95%)
- Preço: R$ 3.500,00
- Categoria: Eletrônicos
- Descrição: Notebook Dell Inspiron 15 com processador Intel Core i5
- Estoque disponível: 25 unidades

Este produto tem alta relevância com sua busca e está dentro do seu orçamento especificado.
```

### Exemplo 2: Comparação de Produtos

**Pergunta:**
```json
{
  "message": "Quais periféricos você tem disponíveis? Preciso de mouse e teclado"
}
```

**Comportamento Esperado:**
- Busca retorna múltiplos documentos da categoria "Periféricos"
- LLM compara e lista opções
- Cita relevância de cada item

**Resposta Esperada:**
```
Encontrei vários periféricos relevantes na base de conhecimento:

**Mouse e Teclado:**

1. **Mouse Logitech MX Master 3** (Relevância: 92%)
   - Preço: R$ 450,00
   - Mouse sem fio com sensor de alta precisão
   - Estoque: 150 unidades

2. **Teclado Mecânico Keychron K2** (Relevância: 89%)
   - Preço: R$ 650,00
   - Teclado mecânico com switches blue
   - Estoque: 80 unidades

**Total para o conjunto:** R$ 1.100,00

Ambos os produtos estão disponíveis em estoque e são altamente relevantes para sua necessidade.
```

### Exemplo 3: Pergunta Fora do Escopo

**Pergunta:**
```json
{
  "message": "Qual é a capital da França?"
}
```

**Comportamento Esperado:**
- Sistema busca no ChromaDB mas não encontra relevância
- Prompt instrui a não inventar informações
- LLM responde honestamente

**Resposta Esperada:**
```
Essa informação não está disponível na minha base de conhecimento atual, que contém dados sobre produtos eletrônicos e periféricos.

Posso ajudá-lo com informações sobre:
- Notebooks e computadores
- Periféricos (mouse, teclado, webcam, headset)
- Componentes (SSD, memória RAM, placas de vídeo, fontes)

Como posso auxiliá-lo com esses produtos?
```

### Exemplo 4: Busca por Faixa de Preço

**Pergunta:**
```json
{
  "message": "O que você tem disponível entre 500 e 800 reais?"
}
```

**Comportamento Esperado:**
- Busca retorna produtos diversos
- LLM filtra por faixa de preço mencionada
- Lista opções ordenadas

**Resposta Esperada:**
```
Encontrei os seguintes produtos na faixa de R$ 500 a R$ 800:

1. **Teclado Mecânico Keychron K2** - R$ 650,00 (Relevância: 85%)
   - Categoria: Periféricos
   - Teclado mecânico com switches blue
   - Estoque: 80 unidades

2. **Headset HyperX Cloud II** - R$ 550,00 (Relevância: 82%)
   - Categoria: Periféricos
   - Headset gamer com som surround 7.1
   - Estoque: 95 unidades

3. **SSD Samsung 970 EVO Plus 1TB** - R$ 800,00 (Relevância: 78%)
   - Categoria: Armazenamento
   - SSD NVMe M.2
   - Estoque: 200 unidades

4. **Fonte Corsair 650W** - R$ 550,00 (Relevância: 75%)
   - Categoria: Componentes
   - 80 Plus Bronze modular
   - Estoque: 60 unidades

Todos os produtos estão disponíveis em estoque.
```

## 🔍 Verificando o RAG em Ação

### Ver Logs do Sistema

Os logs mostram o funcionamento do RAG:

```
INFO: RAG context retrieved for session abc-123
INFO: Retrieved 5 documents with similarities: [0.95, 0.87, 0.82, 0.78, 0.75]
```

### Desabilitar RAG (Teste)

Para comparar respostas COM e SEM RAG:

```python
# No endpoint ou código
response = orchestrator.send_message(session_id, message, use_rag=False)
```

**Com RAG**: Respostas baseadas em dados reais
**Sem RAG**: Respostas genéricas, pode inventar informações

## 🐛 Troubleshooting

### Base de Conhecimento Vazia

**Sintoma:**
```
⚠️ Base de conhecimento vazia. Configure DEFAULT_KB_CSV_PATH ou faça upload de um CSV.
```

**Solução:**
1. Verificar variável de ambiente: `echo $DEFAULT_KB_CSV_PATH`
2. Verificar se arquivo existe: `ls ./data/knowledge_base_example.csv`
3. Recarregar: Fazer upload via endpoint `/admin/knowledge-base/upload`

### RAG Retornando Documentos Irrelevantes

**Sintoma:**
Respostas citam documentos pouco relacionados

**Soluções:**
1. Aumentar threshold de similaridade em `_retrieve_relevant_context`
2. Reduzir `top_k` para retornar menos documentos
3. Melhorar qualidade dos dados no CSV (descrições mais detalhadas)

### LLM Inventando Informações

**Sintoma:**
Resposta contém dados que não estão no CSV

**Soluções:**
1. Verificar se o prompt de sistema está sendo aplicado
2. Fortalecer instruções no `_build_system_prompt`
3. Ajustar temperatura do modelo (reduzir para 0.3-0.5)

## 📊 Métricas de Qualidade

### Como Avaliar as Respostas

1. **Relevância**: Documentos citados são pertinentes?
2. **Precisão**: Dados citados estão corretos conforme CSV?
3. **Completude**: Resposta atende a pergunta completamente?
4. **Transparência**: Sistema indica quando não sabe?
5. **Citação**: Fontes são mencionadas adequadamente?

### Exemplo de Avaliação

| Critério | Score | Nota |
|----------|-------|------|
| Relevância | 5/5 | Documentos altamente relacionados |
| Precisão | 5/5 | Dados exatos do CSV |
| Completude | 4/5 | Poderia sugerir produtos relacionados |
| Transparência | 5/5 | Clara sobre limitações |
| Citação | 5/5 | Cita documentos e relevância |
| **TOTAL** | **24/25** | **96% - Excelente** |

## 🎯 Próximos Passos

1. ✅ Sistema RAG funcionando
2. ✅ Base de conhecimento carregada
3. ✅ Prompt estruturado
4. 🔄 Testar com diferentes perguntas
5. 🔄 Ajustar prompt conforme necessidade
6. 🔄 Adicionar mais dados ao CSV
7. 🔄 Implementar feedback do usuário
