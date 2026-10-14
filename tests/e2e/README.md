# Testes End-to-End (E2E) do <repositório anterior>

Framework de testes de integração reais para o servidor MCP do COBRE. Executa as tools MCP com CLIs reais (`cobre-bridge`, `cobre`) e dados reais, validando comportamento, coletando métricas e gerando relatórios/dashboards.

## Estrutura

```
tests/e2e/
├── eval/                    # Framework core
│   ├── models.py            # TestCase, ExecutionResult, MetricRecord
│   ├── registry.py          # Registro e auto-descoberta de casos
│   ├── validator.py         # Validação de respostas
│   ├── client.py            # Cliente MCP (local/remoto)
│   ├── metrics.py           # Persistência JSONL
│   ├── reporter.py          # Relatórios JSON
│   ├── dashboard.py         # Dashboard HTML
│   ├── prerequisites.py     # Verificação de ambiente
│   └── run.py               # CLI runner
│
├── cases/                   # Casos de teste (auto-descobertos)
│   ├── test_bridge.py       # bridge_check_*, bridge_convert_*, bridge_compare_*
│   ├── test_deck.py         # deck_list, deck_read_parquet, etc
│   ├── test_reference.py    # docs_list, docs_read
│   └── test_results.py      # results_convergence, results_query
│
├── fixtures/                # Dados reais para testes
│   ├── newave/              # Casos NEWAVE
│   ├── decomp/              # Casos DECOMP
│   ├── newave-determ/       # Casos NEWAVE determinístico
│   └── results/             # Output de cobre run (opcional)
│
├── metrics/                 # Histórico de execuções
│   └── history.jsonl        # Append-only (gitignored)
│
└── reports/                 # Relatórios gerados
    ├── latest.json          # Último relatório (gitignored)
    └── latest.html          # Dashboard (gitignored)
```

## Pré-requisitos

1. **cobre-mcp** instalado no ambiente Python:
   ```bash
   pip install -e .
   ```

2. **cobre-bridge** CLI no PATH:
   ```bash
   cargo install cobre-bridge
   ```

3. **cobre** CLI no PATH:
   ```bash
   cargo install cobre
   ```

4. **Fixtures** na pasta `tests/e2e/fixtures/`

## Uso

### Verificar pré-requisitos
```bash
python -m tests.e2e.eval.run --check
```

### Executar todos os testes
```bash
python -m tests.e2e.eval.run
```

### Filtrar por tool específica
```bash
python -m tests.e2e.eval.run --tool deck_list
python -m tests.e2e.eval.run --tool bridge_check_newave
```

### Filtrar por tag
```bash
python -m tests.e2e.eval.run --tag functional    # Apenas testes funcionais
python -m tests.e2e.eval.run --tag edge_case     # Apenas edge cases
python -m tests.e2e.eval.run --tag newave        # Apenas testes NEWAVE
python -m tests.e2e.eval.run --tag decomp        # Apenas testes DECOMP
```

### Modo silencioso (sem progresso)
```bash
python -m tests.e2e.eval.run --quiet
```

### Sem abrir browser
```bash
python -m tests.e2e.eval.run --no-browser
```

## Tools Cobertas

| Tool | Arquivo | Casos |
|------|---------|-------|
| `bridge_check_newave` | test_bridge.py | 2 |
| `bridge_check_decomp` | test_bridge.py | 2 |
| `bridge_convert_decomp` | test_bridge.py | 2 |
| `bridge_compare_decomp` | test_bridge.py | 4 |
| `deck_list` | test_deck.py | 3 |
| `deck_read_parquet` | test_deck.py | 5 |
| `deck_describe_parquet` | test_deck.py | 4 |
| `deck_edit_parquet` | test_deck.py | 2 |
| `docs_list` | test_reference.py | 3 |
| `docs_read` | test_reference.py | 5 |
| `results_convergence` | test_results.py | 3 |
| `results_query` | test_results.py | 8 |

**Total: 44 casos de teste**

## Adicionando Novos Testes

1. Crie um arquivo `test_*.py` em `tests/e2e/cases/`

2. Defina casos usando `TestCase`:
   ```python
   from pathlib import Path
   import sys
   sys.path.insert(0, str(Path(__file__).parent.parent))
   from eval.models import TestCase

   CASES = [
       TestCase(
           tool_name="minha_tool",
           case_id="caso_basico",
           description="Descrição do teste",
           parameters={"param1": "valor1"},
           expected_status="ok",
           expected_fields={"campo": "valor"},
           tags=("functional", "minha_tag"),
       ),
   ]

   def register(registry):
       for case in CASES:
           registry.register(case)
   ```

3. Execute os testes:
   ```bash
   python -m tests.e2e.eval.run --tool minha_tool
   ```

## Matchers Especiais

O validador suporta matchers especiais em `expected_fields`:

| Matcher | Descrição |
|---------|-----------|
| `"__any__"` | Aceita qualquer valor não-None |
| `"__nonempty__"` | String/lista/dict não-vazia |
| `"__contains__:texto"` | Verifica substring |
| `"__gt__:N"` | Maior que N |
| `"__gte__:N"` | Maior ou igual a N |
| `"__lt__:N"` | Menor que N |
| `"__lte__:N"` | Menor ou igual a N |

Exemplo:
```python
expected_fields={
    "count": "__gt__:0",
    "content": "__nonempty__",
    "message": "__contains__:sucesso",
}
```

## Outputs

Após execução, são gerados:

- **`reports/latest.json`**: Relatório JSON com sumário e detalhes
- **`reports/latest.html`**: Dashboard HTML interativo
- **`metrics/history.jsonl`**: Histórico de todas as execuções

## Fixture de Resultados

Para testar `results_convergence` e `results_query`, é necessário gerar output de `cobre run`:

```bash
cobre run tests/e2e/fixtures/newave/cobre-caso-reduzido -o tests/e2e/fixtures/results/sample_run
```

Sem esta fixture, os testes com tag `requires_run` falharão.
