"""Casos de teste para docs/reference tools.

Tools cobertas:
- docs_list
- docs_read
"""
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from eval.models import TestCase


CASES = [
    # =========================================================================
    # docs_list
    # =========================================================================
    TestCase(
        tool_name="docs_list",
        case_id="list_all",
        description="Listar todas as páginas de documentação",
        parameters={},
        expected_status="ok",
        tags=("functional", "docs", "list"),
    ),
    TestCase(
        tool_name="docs_list",
        case_id="list_section_reference",
        description="Listar páginas da seção 'reference'",
        parameters={"section": "reference"},
        expected_status="ok",
        tags=("functional", "docs", "list"),
    ),
    TestCase(
        tool_name="docs_list",
        case_id="list_section_nonexistent",
        description="Listar seção inexistente (deve retornar lista vazia ou ok)",
        parameters={"section": "secao_que_nao_existe_xyz"},
        expected_status="ok",  # Pode retornar ok com lista vazia
        tags=("edge_case", "docs", "list"),
    ),

    # =========================================================================
    # docs_read
    # =========================================================================
    TestCase(
        tool_name="docs_read",
        case_id="read_index",
        description="Ler página index/principal",
        parameters={"page": "index"},
        expected_status="ok",
        expected_fields={"content": "__nonempty__"},
        tags=("functional", "docs", "read"),
    ),
    TestCase(
        tool_name="docs_read",
        case_id="read_cli_reference",
        description="Ler página de referência CLI",
        parameters={"page": "reference/cli-reference"},
        expected_status="ok",
        tags=("functional", "docs", "read"),
    ),
    TestCase(
        tool_name="docs_read",
        case_id="read_error_codes",
        description="Ler página de códigos de erro",
        parameters={"page": "reference/error-codes"},
        expected_status="ok",
        tags=("functional", "docs", "read"),
    ),
    TestCase(
        tool_name="docs_read",
        case_id="read_glossary",
        description="Ler página do glossário",
        parameters={"page": "reference/glossary"},
        expected_status="ok",
        tags=("functional", "docs", "read"),
    ),
    TestCase(
        tool_name="docs_read",
        case_id="read_nonexistent",
        description="Ler página inexistente",
        parameters={"page": "pagina/que/nao/existe/xyz123"},
        expected_status="error",
        tags=("edge_case", "docs", "read"),
    ),
]


def register(registry) -> None:
    """Registra todos os casos no registry."""
    for case in CASES:
        registry.register(case)
