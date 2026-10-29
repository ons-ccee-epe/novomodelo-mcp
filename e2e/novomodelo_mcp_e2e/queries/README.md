# Query E2E Test Framework

Framework de testes E2E via query para validar que um agente (Kiro ou Claude) usa o MCP do novomodelo corretamente, em vez de ler arquivos diretamente via `read_file` ou `list_directory`.

## Visão Geral

O framework descreve o fluxo completo:

```
Query em linguagem natural → Decisão do agente → Execução da tool MCP → Validação da resposta
```

A execução do agente passa pelo executor em container: no host, `QueryRunner.execute` e o CLI `run_queries` recusam com a mensagem "a execução passa pelo executor em container". O que roda no host é o carregamento e a validação dos casos, os parsers de saída de agente e o armazenamento dos resultados.

O objetivo principal é garantir que o agente escolhe a ferramenta MCP correta para cada tipo de consulta e retorna resultados corretos.

## Estrutura de Diretórios

```
e2e/novomodelo_mcp_e2e/
├── queries/                    # Módulo principal do framework
│   ├── __init__.py            # Package exports
│   ├── cases.yaml             # Definições de casos de teste
│   ├── loader.py              # CasesLoader - carrega e valida YAML
│   ├── runner.py              # QueryRunner - parsers de saída de agente; execução só pelo executor em container
│   ├── validator.py           # QueryValidator - valida resultados
│   ├── store.py               # ResultStore - persistência de resultados
│   ├── models.py              # Dataclasses (TestCase, TestResult, etc.)
│   ├── run_queries.py         # CLI (recusa a execução no host)
│   ├── test_runner_unit.py    # Testes unitários do runner
│   ├── test_store_unit.py     # Testes unitários do store
│   ├── test_validator_unit.py # Testes unitários do validator
│   └── README.md              # Esta documentação
│
├── fixtures/                   # Dados de teste (decks NEWAVE/DECOMP)
│   ├── newave/
│   └── decomp/
│
├── results/                    # Resultados de baterias (JSON); criada ao gravar a primeira bateria
│   ├── index.json             # Índice de todas as baterias
│   ├── baseline.json          # Baseline de cada conjunto ({"baselines": {conjunto: batch_id}})
│   └── {batch_id}.json        # Resultado de cada bateria
│
├── metrics/                    # Histórico de métricas
│   └── history.jsonl          # Métricas de todas as baterias (JSONL)
```

O dashboard é o frontend React em `e2e/frontend`, que lê `results/` e `metrics/`.

## Comandos CLI

### Argumentos

O CLI `python -m novomodelo_mcp_e2e.queries.run_queries` não tem opções: só recusa. O conjunto tools
roda pela rodada da bateria (`python -m novomodelo_mcp_e2e rodar --conjuntos tools`, ver
`e2e/README.md`), com filtro por id de caso em `--filtro`.

## Variáveis de Ambiente

| Variável | Descrição | Default |
|----------|-----------|---------|
| `QUERY_TIMEOUT_S` | **Força** o mesmo timeout (s) em todos os casos no `QueryRunner`, ignorando o `timeout_s` do `cases.yaml`. Não vale para a rodada | — (cada caso usa o seu) |

## Formato de Caso de Teste

Os casos de teste são definidos em `cases.yaml` usando formato YAML declarativo:

```yaml
# Exemplo de caso de teste básico
- id: bridge-check-newave-valid
  query: Valide o caso NEWAVE em {caso:bridge_newave_mini}
  expected:
    uses_mcp: true
    tool: bridge_check_newave
    status: ok
  tags: [bridge, newave, validation]

# Exemplo com múltiplas tools aceitas
- id: docs-search-methodology
  query: Busque na documentação sobre política operativa
  expected:
    uses_mcp: true
    tools: [docs_search, docs_read]  # Qualquer uma é válida
    validation:
      response_contains: [policy, operation]
  tags: [docs, methodology]

# Exemplo de teste de erro
- id: deck-read-invalid-path
  query: Leia o arquivo parquet em {FIXTURES}/nonexistent.parquet
  expected:
    uses_mcp: true
    tool: deck_read_parquet
    status: error
    error_contains: "not found"
  tags: [deck, error]

# Exemplo com validação de conteúdo
- id: deck-describe-parquet
  query: Descreva o schema do parquet em {FIXTURES}/deck.parquet
  expected:
    uses_mcp: true
    tool: deck_describe_parquet
    status: ok
    content:
      summary.total: __gt__:0
      columns: __nonempty__
  tags: [deck, schema]
```

### Campos do Caso de Teste

| Campo | Obrigatório | Descrição |
|-------|-------------|-----------|
| `id` | ✓ | Identificador único do teste |
| `query` | ✓ | Query em linguagem natural (suporta `{FIXTURES}`) |
| `timeout_s` | | Timeout (s) do caso. Sem ele, vale `defaults.timeout_s_by_group[<grupo da tool>]` e depois `defaults.timeout_s` (topo do `cases.yaml`) |
| `requires` | | Fontes que precisam existir (suporta `{FIXTURES}`). Se alguma faltar, ou for pasta vazia, o caso sai como `skip` sem disparar o agente e não entra nos percentuais. Casos que testam caminho inexistente de propósito não declaram `requires`. |
| `expected.uses_mcp` | ✓ | Se o teste espera que MCP seja usado |
| `expected.tool` | ✓* | Tool MCP específica esperada |
| `expected.tools` | ✓* | Lista de tools aceitáveis (qualquer uma) |
| `expected.status` | | Status esperado do envelope (`ok` ou `error`) |
| `expected.content` | | Validações de campos do envelope |
| `expected.did_not_use` | | Lista de tools que NÃO devem ser usadas |
| `expected.error_contains` | | Substring esperada na mensagem de erro |
| `expected.validation` | | Validações adicionais (citações, keywords) |
| `tags` | | Lista de tags para categorização/filtragem |

*\* `tool` ou `tools` é obrigatório*

### Matchers Especiais

Para validações flexíveis em `expected.content`:

| Matcher | Descrição | Exemplo |
|---------|-----------|---------|
| `__any__` | Aceita qualquer valor não-None | `field: __any__` |
| `__nonempty__` | Aceita string/lista/dict não-vazia | `items: __nonempty__` |
| `__contains__:texto` | Verifica substring | `msg: __contains__:success` |
| `__gt__:N` | Maior que N | `count: __gt__:0` |
| `__gte__:N` | Maior ou igual a N | `count: __gte__:1` |
| `__lt__:N` | Menor que N | `errors: __lt__:5` |
| `__lte__:N` | Menor ou igual a N | `warnings: __lte__:10` |

## Cobertura de Tools

O framework abrange as tools MCP do novomodelo:

| Grupo | Tools |
|-------|-------|
| **Bridge Check** | `bridge_check_newave`, `bridge_check_decomp` |
| **Bridge Convert** | `bridge_convert_newave`, `bridge_convert_decomp` |
| **Bridge Compare** | `bridge_compare_newave`, `bridge_compare_decomp` |
| **Bridge** | `bridge_dashboard` |
| **Case** | `case_validate`, `case_summary`, `case_init` |
| **Deck** | `deck_list`, `deck_read_parquet`, `deck_describe_parquet`, `deck_edit_parquet`, `deck_read_json`, `deck_edit_json`, `deck_sql` |
| **Docs** | `docs_list`, `docs_search`, `docs_read` |
| **Results** | `results_status`, `results_convergence`, `results_query`, `results_list_entities`, `results_policy`, `results_stochastic` |
| **Schema** | `schema_list`, `schema_get`, `schema_export` |
| **Run** | `run_plan`, `run_apply`, `run_start`, `run_status`, `run_logs`, `run_cancel` |
| **Meta** | `server_info`, `solver_version`, `instalar_novomodelo` |

## Saída e Exit Codes

`run_queries` não carrega casos nem executa: escreve "a execução passa pelo executor em
container" no stderr e sai com código `1`.

O que funciona no host: o carregamento e a validação dos casos (`CasesLoader`), o
`QueryValidator`, os parsers de saída de agente e o `ResultStore`, todos cobertos pelos
testes unitários desta pasta.

## Desenvolvimento

### Executar Testes Unitários

```bash
# Testes do framework
pytest e2e/novomodelo_mcp_e2e/queries/test_*.py -v

# Com cobertura
pytest e2e/novomodelo_mcp_e2e/queries/test_*.py --cov=novomodelo_mcp_e2e.queries --cov-report=term-missing
```

### Adicionar Novos Casos de Teste

1. Edite `cases.yaml`
2. Adicione o caso seguindo o formato YAML
3. Use tags apropriadas para categorização
4. Valide o carregamento: `pytest e2e/novomodelo_mcp_e2e/queries`
