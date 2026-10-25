# novomodelo-mcp

Servidor **MCP** (Model Context Protocol) do Novomodelo: uma **fachada fina e local**
sobre as ferramentas que já existem (`novomodelo` e `novomodelo-bridge`). Com ele, um
agente de IA valida, converte, compara, visualiza, roda e **lê resultados** de casos
por ferramentas padronizadas, sem que este servidor contenha regra de negócio.

> **Princípio:** cada ferramenta envelopa um subcomando de CLI (com `--json` quando
> existe) ou um binding oficial (`novomodelo-python`) e repassa o resultado. Nada de
> reimplementar conversão, validação ou comparação: correções vão para o upstream.

O repositório, o produto e o pacote se chamam `novomodelo-mcp`
(`<organização interna>/novomodelo-mcp`).

## Requisitos

| Peça | Versão | Como instalar |
|---|---|---|
| Python | >= 3.12 | — |
| [`uv`](https://docs.astral.sh/uv/) | — | — |
| `novomodelo` (CLI Rust) | **0.18.1** | instalador do release: `curl --proto '=https' --tlsv1.2 -LsSf https://github.com/ons-ccee-epe/novomodelo/releases/download/v0.18.1/novomodelo-cli-installer.sh \| sh` |
| `novomodelo-bridge` | **0.18.1** | vem com o `uv sync` deste repo |
| `novomodelo-python` | **0.18.1** | vem com o `uv sync` deste repo |

As três peças do novomodelo andam juntas: use a mesma versão em todas, porque o solver só
carrega uma política gravada pela mesma versão do binding. O pin exato fica só no bridge
(`novomodelo-bridge==0.18.1`), que por sua vez fixa a mesma versão da `novomodelo-python`.

## Instalação e execução

```bash
cd novomodelo-mcp
uv sync --system-certs     # --system-certs: redes com proxy que reassina certificados
uv run novomodelo-mcp      # sobe o servidor no transporte stdio
```

> **Rede corporativa:** sem `--system-certs` (ou `UV_SYSTEM_CERTS=1`), o `uv` pode
> falhar no PyPI com `UnknownIssuer` por causa do proxy que reassina certificados.

> **Pasta sincronizada (iCloud, OneDrive):** não desenvolva nem instale dentro dela. O
> iCloud marca os arquivos `.pth` do `.venv` como ocultos, e o Python ignora `.pth`
> ocultos: o `import novomodelo_mcp` falha, e parece faltar `PYTHONPATH`. Se o checkout
> precisa ficar ali, ponha o ambiente fora:
> `UV_PROJECT_ENVIRONMENT=~/.venvs/novomodelo-mcp uv sync` (e o mesmo valor no `uv run`).

O servidor fala **stdio**: não abre porta e é iniciado pelo cliente MCP como
subprocesso. A única requisição externa é a do `server_info` (ver *Versões e rede*).

### Configurar num cliente MCP (Claude Desktop, Claude Code, Kiro)

```bash
novomodelo-mcp configurar --cliente claude-desktop --workspace ~/estudos --mostrar  # só mostra
novomodelo-mcp configurar --cliente claude-desktop --workspace ~/estudos            # grava
```

(No checkout, use `uv run novomodelo-mcp configurar …`.) `--cliente` aceita
`claude-desktop`, `claude-code` e `kiro`; `--workspace` pode ser repetido, e a pasta que ainda não
existe é criada ao gravar (nunca com `--mostrar`). A pasta de trabalho não tem padrão: sem
`--workspace`, o comando pergunta a pasta de estudos quando roda num terminal e sai com
código 2, sem gravar nada, quando não há terminal. Para gravar sem pasta de trabalho, use
`--irrestrito` (não combina com `--workspace`).

O comando grava a entrada `novomodelo` com o **caminho absoluto** do executável deste
pacote (o release do novomodelo publica outro `novomodelo-mcp`, e o nome solto pegaria o
primeiro do `PATH`) e, se informado, `NOVOMODELO_MCP_WORKSPACE`. Altera só essa entrada;
o resto do arquivo é mantido. Uma entrada `novomodelo` que já exista é **substituída
inteira**: o cliente passa a usar o executável deste pacote, e variáveis de
desenvolvimento como `PYTHONPATH`, `NOVOMODELO_MCP_DOCS_DIR` e caminhos de binários saem
(o backup guarda a entrada anterior). Antes de gravar faz backup `<arquivo>.bak-AAAAMMDD-HHMMSS`;
rodar de novo sem mudança não grava nada. `--mostrar` imprime só o trecho que mudaria,
sem tocar em nada. Se o cliente não está na máquina (nem o programa nem a pasta de
configuração dele), o comando avisa e grava mesmo assim: a configuração fica pronta para
quando o cliente for instalado.

| Cliente | Arquivo | Tools de leitura |
|---|---|---|
| Claude Desktop | macOS `~/Library/Application Support/Claude/claude_desktop_config.json`; Windows `%APPDATA%\Claude\claude_desktop_config.json`; Linux `~/.config/Claude/claude_desktop_config.json` | sem lista: escolha "sempre permitir" na primeira chamada |
| Claude Code | `~/.claude.json` (escopo de usuário) | `permissions.allow` em `~/.claude/settings.json`, uma regra por tool |
| Kiro | `~/.kiro/settings/mcp.json` (o `.kiro/settings/mcp.json` do workspace vence) | `autoApprove` na entrada do servidor |

Feche o Claude Code antes de gravar: ele reescreve o `~/.claude.json` enquanto está
aberto. `--instrucoes` (desligado por padrão) também grava uma linha que orienta o
agente a usar o MCP para a metodologia: no Claude Code em `~/.claude/CLAUDE.md`, no Kiro em
`~/.kiro/steering/novomodelo.md`; no Claude Desktop só imprime a linha, para colar nas
preferências.

Depois de gravar, feche o cliente por completo e abra de novo. Para conferir, peça ao
agente a tool `server_info`: ela mostra a versão do MCP, os binários achados, as versões
das peças, o workspace e a origem das docs.

## Leitura × escrita (aprovação no cliente)

Cada tool declara, pelas anotações do MCP (`readOnlyHint`, `destructiveHint`,
`openWorldHint`), se só lê ou se escreve. O cliente pode usar isso para não pedir
aprovação nas tools de leitura. São **dicas**: quem decide é o cliente e a política
da organização. A classificação fica em `src/novomodelo_mcp/tools/annotations.py`;
`tests/test_tool_annotations.py` confere a tabela abaixo contra o servidor.

| Tipo | Tools |
|---|---|
| Só leitura | `server_info`, `solver_version`, `schema_list`, `schema_get`, `docs_list`, `docs_read`, `docs_search`, `deck_list`, `deck_read_json`, `deck_read_parquet`, `deck_describe_parquet`, `deck_sql`, `case_validate`, `case_summary`, `bridge_check_newave`, `bridge_check_decomp`, `results_status`, `results_convergence`, `results_list_entities`, `results_query`, `results_stochastic`, `results_policy`, `run_plan`, `run_status`, `run_logs` |
| Escreve arquivos novos | `case_init`, `schema_export`, `bridge_compare_newave`, `bridge_compare_decomp`, `bridge_dashboard`, `incluir_pastas` |
| Altera ou interrompe | `deck_edit_json`, `deck_edit_parquet`, `run_apply`, `run_start`, `run_cancel`, `instalar_novomodelo`, `bridge_convert_newave`, `bridge_convert_decomp` (com force, apagam o destino) |

A lista de liberação das tools de leitura (Claude Code e Kiro) é gravada pelo
`configurar`, a partir do servidor; para vê-la, rode
`novomodelo-mcp configurar --cliente claude-code --mostrar`.

## Segurança

As ferramentas de deck e resultado recebem caminhos controlados pelo agente. Defina
**`NOVOMODELO_MCP_WORKSPACE`** com a(s) raiz(es) permitida(s) (separadas por `:`):
qualquer caminho fora delas é **recusado** (fail-closed; `resolve()` neutraliza
symlinks e `..`). Sem essa variável o servidor opera **irrestrito**, e o `server_info`
sinaliza o estado.

A recusa (`exit_code` 13) diz ao agente para não ler o caminho por outras ferramentas,
traz a pasta do caminho em `pasta_sugerida` e pede que o agente pergunte ao usuário se
pode incluí-la. Com o sim, o agente chama `incluir_pastas` com todas as pastas de uma
vez: a inclusão vale na hora, sem reabrir o cliente, e fica em `pastas.json` no state
dir, somada às raízes de `NOVOMODELO_MCP_WORKSPACE`. `incluir_pastas` nunca entra na
lista de liberação automática, então o cliente pede aprovação a cada chamada; ela recusa
o que não é pasta, a pasta pessoal inteira (ou acima dela), a raiz do disco, pastas de
configuração de programas (as que começam com `.`, `AppData`, `Library`) e o state dir.
Um `pastas.json` ilegível não libera nada. Sem `NOVOMODELO_MCP_WORKSPACE`, a tool não grava
nada, porque tudo já é aceito. A mesma instrução está nas instructions do servidor e na
descrição de toda tool que recebe caminho.

Edições com `force=True` (gravar violando o schema), `case_init(force=True)`
(sobrescrever arquivos) e `bridge_convert_*(force=True)` (apaga o deck de destino) exigem
`NOVOMODELO_MCP_ALLOW_FORCE=1`.

## Prompt `metodologia`

O servidor oferece o prompt MCP `metodologia(tema)`: uma conversa sobre a metodologia do
novomodelo ancorada nas docs embutidas (busca em inglês com `docs_search`, leitura da
seção com `docs_read` e resposta em português citando `pagina#secao`; quando as docs não
cobrem o assunto, a resposta diz isso). `tema` é opcional e de uma palavra; sem ele, a
pergunta vem na mensagem seguinte.

| Cliente | Onde aparece |
|---|---|
| Claude Code | `/novomodelo:metodologia CVaR` (ou `/mcp__novomodelo__metodologia CVaR`); os argumentos são separados por espaço |
| Kiro | `#` no chat abre o menu de contexto; o prompt tem o ícone MCP e um formulário para `tema` |
| Claude Desktop | menu **+** abaixo da caixa de mensagem, em "novomodelo" |

## Versões e rede

O MCP conversa com o executável, a biblioteca (`novomodelo-python`) e o bridge da
mesma versão (o pin exato da biblioteca no pacote). Se alguma peça estiver em outra
versão, ou faltar, **toda** resposta traz `avisos_de_versao` com o comando para
corrigir; a chamada continua. Nenhum aviso manda rebaixar uma peça: a mais velha que o
MCP sobe até a versão dele; a mais nova pode ser usada, e o aviso aponta a página do guia
para conferir se já saiu o MCP dessa versão (o MCP não tem como saber).

A rede é usada só pelo `server_info`, para ver se há versão nova do novomodelo e do
bridge (no máximo uma vez a cada 6 horas, em poucos segundos), e pelo
`instalar_novomodelo`, e
apenas nestes domínios:
`github.com/ons-ccee-epe/*`, `api.github.com/repos/ons-ccee-epe/*`,
`pypi.org/pypi/novomodelo-bridge/*` e, como destino de download,
`release-assets.githubusercontent.com`. Um novomodelo ou um bridge novo aparece em
`versao_nova` sem comando de instalação: o MCP da mesma versão pode ainda não ter saído
(o repositório do MCP é privado), e a página do guia avisa quando sair. Junto vêm as
mudanças da versão nova (as seções "Changed" e "Fixed" das notas do release no GitHub, as
BREAKING primeiro, com teto de linhas) e o link das notas; o aviso de uma peça mais nova
que o MCP repete as mudanças dela. O HTTPS usa os
certificados do sistema (`truststore`), o que permite
atravessar proxy corporativo. Sem rede, a resposta diz que não foi possível
verificar e onde conferir. Documentação e schemas são embutidos e não usam a rede.

## Variáveis de ambiente

Todas usam o prefixo `NOVOMODELO_MCP_`.

| Variável | Default | Para quê |
|---|---|---|
| `NOVOMODELO_MCP_SOLVER_BIN` | (PATH) | caminho do `novomodelo` |
| `NOVOMODELO_MCP_BRIDGE_BIN` | (o do pacote, senão PATH) | opcional: outro `novomodelo-bridge`; tem prioridade sobre o do pacote |
| `NOVOMODELO_MCP_WORKSPACE` | — | raiz(es) permitida(s) para caminhos (fail-closed quando definida) |
| `NOVOMODELO_MCP_DOCS_DIR` | — | só desenvolvimento: pasta de páginas de um clone das docs, no lugar das embutidas (gera aviso; ver [Documentação e schemas](#documentação-e-schemas)) |
| `NOVOMODELO_MCP_SCHEMAS_DIR` | — | pasta com `*.schema.json` (ver [Documentação e schemas](#documentação-e-schemas)) |
| `NOVOMODELO_MCP_ALLOW_FORCE` | `0` | habilita `deck_edit_json(force=True)`, `case_init(force=True)` e `bridge_convert_*(force=True)`, que apaga o deck de destino |
| `NOVOMODELO_MCP_LOG` | `0` | loga cada chamada no stderr (debug/teste) |
| `NOVOMODELO_MCP_TIMEOUT` | `900` | timeout (s) por chamada de CLI |
| `NOVOMODELO_MCP_MAX_DIAGNOSTICS` | `50` | teto de itens de diagnóstico |
| `NOVOMODELO_MCP_MAX_SUMMARY_CHARS` | `20000` | teto de tamanho do `summary` |
| `NOVOMODELO_MCP_MAX_RESPONSE_KB` | `50` | teto de tamanho de uma resposta com linhas ou listas (`results_query`, `deck_sql`, `deck_read_parquet`, `results_convergence`, `results_policy`, `results_stochastic`, `case_summary`); acima dele as linhas são cortadas, com `cortado_por_tamanho` |
| `NOVOMODELO_MCP_MAX_READ_BYTES` | `5000000` | teto de bytes do que é carregado inteiro na memória: leitura de JSON e `deck_describe_parquet`/`deck_edit_parquet` (pasta ou parquet maior é recusado e aponta o `deck_sql`) |
| `NOVOMODELO_MCP_STATE_DIR` | por SO (ver abaixo) | estado persistente: runs assíncronos (`jobs/`) e calibração (`calibration.json`) |
| `NOVOMODELO_MCP_MAX_JOBS` | `1` | runs simultâneos permitidos pelo `run_start` |
| `NOVOMODELO_MCP_MAX_POLICY_BYTES` | `1073741824` (1 GiB) | maior política (em disco) que o `results_policy` aceita carregar; a biblioteca lê a política inteira em memória |

### Plataformas

Windows, macOS e Linux (inclusive containers). O estado persistente fica em
`NOVOMODELO_MCP_STATE_DIR` ou, por padrão, em `%LOCALAPPDATA%\novomodelo-mcp` (Windows),
`~/Library/Application Support/novomodelo-mcp` (macOS) ou `$XDG_STATE_HOME/novomodelo-mcp`
(Linux, padrão `~/.local/state/novomodelo-mcp`), nunca no diretório temporário do SO.
A detecção de máquina respeita afinidade de CPU e limites de cgroup (Docker/K8s).
Os runs assíncronos são supervisionados por um runner destacado do servidor: o
estado sobrevive a restart do servidor e o cancelamento encerra a árvore de
processos nos três SOs.

## Documentação e schemas

As docs e os schemas são lidos do disco, sem rede.

- **Docs** (`docs_list`, `docs_read`): sempre as **embutidas** no pacote
  (`src/novomodelo_mcp/_bundled/docs`), que são as da versão do MCP. A versão e o commit
  das docs ficam em `_bundled/manifest.json` e aparecem no `server_info` (`docs`).
- **Schemas** (`schema_list`, `schema_get`, `run_apply`, `deck_edit_json`): a primeira fonte
  que existir vence: `NOVOMODELO_MCP_SCHEMAS_DIR`, depois `novomodelo schema export` do
  executável instalado, depois a cópia embutida `_bundled/schemas`.

### Atualizar as docs embutidas (desenvolvimento)

```bash
uv run python scripts/sync_bundled.py --source /caminho/para/clone/do/novomodelo-docs
uv run python scripts/sync_bundled.py --source /caminho/para/clone/do/novomodelo-docs --check
```

O script grava as páginas já resolvidas (os trechos `_impl` entram no lugar dos
componentes, e a marcação MDX sai), os schemas, o índice de busca
(`_bundled/docs_index.sqlite`) e o manifesto (versão do `versions.json` das docs e commit
do clone). Com `--check`, não grava e sai com erro se o embutido divergir da fonte; o CI
roda essa checagem no commit gravado no manifesto.

Para testar mudanças nas docs antes de um release, `NOVOMODELO_MCP_DOCS_DIR` aponta para
a pasta de páginas de um clone (`src/content/docs`). É uma opção de desenvolvimento: com
ela, toda resposta traz um aviso em `avisos_de_versao`.

## Ferramentas

O cliente prefixa cada tool com o nome do servidor (ex.: `mcp__novomodelo__case_validate`).

**Pré-rodada** (`tools/pre_run.py`)
- `bridge_check_newave(src)`: pré-valida entradas NEWAVE (`novomodelo-bridge check newave`)
- `bridge_convert_newave(src, dst, validate, force, dry_run)`: converte NEWAVE → Novomodelo
- `bridge_check_decomp(src)` / `bridge_convert_decomp(src, dst, validate, force, dry_run)`: paridade DECOMP
- `case_validate(case_dir, output_dir)`: valida o deck (binding `novomodelo.io.validate`, estruturado; fallback para o texto do CLI); com `output_dir`, confere também a saída de uma rodada anterior (retomada)
- `case_summary(case_dir)`: o caso como o novomodelo o lê (`novomodelo.io.load_case`): contagens por tipo e `{id, name}` de cada item, com teto

**Pós-rodada** (`tools/post_run.py`)
- `bridge_compare_newave(newave_dir, output_dir, tolerance, fmt, out_dir)` / `bridge_compare_decomp(decomp_dir, output_dir, ...)`: compara resultados. `output_dir` é a pasta de **saída** do `novomodelo run` do caso convertido, não a pasta do caso. O `compare` sai com código 0 mesmo com divergência: o veredito está no envelope
- `bridge_dashboard(case_dir)`: dashboard HTML a partir da pasta do **caso** (grava `<case_dir>/dashboard.html` e devolve o caminho)

**Resultados** (`tools/results.py`)
- `results_status(output_dir)`: status, bounds, gap, iterações, custo e `software_version` (lê os `metadata.json`; em runs ≤ 0.17 usa o campo antigo `cobre_version`)
- `results_convergence(output_dir, tail)`: trajetória de convergência (`convergence.parquet`)
- `results_list_entities(output_dir)`: entidades de simulação disponíveis
- `results_query(output_dir, entity, columns, group_by, agg, scenario, limit)`: consulta agregada da simulação
- `results_stochastic(output_dir, hydro_id, stage, aberturas_do_estagio)`: coeficientes do PAR(p) e árvore de aberturas do run (exige `exports.stochastic: true` no config.json do run)
- `results_policy(output_dir, stage, policy_subdir)`: resumo da política treinada (cortes e cortes ativos por estágio; com `stage`, os cortes daquele estágio sem os coeficientes)

**Manipulador de decks** (`tools/deck.py`)
- `deck_list(case_dir, max_files)`: **mapa do caso**. Lista as entradas (.json/.parquet) com caminho, tamanho e o tipo de schema; resume cada rodada (pasta com `training/metadata.json`) numa linha, sem listar a saída; cita os demais arquivos só pelo nome
- `deck_read_json` · `deck_read_parquet` · `deck_describe_parquet`
- `deck_edit_json(path, changes, dry_run, ensure_valid, force)`: backup + escrita atômica; `ensure_valid=True` revalida o caso e reverte se reprovar
- `deck_edit_parquet(path, where, set_values, dry_run)`: preserva colunas e dtypes
- `deck_sql(query, max_rows)`: SQL **read-only** (DuckDB: `SELECT`, `WITH`, `DESCRIBE`, `SUMMARIZE`) sobre parquet/csv/json do deck ou dos resultados; caminhos confinados ao workspace

**Referência** (`tools/reference.py`)
- `schema_list()` / `schema_get(tipo)`: JSON Schemas de entrada; também no resource `novomodelo://schema/{tipo}`
- `docs_list(section)`: páginas das docs embutidas, com título e descrição
- `docs_read(page, secao)`: uma página das docs embutidas; com `secao` (âncora devolvida pelo `docs_search`, ou título), só aquela seção; sem `page`, a lista de páginas (a do `docs_list`)
- `docs_search(consulta, k)`: busca por palavra nas docs embutidas (de preferência em inglês; os termos em português do glossário das docs são traduzidos); devolve página, seção e trecho

**Solver** (`tools/novomodelo_meta.py`)
- `solver_version()`: versão, backend e build do `novomodelo` (texto do CLI parseado + `raw`)
- `schema_export(output_dir)`: exporta os JSON Schemas (`novomodelo schema export`)
- `instalar_novomodelo(confirmar, pasta)`: instala o executável oficial da versão esperada pelo instalador do release, com o SHA-256 conferido; sem `confirmar=True`, só mostra o plano (URL, hash, destino, comando manual). Usa a rede. No Windows, o instalador oficial `.ps1` não confere o hash do pacote que ele baixa

**Scaffold e execução** (`tools/run.py`)
- `case_init(directory, template, list, force)`: cria um caso a partir de template embutido (`novomodelo init`; ex.: `1dtoy`)
- `run_plan(case_dir, time_budget_s=900, threads)`: **não executa, não grava**. Estima tempo
  (custo computacional) e memória do run local. O tempo por solve é **medido nesta máquina**,
  separado para treino e simulação (`duração ÷ solves` dos `metadata.json`): primeiro o registro
  de calibração do MCP (runs via `run_start`, indexados por `machine_id`), depois
  `training/metadata.json` do workspace com o mesmo hostname. Prefere runs com a **mesma modelagem**
  (dimensões + assinatura do `config.json`). Threads: núcleos de **performance** em CPU híbrida,
  senão cores − 1. Modelo `solves ≈ iters × fwd × Σ(1+aberturas)`. Devolve máquina, pontos de
  referência, a conta, parâmetros atuais × sugeridos (`apply_overrides`), veredito (`cabe` |
  `cabe_com_ajustes` | `nao_cabe` | `indeterminado`) e o aviso de que run local pequeno **pode não convergir**
- `run_apply(case_dir, overrides, dry_run)`: aplica knobs de **config.json** (`forward_passes`,
  `iteration_limit`, `simulation_scenarios`, `simulation_enabled`) com schema + backup + escrita atômica
- `run_start(case_dir, threads, output, time_budget_s, override, overwrite)`: dispara `novomodelo run … --comm-backend local
  --quiet` em background e devolve `job_id` na hora; recusa se o plano disser `nao_cabe` (salvo `override=True`)
  e recusa um `output` com rodada concluída, sugerindo outro (`output_sugerido`), salvo `overwrite=True`
- `run_status(job_id)` · `run_logs(job_id, lines)` · `run_cancel(job_id)`

**Diagnóstico**
- `server_info()`: a versão do MCP (`versao_mcp`), binários, versões das peças (`versoes`), se há versão nova (`versao_nova`), workspace, pastas incluídas (`pastas_incluidas`), docs, state dir e settings
- `incluir_pastas(pastas)`: acrescenta pastas de estudo às raízes do guard, depois de o usuário aceitar; vale na hora e fica gravado em `pastas.json` no state dir

## Estrutura

```
src/novomodelo_mcp/
├── server.py              # sobe o FastMCP e registra as tools
├── config.py              # Settings lidos do ambiente (prefixo NOVOMODELO_MCP_)
├── names.py               # nomes dos programas externos (solver, bridge, binding)
├── adapters/              # única camada que toca processo, arquivo ou binding
│   ├── bridge.py          # run_bridge (CLI do bridge, --json)
│   ├── novomodelo.py      # CLI do solver + validação pelo binding
│   ├── discovery.py       # acha binários e versões
│   ├── reference.py       # docs e schemas (cascata acima)
│   ├── deck_io.py         # leitura/edição de deck (JSON/Parquet)
│   ├── results.py         # leitura de resultados
│   ├── sql.py             # SQL read-only (DuckDB) + guard fail-closed
│   ├── validate.py        # checagem leve de parâmetros do compare
│   ├── machine.py         # CPUs (performance/híbrida, cgroup), RAM; multiplataforma
│   ├── runtime.py         # tempo medido por solve + registro de calibração
│   ├── run_plan.py        # plano de execução (leitura do caso + veredito)
│   ├── jobs.py            # runs assíncronos: estado, logs, cancelamento
│   ├── _job_runner.py     # supervisor destacado de cada run
│   ├── state.py           # state dir por SO, escrita atômica, lock
│   ├── paths.py           # guard de workspace (fail-closed)
│   ├── obs.py             # log opcional no stderr
│   └── envelope.py        # envelope de erro (fonte única)
├── tools/                 # o que o agente enxerga: registra as tools e molda a saída
│   ├── pre_run.py · post_run.py · results.py · deck.py · reference.py
│   ├── novomodelo_meta.py · run.py · shaping.py
│   ├── annotations.py     # leitura × escrita de cada tool (anotações MCP)
└── _bundled/              # cópia embutida de docs e schemas (ver acima)
scripts/
├── sync_bundled.py        # atualiza _bundled/ a partir de um clone do novomodelo-docs
├── rebrand/map.toml       # mapa de nomes para a ferramenta de rename do upstream
└── gen/sync-kiro-steering.py
tests/
├── test_*.py · smoke_*.py # pytest coleta os dois; offline
├── fake_novomodelo.py · fake_novomodelo_bridge.py · _fakes.py   # binários falsos
└── try_tools.py           # utilitário manual (fora do CI)
```

## Testes

```bash
uv run pytest -q              # suíte completa (test_* e smoke_*), offline, com binários falsos
uv run ruff check src tests
```

**Bateria de ponta a ponta** contra os programas reais (fora do CI): sobe o servidor como um
cliente MCP, confere as anotações que ele anuncia e chama todas as tools num rascunho dentro do
workspace (`<workspace>/_e2e/<data-hora>/`). As tools do bridge usam os decks mínimos públicos do
`novomodelo-bridge` (`tests/decks/newave_mini` e `decomp_mini`); sem `--bridge-repo`, elas ficam como PULADAS:

```bash
uv run python scripts/e2e_live.py --workspace /caminho/para/estudos \
    --bridge-repo /caminho/para/novomodelo-bridge     # decks mínimos públicos do bridge
uv run python scripts/e2e_live.py --workspace … --bridge-repo … --claude-code   # + aprovação no Claude Code
```

A execução **real** do solver (`novomodelo init 1dtoy` + 1 iteração) fica fora do CI:
`NOVOMODELO_MCP_REAL_SOLVER=1 uv run python tests/smoke_run.py`.

## Renomear o produto

O nome do produto já mudou uma vez e vai mudar de novo (<nome futuro>).
O rename é feito pela mesma ferramenta que o upstream usa
(`novomodelo/scripts/rebrand/rebrand.py`), guiada por `scripts/rebrand/map.toml`:

```bash
R=/caminho/para/novomodelo/scripts/rebrand/rebrand.py
M=scripts/rebrand/map.toml
uv run --no-sync python $R paths  --root . --map $M   # move caminhos (git mv); commitar sozinho
uv run --no-sync python $R tokens --root . --map $M   # reescreve conteúdo
uv run --no-sync python $R check  --root . --map $M   # 0 ocorrências = pronto
```

Para o próximo nome, crie um mapa com `from = "novomodelo"`. As exceções atuais
(`<repositório anterior>`, `cobre_version`, `cobrem`) estão comentadas no próprio mapa.

**Temporário, enquanto o MCP vive fora do repo do novomodelo:** o CI roda o `check` em todo push e PR (job `rename-guard`), com a ferramenta baixada do
novomodelo na mesma tag do pin do `novomodelo-bridge`. Se o nome antigo reaparecer, o CI falha.

## Atualizar para uma versão nova do novomodelo

**Temporário, enquanto o MCP vive fora do repo do novomodelo:** o Dependabot abre um PR para a `develop` quando sai um `novomodelo-bridge` novo; a
`novomodelo-python` sobe junto no `uv.lock`. Ao aceitar, suba junto o `ref` do job `rename-guard` em `.github/workflows/ci.yml` para a
mesma tag, e atualize o novomodelo e o bridge na máquina para a mesma versão.

A versão do MCP (`version` no `pyproject.toml`) é a do novomodelo; uma correção só do MCP
vira `.postN` (ex.: `0.18.0.post1`). `tests/test_package_metadata.py` confere que a versão
acompanha o pin do bridge e que o `initialize` anuncia a versão do MCP.

## Release

`.github/workflows/release.yml` gera o pacote a partir de uma tag `v<versão>`, igual à
`version` do `pyproject.toml` (com outra versão, o workflow falha):

1. confere as docs embutidas contra o commit do `novomodelo-docs` gravado no manifesto e
   roda os testes;
2. gera o wheel e o sdist, e o `SHA256SUMS` dos dois;
3. instala o wheel com `uv tool install` num diretório vazio, em Linux, macOS e Windows, e
   confere pelo stdio a versão anunciada, as tools e o `server_info`
   (`scripts/conferir_instalacao.py`);
4. publica os arquivos no release do GitHub com o nome da tag.

Quem cria a tag é quem mantém o repositório (`git tag v0.18.0 && git push origin v0.18.0`). Para
ensaiar sem publicar, faça push numa branch `ensaio/<nome>` (ou use "Run workflow" na aba
Actions, depois que o workflow estiver na branch padrão): os arquivos ficam como artefato
da execução.

Se a organização não permitir `contents: write` ao `GITHUB_TOKEN`, o job "Publicar no
release" falha e o resto continua valendo. Nesse caso, baixe o artefato da execução e
anexe à mão: `gh release create v<versão> novomodelo_mcp-*.whl novomodelo_mcp-*.tar.gz
SHA256SUMS --title "novomodelo-mcp <versão>"`.

## Licença

Apache-2.0 (ver `LICENSE`), alinhada ao ecossistema Novomodelo.
