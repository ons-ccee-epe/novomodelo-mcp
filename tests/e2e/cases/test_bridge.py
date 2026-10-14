"""Casos de teste para bridge tools: check, convert, compare.

Tools cobertas:
- bridge_check_newave
- bridge_check_decomp
- bridge_convert_decomp
- bridge_compare_decomp
"""
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from eval.models import TestCase

# Diretório de fixtures (relativo ao diretório do projeto)
FIXTURES = Path(__file__).parent.parent / "fixtures"

# Caminhos absolutos para as fixtures
NEWAVE_ORIGINAL = str(FIXTURES / "newave" / "newave-caso-reduzido")
NEWAVE_COBRE = str(FIXTURES / "newave" / "cobre-caso-reduzido")
DECOMP_ORIGINAL = str(FIXTURES / "decomp" / "decomp-mar-26-rv2-reduzido")
DECOMP_COBRE = str(FIXTURES / "decomp" / "cobre-mar-26-rv2-reduzido")

# Diretório temporário para conversões (não será criado se dry_run=True)
TEMP_DIR = str(FIXTURES / "temp")


CASES = [
    # =========================================================================
    # bridge_check_newave
    # =========================================================================
    TestCase(
        tool_name="bridge_check_newave",
        case_id="valid_newave_ago26",
        description="Check em caso NEWAVE ago-26 válido",
        parameters={"src": NEWAVE_ORIGINAL},
        expected_status="ok",
        expected_fields={"exit_code": 0},
        tags=("functional", "newave", "bridge", "check"),
    ),
    TestCase(
        tool_name="bridge_check_newave",
        case_id="nonexistent_path",
        description="Check em caminho que não existe",
        parameters={"src": "/caminho/inexistente/xyz123"},
        expected_status="error",
        tags=("edge_case", "newave", "bridge", "check"),
    ),

    # =========================================================================
    # bridge_check_decomp
    # =========================================================================
    TestCase(
        tool_name="bridge_check_decomp",
        case_id="valid_decomp_mar26",
        description="Check em caso DECOMP mar-26 válido",
        parameters={"src": DECOMP_ORIGINAL},
        expected_status="ok",
        expected_fields={"exit_code": 0},
        tags=("functional", "decomp", "bridge", "check"),
    ),
    TestCase(
        tool_name="bridge_check_decomp",
        case_id="nonexistent_path",
        description="Check em caminho que não existe",
        parameters={"src": "/caminho/inexistente/xyz123"},
        expected_status="error",
        tags=("edge_case", "decomp", "bridge", "check"),
    ),

    # =========================================================================
    # bridge_convert_decomp
    # =========================================================================
    TestCase(
        tool_name="bridge_convert_decomp",
        case_id="convert_dry_run",
        description="Conversão DECOMP com dry_run=True (não grava)",
        parameters={
            "src": DECOMP_ORIGINAL,
            "dst": TEMP_DIR + "/converted_decomp_dryrun",
            "dry_run": True,
            "validate": False,
        },
        expected_status="ok",
        expected_fields={"exit_code": 0},
        tags=("functional", "decomp", "bridge", "convert"),
    ),
    TestCase(
        tool_name="bridge_convert_decomp",
        case_id="convert_nonexistent_src",
        description="Conversão com source inexistente",
        parameters={
            "src": "/caminho/inexistente/xyz123",
            "dst": TEMP_DIR + "/should_not_exist",
            "dry_run": True,
        },
        expected_status="error",
        tags=("edge_case", "decomp", "bridge", "convert"),
    ),

    # =========================================================================
    # bridge_compare_decomp
    # =========================================================================
    TestCase(
        tool_name="bridge_compare_decomp",
        case_id="compare_decomp_json",
        description="Comparação DECOMP vs COBRE em formato JSON",
        parameters={
            "decomp_dir": DECOMP_ORIGINAL,
            "cobre_dir": DECOMP_COBRE,
            "fmt": "json",
        },
        expected_status="ok",
        tags=("functional", "decomp", "bridge", "compare"),
    ),
    TestCase(
        tool_name="bridge_compare_decomp",
        case_id="compare_with_tolerance",
        description="Comparação com tolerance customizada",
        parameters={
            "decomp_dir": DECOMP_ORIGINAL,
            "cobre_dir": DECOMP_COBRE,
            "tolerance": 0.01,
            "fmt": "json",
        },
        expected_status="ok",
        tags=("functional", "decomp", "bridge", "compare"),
    ),
    TestCase(
        tool_name="bridge_compare_decomp",
        case_id="compare_nonexistent_decomp",
        description="Comparação com decomp_dir inexistente",
        parameters={
            "decomp_dir": "/caminho/inexistente/xyz123",
            "cobre_dir": DECOMP_COBRE,
            "fmt": "json",
        },
        expected_status="error",
        tags=("edge_case", "decomp", "bridge", "compare"),
    ),
    TestCase(
        tool_name="bridge_compare_decomp",
        case_id="compare_nonexistent_cobre",
        description="Comparação com cobre_dir inexistente",
        parameters={
            "decomp_dir": DECOMP_ORIGINAL,
            "cobre_dir": "/caminho/inexistente/xyz123",
            "fmt": "json",
        },
        expected_status="error",
        tags=("edge_case", "decomp", "bridge", "compare"),
    ),
]


def register(registry) -> None:
    """Registra todos os casos no registry."""
    for case in CASES:
        registry.register(case)
