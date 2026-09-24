# Relatório de Migração: Kayfabe-Loop para Google Gemini

Este documento resume as alterações realizadas no orquestrador `kayfabe-loop` para migrar de Anthropic Claude para **Google Gemini via Vertex AI**, otimizando custo e aproveitando a janela de contexto de 2M tokens.

## 1. Mapeamento de Modelos (Router)

O `model_router.py` e o `config.yaml` foram atualizados para usar a hierarquia Gemini:

| Categoria de Tarefa | Modelo Gemini | Função no Projeto |
| :--- | :--- | :--- |
| `design_or_spike` | **Gemini 1.5 Pro** | Engenharia reversa complexa, análise de ioctls e arquitetura. |
| `implementation` | **Gemini 1.5 Flash** | Escrita de código Rust contra padrões estabelecidos e iterações rápidas. |
| `verification` | **Gemini 1.5 Flash** | Geração de testes e oráculos diferenciais. |
| `chore` | **Gemini 2.0 Flash** | Atualização de documentação, logs e tarefas de limpeza. |

## 2. Projeção de Custos Atualizada (P0 a P8)

Com base no `task_graph.yaml` e nos preços atuais do Vertex AI (setembro/2026), a economia em tokens é de aproximadamente **86%**.

| Componente | Custo Original (Claude) | **Custo Atualizado (Gemini)** | Redução |
| :--- | :--- | :--- | :--- |
| **Tokens (Sem Caching)** | ~$683.00 | **$92.01** | **-86.5%** |
| **Tokens (40% Cache Hit)** | ~$525.00 | **$67.74** | **-87.0%** |
| **GKE L4 Infra (Testes)** | $1,309.00 | $1,309.00 | 0% |
| **Total Estimado** | **~$2,000.00** | **~$1,400.00** | **-30%** |

## 3. Alterações nos Arquivos do Código

*   **`orchestrator/pricing.py`**: Substituídas as tabelas de preços e IDs de modelos da Anthropic pelos valores do Gemini no Vertex AI.
*   **`orchestrator/vertex_client.py`**: Classe `VertexClaudeClient` substituída por `VertexGeminiClient`, utilizando a biblioteca nativa `vertexai.generative_models`.
*   **`orchestrator/model_router.py`**: Lógica de escalonamento atualizada para apontar para `gemini-1.5-pro` em caso de falhas repetidas.
*   **`orchestrator/config.yaml`**: Região padrão alterada para `us-central1` e chaves de roteamento migradas para Gemini.
*   **`orchestrator/task_graph.yaml`**: Buckets de planejamento atualizados com os novos identificadores.

## 4. Próximos Passos (Prontos para Execução)

O sistema foi corrigido mas **não foi executado**, conforme sua instrução.
1.  **Instalação de Dependências**: O `requirements.txt` agora exige `google-cloud-aiplatform>=1.70`.
2.  **Autenticação**: Certifique-se de que o ambiente tem acesso ao projeto GCP via `gcloud auth application-default login`.
3.  **Execução**: O comando para iniciar o loop permanece `python main.py run --phase P0`.

---
*Relatório gerado em 24/09/2026 como parte do projeto **Wonder GPU**.*
