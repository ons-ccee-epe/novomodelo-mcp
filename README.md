# <repositório anterior>

Servidor **MCP** (Model Context Protocol) do Cobre — uma **fachada fina e offline**
sobre as CLIs que já existem (`cobre-bridge` e `cobre`). Um agente de IA passa a
poder validar, converter, comparar, visualizar e **ler resultados** de casos por
ferramentas padronizadas, sem que este servidor contenha qualquer regra de negócio.

> **Princípio:** cada ferramenta envelopa um subcomando de CLI (com `--json`) ou um
> binding oficial (`cobre-python`), e repassa o resultado. Nada de reimplementar
> conversão, validação ou comparação.

## Requisitos

- Python **>= 3.12**
- [`uv`](https://docs.astral.sh/uv/)
- `cobre-bridge` no PATH (conversão / comparação / dashboard)
- `cobre` no PATH ou em `COBRE_BIN` (validação de deck e, futuramente, execução)

## Instalação e execução

```bash
cd <repositório anterior>
uv sync --system-certs     # --system-certs: redes com proxy/CA corporativo (ex.: ONS)
uv run cobre-mcp           # sobe o servidor no transporte stdio
```

> **Rede corporativa:** sem `--system-certs` (ou `UV_SYSTEM_CERTS=1`), o `uv` pode
> falhar no PyPI com `UnknownIssuer` por causa do proxy que reassina certificados.

O servidor fala **stdio** — não abre porta nem faz requisição externa; é iniciado
pelo cliente MCP como subprocesso.

### Configurar num cliente MCP (Claude Code, Claude Desktop, Kiro)

O formato do bloco é o mesmo; muda só onde se cola (ex.: `claude mcp add` grava em
`~/.claude.json`). Exemplo chamando o Python do venv direto (arranque rápido e
robusto, sem rebuild):

```json
{
  "mcpServers": {
    "cobre": {
      "command": "/caminho/para/<repositório anterior>/.venv/bin/python",
      "args": ["-m", "cobre_mcp"],
      "env": {
        "PYTHONPATH": "/caminho/para/<repositório anterior>/src",
        "PATH": "/caminho/para/.cargo/bin:/caminho/para/.local/bin:/usr/bin:/bin",
        "COBRE_BIN": "/caminho/para/.cargo/bin/cobre",
        "COBRE_MCP_WORKSPACE": "/caminho/para/seus/estudos",
        "UV_SYSTEM_CERTS": "1"
      }
    }
  }
}
```

## Segurança

As ferramentas de deck/resultado recebem caminhos controlados pelo agente. Defina
**`COBRE_MCP_WORKSPACE`** com a(s) raiz(es) permitida(s) (separadas por `:`): qualquer
caminho fora delas é **recusado** (fail-closed; `resolve()` neutraliza symlinks e `..`).
Sem essa variável o servidor opera **irrestrito** — o `cobre_mcp_info` sinaliza o estado.
Edições com `force=True` (gravar violando o schema) exigem `COBRE_MCP_ALLOW_FORCE=1`.

## Variáveis de ambiente

| Variável | Default | Para quê |
|---|---|---|
| `COBRE_BRIDGE_BIN` | (PATH) | caminho do `cobre-bridge` |
| `COBRE_BIN` | (PATH) | caminho do `cobre` |
| `COBRE_SCHEMAS_DIR` | — | dir com `*.schema.json` (habilita validação por schema no `deck_edit_json`) |
| `COBRE_DOCS_DIR` | — | mirror local do `cobre-docs` (habilita `docs_list`/`docs_read`) |
| `COBRE_MCP_WORKSPACE` | — | raiz(es) permitida(s) para caminhos (fail-closed quando setada) |
| `COBRE_MCP_ALLOW_FORCE` | `0` | habilita `deck_edit_json(force=True)` |
| `COBRE_MCP_LOG` | `0` | loga cada chamada no stderr (debug/teste) |
| `COBRE_MCP_TIMEOUT` | `900` | timeout (s) por chamada de CLI |
| `COBRE_MCP_MAX_DIAGNOSTICS` | `50` | teto de itens de diagnóstico |
| `COBRE_MCP_MAX_SUMMARY_CHARS` | `20000` | teto de tamanho do `summary` |
| `COBRE_MCP_MAX_INLINE_ROWS` | `50` | teto de linhas de amostra (parquet) |
| `COBRE_MCP_MAX_READ_BYTES` | `5000000` | teto de bytes na leitura direta de JSON |
| `COBRE_MCP_MAX_QUERY_ROWS` | `1000` | teto de linhas do `deck_sql` |

## Ferramentas

**Pré-rodada** (`tools/pre_run.py`)
- `bridge_check_newave(src)` — pré-valida entradas NEWAVE (`cobre-bridge check newave`)
- `bridge_convert_newave(src, dst, validate, force, dry_run)` — converte NEWAVE→Cobre
- `cobre_validate_deck(case_dir)` — valida o deck (binding `cobre.io.validate`, estruturado; fallback texto)
- `bridge_check_decomp(src)` / `bridge_convert_decomp(src, dst, ...)` — paridade DECOMP

**Pós-rodada** (`tools/post_run.py`)
- `bridge_compare_newave(...)` / `bridge_compare_decomp(...)` — compara resultados
- `bridge_dashboard(case_dir)` — dashboard HTML (retorna o caminho)

**Resultados** (`tools/results.py`)
- `results_status(output_dir)` — status, bounds, gap, custo (lê os `metadata.json`)
- `results_convergence(output_dir, tail)` — trajetória de convergência (`convergence.parquet`)
- `results_list_entities(output_dir)` — entidades de simulação disponíveis
- `results_query(output_dir, entity, group_by, agg, columns, scenario, limit)` — consulta agregada da simulação

**Manipulador de decks** (`tools/deck.py`)
- `deck_list` · `deck_read_json` · `deck_read_parquet` · `deck_describe_parquet`
- `deck_edit_json` (valida contra schema, backup + atômico) · `deck_edit_parquet` (preserva colunas/dtypes)
- `deck_sql(query, max_rows)` — consulta SQL **read-only** (DuckDB) sobre parquet/csv/json do deck ou dos resultados; guard confina os caminhos ao workspace

**Referência** (`tools/reference.py`)
- `schema_list()` / `schema_get(tipo)` — JSON Schemas de entrada (via `cobre schema export` ou `COBRE_SCHEMAS_DIR`); também expostos no resource `cobre://schema/{tipo}`
- `docs_list(section)` / `docs_read(page)` — documentação offline do `cobre-docs` (`COBRE_DOCS_DIR`)

**Diagnóstico** — `cobre_mcp_info()` (binários, versões, workspace, settings)

## Estrutura

```
src/cobre_mcp/
├── server.py            # sobe o FastMCP e registra as tools
├── config.py            # Settings via ambiente
├── adapters/
│   ├── bridge.py        # run_bridge  (peça compartilhada)
│   ├── cobre.py         # run_cobre + validação por binding
│   ├── discovery.py     # acha binários e versões
│   ├── deck_io.py       # leitura/edição de deck (JSON/Parquet)
│   ├── results.py       # leitura de resultados
│   ├── sql.py           # consulta SQL read-only (DuckDB) + guard fail-closed
│   ├── paths.py         # guard de workspace (fail-closed)
│   └── envelope.py      # envelope de erro (fonte única)
└── tools/
    ├── pre_run.py · post_run.py · results.py · deck.py · shaping.py
tests/
├── smoke.py · smoke_deck.py · smoke_results.py · smoke_paths.py · smoke_sql.py   # stdlib, offline
├── test_adapters.py                                               # pytest
├── fake_cobre_bridge.py                                           # cobre-bridge falso
└── try_tools.py                                                   # utilitário manual (não é CI)
```

## Testes

Sem dependências (rápido, offline):

```bash
python3 tests/smoke.py && python3 tests/smoke_deck.py \
  && python3 tests/smoke_results.py && python3 tests/smoke_paths.py
```

Suite pytest (após `uv sync`):

```bash
uv run pytest
```

## Desenvolvimento

```bash
uv run ruff check .
uv run ruff format .
```

## Licença

Apache-2.0 (ver arquivo `LICENSE`), alinhado ao ecossistema Cobre.
