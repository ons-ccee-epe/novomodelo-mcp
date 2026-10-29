# Launcher de dev — disparar a bateria e ler as rodadas pela UI

Este launcher é a ponte entre o frontend e a bateria: dispara
`python -m tests.e2e rodar`, lista e detalha as rodadas gravadas em `Config.resultados`,
serve as baterias antigas e as cargas gravadas, mantém as baselines e dispara testes de
carga. É um **FastAPI de dev** (Python 3.12) que roda só na máquina de quem desenvolve,
em `127.0.0.1`; não é um backend de produção.

Nenhum agente roda no host: toda execução de agente passa pelo executor em container, seja
pela rodada ou pela carga do modo `agent`.

```
frontend (SPA Vite)  --/api/*-->  launcher FastAPI  --subprocess desanexado-->  python -m tests.e2e rodar
      ^                                  |                                               |
      |                                  +--subprocess--> motor de carga                 v
      +---------- /api/rodadas, /data/* <------------------------ Config.resultados (manifesto, registros)
```

## O que ele reusa (não reimplementa nada)

| Peça do launcher | Reusa |
|---|---|
| `service.RodadaService.disparar` | `python -m tests.e2e rodar` (`tests/e2e/__main__.py`) com os argumentos validados |
| `service.RodadaService.listar` / `detalhe` | `carregar_config`, `ler_manifesto`, `ler_registros` e o `decidir` do critério, sem base de comparação |
| `command_preview` | os mesmos argumentos do disparo, com a wheel pelo nome do arquivo |
| `load_service` | o motor `tests.e2e.load.run`, que roda o modo `agent` pelo executor (`executar`) |

## Rodadas

`POST /api/rodadas` aceita só estas opções, cada uma com o valor validado; campo
desconhecido é recusado (`422`) e nada passa por shell:

| Campo | Vira | Valor aceito |
|---|---|---|
| `mcp` (obrigatório) | `--mcp` | `sem` ou o nome de uma wheel que exista na pasta configurada |
| `rodada` | `--rodada` | nome de rodada começado por letra ou dígito (`[A-Za-z0-9._-]`, até 100); sem ele o launcher gera um e devolve |
| `conjuntos` | `--conjuntos` | `tools`, `usuario` |
| `agentes` | `--agentes` | `claude`, `kiro` |
| `filtro` | `--filtro` | padrões de nome (`[A-Za-z0-9_.*?-]`) separados por vírgula |
| `repeticoes`, `max_execucoes`, `max_minutos`, `esperar_limite`, `paralelo_por_agente`, `completa` | as opções de mesmo nome do `rodar` | inteiros em faixas fixas e booleano |

A pasta das wheels vem da variável de ambiente do launcher `NOVOMODELO_LAUNCHER_PASTA_WHEELS`.
O corpo cita a wheel só pelo nome do arquivo; o launcher a resolve dentro da pasta
(links para fora e `..` são recusados). Sem a variável, só `sem` é aceito. `--origem-mcp`
não é exposto: a origem da wheel é texto livre.

O processo roda desanexado (sessão própria no POSIX, grupo de processos no Windows), com a
saída da bateria em `<resultados>/.launcher/<rodada>.log` (modo `600`). O launcher
responde `409` enquanto a rodada anterior, ou uma carga, não terminou. A rodada é retomável
pelo mesmo `rodada`; o estado do disparo (`em_andamento`, `finalizada`, código de saída) vale
só enquanto o launcher estiver de pé.

`GET /api/rodadas` resume cada pasta com `manifesto.json`; `GET /api/rodadas/{id}` devolve o
manifesto, os registros e, por configuração do manifesto, a decisão do critério sem base de
comparação (o go/no-go com base vem de `python -m tests.e2e go-no-go`). Uma rodada
bloqueada por segredo aparece com `bloqueada: true` e sem registros nem decisão. O `id`
segue o padrão de nome de rodada antes de virar caminho: nome inválido dá `422`, rodada
inexistente `404`.

`GET /api/command-preview?mcp=&conjuntos=&agentes=&filtro=&repeticoes=&completa=` devolve o
comando equivalente do `rodar` (`comando`) e a lista de argumentos, sem segredo nem
caminho absoluto do host; nada é iniciado nem gravado.

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

Abra `http://127.0.0.1:5174`. As rodadas gravadas ficam em `/api/rodadas`; as baterias
antigas, na aba **Histórico**.

## Rotas (`/api`)

| Método | Rota | Função |
|---|---|---|
| GET | `/api/health` | saúde do launcher |
| GET | `/api/cases` | biblioteca de prompts (casos) |
| GET | `/api/command-preview?mcp=&conjuntos=&agentes=&filtro=&repeticoes=&completa=` | comando equivalente do `rodar` e seus argumentos; nada é iniciado nem gravado |
| POST | `/api/rodadas` | dispara a bateria com as opções da lista branca (ver Rodadas); 422 em valor fora da lista ou wheel fora da pasta configurada, 409 se há run ativo |
| GET | `/api/rodadas` | resumo das rodadas gravadas em `Config.resultados` |
| GET | `/api/rodadas/{id}` | manifesto, registros e decisão por configuração (sem base); 404 se não existe |
| GET | `/api/baselines` | baseline vigente de cada conjunto (`{"baselines": {conjunto: batch_id}}`) |
| PUT | `/api/baselines/{conjunto}` | define a bateria (body: `batch_id`) como baseline do conjunto; 404 se a bateria não existe, 409 se é de outro conjunto |
| DELETE | `/api/baselines/{conjunto}` | remove a baseline do conjunto |
| GET | `/api/load-tools` | tools do catálogo de carga, se há fonte para cada uma, se gravam (cópia por sessão), se são pesadas, se são do mix padrão, as barradas com o motivo, e os limites do modo tools |
| GET | `/api/load-cases` | casos por agente, com `available`/`reason` (se podem entrar na carga), `writes`, `heavy` e os limites do modo agent |
| GET | `/api/load-capacity?mode=tools\|agent&provider=...` | sessões simultâneas recomendadas para esta máquina e a seleção (`tools=a,b`; ou `case_id`, `group`, `tags`), o fator limitante (teto, memória, CPU ou disco) e a conta; 422 em seleção inválida |
| POST | `/api/load-runs` | dispara um teste de carga (body: `mode?` tools/agent, `concurrency`, `duration_seconds`, `iterations?`, `timeout_seconds?`; tools: `tools?`, omitido = mix padrão; agent: `provider?` (`claude` por padrão), `mcp?` (`sem` ou o nome de uma wheel da pasta configurada) e no máximo um entre `case_id`, `group`, `tags`); 422 em entrada inválida, tool fora do catálogo, wheel fora da pasta ou seleção sem caso elegível; 409 se qualquer run estiver ativo |
| GET | `/api/load-runs` | cargas desta sessão |
| GET | `/api/load-runs/{run_id}` | estado de uma carga, com o progresso ao vivo (polling) |
| POST | `/api/load-runs/{run_id}/cancel` | para a carga e encerra todos os servidores MCP; não grava |
| GET | `/data/{results\|metrics}/...` | baterias/histórico (mesma convenção do Vite); as cargas gravadas ficam em `/data/results/load/` |

Os `POST`, `PUT` e `DELETE` exigem o header `X-Launcher: 1` (o frontend já envia).

## Segurança (dev)

- **Bind fixo em `127.0.0.1`** (nunca exposto na rede).
- **Host** restrito a `127.0.0.1`/`localhost` (anti DNS rebinding), também no `/data` do Vite.
- **CORS** liberado só para `http://127.0.0.1:5174` e `localhost:5174`.
- Um run por vez (`run_gate.RunGate`), de rodada ou de carga: com um ativo, o POST de outro devolve 409.
- A lista branca do disparo recusa campo desconhecido, texto livre e wheel fora da pasta
  configurada; a linha de comando nunca passa por shell.
- Serving de `/data` confinado a `results/` e `metrics/` (anti path traversal); o
  subdiretório `results/load/` fica dentro dessa raiz e passa pela mesma checagem.
- O path guard do MCP aceita o diretório de fixtures e os alvos de links dentro
  dele, desde que fiquem dentro do repositório.

### Agente fora do host

O launcher não inicia processo de agente: ele sobe `python -m tests.e2e rodar` e o motor de carga, e o agente roda no container do executor. Nenhum comando que dispensa a aprovação
de tools nativas existe no código da bateria fora do executor em container, e um
teste varre `tests/e2e/` para garantir isso.

## Teste de carga

A aba **Testes de Carga** do dashboard dispara `POST /api/load-runs`
(`tests/e2e/load/README.md` explica o mix, os casos, a cópia das fixtures por sessão,
o isolamento e as métricas): N sessões, cada uma com o seu próprio processo do
servidor MCP, chamando as tools do mix (por padrão as leves e somente leitura). Com tool
que grava na seleção, cada sessão roda numa cópia própria das fixtures, e o servidor dela
só enxerga essa cópia. No modo `agent`, cada sessão é uma sequência de execuções no
container do executor, com o `mcp` escolhido. O launcher não reimplementa nada: roda
`python -m tests.e2e.load.run --json-progress ...` e lê os eventos JSON que ele imprime.

- **Subprocesso, não thread.** Cancelar é matar uma árvore só (motor + N servidores, ou
  o motor das sessões de agente), sem depender de um desligamento limpo de cada um,
  e a medição não disputa o event loop do HTTP. No Windows o motor entra num Job Object com
  `KILL_ON_JOB_CLOSE` (`process_tree.ProcessTree`); em POSIX é líder de sessão.
  Fechar o launcher fecha o job; o stdin do motor também fecha, e ele para sozinho.
- **O body não escolhe o que roda.** `tools` é validada contra o catálogo fechado (422
  se pedir uma tool fora dele, como `run_start` ou `server_info`, com o motivo), campos desconhecidos são
  recusados e os limites de sessões simultâneas, duração, iterações e timeout vêm do motor
  (`GET /api/load-tools` e `GET /api/load-cases` devolvem os valores em vigor de cada
  modo). Campos de um modo no outro dão 422. No modo agent, a wheel do `mcp` é validada
  contra a pasta configurada e uma seleção sem caso elegível (só casos barrados, grupo
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
