# Bateria E2E do novomodelo-mcp

Testes de integração do servidor MCP com as CLIs reais (`novomodelo-bridge`, `novomodelo`) e dados reais. A bateria mede se as tools respondem como esperado, se um agente de IA as escolhe e usa bem, e como o servidor se comporta sob carga concorrente.

Autores originais da bateria: Raquel Grillo e João Weydt.

## Estrutura

```
tests/e2e/
├── eval/        # Execução determinística das tools: registro de casos, validação, métricas e relatório
├── queries/     # Perguntas em linguagem natural a um agente; valida quais tools ele chamou (queries/README.md)
├── launcher/    # Servidor local (FastAPI, só em 127.0.0.1) que dispara as baterias pelo painel (launcher/README.md)
├── load/        # Teste de carga: N clientes, um servidor MCP por cliente (load/README.md)
├── frontend/    # Painel React/Vite com histórico, comparação e carga (frontend/README.md)
└── reports/     # Relatórios gerados pelo `eval`
```

## Pré-requisitos

- Python e as dependências da bateria: `uv sync --group e2e`
- `novomodelo-bridge` e `novomodelo` no `PATH`
- Para o painel: Node.js e `npm --prefix tests/e2e/frontend ci`
- Para as perguntas a agente (`queries/` e modo `agent` do `load/`): um provedor de agente instalado (`kiro-cli` ou `claude`), com as credenciais dele
- Opcional, para medir CPU e memória no teste de carga: `uv pip install psutil`

Os decks e demais dados dos casos ficam numa pasta `fixtures`, ao lado do código da bateria, ignorada pelo git.

## Como rodar

A bateria inteira de testes automatizados (as suítes `*_unit.py` e a de integração do `load/`):

```bash
uv sync --group e2e
uv run --group e2e pytest tests/e2e -q -o addopts=--strict-markers
```

O `pytest` padrão do repositório deixa `tests/e2e/` de fora (`addopts` com `--ignore=tests/e2e`); o `-o addopts=...` acima troca essa opção só para esta chamada.

Cada parte também roda sozinha:

```bash
uv run --group e2e python -m tests.e2e.eval.run --check          # verifica os pré-requisitos
uv run --group e2e python -m tests.e2e.eval.run --tool deck_list # uma tool; também --tag e --quiet
uv run --group e2e python -m tests.e2e.queries.run_queries       # recusa fora do executor em container
uv run --group e2e python -m tests.e2e.load.run --concurrency 4 --duration 30
```

## Configuração

Tudo vem de variável de ambiente ou de argumento. A bateria lê:

| Variável | O que faz | Default |
|---|---|---|
| `NOVOMODELO_MCP_TARGET` | Alvo do `eval`: `local` ou a URL de um servidor MCP | `local` |
| `NOVOMODELO_MCP_METRICS_PATH` | Arquivo JSONL do histórico de métricas do `eval` | pasta `metrics` da bateria |
| `QUERY_FIXTURES_DIR` | Pasta com os decks usados pelas perguntas | pasta `fixtures` da bateria |
| `QUERY_TIMEOUT_S` | Força um timeout único, em segundos, para todas as perguntas ao agente | não definida: cada caso usa o seu `timeout_s` de `queries/cases.yaml` (por caso ou grupo) |
| `KIRO_API_KEY` | Credencial do `kiro-cli`; sem ela, vale o login já feito no próprio `kiro-cli` | não definida |

Nunca grave credenciais em arquivo do repositório. Lê-las do ambiente, ou de um arquivo fora do repositório com permissão `600`, mantém o valor fora do código e dos logs.

## Painel

```bash
npm --prefix tests/e2e/frontend ci
npm --prefix tests/e2e/frontend run build
```

Lint, testes e servidor de desenvolvimento do painel estão em `frontend/README.md`.
