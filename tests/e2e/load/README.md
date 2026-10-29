# Teste de carga do servidor MCP

Mede como o servidor `novomodelo-mcp` se comporta com várias sessões simultâneas.
Há dois modos:

- **`tools`** (padrão): não usa agente de IA. Abre N sessões pelo SDK `mcp`, **cada
  uma com o seu próprio processo do servidor** (stdio, como em produção, onde há um
  processo por cliente), e chama direto as tools do mix.
- **`agent`**: N sessões de agente (`claude` ou `kiro`) ao mesmo tempo, cada uma
  rodando em laço os casos do `tests/e2e/queries/cases.yaml` que podem rodar em
  paralelo, validados como no conjunto de tools. Cada execução é um container do
  executor, com a cópia própria do caso público citado no pedido. Ver
  [Modo agent](#modo-agent).

## Como rodar

```bash
# Raiz do repositório, com o ambiente do projeto ativo
python -m tests.e2e.load.run --concurrency 4 --duration 30
python -m tests.e2e.load.run --concurrency 2 --duration 10 --tools deck_list,docs_search
python -m tests.e2e.load.run --concurrency 8 --duration 60 --iterations 200 --timeout 30
python -m tests.e2e.load.run --concurrency 2 --duration 10 --tools deck_edit_json,run_plan,deck_list
```

| Opção | Efeito |
|---|---|
| `--mode tools\|agent` | `tools` (padrão) ou `agent`. |
| `--concurrency N` | Sessões simultâneas (no modo tools, um servidor por sessão). |
| `--duration S` | Janela de carga, em segundos. |
| `--iterations M` | Opcional. **Por sessão**: chamadas (tools) ou casos (agent); cada sessão para ao chegar em M ou ao fim de `--duration`, o que vier primeiro. |
| `--tools a,b` | Só tools. Tools do catálogo (`mix.ALLOWED_TOOLS`); sem a opção, o mix padrão (`mix.DEFAULT_TOOLS`: as leves e somente leitura). As que gravam e as pesadas entram só pelo nome. |
| `--timeout T` | tools: segundos sem resposta até contar `timeout` e recriar a sessão. agent: timeout de cada caso (sem a opção, o `timeout_s` do próprio caso). |
| `--no-warmup` | Só tools. Não aquece as sessões: as primeiras chamadas (frias) entram nas métricas. |
| `--provider kiro-cli\|claude` | Só agent. Sem a opção, `claude`. |
| `--mcp sem\|WHEEL` | Só agent: a imagem das sessões, a da configuração `sem` ou a da wheel do MCP (a mesma que `python -m tests.e2e preparar --mcp` construiu). Sem a opção, `sem`. |
| `--case ID`, `--group G`, `--tags a,b` | Só agent, no máximo uma: um caso, um grupo (o da tool esperada, como na tela) ou tags (qualquer uma). Sem nenhuma, todos os casos elegíveis. |
| `--no-save` | Não grava em `results/load/` (pasta criada sob demanda). |
| `--fixtures`, `--results-dir` | Raiz das fixtures (vira o workspace do servidor) e pasta de resultados. |
| `--server-command` | Só tools. Comando do servidor, no lugar do padrão. |
| `--server-log` | Arquivo para o stderr dos servidores (por padrão é descartado). |
| `--work-dir` | Pasta onde o run cria a sua pasta temporária (sessões e cópias das fixtures), apagada ao fim. Sem a opção, o TEMP. |
| `--json-progress` | Modo do launcher: eventos JSON em linhas no stdout. |

`python -m tests.e2e.load.run --help` mostra os limites aceitos (definidos em
`engine.py`: `MIN_CONCURRENCY` a `MAX_CONCURRENCY`, `MIN_DURATION_S` a
`MAX_DURATION_S`, `MAX_TIMEOUT_S`, `MAX_ITERATIONS`; no modo agent o teto de sessões
é `MAX_AGENT_CONCURRENCY`, em `agent_engine.py`). Valores fora deles, opções do outro
modo ou provedor desconhecido saem com código 2, sem subir nenhum processo.
No modo agent, ambiente do executor incompleto (motor, token ou volume) ou wheel inexistente saem com código 1 sem subir sessão; no modo tools, se as cópias das fixtures por sessão não cabem no disco, a carga sai com código 1 antes
de copiar ([Cópia das fixtures por sessão](#cópia-das-fixtures-por-sessão)).

Pela UI: aba **Carga** do dashboard (`tests/e2e/frontend`), que dispara pelo
launcher (`tests/e2e/launcher/README.md`).

No modo tools, o servidor testado é o do **checkout**: o Python do `.venv` do
projeto com `-m novomodelo_mcp` (`client.default_server_command`). O
`~/.kiro/settings/mcp.json` não é usado, porque costuma apontar para outra
instalação (`uv tool`), e a carga mediria a instalação errada. No modo agent o servidor é o
que a imagem do `--mcp` traz.

## O mix de chamadas

O catálogo está em `mix.py` (`CATALOG`) e é uma lista fechada. Cada tool cai numa classe:

| Classe | Tools | Na carga |
|---|---|---|
| Leve, somente leitura | `deck_*` de leitura, `docs_*`, `schema_list`/`schema_get`, `results_*` | O mix padrão (`DEFAULT_TOOLS`), quando `--tools` não é dado |
| Grava (`mix.writes_files`) | `bridge_convert_*`, `bridge_compare_*`, `bridge_dashboard`, `deck_edit_*`, `case_init`, `schema_export`, `run_apply` | Só pelo nome, e cada sessão grava na sua cópia das fixtures |
| Pesada (`mix.is_heavy_tool`) | `bridge_*` e `run_plan` (sobem o bridge ou a CLI do solver a cada chamada) | Só pelo nome; o limitador cobra mais por sessão |

Ficam **fora da carga**, nos dois modos, as de `mix.is_forbidden_tool`, com o motivo
em `mix.barred_reason` (mostrado na tela e no 422 do launcher):

- `run_start` dispara o solver (`novomodelo run`) destacado do servidor: o run leva
  minutos com os núcleos de performance e sobrevive à sessão (o runner do job é
  lançado para sobreviver ao servidor), e N sessões saturariam a máquina; a carga
  mediria o solver, não o servidor. Além disso, todo servidor da carga roda com
  `NOVOMODELO_MCP_MAX_JOBS=0`, e o `run_start` recusa qualquer run (nem um agente o
  dispara por conta própria);
- `run_status`, `run_logs` e `run_cancel` dependem de um run iniciado por `run_start`:
  sem ele, só mediriam o erro de job inexistente;
- `server_info` e `instalar_novomodelo` usam a rede.

Uma tool só entra no mix se está no catálogo e o servidor a anuncia sem
`openWorldHint` e, se não for das que gravam, com `readOnlyHint`: uma tool tida como
de leitura que passe a gravar sai do mix em vez de gravar fora da cópia. O import do
módulo quebra se alguém colar no catálogo uma tool barrada; o POST do launcher recusa
(422) qualquer tool fora do catálogo.

Os argumentos usam caminhos de `{FIXTURES}` (os decks de `cases.yaml` e os de
`tests/e2e/fixtures/README.md`) e exemplos das docstrings das tools. Uma
chamada cuja fonte falta, ou é uma pasta vazia, é pulada e listada em
`mix.excluded` com o motivo. `GET /api/load-tools` mostra o que está disponível, a
classe de cada tool e as barradas.

As chamadas que gravam continuam válidas quando repetidas em laço na mesma cópia: as
edições (`deck_edit_*`, `run_apply`) regravam o valor que as fixtures já têm, a
conversão usa `force` (no bridge ele não é travado), relatórios e dashboard são
sobrescritos e `case_init` recebe uma pasta nova por chamada (`{CALL}`; o `force` dele
é travado no servidor por `NOVOMODELO_MCP_ALLOW_FORCE`, que a carga não liga).

Antes da carga, um **pré-voo** num cliente à parte roda cada chamada uma vez;
uma que erra ou trava sai do mix (`pré-voo: ...`) em vez de virar taxa de erro.
Quando uma tool pesada fica sem resposta, as demais do mesmo grupo não são chamadas
(cada uma custaria outro timeout) e saem com o motivo.

### O bridge trava no modo tools (Windows)

No Windows, o servidor sobe o bridge com `subprocess.run` sem `stdin`, o
bridge (um Python) herda o stdin do servidor, que tem uma leitura síncrona pendente
no pipe do cliente MCP, e trava ao iniciar até o cliente escrever nesse pipe. O
cliente da carga não escreve nada enquanto espera a resposta, então toda tool
`bridge_*` fica sem resposta até o timeout e o pré-voo a tira do mix, com essa causa
no motivo. Com o stdin trocado por `DEVNULL` o mesmo bridge responde em segundos. A
correção é do servidor (`stdin=subprocess.DEVNULL` em `run_bridge`, `src/novomodelo_mcp/adapters/bridge.py`),
não da carga; o motor não manda pings para mascarar o defeito. No modo agent o bridge
só destrava quando o agente escreve no stdin do servidor, o que é a provável causa das
latências longas e dos timeouts dos casos `bridge-*` na esteira.

## O que é medido

- **Por tool e total:** chamadas, ok/erro/timeout, taxa de erro, vazão
  (chamadas/s) e latência mín/média/p50/p95/p99/máx.
- **Latência só das chamadas ok.** O tempo de um timeout é o próprio limite, e
  uma falha rápida puxaria a média para baixo. Erros e timeouts entram na taxa
  de erro: `(erros + timeouts) / chamadas`.
- **Percentis** por interpolação linear entre postos vizinhos (a mesma definição
  do default do numpy).
- **Série temporal:** buckets de 1 s pelo instante de conclusão, com chamadas,
  falhas, p50 e p95. O gráfico descarta o último bucket quando a janela mal o abrange.
- **Subida dos servidores, à parte:** tempo por cliente, até todos prontos,
  aquecimento e pré-voo. O relógio da carga só começa depois que **todos** os
  clientes estão prontos. Com cópia das fixtures, o tempo dela fica em `copy_ms` de
  cada subida, fora do `ms` do servidor.
- **Aquecimento:** cada cliente chama uma vez cada tool do mix antes da carga; essas
  chamadas ficam fora das métricas (a primeira chamada de uma tool carrega bibliotecas).
- **CPU e RSS** dos processos do servidor, se o `psutil` estiver instalado
  (opcional: `uv pip install psutil`). Sem ele o relatório diz `available: false` e a carga segue.

### Timeout e clientes recriados

Cada chamada leva o timeout de `--timeout`. Sem resposta a tempo, a chamada é
contada como `timeout` e o cliente é encerrado e recriado: uma sessão stdio que
perdeu uma resposta não é confiável. A recriação aparece em `startup.respawns`.
Chamadas ainda em curso quando a janela fecha têm alguns segundos para
responder; as que não respondem são abandonadas (`abandoned_calls`) e não
entram nas métricas.

## Resultado gravado

`tests/e2e/results/load/<id>.json` e `tests/e2e/results/load/index.json` (pasta criada
na primeira gravação), com o id no formato `{timestamp}_{git_short_sha}` do
`ResultStore`. O `index.json` das baterias (`results/index.json`) não é tocado. O JSON traz a
configuração, o mix (com os excluídos), a subida, a cópia por sessão (`sandbox`), os
totais, o `per_tool`, a `series`, os erros agrupados e os recursos. O contrato
espelhado no frontend está em `tests/e2e/frontend/src/shared/types.ts` (`LoadRun`).
JSONs gravados antes da cópia por sessão não têm `sandbox` e continuam legíveis.

## Cópia das fixtures por sessão

Só no modo tools. Quando a seleção tem tool que grava, cada sessão recebe, na pasta temporária do
run, uma cópia própria das fixtures (`sandbox.py`), feita na subida da sessão:

- só as subárvores que a seleção usa (`categoria/caso`, como
  `newave/novomodelo-mini` ou `results/sample_run`), com o layout das originais,
  mais uma `scratch/` vazia; um caminho que não existe nas fixtures também não existe
  na cópia (os casos de erro continuam dando erro);
- os argumentos das chamadas passam a apontar para a cópia;
- o `NOVOMODELO_MCP_WORKSPACE` do servidor da sessão é **só a cópia**: o path guard do
  servidor, fail-closed, recusa as fixtures originais e a cópia de outra sessão;
- a pasta do run é apagada ao fim, em erro e em Ctrl+C; pelo launcher, que mata o motor
  no cancelamento, quem apaga é o launcher, depois que a árvore do motor morre.

Sem nada que grave na seleção, não há cópia: as sessões leem as fixtures originais,
como antes. Em toda carga do modo tools, cada servidor tem ainda TEMP e
`NOVOMODELO_MCP_STATE_DIR` próprios (o `run_plan` lê e grava a calibração no state dir) e
roda com `NOVOMODELO_MCP_MAX_JOBS=0`.

Antes de copiar, a carga confere o disco da pasta do run: sessões × (cópia +
`SANDBOX_GROWTH` para o que as tools gravam nela) precisa caber no espaço livre menos
`DISK_HEADROOM`. O resultado traz o plano, o tempo médio e máximo da cópia e o maior
tamanho de uma cópia ao fim (`sandbox.final_mb_max`), para conferir a folga.

## Modo agent

Cada execução de caso é um container do executor (`executor.container.executar`, sem
`liberar`): o agente não vê o host, recebe a cópia do caso e o MCP da imagem escolhida em
`--mcp`. Antes, `python -m tests.e2e preparar --mcp ...` constrói a imagem e o secret do
token; a carga confere o ambiente (`verificar`) e sai com código 1 se faltar algo.

### Quais casos entram

A seleção é a do conjunto de tools (todos, um grupo ou um caso; pela CLI também tags).
Fica de fora da carga, com o motivo no resultado (`cases.excluded`) e na tela, o caso:

- cuja tool esperada (`tool`, ou qualquer uma de `tools`) é barrada por
  `mix.is_forbidden_tool`, a mesma barreira do modo tools (o solver e os jobs dele, e a
  rede; ver [O mix de chamadas](#o-mix-de-chamadas));
- que não usa o MCP (não exercita o servidor);
- cuja fonte (`requires`) falta;
- cuja tool grava (`mix.writes_files`, ou anunciada pelo servidor como escrita no pré-voo,
  `executor.container.tools_do_servidor`): `agent_cases.REASON_WRITES`, "tool que grava:
  no container ela fica negada; a carga mediria a negação";
- cuja tool o servidor deste checkout anuncia com rede.

O marcador `{caso:<nome lógico>}` do pedido vira `/estudos/<nome lógico>` e a cópia do caso
público vem de `executor.casos.pasta_preparados`, como no conjunto de tools
(`adaptador.pedido_do_caso`). Os casos
pesados (`bridge_*`, `run_plan`) também entram.

`GET /api/load-cases` lista cada caso com `available`, `reason`, `writes` e `heavy`. O
teste `test_agent_cases_unit.py::TestRealCatalog` confere, contra as anotações do
servidor do checkout, que toda tool que grava está na lista das que gravam ou barrada, e
que toda tool de rede está barrada.

A carga não libera nenhuma tool: uma tool que pede aprovação fica negada no container,
nos dois agentes, e o resultado traz as tools negadas (`agent.denied_tools`). Por isso os
casos de tools que gravam não entram na carga.

### Isolamento entre sessões

Cada sessão tem a sua pasta de registros sob a raiz temporária do run, apagada ao fim
(`agent_session.py`), e cada execução é um container descartável com a cópia própria do
caso, sem home nem socket do host; o servidor MCP de cada container tem o seu TEMP e o
seu state dir.

### Fases e métricas

`preflight` (carrega os casos, aplica as exclusões e lê as dicas das tools do servidor
deste checkout; não gasta tokens), `starting` (pastas e runners das sessões),
`running` e `finishing`: ao fim da janela nenhuma sessão começa caso novo, e os casos
em curso terminam, limitados pelo timeout do próprio caso.

Cada execução tem dois resultados separados:

- **Transporte**: `ok` (o agente completou), `timeout` ou `error` (exceção, agente sem
  resposta nem tool-call, erro da API como limite de taxa ou, no claude, servidor MCP
  que não conectou). Alimenta a taxa de erro; a latência ponta a ponta (p50/p95/p99)
  abrange só as execuções completas.
- **Validação** (o mesmo `QueryValidator` da esteira): `pass`, `partial` ou `fail`.
  Alimenta a taxa de aprovação. Um `fail` é uma execução completa.

Por caso e no total: execuções, contagem por status, aprovação, taxa de erro, vazão
(casos/min), latência e a média de tool-calls (todas e só as do MCP). A série usa
buckets de `AGENT_BUCKET_SECONDS`. CPU e RSS somam a árvore do motor (o cliente do container); o agente e o servidor MCP rodam dentro do container e não entram. O JSON gravado traz `mode: "agent"`, o provedor, a imagem, as
tools negadas, as sessões e os casos selecionados e excluídos. A tela só
compara cargas do mesmo modo.

## Limitador de sessões simultâneas

`GET /api/load-capacity` (`capacity.py`) estima quantas sessões a máquina aguenta para
o modo, o provedor e a **seleção** (`mode=tools&tools=a,b`, sem `tools` = mix padrão;
`mode=agent&provider=...` com no máximo um entre `case_id`, `group` e `tags`) e diz o
fator que limita:

```
memória = piso(MB disponíveis × (1 − MEMORY_HEADROOM) ÷ MB por sessão)
CPU     = piso((núcleos lógicos − RESERVED_CORES) ÷ núcleos por sessão)
disco   = piso(MB livres na pasta do run × (1 − DISK_HEADROOM) ÷ MB de disco por sessão)
recomendado = max(1, min(teto do modo, memória, CPU, disco))
```

O custo por sessão depende do **perfil** da seleção: `pesada` se ela tem tool que sobe
o bridge ou a CLI do solver (`mix.is_heavy_tool`), `leve` no resto. Ele vem das cargas
gravadas do mesmo modo (e provedor, no agent) e do mesmo perfil (`store.record_is_heavy`,
pelas chamadas que passaram do pré-voo ou pelas tools dos casos selecionados): pico de
RSS e CPU média da árvore divididos pelas sessões que subiram, o maior entre as
`HISTORY_RUNS` mais recentes. Sem histórico do perfil vale a estimativa `DEFAULT_COST`
do modo e perfil (a pesada é maior e está documentada em `capacity.py`), e a resposta
avisa. O fator disco só entra quando a seleção grava: MB de disco por sessão = tamanho
da cópia (medido agora nas fixtures) × (1 + `SANDBOX_GROWTH`). Sem psutil só os núcleos
(e o disco) entram, com aviso. Memória e disco livres são instantâneos da consulta.

A tela mostra o recomendado, o limite de cada fator, o custo por sessão e o que a
seleção pede (pesada, grava, tamanho da cópia) perto de "Sessões simultâneas", e pede a
estimativa de novo quando a seleção muda; recusa valores acima do teto do modo e só
avisa acima do recomendado. O launcher recusa (422) o teto.

## Encerramento

Terminar ou cancelar deixa zero processo do servidor: o SDK encerra cada árvore
ao sair do cliente. No modo agent, parar encerra as sessões e a execução em curso conta em `abandoned_calls`. Pelo launcher, o motor roda num subprocesso que entra num
Job Object (Windows) ou é líder de sessão (POSIX); cancelar mata o grupo todo, e um
descendente criado no meio do kill não escapa. Ctrl+C na CLI interrompe com
elegância e grava o parcial com `interrupted: true` (código 130); um segundo
Ctrl+C aborta. A pasta temporária do run (sessões e cópias) é apagada pelo motor ao fim,
inclusive em erro e Ctrl+C; no cancelamento pelo launcher, que mata o motor, o launcher
a apaga depois que a árvore morre.

## Testes

```bash
uv run --no-sync pytest tests/e2e/load
```

Os testes unitários usam clientes e runners falsos (`fakes.py`): não sobem o
servidor nem um agente, e não gastam tokens. `test_sandbox_unit.py` abrange a cópia por
sessão (o que é copiado, caminhos distintos, prompt reescrito, workspace só da cópia,
reset entre execuções, disco e limpeza).
`test_load_integration.py` usa um servidor MCP falso (`fake_mcp_server.py`) por
stdio real para cobrir timeout com recriação, cancelamento e ausência de processos
sobrando. Com `LOAD_E2E_REAL=1` roda também uma carga curta contra o servidor real.
