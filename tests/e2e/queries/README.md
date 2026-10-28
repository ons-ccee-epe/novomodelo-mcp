# Query E2E Test Framework

Framework de testes E2E via query para validar que o Kiro/Claude usa o MCP do novomodelo corretamente, em vez de ler arquivos diretamente via `read_file` ou `list_directory`.

## Visão Geral

Este framework substitui os testes E2E antigos que chamavam tools diretamente, implementando um fluxo completo:

```
Query em linguagem natural → Decisão do agente → Execução da tool MCP → Validação da resposta
```

O objetivo principal é garantir que o agente escolhe a ferramenta MCP correta para cada tipo de consulta e retorna resultados corretos.

## Estrutura de Diretórios

```
tests/e2e/
├── queries/                    # Módulo principal do framework
│   ├── __init__.py            # Package exports
│   ├── cases.yaml             # Definições de casos de teste (~60 casos)
│   ├── loader.py              # CasesLoader - carrega e valida YAML
│   ├── runner.py              # QueryRunner - executa queries via Kiro CLI
│   ├── validator.py           # QueryValidator - valida resultados
│   ├── store.py               # ResultStore - persistência de resultados
│   ├── models.py              # Dataclasses (TestCase, TestResult, etc.)
│   ├── run_queries.py         # CLI Entry Point
│   ├── test_runner_unit.py    # Testes unitários do runner
│   ├── test_store_unit.py     # Testes unitários do store
│   ├── test_validator_unit.py # Testes unitários do validator
│   └── README.md              # Esta documentação
│
├── fixtures/                   # Dados de teste (decks NEWAVE/DECOMP)
│   ├── newave/
│   └── decomp/
│
├── results/                    # Resultados de baterias (JSON)
│   ├── index.json             # Índice de todas as baterias
│   ├── baseline.json          # Baseline de cada conjunto ({"baselines": {conjunto: batch_id}})
│   └── {batch_id}.json        # Resultado de cada bateria
│
├── metrics/                    # Histórico de métricas
│   └── history.jsonl          # Métricas de todas as baterias (JSONL)
```

O dashboard é o frontend React em `tests/e2e/frontend`, que lê `results/` e `metrics/`.

## Comandos CLI

### Execução Básica

```bash
# Executar todos os testes
python -m tests.e2e.queries.run_queries

# Executar testes com timeout customizado (em segundos)
python -m tests.e2e.queries.run_queries --timeout 180
```

### Filtragem de Testes

```bash
# Filtrar por tags (OR logic - executa testes com qualquer uma das tags)
python -m tests.e2e.queries.run_queries --tags bridge deck

# Executar apenas testes de uma categoria específica
python -m tests.e2e.queries.run_queries --tags newave

# Executar um teste específico por ID
python -m tests.e2e.queries.run_queries --case bridge-check-newave-valid
```

### Execução Paralela

```bash
# Executar N testes em paralelo
python -m tests.e2e.queries.run_queries --parallel 4

# Combinar com filtros
python -m tests.e2e.queries.run_queries --tags bridge --parallel 2
```

### Dashboard e Relatórios

```bash
# Mostrar como abrir o dashboard (frontend) para a bateria executada
python -m tests.e2e.queries.run_queries --report

# Marcar a bateria como baseline do seu conjunto (todos, grupo:<nome> ou pergunta:<id>);
# baselines de outros conjuntos são preservadas
python -m tests.e2e.queries.run_queries --set-baseline

# Comparar com uma bateria específica
python -m tests.e2e.queries.run_queries --compare 20241215_143052_abc1234
```

### Exemplos Combinados

```bash
# Executar testes de bridge em paralelo e gerar relatório
python -m tests.e2e.queries.run_queries --tags bridge --parallel 4 --report

# Executar todos os testes e definir como baseline
python -m tests.e2e.queries.run_queries --set-baseline --report

# Executar com timeout extendido para testes lentos
python -m tests.e2e.queries.run_queries --tags results --timeout 300 --parallel 2
```

## Variáveis de Ambiente

| Variável | Descrição | Default |
|----------|-----------|---------|
| `KIRO_API_KEY` | API key para autenticação no Kiro CLI. Se não definida, assume autenticação via `kiro-cli login` | - |
| `QUERY_TIMEOUT_S` | **Força** o mesmo timeout (s) em todos os casos, ignorando o `timeout_s` do `cases.yaml`. Use só para depurar | — (cada caso usa o seu) |
| `QUERY_FIXTURES_DIR` | Caminho para o diretório de fixtures | `tests/e2e/fixtures` |

### Exemplo de Uso

```bash
# Definir API key (o timeout vem do cases.yaml, por caso/grupo)
export KIRO_API_KEY="sua-api-key-aqui"

# Executar testes
python -m tests.e2e.queries.run_queries
```

```powershell
# PowerShell
$env:KIRO_API_KEY = "sua-api-key-aqui"

python -m tests.e2e.queries.run_queries
```

## Formato de Caso de Teste

Os casos de teste são definidos em `cases.yaml` usando formato YAML declarativo:

```yaml
# Exemplo de caso de teste básico
- id: bridge-check-newave-valid
  query: Valide o caso NEWAVE em {FIXTURES}/newave/newave-caso-reduzido
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

O framework abrange todas as 37 tools MCP do novomodelo:

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

O CLI exibe progresso durante a execução:

```
Carregados 60 casos de teste
[1/60] bridge-check-newave-valid... ✓ pass (1523ms)
[2/60] bridge-check-newave-invalid-path... ✓ pass (892ms)
[3/60] bridge-check-decomp-valid... ✗ fail (2341ms)
...

============================================================
Batch: 20241215_143052_abc1234
Total: 60 | Passed: 58 | Failed: 2 | Timeout: 0
MCP Used: 98.3% | Correct Tool: 96.7%
============================================================
```

**Exit codes:**
- `0` - Todos os testes passaram
- `1` - Pelo menos um teste falhou

## Integração com CI/CD

```yaml
# Exemplo de workflow GitHub Actions
jobs:
  e2e-queries:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: pip install -e .
      
      - name: Run Query E2E Tests
        env:
          KIRO_API_KEY: ${{ secrets.KIRO_API_KEY }}
        run: |
          python -m tests.e2e.queries.run_queries --parallel 4 --report
      
      - name: Upload Results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: e2e-results
          path: tests/e2e/results/
```

## Desenvolvimento

### Executar Testes Unitários

```bash
# Testes do framework
pytest tests/e2e/queries/test_*.py -v

# Com cobertura
pytest tests/e2e/queries/test_*.py --cov=tests.e2e.queries --cov-report=term-missing
```

### Adicionar Novos Casos de Teste

1. Edite `cases.yaml`
2. Adicione o caso seguindo o formato YAML
3. Use tags apropriadas para categorização
4. Execute para validar: `python -m tests.e2e.queries.run_queries --case seu-novo-caso`
