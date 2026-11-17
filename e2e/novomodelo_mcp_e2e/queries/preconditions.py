"""Pré-requisitos de um caso: as fontes (decks/casos) que ele precisa encontrar.

Um teste de conversão ou validação sem o deck de entrada só mede a ausência do
arquivo, não o agente; o caso é pulado (status "skip") em vez de rodar.
"""

from __future__ import annotations

from pathlib import Path

from novomodelo_mcp_e2e.queries.models import QueryTestCase, TestResult

__all__ = ["missing_sources", "skipped_result"]


def _is_present(path: Path) -> bool:
    # Diretório vazio conta como ausente: é o que sobra de um junction/clone
    # sem os dados (as fixtures são gitignored).
    if path.is_file():
        return True
    return path.is_dir() and any(path.iterdir())


def missing_sources(case: QueryTestCase) -> list[str]:
    """Fontes declaradas em ``requires`` que não existem (ou estão vazias)."""
    return [src for src in case.requires if not _is_present(Path(src))]


def skipped_result(case: QueryTestCase, missing: list[str]) -> TestResult:
    """TestResult "skip" para um caso cuja fonte não está disponível."""
    return TestResult(
        test_id=case.id,
        query=case.query,
        expected_tool=case.expected.tool,
        expected_tools=case.expected.tools,
        actual_tool=None,
        all_tool_calls=[],
        status="skip",
        latency_ms=0.0,
        tool_latency_ms=None,
        mcp_used=False,
        correct_tool=False,
        correct_result=False,
        agent_response="",
        error_message="Fonte ausente: " + "; ".join(missing),
        tags=list(case.tags),
        validation_checks=[],
    )
