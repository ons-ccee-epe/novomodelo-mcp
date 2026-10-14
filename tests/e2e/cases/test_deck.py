"""Casos de teste para deck tools: list, read, describe, edit.

Tools cobertas:
- deck_list
- deck_read_parquet
- deck_describe_parquet
- deck_edit_parquet
"""
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from eval.models import TestCase

# Diretório de fixtures
FIXTURES = Path(__file__).parent.parent / "fixtures"

# Caminhos para decks COBRE convertidos
NEWAVE_COBRE = str(FIXTURES / "newave" / "cobre-caso-reduzido")
DECOMP_COBRE = str(FIXTURES / "decomp" / "cobre-mar-26-rv2-reduzido")

# Arquivos parquet específicos
HYDRO_GEOMETRY = str(FIXTURES / "newave" / "cobre-caso-reduzido" / "system" / "hydro_geometry.parquet")
HYDRO_PRODUCTIVITY = str(FIXTURES / "newave" / "cobre-caso-reduzido" / "system" / "hydro_energy_productivity.parquet")
TAILRACE_CURVES = str(FIXTURES / "newave" / "cobre-caso-reduzido" / "system" / "tailrace_curves.parquet")

# Parquet do DECOMP
DECOMP_HYDRO_GEOMETRY = str(FIXTURES / "decomp" / "cobre-mar-26-rv2-reduzido" / "system" / "hydro_geometry.parquet")


CASES = [
    # =========================================================================
    # deck_list
    # =========================================================================
    TestCase(
        tool_name="deck_list",
        case_id="list_newave_cobre",
        description="Listar arquivos do deck COBRE NEWAVE",
        parameters={"case_dir": NEWAVE_COBRE},
        expected_status="ok",
        expected_fields={"count": "__gt__:0"},
        tags=("functional", "deck", "newave", "list"),
    ),
    TestCase(
        tool_name="deck_list",
        case_id="list_decomp_cobre",
        description="Listar arquivos do deck COBRE DECOMP",
        parameters={"case_dir": DECOMP_COBRE},
        expected_status="ok",
        expected_fields={"count": "__gt__:0"},
        tags=("functional", "deck", "decomp", "list"),
    ),
    TestCase(
        tool_name="deck_list",
        case_id="list_nonexistent",
        description="Listar caminho inexistente",
        parameters={"case_dir": "/caminho/inexistente/xyz123"},
        expected_status="error",
        tags=("edge_case", "deck", "list"),
    ),

    # =========================================================================
    # deck_read_parquet
    # =========================================================================
    TestCase(
        tool_name="deck_read_parquet",
        case_id="read_hydro_geometry",
        description="Ler hydro_geometry.parquet completo",
        parameters={"path": HYDRO_GEOMETRY},
        expected_status="ok",
        expected_fields={"nrows": "__gt__:0"},
        tags=("functional", "deck", "parquet", "read"),
    ),
    TestCase(
        tool_name="deck_read_parquet",
        case_id="read_hydro_productivity",
        description="Ler hydro_energy_productivity.parquet",
        parameters={"path": HYDRO_PRODUCTIVITY},
        expected_status="ok",
        expected_fields={"nrows": "__gt__:0"},
        tags=("functional", "deck", "parquet", "read"),
    ),
    TestCase(
        tool_name="deck_read_parquet",
        case_id="read_with_limit",
        description="Ler parquet com limit de linhas",
        parameters={
            "path": HYDRO_GEOMETRY,
            "limit": 5,
        },
        expected_status="ok",
        tags=("functional", "deck", "parquet", "read"),
    ),
    TestCase(
        tool_name="deck_read_parquet",
        case_id="read_with_columns",
        description="Ler parquet com filtro de colunas",
        parameters={
            "path": HYDRO_GEOMETRY,
            "columns": ["hydro_id", "volume_hm3"],
            "limit": 10,
        },
        expected_status="ok",
        tags=("functional", "deck", "parquet", "read"),
    ),
    TestCase(
        tool_name="deck_read_parquet",
        case_id="read_nonexistent",
        description="Ler arquivo parquet inexistente",
        parameters={"path": "/caminho/inexistente/arquivo.parquet"},
        expected_status="error",
        tags=("edge_case", "deck", "parquet", "read"),
    ),

    # =========================================================================
    # deck_describe_parquet
    # =========================================================================
    TestCase(
        tool_name="deck_describe_parquet",
        case_id="describe_hydro_geometry",
        description="Descrever hydro_geometry.parquet",
        parameters={"path": HYDRO_GEOMETRY},
        expected_status="ok",
        expected_fields={"nrows": "__gt__:0"},
        tags=("functional", "deck", "parquet", "describe"),
    ),
    TestCase(
        tool_name="deck_describe_parquet",
        case_id="describe_tailrace",
        description="Descrever tailrace_curves.parquet",
        parameters={"path": TAILRACE_CURVES},
        expected_status="ok",
        tags=("functional", "deck", "parquet", "describe"),
    ),
    TestCase(
        tool_name="deck_describe_parquet",
        case_id="describe_decomp_hydro",
        description="Descrever hydro_geometry do DECOMP",
        parameters={"path": DECOMP_HYDRO_GEOMETRY},
        expected_status="ok",
        tags=("functional", "deck", "parquet", "describe", "decomp"),
    ),
    TestCase(
        tool_name="deck_describe_parquet",
        case_id="describe_nonexistent",
        description="Descrever arquivo inexistente",
        parameters={"path": "/caminho/inexistente/arquivo.parquet"},
        expected_status="error",
        tags=("edge_case", "deck", "parquet", "describe"),
    ),

    # =========================================================================
    # deck_edit_parquet
    # =========================================================================
    TestCase(
        tool_name="deck_edit_parquet",
        case_id="edit_dry_run",
        description="Editar parquet com dry_run=True (não grava)",
        parameters={
            "path": HYDRO_GEOMETRY,
            "where": {"hydro_id": 1},
            "set_values": {"volume_hm3": 100.0},
            "dry_run": True,
        },
        expected_status="ok",
        tags=("functional", "deck", "parquet", "edit"),
    ),
    TestCase(
        tool_name="deck_edit_parquet",
        case_id="edit_nonexistent",
        description="Editar arquivo inexistente",
        parameters={
            "path": "/caminho/inexistente/arquivo.parquet",
            "where": {"id": 1},
            "set_values": {"value": 0},
            "dry_run": True,
        },
        expected_status="error",
        tags=("edge_case", "deck", "parquet", "edit"),
    ),
]


def register(registry) -> None:
    """Registra todos os casos no registry."""
    for case in CASES:
        registry.register(case)
