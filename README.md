# novomodelo-mcp

Servidor [MCP](https://modelcontextprotocol.io) (Model Context Protocol) do
[novomodelo](https://github.com/ons-ccee-epe/novomodelo): com ele, um agente de IA valida,
converte, compara, roda e lê os resultados de casos, e responde sobre a metodologia pelas
docs oficiais.

O servidor é uma fachada local sobre as ferramentas do ecossistema: cada tool chama um
subcomando do `novomodelo` ou do `novomodelo-bridge` (com `--json`), ou o binding
`novomodelo-python`, e repassa o resultado. Ele não reimplementa conversão, validação nem
comparação. Fala **stdio**, não abre porta e é iniciado pelo cliente MCP como subprocesso.

## Instalação

```bash
uv tool install --compile-bytecode novomodelo-mcp
```

O pacote traz o `novomodelo-bridge`, a biblioteca `novomodelo-python` e as docs da mesma
versão. O executável `novomodelo` é instalado à parte, na mesma versão: peça ao agente
"instale o executável do novomodelo" (tool `install_novomodelo`, que usa o instalador
oficial da release e confere o SHA-256), ou use o instalador da
[release](https://github.com/ons-ccee-epe/novomodelo/releases) da versão do MCP.

Requisitos: Python 3.12 ou mais novo e [`uv`](https://docs.astral.sh/uv/). Os requisitos do
executável por sistema estão na página de instalação das
[docs](https://docs.modelossetoreletrico.org.br/).

> **Rede com proxy que reassina certificados:** use `uv tool install --system-certs …`
> (ou `UV_SYSTEM_CERTS=1`); sem isso, o `uv` pode falhar no PyPI com `UnknownIssuer`.

### Instalar com um assistente de IA

Cole este pedido no seu assistente (Claude Code, Kiro, Claude Desktop ou outro):

```text
Quero instalar o MCP do novomodelo (pacote novomodelo-mcp, no PyPI) nesta máquina. Siga os passos abaixo, na ordem.

Como trabalhar:
- Se você pode rodar comandos nesta máquina, rode-os você mesmo, mas mostre cada comando antes e espere a minha aprovação.
- Se você não pode, me guie passo a passo: um comando de cada vez, esperando eu colar a saída antes de seguir.
- Se um passo falhar, pare e me explique o erro antes de tentar outra coisa.

Passos:
1. Descubra o sistema: Windows, Mac ou Linux. No Windows, use o PowerShell.
2. Veja se o uv está instalado (uv --version). Se faltar, instale pelo instalador oficial (https://docs.astral.sh/uv/) e recarregue o terminal.
3. Instale: uv tool install --compile-bytecode novomodelo-mcp. Se depois o novomodelo-mcp não for encontrado, recarregue o terminal.
4. Pergunte qual cliente eu uso: Claude Desktop (claude-desktop), Claude Code (claude-code) ou Kiro (kiro). Pergunte também em que pasta ficam os meus estudos: o MCP só lê e grava dentro dela. Não escolha a pasta por mim. Rode primeiro, só para mostrar o que vai ser gravado:
   novomodelo-mcp configurar --cliente <cliente> --workspace "<pasta>" --mostrar
   Me mostre o resultado e, depois que eu aprovar, rode o mesmo comando sem o --mostrar.
   Se você é o próprio Claude Code e o cliente é o claude-code, não rode o comando sem o --mostrar: o Claude Code reescreve o ~/.claude.json enquanto está aberto. Me peça para fechar o Claude Code, rodar esse comando num terminal e abrir o Claude Code de novo.
5. Peça que eu feche e abra o cliente e, numa conversa nova, peça "rode o server_info".
6. Se o server_info avisar que falta o executável do novomodelo, me diga para pedir, na mesma conversa: "instale o executável do novomodelo".
```

### Configurar num cliente MCP

```bash
novomodelo-mcp configurar --cliente claude-desktop --workspace ~/estudos --mostrar  # só mostra
novomodelo-mcp configurar --cliente claude-desktop --workspace ~/estudos            # grava
```

`--cliente` aceita `claude-desktop`, `claude-code` e `kiro`; `--workspace` pode ser
repetido, e a pasta que ainda não existe é criada ao gravar (nunca com `--mostrar`). A
pasta de trabalho não tem padrão: sem `--workspace`, o comando pergunta a pasta de estudos
quando roda num terminal e sai com código 2, sem gravar nada, quando não há terminal. Para
gravar sem pasta de trabalho, use `--irrestrito` (não combina com `--workspace`).

O comando grava a entrada `novomodelo` com o **caminho absoluto** do executável deste
pacote e, se informado, `NOVOMODELO_MCP_WORKSPACE`. Altera só essa entrada; o resto do
arquivo é mantido. Uma entrada `novomodelo` que já exista é **substituída inteira** (o
backup guarda a anterior). Antes de gravar faz backup `<arquivo>.bak-AAAAMMDD-HHMMSS`;
rodar de novo sem mudança não grava nada. Se o cliente não está na máquina, o comando
avisa e grava mesmo assim: a configuração fica pronta para quando o cliente for instalado.

| Cliente | Arquivo | Tools de leitura |
|---|---|---|
| Claude Desktop | macOS `~/Library/Application Support/Claude/claude_desktop_config.json`; Windows `%APPDATA%\Claude\claude_desktop_config.json`; Linux `~/.config/Claude/claude_desktop_config.json` | sem lista: escolha "sempre permitir" na primeira chamada |
| Claude Code | `~/.claude.json` (escopo de usuário) | `permissions.allow` em `~/.claude/settings.json`, uma regra por tool |
| Kiro | `~/.kiro/settings/mcp.json` (o `.kiro/settings/mcp.json` do workspace vence) | pede aprovação; o `autoApprove` gravado na entrada do servidor é ignorado pelo Kiro atual |

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
da organização.

| Tipo | Tools |
|---|---|
| Só leitura | `server_info`, `solver_version`, `schema_list`, `schema_get`, `docs_list`, `docs_read`, `docs_search`, `deck_list`, `deck_read_json`, `deck_read_parquet`, `deck_describe_parquet`, `deck_sql`, `case_validate`, `case_summary`, `bridge_check_newave`, `bridge_check_decomp`, `results_status`, `results_convergence`, `results_list_entities`, `results_query`, `results_stochastic`, `results_policy`, `run_plan`, `run_status`, `run_logs` |
| Escreve arquivos novos | `case_init`, `schema_export`, `bridge_convert_newave`, `bridge_convert_decomp`, `bridge_compare_newave`, `bridge_compare_decomp`, `bridge_dashboard`, `include_folders` |
| Altera ou interrompe | `deck_edit_json`, `deck_edit_parquet`, `run_apply`, `run_start`, `run_cancel`, `install_novomodelo` |

A lista de liberação das tools de leitura (Claude Code e Kiro) é gravada pelo
`configurar`, a partir do servidor; para vê-la, rode
`novomodelo-mcp configurar --cliente claude-code --mostrar`.

## Ferramentas

O cliente prefixa cada tool com o nome do servidor (ex.: `mcp__novomodelo__case_validate`).

**Pré-rodada**
- `bridge_check_newave(src)`: pré-valida entradas NEWAVE (`novomodelo-bridge check newave`)
- `bridge_convert_newave(src, dst, validate, force, dry_run)`: converte NEWAVE → novomodelo
- `bridge_check_decomp(src)` / `bridge_convert_decomp(src, dst, validate, force, dry_run, import_fcf)`: o mesmo para DECOMP; `import_fcf=False` converte sem importar os cortes da FCF (`--no-fcf`)
- `case_validate(case_dir, output_dir)`: valida o deck (binding `novomodelo.io.validate`, estruturado; fallback para o texto do CLI); com `output_dir`, confere também a saída de uma rodada anterior (retomada)
- `case_summary(case_dir)`: o caso como o novomodelo o lê (`novomodelo.io.load_case`): contagens por tipo (`counts`) e `{id, name}` de cada item (`items`), com teto

**Pós-rodada**
- `bridge_compare_newave(newave_dir, output_dir, tolerance, fmt, out_dir)` / `bridge_compare_decomp(decomp_dir, output_dir, ...)`: compara resultados. `output_dir` é a pasta de **saída** do `novomodelo run` do caso convertido, não a pasta do caso. O `compare` sai com código 0 mesmo com divergência: o veredito está no envelope
- `bridge_dashboard(case_dir)`: dashboard HTML a partir da pasta do **caso** (grava `<case_dir>/dashboard.html` e devolve o caminho)

**Resultados**

`output_dir` é a pasta de uma rodada: a que tem `training/metadata.json`, com qualquer nome. Uma pasta acima dela (a do caso, a do estudo) é recusada, e a recusa traz as rodadas encontradas abaixo: com uma só, em `suggested_output`; com várias, só a lista em `runs`, para o usuário escolher.

- `results_status(output_dir)`: status, bounds, gap, iterações, custo e `software_version` (lê os `metadata.json`)
- `results_convergence(output_dir, tail)`: trajetória de convergência (`convergence.parquet`)
- `results_list_entities(output_dir)`: entidades de simulação disponíveis
- `results_query(output_dir, entity, columns, group_by, agg, scenario, limit)`: consulta agregada da simulação
- `results_stochastic(output_dir, hydro_id, stage, openings_stage)`: coeficientes do PAR(p) e árvore de aberturas do run (exige `exports.stochastic: true` no config.json do run)
- `results_policy(output_dir, stage, policy_subdir)`: resumo da política treinada (cortes e cortes ativos por estágio; com `stage`, os cortes daquele estágio sem os coeficientes)

**Decks**
- `deck_list(case_dir, max_files)`: **mapa do caso**. Lista as entradas (.json/.parquet) com caminho, tamanho e o tipo de schema; resume cada rodada (pasta com `training/metadata.json`) numa linha, sem listar a saída; cita os demais arquivos só pelo nome
- `deck_read_json` · `deck_read_parquet` · `deck_describe_parquet`
- `deck_edit_json(path, changes, dry_run, ensure_valid, force)`: backup + escrita atômica; `ensure_valid=True` revalida o caso e reverte se reprovar
- `deck_edit_parquet(path, where, set_values, dry_run)`: preserva colunas e dtypes
- `deck_sql(query, max_rows)`: SQL **read-only** (DuckDB: `SELECT`, `WITH`, `DESCRIBE`, `SUMMARIZE`) sobre parquet/csv/json do deck ou dos resultados; caminhos confinados ao workspace

**Referência**
- `schema_list()` / `schema_get(type)`: JSON Schemas de entrada; também no resource `novomodelo://schema/{type}`
- `docs_list(prefix)`: páginas das docs embutidas, com título e descrição; com `prefix`, só as de caminho começando por ele
- `docs_read(page, section)`: uma página das docs embutidas; com `section` (âncora devolvida pelo `docs_search`, ou título), só aquela seção; sem `page`, a lista de páginas (a do `docs_list`)
- `docs_search(query, k)`: busca por palavra nas docs embutidas (de preferência em inglês; os termos em português do glossário das docs são traduzidos); devolve página, seção e trecho

**Solver**
- `solver_version()`: versão, backend e build do `novomodelo` (texto do CLI parseado + `raw`)
- `schema_export(output_dir)`: exporta os JSON Schemas (`novomodelo schema export`)
- `install_novomodelo(confirm, install_dir)`: instala o executável oficial da versão esperada pelo instalador da release, com o SHA-256 conferido; sem `confirm=True`, só mostra o plano (URL, hash, destino, comando manual). Usa a rede. No Windows, o instalador oficial `.ps1` não confere o hash do pacote que ele baixa

**Caso e execução**
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
  e recusa um `output` com rodada concluída, sugerindo outro (`suggested_output`), salvo `overwrite=True`
- `run_status(job_id)` · `run_logs(job_id, lines)` · `run_cancel(job_id)`

**Diagnóstico**
- `server_info()`: a versão do MCP (`mcp_version`), binários, versões das peças (`versions`), se há versão nova (`new_version`), workspace, pastas incluídas (`included_folders`), docs, state dir e settings
- `include_folders(folders)`: acrescenta pastas de estudo às raízes do guard, depois de o usuário aceitar; vale na hora e fica gravado em `pastas.json` no state dir

### Prompt `metodologia`

O servidor oferece o prompt MCP `metodologia(tema)`: uma conversa sobre a metodologia do
novomodelo ancorada nas docs embutidas (busca em inglês com `docs_search`, leitura da
seção com `docs_read` e resposta em português citando `page#section`; quando as docs não
tratam do assunto, a resposta diz isso). `tema` é opcional e de uma palavra; sem ele, a
pergunta vem na mensagem seguinte.

| Cliente | Onde aparece |
|---|---|
| Claude Code | `/novomodelo:metodologia CVaR` (ou `/mcp__novomodelo__metodologia CVaR`); os argumentos são separados por espaço |
| Kiro | `#` no chat abre o menu de contexto; o prompt tem o ícone MCP e um formulário para `tema` |
| Claude Desktop | menu **+** abaixo da caixa de mensagem, em "novomodelo" |

## Segurança

As ferramentas de deck e resultado recebem caminhos controlados pelo agente. Defina
**`NOVOMODELO_MCP_WORKSPACE`** com a(s) raiz(es) permitida(s) (separadas por `:`):
qualquer caminho fora delas é **recusado** (fail-closed; `resolve()` neutraliza
symlinks e `..`). Sem essa variável o servidor opera **irrestrito**, e o `server_info`
sinaliza o estado.

A recusa (`exit_code` 13) diz ao agente para não ler o caminho por outras ferramentas,
traz a pasta do caminho em `suggested_folder` e pede que o agente pergunte ao usuário se
pode incluí-la. Com o sim, o agente chama `include_folders` com todas as pastas de uma
vez: a inclusão vale na hora, sem reabrir o cliente, e fica em `pastas.json` no state
dir, somada às raízes de `NOVOMODELO_MCP_WORKSPACE`. `include_folders` nunca entra na
lista de liberação automática, então o cliente pede aprovação a cada chamada; ela recusa
o que não é pasta, a pasta pessoal inteira (ou acima dela), a raiz do disco, pastas de
configuração de programas (as que começam com `.`, `AppData`, `Library`) e o state dir.
Um `pastas.json` ilegível não libera nada. Sem `NOVOMODELO_MCP_WORKSPACE`, a tool não grava
nada, porque tudo já é aceito.

Edições com `force=True` (gravar violando o schema), `case_init(force=True)`
(sobrescrever arquivos) e `bridge_convert_*(force=True)` (apaga o deck de destino) exigem
`NOVOMODELO_MCP_ALLOW_FORCE=1`.

## Versões e rede

O MCP conversa com o executável, a biblioteca (`novomodelo-python`) e o bridge da
mesma versão. Se alguma peça estiver em outra versão, ou faltar, **toda** resposta traz
`version_warnings` com os comandos para alinhar; a chamada continua, e a instrução do
servidor pede ao agente que ofereça rodar os comandos, com o ok da pessoa. A peça mais
velha que o MCP sobe até a versão dele. Para a mais nova há dois caminhos: atualizar o
MCP para a versão dela, ou voltar a peça para a versão do MCP.

A rede é usada só pelo `server_info`, para ver se há versão nova do novomodelo, do bridge e
do MCP (no máximo uma vez a cada 6 horas, em poucos segundos), e pelo `install_novomodelo`,
e apenas nestes domínios: `github.com/ons-ccee-epe/*`, `api.github.com/repos/ons-ccee-epe/*`,
`pypi.org/pypi/novomodelo-bridge/*`, `pypi.org/pypi/novomodelo-mcp/*` e, como destino de
download, `release-assets.githubusercontent.com`. Junto com a versão nova vêm as mudanças
dela (as seções "Changed" e "Fixed" das notas da release, as BREAKING primeiro, com teto de
linhas) e o link das notas. O HTTPS usa os certificados do sistema (`truststore`), o que
permite atravessar proxy corporativo. Sem rede, a resposta diz que não foi possível
verificar e onde conferir. Documentação e schemas são embutidos e não usam a rede.

## Documentação e schemas

As docs e os schemas são lidos do disco, sem rede.

- **Docs** (`docs_list`, `docs_read`, `docs_search`): as embutidas no pacote, que são as
  da versão do MCP, com os changelogs do novomodelo e do bridge (`changelog/novomodelo` e
  `changelog/novomodelo-bridge`, uma seção por versão). A versão e o commit das docs
  aparecem no `server_info` (`docs`).
- **Schemas** (`schema_list`, `schema_get`, `run_apply`, `deck_edit_json`): a primeira fonte
  que existir vence: `NOVOMODELO_MCP_SCHEMAS_DIR`, depois `novomodelo schema export` do
  executável instalado, depois a cópia embutida.

## Variáveis de ambiente

Todas usam o prefixo `NOVOMODELO_MCP_`.

| Variável | Default | Para quê |
|---|---|---|
| `NOVOMODELO_MCP_SOLVER_BIN` | (PATH) | caminho do `novomodelo` |
| `NOVOMODELO_MCP_BRIDGE_BIN` | (o do pacote, senão PATH) | opcional: outro `novomodelo-bridge`; tem prioridade sobre o do pacote |
| `NOVOMODELO_MCP_WORKSPACE` | — | raiz(es) permitida(s) para caminhos (fail-closed quando definida) |
| `NOVOMODELO_MCP_DOCS_DIR` | — | só desenvolvimento: pasta de páginas de um clone das docs, no lugar das embutidas (gera aviso em `version_warnings`) |
| `NOVOMODELO_MCP_SCHEMAS_DIR` | — | pasta com `*.schema.json` (ver [Documentação e schemas](#documentação-e-schemas)) |
| `NOVOMODELO_MCP_ALLOW_FORCE` | `0` | habilita `deck_edit_json(force=True)`, `case_init(force=True)` e `bridge_convert_*(force=True)`, que apaga o deck de destino |
| `NOVOMODELO_MCP_LOG` | `0` | loga cada chamada no stderr (debug/teste) |
| `NOVOMODELO_MCP_TIMEOUT` | `900` | timeout (s) por chamada de CLI |
| `NOVOMODELO_MCP_MAX_DIAGNOSTICS` | `50` | teto de itens de diagnóstico |
| `NOVOMODELO_MCP_MAX_SUMMARY_CHARS` | `20000` | teto de tamanho do `summary` |
| `NOVOMODELO_MCP_MAX_RESPONSE_KB` | `50` | teto de tamanho de uma resposta com linhas ou listas (`results_query`, `deck_sql`, `deck_read_parquet`, `results_convergence`, `results_policy`, `results_stochastic`, `case_summary` e as tools `bridge_*`); acima dele as linhas são cortadas, com `size_truncation`; nas tools `bridge_*`, são as linhas das tabelas dos diagnósticos, a maior tabela primeiro, e cada tabela cortada traz `truncated` e `rows_total` |
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

## Licença

Apache-2.0, a mesma do novomodelo.

## Links

- Docs: <https://docs.modelossetoreletrico.org.br/>
- Repositório: <https://github.com/ons-ccee-epe/novomodelo-mcp>
- Issues: <https://github.com/ons-ccee-epe/novomodelo-mcp/issues>
- Notas de cada versão: <https://github.com/ons-ccee-epe/novomodelo-mcp/releases>
