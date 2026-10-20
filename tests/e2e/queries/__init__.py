"""Query E2E Test Framework para <repositório anterior>.

Este módulo implementa um framework de testes E2E via query para validar que o
Kiro/Claude usa o MCP do novomodelo quando deveria, em vez de ler arquivos
diretamente via `read_file` ou `list_directory`.

O fluxo de teste completo é:
    query em linguagem natural → decisão do agente → execução da tool MCP → validação da resposta

Módulos:
    - cases.yaml: Definições de casos de teste em formato YAML declarativo
    - loader.py: CasesLoader para carregar e validar casos de teste
    - models.py: Data models (QueryTestCase, TestResult, BatchResult, etc.)
    - runner.py: QueryRunner para executar queries via Kiro CLI
    - validator.py: QueryValidator para validar resultados contra expectativas
    - store.py: ResultStore para persistir resultados e métricas
    - dashboard.py: QueryDashboard para gerar relatórios HTML interativos
    - run_queries.py: CLI entry point para executar testes
"""

from tests.e2e.queries.dashboard import QueryDashboard
from tests.e2e.queries.loader import CasesLoader, CasesLoaderError
from tests.e2e.queries.models import (
    BatchMetrics,
    BatchResult,
    ExpectedResult,
    GroupMetrics,
    QueryResult,
    QueryTestCase,
    TagMetrics,
    TestResult,
    ToolCall,
    ValidationCheck,
    ValidationResult,
    ValidationSpec,
)
from tests.e2e.queries.runner import QueryRunner
from tests.e2e.queries.store import ResultStore, TOOL_GROUPS
from tests.e2e.queries.validator import (
    MCP_TOOLS,
    NATIVE_TOOLS,
    QueryValidator,
    classify_tool,
    get_nested,
    values_match,
)

__all__ = [
    # Definição de casos de teste
    "QueryTestCase",
    "ExpectedResult",
    "ValidationSpec",
    # Loader
    "CasesLoader",
    "CasesLoaderError",
    # Execução
    "ToolCall",
    "QueryResult",
    "QueryRunner",
    # Validação
    "ValidationCheck",
    "ValidationResult",
    "QueryValidator",
    # Validator helpers
    "MCP_TOOLS",
    "NATIVE_TOOLS",
    "classify_tool",
    "get_nested",
    "values_match",
    # Persistência
    "ResultStore",
    "TOOL_GROUPS",
    # Dashboard
    "QueryDashboard",
    # Resultados de bateria
    "TestResult",
    "BatchResult",
    "BatchMetrics",
    "TagMetrics",
    "GroupMetrics",
]
