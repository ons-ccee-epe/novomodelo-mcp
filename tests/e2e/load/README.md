# Teste de carga do servidor MCP

Mede como o servidor `novomodelo-mcp` se comporta com vários clientes ao mesmo
tempo. Não usa agente de IA: abre N clientes concorrentes pelo SDK `mcp`, **cada
um com o seu próprio processo do servidor** (stdio, como em produção, onde há um
processo por cliente), e chama direto as tools do mix.

## Como rodar

```bash
# Raiz do repositório, com o ambiente do projeto ativo
python -m tests.e2e.load.run --concurrency 4 --duration 30
python -m tests.e2e.load.run --concurrency 2 --duration 10 --tools deck_list,docs_search
python -m tests.e2e.load.run --concurrency 8 --duration 60 --iterations 200 --timeout 30
```

| Opção | Efeito |
|---|---|
| `--concurrency N` | Clientes concorrentes (um servidor por cliente). |
| `--duration S` | Janela de carga, em segundos. |
| `--iterations M` | Opcional. Chamadas **por cliente**: cada cliente para ao fazer M chamadas ou ao fim de `--duration`, o que vier primeiro. |
| `--tools a,b` | Subconjunto do mix. Só aceita tools do catálogo somente leitura. |
| `--timeout T` | Segundos sem resposta até contar `timeout` e recriar o cliente. |
| `--no-warmup` | Não aquece os clientes: as primeiras chamadas (frias) entram nas métricas. |
| `--no-save` | Não grava em `tests/e2e/results/load/`. |
| `--fixtures`, `--results-dir` | Raiz das fixtures (vira o workspace do servidor) e pasta de resultados. |
| `--server-command` | Comando do servidor, no lugar do padrão. |
| `--server-log` | Arquivo para o stderr dos servidores (por padrão é descartado). |
| `--json-progress` | Modo do launcher: eventos JSON em linhas no stdout. |

`python -m tests.e2e.load.run --help` mostra os limites aceitos (definidos em
`engine.py`: `MIN_CONCURRENCY` a `MAX_CONCURRENCY`, `MIN_DURATION_S` a
`MAX_DURATION_S`, `MAX_TIMEOUT_S`, `MAX_ITERATIONS`). Valores fora deles saem com
código 2, sem subir nenhum processo.

Pela UI: aba **Carga** do dashboard (`tests/e2e/frontend`), que dispara pelo
launcher (`tests/e2e/launcher/README.md`).

O servidor testado é o do **checkout**: `sys.executable -m novomodelo_mcp`. O
`~/.kiro/settings/mcp.json` não é usado, porque costuma apontar para outra
instalação (`uv tool`), e a carga mediria a instalação errada.

## O mix de chamadas

O catálogo está em `mix.py` (`CATALOG`) e é uma lista fechada de tools somente
leitura: `deck_*` de leitura, `docs_*`, `schema_list`/`schema_get` e
`results_*` de leitura. Ficam de fora `run_*`, `*_convert_*`, `deck_edit_*`,
`case_init`, `schema_export`, `instalar_*`, `bridge_*` e `server_info` (usa a rede).

Uma tool só entra no mix se **as duas** condições valem: está no catálogo e o
servidor a anuncia com `readOnlyHint` e sem `openWorldHint`. A primeira barreira
quebra o import do módulo se alguém colar uma tool de escrita no catálogo; o
POST do launcher recusa (422) qualquer tool fora dela.

Os argumentos usam caminhos de `{FIXTURES}` (os decks de `cases.yaml` e os de
`tests/e2e/fixtures/README.md`) e exemplos das docstrings das tools. Uma
chamada cuja fonte falta, ou é uma pasta vazia, é pulada e listada em
`mix.excluded` com o motivo. `GET /api/load-tools` mostra o que está disponível.

Antes da carga, um **pré-voo** num cliente à parte roda cada chamada uma vez;
uma que erra ou trava sai do mix (`pré-voo: ...`) em vez de virar taxa de erro.

## O que é medido

- **Por tool e total:** chamadas, ok/erro/timeout, taxa de erro, vazão
  (chamadas/s) e latência mín/média/p50/p95/p99/máx.
- **Latência só das chamadas ok.** O tempo de um timeout é o próprio limite, e
  uma falha rápida puxaria a média para baixo. Erros e timeouts entram na taxa
  de erro: `(erros + timeouts) / chamadas`.
- **Percentis** por interpolação linear entre postos vizinhos (a mesma definição
  do default do numpy).
- **Série temporal:** buckets de 1 s pelo instante de conclusão, com chamadas,
  falhas, p50 e p95. O gráfico descarta o último bucket quando a janela mal o cobre.
- **Subida dos servidores, à parte:** tempo por cliente, até todos prontos,
  aquecimento e pré-voo. O relógio da carga só começa depois que **todos** os
  clientes estão prontos.
- **Aquecimento:** cada cliente chama uma vez cada tool do mix antes da carga; essas
  chamadas ficam fora das métricas (a primeira chamada de uma tool carrega bibliotecas).
- **CPU e RSS** dos processos do servidor, se o `psutil` estiver instalado
  (`pip install psutil`). Sem ele o relatório diz `available: false` e a carga segue.

### Timeout e clientes recriados

Cada chamada leva o timeout de `--timeout`. Sem resposta a tempo, a chamada é
contada como `timeout` e o cliente é encerrado e recriado: uma sessão stdio que
perdeu uma resposta não é confiável. A recriação aparece em `startup.respawns`.
Chamadas ainda em curso quando a janela fecha têm alguns segundos para
responder; as que não respondem são abandonadas (`abandoned_calls`) e não
entram nas métricas.

## Resultado gravado

`tests/e2e/results/load/<id>.json` e `tests/e2e/results/load/index.json`, com o id
no formato `{timestamp}_{git_short_sha}` do `ResultStore`. O `index.json` das
baterias de agente (`results/index.json`) não é tocado. O JSON traz a
configuração, o mix (com os excluídos), a subida, os totais, o `per_tool`, a
`series`, os erros agrupados e os recursos. O contrato espelhado no frontend
está em `tests/e2e/frontend/src/shared/types.ts` (`LoadRun`).

## Encerramento

Terminar ou cancelar deixa zero processo do servidor: o SDK encerra cada árvore
ao sair do cliente. Pelo launcher, o motor roda num subprocesso que entra num
Job Object (Windows) ou é líder de sessão (POSIX); cancelar mata o grupo todo, e um
descendente criado no meio do kill não escapa. Ctrl+C na CLI interrompe com
elegância e grava o parcial com `interrupted: true` (código 130); um segundo
Ctrl+C aborta.

## Testes

```bash
uv run --no-sync pytest tests/e2e/load
```

Os testes unitários usam clientes falsos (`fakes.py`) e não sobem o servidor.
`test_load_integration.py` usa um servidor MCP falso (`fake_mcp_server.py`) por
stdio real para cobrir timeout com recriação, cancelamento e ausência de processos
sobrando. Com `LOAD_E2E_REAL=1` roda também uma carga curta contra o servidor real.
