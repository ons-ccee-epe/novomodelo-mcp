# Bateria E2E do novomodelo-mcp

Testes de integração do servidor MCP com as CLIs reais (`novomodelo-bridge`, `novomodelo`) e dados reais. A bateria mede se as tools respondem como esperado, se um agente de IA as escolhe e usa bem, e como o servidor se comporta sob carga concorrente.

Autores originais da bateria: Raquel Pereira Grillo e João Weydt.

## Estrutura

```
tests/e2e/
├── queries/     # Perguntas em linguagem natural a um agente; valida quais tools ele chamou (queries/README.md)
├── launcher/    # Servidor local (FastAPI, só em 127.0.0.1) que dispara as baterias pelo painel (launcher/README.md)
├── load/        # Teste de carga: N clientes, um servidor MCP por cliente (load/README.md)
└── frontend/    # Painel React/Vite com histórico, comparação e carga (frontend/README.md)
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
uv run --group e2e python -m tests.e2e.queries.run_queries       # recusa fora do executor em container
uv run --group e2e python -m tests.e2e.load.run --concurrency 4 --duration 30
```

## Rodada com agentes e veredito

O fluxo roda no executor em container (podman), pela CLI `python -m tests.e2e`:

```bash
uv run --group e2e python -m tests.e2e verificar
uv run --group e2e python -m tests.e2e preparar --mcp sem caminho/da/wheel.whl
uv run --group e2e python -m tests.e2e rodar --mcp caminho/da/wheel.whl --rodada ID
uv run --group e2e python -m tests.e2e go-no-go ID --alvo CONFIG [--baseline RODADA] [--baseline-config CONFIG]
uv run --group e2e python -m tests.e2e marcar-lancamento ID VERSAO --config CONFIG
```

- `verificar` confere motor, pastas, token e volume do Kiro; `preparar` constrói as imagens e cria o secret do token; `rodar` grava o manifesto e um registro por execução e é retomável pelo `--rodada`.
- `go-no-go` grava `relatorio-go-no-go.md` e `junit.xml` na pasta da rodada. A base de comparação é, nesta ordem: `--baseline-config` (na mesma rodada, ou na de `--baseline` quando vêm juntas), `--baseline`, o último lançamento marcado, ou nenhuma (só a determinística bloqueia). O relatório lista, por configuração, a versão, o SHA-256 e a origem do wheel, e as versões de cada imagem.
- `marcar-lancamento` torna uma configuração da rodada a base do próximo `go-no-go`; só por decisão de quem libera a versão.

Variáveis de ambiente da `Config` (todas opcionais):

| Variável | O que faz | Default |
|---|---|---|
| `NOVOMODELO_BATERIA_MOTOR` | Motor de container; só o `podman` é aceito | `podman`, se estiver no `PATH` |
| `NOVOMODELO_BATERIA_RESULTADOS` | Pasta das rodadas e do `lancamentos.json` | pasta de dados do usuário, `novomodelo-mcp-bateria/resultados` |
| `NOVOMODELO_BATERIA_CASOS` | Pasta com um subdiretório por caso grande | não definida: esses casos ficam pulados |
| `NOVOMODELO_BATERIA_CENARIOS_EXTRA` | Pasta de cenários extras, fora do repositório | não definida |
| `NOVOMODELO_BATERIA_TOKEN_CLAUDE` | Arquivo (permissão `600`, fora do repositório) com o token do Claude | `token-claude` na pasta de configuração do usuário |
| `NOVOMODELO_BATERIA_VOLUME_KIRO` | Volume do podman com o login do Kiro | `novomodelo-bateria-kiro` |
| `NOVOMODELO_BATERIA_MEMORIA` | Limite de memória de cada container | `6g` |

Códigos de saída do `rodar`: 0 rodada completa; 1 determinística com falha, imagem não pronta ou execução sem registro; 2 argumentos inválidos ou retomada recusada; 3 segredo na pasta da rodada; 4 limite de uso do agente ou do juiz; 5 orçamento estourado; 130 Ctrl-C.

Códigos de saída do `go-no-go` (outro subcomando, outra tabela): 0 go; 1 no-go; 2 inconclusivo ou recusa (rodada ou configuração inexistente, segredo bloqueado).

## Configuração

Tudo vem de variável de ambiente ou de argumento. A bateria lê:

| Variável | O que faz | Default |
|---|---|---|
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
