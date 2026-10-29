# Launcher de dev — disparar os testes das tools MCP pela UI

Este launcher é a ponte entre o frontend e as peças da bateria: lista casos e
provedores, serve as baterias e as cargas gravadas, mantém as baselines e dispara
testes de carga do modo `tools`. É um **FastAPI de dev** (Python 3.12) que roda só
na máquina de quem desenvolve, em `127.0.0.1`; não é um backend de produção.

A execução de agente (`POST /api/runs` e `POST /api/load-runs` no modo `agent`) passa
pelo executor em container: no launcher, esses disparos respondem `409` com
"a execução passa pelo executor em container", e nenhum agente roda no host.

```
frontend (SPA Vite)  --/api/*-->  launcher FastAPI  --subprocess-->  motor de carga (modo tools)
      ^
      +---------------- /data/* (ResultStore: results/*.json, metrics/history.jsonl)
```

## O que ele reusa (não reimplementa nada)

O launcher é uma casca fina sobre `tests/e2e/queries/*`:

| Peça do launcher | Reusa |
|---|---|
| `provider_runner.ProviderQueryRunner` | estende `queries.runner.QueryRunner` com o parse da saída `stream-json` de cada provedor; não executa agente |
| `service.RunService` | `CasesLoader`, `QueryValidator`, `ResultStore`, `_build_test_result`; `start_run` recusa o disparo |

O frontend consome os JSON gravados em `results/` e `metrics/`.

## Provedores suportados

Detectados no PATH (`GET /api/providers`):

- **kiro-cli**
- **claude** (Claude Code)

O seletor na UI escolhe; a escolha é validada contra o que está instalado. Sem
seleção, usa o primeiro instalado (kiro-cli tem prioridade). O provedor é uma
referência para o comando de exemplo e para o executor; o launcher não o invoca.

## Como rodar

Em dois terminais (ou use o script combinado abaixo):

```bash
# 1) Launcher (as dependências vêm do grupo `e2e` do pyproject.toml)
cd novomodelo-mcp
uv sync --group e2e
uv run --group e2e python -m tests.e2e.launcher.serve          # 127.0.0.1:5175

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

Abra `http://127.0.0.1:5174`. Na aba **Testes Funcionais**:

- **Esteira completa**, **Grupo** (bridge, deck, docs, …) e **Pergunta** (um caso
  isolado) escolhem o conjunto; o disparo responde 409 enquanto a execução de
  agente passa só pelo executor em container.

O quadro de comando mostra um comando de referência do conjunto escolhido; nada é
executado. As baterias gravadas ficam na aba **Histórico**.

## Rotas (`/api`)

| Método | Rota | Função |
|---|---|---|
| GET | `/api/health` | saúde do launcher |
| GET | `/api/providers` | provedores detectados + default |
| GET | `/api/cases` | biblioteca de prompts (casos) |
| GET | `/api/command-preview?provider=&tags=&case_id=` | comando de referência do conjunto: o do terminal (só kiro-cli) e o do agente, com o conjunto e o total de casos; nada é iniciado nem gravado |
| GET | `/api/baselines` | baseline vigente de cada conjunto (`{"baselines": {conjunto: batch_id}}`) |
| PUT | `/api/baselines/{conjunto}` | define a bateria (body: `batch_id`) como baseline do conjunto; 404 se a bateria não existe, 409 se é de outro conjunto |
| DELETE | `/api/baselines/{conjunto}` | remove a baseline do conjunto |
| POST | `/api/runs` | aceita o body (`provider?`, `tags?`, `case_id?`, `timeout_seconds?`) e responde 409: a execução passa pelo executor em container |
| GET | `/api/runs` | runs desta sessão |
| GET | `/api/runs/{run_id}` | estado de um run (polling), com o `TestResult` completo de cada caso já terminado |
| POST | `/api/runs/{run_id}/cancel` | para o run (interrompe o caso atual; não grava bateria) |
| GET | `/api/load-tools` | tools do catálogo de carga, se há fonte para cada uma, se gravam (cópia por sessão), se são pesadas, se são do mix padrão, as barradas com o motivo, e os limites do modo tools |
| GET | `/api/load-cases` | casos por agente, com `available`/`reason` (se podem entrar na carga), `writes`, `heavy` e os limites do modo agent |
| GET | `/api/load-capacity?mode=tools\|agent&provider=...` | sessões simultâneas recomendadas para esta máquina e a seleção (`tools=a,b`; ou `case_id`, `group`, `tags`), o fator limitante (teto, memória, CPU ou disco) e a conta; 422 em seleção inválida |
| POST | `/api/load-runs` | dispara um teste de carga do modo `tools` (body: `mode?` tools/agent, `concurrency`, `duration_seconds`, `iterations?`, `timeout_seconds?`; tools: `tools?`, omitido = mix padrão; agent: `provider?` e no máximo um entre `case_id`, `group`, `tags`); 422 em entrada inválida, tool fora do catálogo, provedor não instalado ou seleção sem caso elegível; 409 se qualquer run estiver ativo e 409 no modo `agent` (a execução passa pelo executor em container) |
| GET | `/api/load-runs` | cargas desta sessão |
| GET | `/api/load-runs/{run_id}` | estado de uma carga, com o progresso ao vivo (polling) |
| POST | `/api/load-runs/{run_id}/cancel` | para a carga e encerra todos os servidores MCP; não grava |
| GET | `/data/{results\|metrics}/...` | baterias/histórico (mesma convenção do Vite); as cargas gravadas ficam em `/data/results/load/` |

Os `POST`, `PUT` e `DELETE` exigem o header `X-Launcher: 1` (o frontend já envia).

## Segurança (dev)

- **Bind fixo em `127.0.0.1`** (nunca exposto na rede).
- **Host** restrito a `127.0.0.1`/`localhost` (anti DNS rebinding), também no `/data` do Vite.
- **CORS** liberado só para `http://127.0.0.1:5174` e `localhost:5174`.
- Um run por vez (`run_gate.RunGate`): com uma carga ativa, o POST de outra devolve 409.
  `timeout_seconds` entre 0 e 1800, só valores finitos.
- Serving de `/data` confinado a `results/` e `metrics/` (anti path traversal); o
  subdiretório `results/load/` fica dentro dessa raiz e passa pela mesma checagem.
- O path guard do MCP aceita o diretório de fixtures e os alvos de links dentro
  dele, desde que fiquem dentro do repositório.

### Agente fora do host

O launcher não inicia processo de agente: nenhum comando que dispensa a aprovação
de tools nativas existe no código da bateria fora do executor em container, e um
teste varre `tests/e2e/` para garantir isso.

## Teste de carga

A aba **Testes de Carga** do dashboard dispara `POST /api/load-runs` no modo `tools`
(`tests/e2e/load/README.md` explica o mix, os casos, a cópia das fixtures por sessão,
o isolamento e as métricas): N sessões, cada uma com o seu próprio processo do
servidor MCP, chamando as tools do mix (por padrão as leves e somente leitura). O modo
`agent` responde 409, pois a execução de agente passa pelo executor em container. Com tool que grava na seleção,
cada sessão roda numa cópia própria das fixtures, e o servidor dela só enxerga essa
cópia. O launcher não reimplementa nada: roda
`python -m tests.e2e.load.run --json-progress ...` e lê os eventos JSON que ele imprime.

- **Subprocesso, não thread.** Cancelar é matar uma árvore só (motor + N servidores, ou
  N servidores), sem depender de um desligamento limpo de cada um,
  e a medição não disputa o event loop do HTTP. No Windows o motor entra num Job Object com
  `KILL_ON_JOB_CLOSE` (`process_tree.ProcessTree`); em POSIX é líder de sessão.
  Fechar o launcher fecha o job; o stdin do motor também fecha, e ele para sozinho.
- **O body não escolhe o que roda.** `tools` é validada contra o catálogo fechado (422
  se pedir uma tool fora dele, como `run_start` ou `server_info`, com o motivo), campos desconhecidos são
  recusados e os limites de sessões simultâneas, duração, iterações e timeout vêm do motor
  (`GET /api/load-tools` e `GET /api/load-cases` devolvem os valores em vigor de cada
  modo). Campos de um modo no outro dão 422. No modo agent, o provedor é validado
  contra o PATH e uma seleção sem caso elegível (só casos barrados, grupo
  inexistente...) dá 422 antes do 409. O comando do servidor e a pasta de trabalho não
  são configuráveis pela API.
- **Pasta de trabalho.** Cada carga recebe uma `--work-dir` temporária criada pelo
  launcher (sessões e cópias das fixtures) e apagada depois que a árvore do motor
  termina, também no cancelamento, quando o motor é morto sem tempo de limpar.
- **Limitador.** `GET /api/load-capacity` estima as sessões simultâneas que a máquina
  aguenta para a seleção (memória, CPU, disco das cópias e o teto do modo, com custo por
  sessão maior para seleções pesadas); a tela mostra a conta e avisa acima do
  recomendado, sem bloquear. O teto do modo é validado também no POST.
- **Cancelar não grava.** Um run interrompido não entra
  no histórico; o estado mostra o que foi medido até ali.
- **Progresso.** `GET /api/load-runs/{id}` devolve `phase` (`preflight`, `starting`,
  `running`, `finishing`) e `progress` (contagens, p50/p95/p99, vazão e a série dos
  últimos segundos). Ao terminar, `load_id` aponta para `/data/results/load/<id>.json`.
- `psutil` é opcional (CPU/RSS dos servidores no resultado): `pip install psutil`.

## Sem o launcher

Se o launcher estiver offline, o **Histórico** ainda mostra as baterias já gravadas
(somente leitura) e a aba **Testes de Carga** faz o mesmo com as cargas gravadas; o
disparo e a edição de baselines ficam indisponíveis até subir o launcher.
