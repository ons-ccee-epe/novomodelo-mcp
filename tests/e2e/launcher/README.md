# Launcher de dev — disparar os testes das tools MCP pela UI

Este launcher resolve o requisito: **o frontend dispara os testes num provedor
de IA (kiro-cli ou claude), e mostra o resultado no relatório existente.**

Um navegador não executa `kiro-cli`/`claude` sozinho (sandbox). A ponte é um
processo local que escuta HTTP e executa o CLI — aqui, um **FastAPI de dev**
(Python 3.12, o executor server-side). Ele NÃO é um backend de
produção: roda só na máquina do dev, em `127.0.0.1`.

```
frontend (SPA Vite)  --/api/*-->  launcher FastAPI  --subprocess-->  kiro-cli / claude
      ^                                                                    |
      |                                                                    v
      +---------------- /data/* (ResultStore: results/*.json) <--- tool MCP novomodelo::*
```

## O que ele reusa (não reimplementa nada)

O launcher é uma casca fina sobre `tests/e2e/queries/*`:

| Peça do launcher | Reusa |
|---|---|
| `provider_runner.ProviderQueryRunner` | estende `queries.runner.QueryRunner` (só troca o comando/validação) |
| `service.RunService` | `CasesLoader`, `QueryValidator`, `ResultStore`, `_build_test_result` |
| disparo | mesma execução headless + parse de tool-calls do runner existente |

A bateria gravada é **idêntica** à do `run_queries.py`. O frontend consome os
mesmos JSON de sempre.

## Provedores suportados

Detectados no PATH (`GET /api/providers`):

- **kiro-cli** — `chat --no-interactive --trust-all-tools -vvv "<prompt>"`
- **claude** (Claude Code) — `--print --verbose --dangerously-skip-permissions "<prompt>"`

O seletor na UI escolhe; a escolha é validada contra o que está instalado. Sem
seleção, usa o primeiro instalado (kiro-cli tem prioridade).

## Como rodar

Em dois terminais (ou use o script combinado abaixo):

```bash
# 1) Launcher (uma vez: instalar deps num venv)
cd <repositório anterior>
pip install -r tests/e2e/launcher/requirements.txt
python -m tests.e2e.launcher.serve          # 127.0.0.1:5175

# 2) Frontend
cd tests/e2e/frontend
npm install                                   # primeira vez
npm run dev                                    # 127.0.0.1:5174
```

Ou num comando só (sobe os dois):

```bash
cd tests/e2e/frontend
npm run dev:launcher
```

Abra `http://127.0.0.1:5174`. No topo do dashboard:

- **Esteira completa** — roda todos os casos.
- **Rodar grupo** — roda um grupo de tools (bridge, deck, docs, …).
- **Biblioteca de prompts** — roda um caso isolado.

O progresso aparece ao vivo; ao terminar, a nova bateria é carregada
automaticamente no relatório.

## Rotas (`/api`)

| Método | Rota | Função |
|---|---|---|
| GET | `/api/health` | saúde do launcher |
| GET | `/api/providers` | provedores detectados + default |
| GET | `/api/cases` | biblioteca de prompts (casos) |
| POST | `/api/runs` | dispara (body: `provider?`, `tags?`, `case_id?`, `timeout_seconds?`); 409 se já houver um run ativo |
| GET | `/api/runs` | runs desta sessão |
| GET | `/api/runs/{run_id}` | estado de um run (polling) |
| POST | `/api/runs/{run_id}/cancel` | para o run (interrompe o caso atual; não grava bateria) |
| GET | `/data/{results\|metrics}/...` | baterias/histórico (mesma convenção do Vite) |

Os `POST` exigem o header `X-Launcher: 1` (o frontend já envia).

## Segurança (dev)

- **Bind fixo em `127.0.0.1`** (nunca exposto na rede).
- **Host** restrito a `127.0.0.1`/`localhost` (anti DNS rebinding), também no `/data` do Vite.
- **CORS** liberado só para `http://127.0.0.1:5174` e `localhost:5174`.
- Um run por vez; `timeout_seconds` entre 0 e 1800, só valores finitos.
- Serving de `/data` confinado a `results/` e `metrics/` (anti path traversal).
- O path guard do MCP aceita o diretório de fixtures e os alvos de links dentro
  dele, desde que fiquem dentro do repositório.

### Risco aceito: agentes sem restrição de tools nativas

`--trust-all-tools` (kiro-cli) e `--dangerously-skip-permissions` (claude) liberam
shell e leitura/escrita de arquivos sem aprovação; o path guard do MCP não limita
essas tools. Um prompt injection num dado lido pelo agente (deck, saída de tool,
doc) pode executar comandos com o usuário de quem roda os testes.

A restrição **não** é aplicada de propósito: os casos validam se o agente prefere
as tools do MCP às nativas (`did_not_use`), e bloquear as nativas tornaria essa
medição sem sentido. Mitigação: rode só em dev local, com fixtures de origem
confiável.

## Sem o launcher

Se o launcher estiver offline, o dashboard ainda mostra as baterias já gravadas
(somente leitura) e exibe um aviso com o comando para subi-lo.
