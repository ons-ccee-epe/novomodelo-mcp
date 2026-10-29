"""CLI de execução da bateria de queries.

A execução do agente passa pelo executor em container: o CLI não tem opções e
recusa com erro explícito. Este módulo também guarda
``_build_test_result``, que converte (caso, resultado, validação) em ``TestResult``.
"""

from __future__ import annotations

import argparse
import sys

from tests.e2e.queries.models import (
    QueryResult,
    QueryTestCase,
    TestResult,
)
from tests.e2e.queries.runner import EXECUCAO_SO_NO_EXECUTOR
from tests.e2e.queries.validator import ValidationResult

__all__ = ["main"]


def _build_test_result(
    case: QueryTestCase,
    result: QueryResult,
    validation: ValidationResult,
) -> TestResult:
    """Constrói TestResult a partir de case, result e validation.

    Args:
        case: Caso de teste executado
        result: Resultado da execução da query
        validation: Resultado da validação

    Returns:
        TestResult completo para persistência
    """
    from tests.e2e.queries.validator import classify_tool

    # Determinar tool principal chamada (primeira MCP tool, ou primeira tool)
    actual_tool: str | None = None
    for tc in result.tool_calls:
        if classify_tool(tc.name) == "mcp":
            actual_tool = tc.name
            break
    if actual_tool is None and result.tool_calls:
        actual_tool = result.tool_calls[0].name

    # Determinar se MCP foi usado
    mcp_used = any(classify_tool(tc.name) == "mcp" for tc in result.tool_calls)

    # Determinar se tool correta foi chamada
    # Use set membership como o validator faz (order-independent)
    called_names = {tc.name for tc in result.tool_calls}
    correct_tool = False
    if case.expected.tool:
        correct_tool = case.expected.tool in called_names
    elif case.expected.tools:
        correct_tool = bool(called_names & set(case.expected.tools))

    # Serializar tool calls para JSON
    all_tool_calls = [
        {"name": tc.name, "args": tc.args, "tool_id": tc.tool_id} for tc in result.tool_calls
    ]

    # Serializar validation checks
    validation_checks = [
        {
            "name": check.name,
            "passed": check.passed,
            "expected": check.expected,
            "actual": check.actual,
            "message": check.message,
        }
        for check in validation.checks
    ]

    # Determinar status granular:
    # - "pass": tudo passou
    # - "partial": MCP usado e tool correta, mas validação de resultado falhou
    # - "fail": MCP não usado ou tool errada
    # - "timeout": timeout na execução
    if result.status == "timeout":
        status = "timeout"
    elif case.expected.uses_mcp:
        if mcp_used and correct_tool:
            # MCP ok - verificar se é pass completo ou partial
            if validation.valid:
                status = "pass"
            else:
                status = "partial"
        else:
            status = "fail"
    else:
        # Teste não espera MCP - usar validação direta
        status = "pass" if validation.valid else "fail"

    return TestResult(
        test_id=case.id,
        query=case.query,
        expected_tool=case.expected.tool,
        expected_tools=case.expected.tools,
        actual_tool=actual_tool,
        all_tool_calls=all_tool_calls,
        status=status,
        latency_ms=result.latency_ms,
        tool_latency_ms=None,  # TODO: extrair do envelope quando disponível
        mcp_used=mcp_used,
        correct_tool=correct_tool,
        correct_result=validation.valid,
        agent_response=result.agent_response,
        error_message=(
            f"Timeout do teste: sessão do agente encerrada após {result.timeout_s:.0f}s"
            if result.status == "timeout" and result.timeout_s
            else validation.failure_reason
        ),
        tags=list(case.tags),
        validation_checks=validation_checks,
    )


def main(argv: list[str] | None = None) -> int:
    """Recusa a execução: o agente só roda na rodada da bateria, no executor em container.

    Returns:
        1, sempre.
    """
    parser = argparse.ArgumentParser(
        prog="run_queries",
        description=(
            "Recusa a execução no host; o conjunto tools roda pela rodada "
            "(python -m tests.e2e rodar --conjuntos tools)."
        ),
    )
    parser.parse_args(argv)

    print(f"Erro: {EXECUCAO_SO_NO_EXECUTOR}.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
