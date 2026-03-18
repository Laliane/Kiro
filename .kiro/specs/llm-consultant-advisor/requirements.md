# Requirements Document

## Introduction

Este sistema permite que um consultor interaja com um LLM (Large Language Model) para obter orientações, analisar dados estruturados e encontrar registros similares em uma base de dados comparando-os com um item fornecido pelo próprio consultor. O objetivo é apoiar a tomada de decisão do consultor com base em histórico, padrões e similaridade semântica ou vetorial.

## Glossary

- **System**: O sistema LLM Consultant Advisor como um todo.
- **Consultant**: O usuário humano que interage com o sistema para obter análises e recomendações.
- **LLM**: Large Language Model — modelo de linguagem utilizado para processar linguagem natural e gerar respostas.
- **Query_Item**: A descrição em linguagem natural fornecida pelo Consultant como referência para busca de similaridade.
- **Record**: Uma entrada individual na base de dados do sistema.
- **Knowledge_Base**: O repositório de registros estruturados, originado de um arquivo CSV, utilizado para análise e busca de similaridade.
- **Similarity_Engine**: O componente responsável por calcular e ranquear a similaridade entre o Query_Item e os Records da Knowledge_Base.
- **Chat_Interface**: O componente de interface de chat dedicado e exclusivo para a interação conversacional entre o Consultant e o LLM.
- **Analysis_Report**: O documento gerado pelo sistema contendo os resultados da análise e registros similares.
- **Session**: Uma sessão de interação entre o Consultant e o System.
- **Attribute_Extractor**: O componente responsável por interpretar a descrição em linguagem natural do Query_Item e extrair os atributos relevantes para a busca.
- **CSV_Preprocessor**: O componente responsável por ler, limpar e transformar os registros do arquivo CSV antes da geração de embeddings.

---

## Requirements

### Requirement 1: Interação Conversacional com o LLM via Chat Dedicado

**User Story:** Como consultor, quero ter acesso a um chat dedicado para conversar com o LLM em linguagem natural, para que eu possa enviar pedidos, fazer perguntas, obter orientações e explorar informações sem precisar de conhecimento técnico.

#### Acceptance Criteria

1. THE System SHALL disponibilizar ao Consultant uma Chat_Interface dedicada e exclusiva para toda a interação com o LLM, separada de qualquer outra interface do sistema.
2. THE Chat_Interface SHALL aceitar mensagens de texto em linguagem natural enviadas pelo Consultant.
3. WHEN o Consultant envia uma mensagem pela Chat_Interface, THE LLM SHALL gerar uma resposta contextualizada dentro de 10 segundos.
4. WHILE uma Session está ativa, THE Chat_Interface SHALL manter o histórico completo da conversa e utilizá-lo como contexto para respostas subsequentes.
5. IF o LLM não conseguir processar uma mensagem, THEN THE System SHALL exibir uma mensagem de erro descritiva ao Consultant na Chat_Interface e registrar o erro internamente.
6. THE Chat_Interface SHALL suportar múltiplas Sessions independentes para o mesmo Consultant.

---

### Requirement 2: Fornecimento do Query Item pelo Consultor em Linguagem Natural

**User Story:** Como consultor, quero descrever o item de referência em linguagem natural diretamente no chat, para que o sistema interprete minha descrição e extraia os atributos necessários para a busca por registros similares.

#### Acceptance Criteria

1. THE Chat_Interface SHALL permitir que o Consultant forneça um Query_Item exclusivamente como descrição em linguagem natural, sem exigir formato estruturado, JSON ou arquivo.
2. WHEN o Consultant fornece a descrição do Query_Item, THE Attribute_Extractor SHALL interpretar o texto e extrair os atributos relevantes para a busca de similaridade.
3. WHEN os atributos são extraídos, THE System SHALL apresentar ao Consultant os atributos identificados para confirmação antes de prosseguir com a busca.
4. IF o Attribute_Extractor não conseguir identificar atributos suficientes na descrição fornecida, THEN THE System SHALL solicitar ao Consultant, via Chat_Interface, informações adicionais sobre os atributos ausentes.
5. WHEN o Query_Item é confirmado pelo Consultant, THE System SHALL disponibilizar o item para análise pela Similarity_Engine.

---

### Requirement 3: Busca de Registros Similares na Knowledge Base

**User Story:** Como consultor, quero que o sistema encontre registros similares ao item que forneci, para que eu possa identificar padrões, precedentes e casos relacionados.

#### Acceptance Criteria

1. WHEN um Query_Item validado está disponível, THE Similarity_Engine SHALL calcular a similaridade entre o Query_Item e todos os Records da Knowledge_Base.
2. THE Similarity_Engine SHALL retornar os Records ordenados por grau de similaridade em ordem decrescente.
3. THE System SHALL apresentar ao Consultant os N registros mais similares, onde N é configurável pelo Consultant com valor padrão de 10.
4. WHEN nenhum Record com similaridade acima do limiar mínimo configurado for encontrado, THE System SHALL informar ao Consultant que nenhum resultado relevante foi identificado.
5. THE Similarity_Engine SHALL suportar busca por similaridade semântica utilizando embeddings vetoriais.

---

### Requirement 4: Análise de Dados pelo LLM com Explicabilidade da Similaridade

**User Story:** Como consultor, quero que o LLM analise os registros similares encontrados e explique quais atributos mais influenciaram a escolha, para que eu receba insights, recomendações e entenda o raciocínio por trás dos resultados.

#### Acceptance Criteria

1. WHEN registros similares são retornados pela Similarity_Engine, THE LLM SHALL analisar os Records e gerar um Analysis_Report com insights e padrões identificados.
2. THE Analysis_Report SHALL conter: resumo dos registros similares, padrões identificados, diferenças relevantes em relação ao Query_Item e recomendações para o Consultant.
3. THE Analysis_Report SHALL incluir uma seção de explicabilidade que identifica e ordena os atributos do Query_Item que mais contribuíram para a seleção de cada Record similar, com justificativa em linguagem natural.
4. THE LLM SHALL fundamentar cada recomendação em pelo menos um Record específico da Knowledge_Base, citando o identificador do Record.
5. IF a Knowledge_Base não contiver Records suficientes para análise confiável, THEN THE LLM SHALL indicar explicitamente a limitação no Analysis_Report.
6. WHEN o Consultant solicita esclarecimentos sobre o Analysis_Report ou sobre a explicabilidade dos atributos, THE LLM SHALL responder com base no contexto da Session atual.

---

### Requirement 5: Gerenciamento e Pré-processamento da Knowledge Base a partir de CSV

**User Story:** Como consultor, quero que a base de dados seja carregada a partir de um arquivo CSV e que os registros sejam pré-processados e armazenados de forma otimizada, para que as buscas por similaridade vetorial produzam resultados de alta qualidade.

#### Acceptance Criteria

1. THE System SHALL aceitar um arquivo CSV como fonte de dados para a Knowledge_Base, contendo múltiplos registros estruturados.
2. WHEN um arquivo CSV é fornecido, THE CSV_Preprocessor SHALL ler, limpar e normalizar os registros, removendo duplicatas, tratando valores ausentes e padronizando formatos de campos antes da geração de embeddings.
3. WHEN os registros estão pré-processados, THE System SHALL gerar embeddings vetoriais de alta qualidade para cada Record, combinando os campos relevantes em uma representação textual enriquecida antes da vetorização.
4. THE System SHALL armazenar os embeddings gerados em um banco de dados vetorial otimizado para buscas de similaridade de alta performance.
5. WHEN o arquivo CSV é atualizado e recarregado, THE CSV_Preprocessor SHALL reprocessar apenas os Records novos ou modificados e atualizar os embeddings correspondentes na Knowledge_Base.
6. IF o arquivo CSV contiver registros com campos obrigatórios ausentes após o pré-processamento, THEN THE System SHALL registrar os registros inválidos em um log de erros e prosseguir com os registros válidos.
7. THE System SHALL garantir que operações de carga e atualização da Knowledge_Base sejam refletidas nas buscas subsequentes sem necessidade de reinicialização.

---

### Requirement 6: Exportação do Analysis Report

**User Story:** Como consultor, quero exportar o relatório de análise gerado, para que eu possa compartilhá-lo ou arquivá-lo fora do sistema.

#### Acceptance Criteria

1. WHEN um Analysis_Report é gerado, THE System SHALL disponibilizar a opção de exportação ao Consultant.
2. THE System SHALL suportar exportação do Analysis_Report nos formatos PDF e JSON.
3. WHEN o Consultant solicita a exportação, THE System SHALL gerar o arquivo e disponibilizá-lo para download em até 5 segundos.
4. IF ocorrer um erro durante a exportação, THEN THE System SHALL notificar o Consultant com uma mensagem descritiva e preservar o Analysis_Report na Session.

---

### Requirement 7: Segurança e Controle de Acesso

**User Story:** Como administrador, quero que o acesso ao sistema seja controlado, para que apenas consultores autorizados possam interagir com os dados e o LLM.

#### Acceptance Criteria

1. THE System SHALL exigir autenticação do Consultant antes de iniciar uma Session.
2. WHEN um Consultant não autenticado tenta acessar qualquer funcionalidade, THE System SHALL redirecionar para o fluxo de autenticação.
3. THE System SHALL registrar em log todas as Sessions, incluindo identificador do Consultant, timestamp de início e fim, e Query_Items utilizados.
4. WHILE uma Session está inativa por mais de 30 minutos, THE System SHALL encerrar a Session automaticamente e exigir nova autenticação.
5. THE System SHALL garantir que os dados da Knowledge_Base e os Analysis_Reports sejam acessíveis apenas ao Consultant autenticado na Session vigente.

---

### Requirement 8: Seleção Manual de Registros Similares pelo Consultor

**User Story:** Como consultor, quero escolher manualmente quais registros similares ranqueados desejo utilizar, para que eu tenha controle sobre quais itens serão considerados na análise e em integrações posteriores.

#### Acceptance Criteria

1. WHEN os Records similares são apresentados ao Consultant, THE System SHALL permitir que o Consultant selecione individualmente qualquer quantidade de Records da lista ranqueada.
2. THE System SHALL exibir o estado de seleção de cada Record de forma visualmente distinta, indicando quais estão marcados como escolhidos.
3. WHEN o Consultant marca ou desmarca um Record, THE System SHALL atualizar imediatamente o conjunto de Records selecionados sem recarregar a lista completa.
4. THE System SHALL permitir que o Consultant altere sua seleção a qualquer momento durante a Session ativa, adicionando ou removendo Records do conjunto selecionado.
5. IF o Consultant não selecionar nenhum Record, THEN THE System SHALL manter o conjunto de Records selecionados vazio e impedir ações que dependam de seleção sem notificar o Consultant sobre a ausência de itens selecionados.
6. THE System SHALL disponibilizar ao Consultant uma indicação do total de Records atualmente selecionados.

---

### Requirement 9: Envio de Registros Selecionados para API Externa

**User Story:** Como consultor, quero enviar os registros que selecionei para uma API externa, para que eu possa integrá-los com outros sistemas e fluxos de trabalho.

#### Acceptance Criteria

1. WHEN o Consultant possui ao menos um Record selecionado, THE System SHALL disponibilizar a opção de envio dos Records selecionados para uma API externa configurada.
2. WHEN o Consultant aciona o envio, THE System SHALL transmitir os Records selecionados para o endpoint da API externa no formato JSON, incluindo todos os atributos de cada Record e seus respectivos scores de similaridade.
3. WHEN a API externa retorna uma resposta de sucesso, THE System SHALL notificar o Consultant com uma confirmação de envio bem-sucedido.
4. IF a API externa retornar um erro ou não estiver disponível, THEN THE System SHALL notificar o Consultant com uma mensagem descritiva contendo o código de status retornado e preservar os Records selecionados para nova tentativa.
5. THE System SHALL permitir a configuração do endpoint da API externa, incluindo URL e credenciais de autenticação, sem necessidade de alteração de código.
6. THE System SHALL registrar em log cada operação de envio, incluindo timestamp, identificador do Consultant, quantidade de Records enviados e status da resposta da API externa.
