"""Casos de teste para results tools.

Tools cobertas:
- results_convergence
- results_query

NOTA: Estas tools requerem output de `cobre run` para funcionar.
Se a fixture results/sample_run não existir, os testes funcionais
retornarão erro (esperado). Os casos de edge_case (paths inválidos)
funcionam independente da fixture.
"""
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from eval.models import TestCase

# Diretório de fixtures
FIXTURES = Path(__file__).parent.parent / "fixtures"

# Diretório de resultados (precisa ser gerado com `cobre run`)
RESULTS_DIR = str(FIXTURES / "results" / "sample_run")


CASES = [
    # =========================================================================
    # results_convergence
    # =========================================================================
    TestCase(
        tool_name="results_convergence",
        case_id="convergence_valid",
        description="Ler convergência de run válido",
        parameters={"output_dir": RESULTS_DIR},
        expected_status="ok",
        tags=("functional", "results", "convergence", "requires_run"),
    ),
    TestCase(
        tool_name="results_convergence",
        case_id="convergence_with_tail",
        description="Ler convergência com tail customizado",
        parameters={
            "output_dir": RESULTS_DIR,
            "tail": 10,
        },
        expected_status="ok",
        tags=("functional", "results", "convergence", "requires_run"),
    ),
    TestCase(
        tool_name="results_convergence",
        case_id="convergence_nonexistent",
        description="Ler convergência de caminho inexistente",
        parameters={"output_dir": "/caminho/inexistente/xyz123"},
        expected_status="error",
        tags=("edge_case", "results", "convergence"),
    ),

    # =========================================================================
    # results_query
    # =========================================================================
    TestCase(
        tool_name="results_query",
        case_id="query_hydros",
        description="Query entity hydros",
        parameters={
            "output_dir": RESULTS_DIR,
            "entity": "hydros",
            "limit": 10,
        },
        expected_status="ok",
        tags=("functional", "results", "query", "requires_run"),
    ),
    TestCase(
        tool_name="results_query",
        case_id="query_costs",
        description="Query entity costs",
        parameters={
            "output_dir": RESULTS_DIR,
            "entity": "costs",
            "limit": 10,
        },
        expected_status="ok",
        tags=("functional", "results", "query", "requires_run"),
    ),
    TestCase(
        tool_name="results_query",
        case_id="query_with_columns",
        description="Query com filtro de colunas",
        parameters={
            "output_dir": RESULTS_DIR,
            "entity": "hydros",
            "columns": ["hydro_id", "stage_id"],
            "limit": 5,
        },
        expected_status="ok",
        tags=("functional", "results", "query", "requires_run"),
    ),
    TestCase(
        tool_name="results_query",
        case_id="query_with_aggregation",
        description="Query com group_by e agregação",
        parameters={
            "output_dir": RESULTS_DIR,
            "entity": "hydros",
            "columns": ["value"],
            "group_by": ["hydro_id"],
            "agg": "mean",
        },
        expected_status="ok",
        tags=("functional", "results", "query", "requires_run"),
    ),
    TestCase(
        tool_name="results_query",
        case_id="query_with_scenario",
        description="Query filtrando por cenário",
        parameters={
            "output_dir": RESULTS_DIR,
            "entity": "hydros",
            "scenario": 1,
            "limit": 10,
        },
        expected_status="ok",
        tags=("functional", "results", "query", "requires_run"),
    ),
    TestCase(
        tool_name="results_query",
        case_id="query_invalid_entity",
        description="Query com entity inválida",
        parameters={
            "output_dir": RESULTS_DIR,
            "entity": "entidade_que_nao_existe_xyz",
            "limit": 10,
        },
        expected_status="error",
        tags=("edge_case", "results", "query"),
    ),
    TestCase(
        tool_name="results_query",
        case_id="query_nonexistent_dir",
        description="Query em diretório inexistente",
        parameters={
            "output_dir": "/caminho/inexistente/xyz123",
            "entity": "hydros",
        },
        expected_status="error",
        tags=("edge_case", "results", "query"),
    ),
]


def register(registry) -> None:
    """Registra todos os casos no registry."""
    for case in CASES:
        registry.register(case)
