"""CLI Entry Point para execução de testes E2E via query.

Este módulo implementa a interface de linha de comando para executar testes E2E
via query no Kiro CLI.

Implements:
- Req 16.1: Executável via `python -m tests.e2e.queries.run_queries`
- Req 16.2: Flag `--tags` para filtrar testes por tags
- Req 16.3: Flag `--case` para executar um teste específico por ID
- Req 16.4: Flag `--parallel N` para execução paralela
- Req 16.5: Durante execução, exibir progresso no terminal
- Req 16.6: Após execução, exibir sumário com total passed/failed/skipped
- Req 16.7: Exit code 1 se qualquer teste falha
- Req 16.8: Flag `--report` para gerar dashboard
- Req 16.9: Flag `--set-baseline` para marcar bateria como baseline
- Req 16.10: Flag `--compare BATCH_ID` para comparar com bateria específica
- Req 19.1-19.4: Configuração via variáveis de ambiente

Usage:
    python -m tests.e2e.queries.run_queries
    python -m tests.e2e.queries.run_queries --tags bridge deck
    python -m tests.e2e.queries.run_queries --case check-newave-valid
    python -m tests.e2e.queries.run_queries --parallel 4 --report
    python -m tests.e2e.queries.run_queries --set-baseline
    python -m tests.e2e.queries.run_queries --compare 20241215_143052_abc1234
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from tests.e2e.queries.loader import CasesLoader, CasesLoaderError
from tests.e2e.queries.models import (
    QueryTestCase,
    QueryResult,
    TestResult,
)
from tests.e2e.queries.runner import QueryRunner
from tests.e2e.queries.store import ResultStore
from tests.e2e.queries.validator import QueryValidator, ValidationResult

__all__ = ["main"]

# Lock for thread-safe progress output
_print_lock = threading.Lock()


def _get_env_int(name: str, default: int) -> int:
    """Obtém variável de ambiente como inteiro.

    Args:
        name: Nome da variável de ambiente
        default: Valor padrão se não definida

    Returns:
        Valor inteiro da variável ou default
    """
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _get_env_path(name: str, default: Path) -> Path:
    """Obtém variável de ambiente como Path.

    Args:
        name: Nome da variável de ambiente
        default: Valor padrão se não definida

    Returns:
        Path da variável ou default
    """
    value = os.environ.get(name)
    if value is None:
        return default
    return Path(value)


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
    # Use set membership como o validator faz (Req 4.4: order-independent)
    called_names = {tc.name for tc in result.tool_calls}
    correct_tool = False
    if case.expected.tool:
        correct_tool = case.expected.tool in called_names
    elif case.expected.tools:
        correct_tool = bool(called_names & set(case.expected.tools))

    # Serializar tool calls para JSON
    all_tool_calls = [
        {"name": tc.name, "args": tc.args, "tool_id": tc.tool_id}
        for tc in result.tool_calls
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
        error_message=validation.failure_reason,
        tags=list(case.tags),
        validation_checks=validation_checks,
    )


def main() -> int:
    """Entry point principal do CLI.

    Returns:
        0 se todos os testes passaram, 1 se qualquer teste falhou.
    """
    parser = argparse.ArgumentParser(
        prog="run_queries",
        description="Executa testes E2E via query no Kiro CLI",
    )
    parser.add_argument(
        "--tags",
        nargs="+",
        metavar="TAG",
        help="Filtrar testes por tags (OR logic)",
    )
    parser.add_argument(
        "--case",
        metavar="ID",
        help="Executar um caso específico por ID",
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=1,
        metavar="N",
        help="Número de testes em paralelo (default: 1)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        metavar="SECONDS",
        help="Timeout por query em segundos (default: 120, configurável via QUERY_TIMEOUT_S)",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Gerar dashboard após execução",
    )
    parser.add_argument(
        "--set-baseline",
        action="store_true",
        dest="set_baseline",
        help="Marcar esta bateria como baseline",
    )
    parser.add_argument(
        "--compare",
        metavar="BATCH_ID",
        help="Comparar com bateria específica",
    )

    args = parser.parse_args()

    # Configuração de diretórios
    # base_dir é tests/e2e/ (parent de queries/)
    base_dir = Path(__file__).parent.parent
    cases_path = Path(__file__).parent / "cases.yaml"

    # Fixtures: configurável via QUERY_FIXTURES_DIR (Req 19.2)
    default_fixtures_dir = base_dir / "fixtures"
    fixtures_dir = _get_env_path("QUERY_FIXTURES_DIR", default_fixtures_dir)

    # Outros diretórios
    results_dir = base_dir / "results"
    metrics_dir = base_dir / "metrics"
    reports_dir = base_dir / "reports"

    # Timeout: CLI arg > env var > default (Req 19.3)
    default_timeout = _get_env_int("QUERY_TIMEOUT_S", 120)
    timeout = args.timeout if args.timeout is not None else default_timeout

    # API key: via KIRO_API_KEY (Req 19.1, 19.4)
    api_key = os.environ.get("KIRO_API_KEY")

    # Carregar casos de teste
    try:
        loader = CasesLoader(cases_path, fixtures_dir)
        cases = loader.load(tags=args.tags, case_id=args.case)
    except CasesLoaderError as e:
        print(f"Erro ao carregar casos de teste: {e}", file=sys.stderr)
        return 1

    if not cases:
        print("Nenhum caso de teste encontrado com os filtros especificados.")
        return 0

    print(f"Carregados {len(cases)} casos de teste")

    # Inicializar componentes
    runner = QueryRunner(timeout_seconds=float(timeout), api_key=api_key)
    validator = QueryValidator()
    store = ResultStore(results_dir, metrics_dir)

    # Executar testes
    # Req 16.4: Flag `--parallel N` para execução paralela
    # Req 16.5: Durante execução, exibir progresso no terminal
    test_results: list[TestResult] = []
    total_cases = len(cases)

    if args.parallel <= 1:
        # Execução sequencial (default)
        for i, case in enumerate(cases, 1):
            print(f"[{i}/{total_cases}] {case.id}...", end=" ", flush=True)

            result = runner.execute(case)
            validation = validator.validate(case, result)

            test_result = _build_test_result(case, result, validation)
            test_results.append(test_result)

            # Exibir status com detalhes (Req 16.5)
            # Use ASCII-safe icons to avoid encoding issues on Windows cp1252
            if test_result.status == "pass":
                status_icon = "[OK]"
            elif test_result.status == "partial":
                status_icon = "[PARTIAL]"
            else:
                status_icon = "[FAIL]"
            
            print(f"{status_icon} {test_result.status} ({result.latency_ms:.0f}ms)")
            
            # Mostrar detalhes para partial e fail
            if test_result.status in ("partial", "fail"):
                for check in validation.checks:
                    # Use ASCII-safe icons to avoid encoding issues on Windows cp1252
                    check_icon = "[OK]" if check.passed else "[X]"
                    print(f"    {check_icon} {check.message}")
    else:
        # Execução paralela com ThreadPoolExecutor
        print(f"Executando com {args.parallel} threads em paralelo...")

        # Dictionary to store results in order
        results_by_index: dict[int, TestResult] = {}
        completed_count = 0
        completed_lock = threading.Lock()

        def execute_test(idx: int, case: QueryTestCase) -> tuple[int, TestResult, ValidationResult]:
            """Executa um único teste e retorna índice, resultado e validação."""
            result = runner.execute(case)
            validation = validator.validate(case, result)
            test_result = _build_test_result(case, result, validation)
            return idx, test_result, validation

        with ThreadPoolExecutor(max_workers=args.parallel) as executor:
            # Submit all tasks
            futures = {
                executor.submit(execute_test, idx, case): (idx, case)
                for idx, case in enumerate(cases)
            }

            # Process results as they complete
            for future in as_completed(futures):
                idx, case = futures[future]
                try:
                    result_idx, test_result, validation = future.result()
                    results_by_index[result_idx] = test_result

                    # Thread-safe progress update
                    with completed_lock:
                        completed_count += 1
                        current = completed_count

                    # Thread-safe print (Req 16.5)
                    # Use ASCII-safe icons to avoid encoding issues on Windows cp1252
                    status_icon = "[OK]" if validation.valid else "[FAIL]"
                    with _print_lock:
                        print(
                            f"[{current}/{total_cases}] {case.id}... "
                            f"{status_icon} {validation.status} "
                            f"({test_result.latency_ms:.0f}ms)"
                        )

                except Exception as e:
                    # Handle execution errors gracefully
                    with completed_lock:
                        completed_count += 1
                        current = completed_count

                    # Create a failed test result for the error case
                    error_result = TestResult(
                        test_id=case.id,
                        query=case.query,
                        expected_tool=case.expected.tool,
                        expected_tools=case.expected.tools,
                        actual_tool=None,
                        all_tool_calls=[],
                        status="fail",
                        latency_ms=0.0,
                        tool_latency_ms=None,
                        mcp_used=False,
                        correct_tool=False,
                        correct_result=False,
                        agent_response="",
                        error_message=f"Execution error: {e}",
                        tags=list(case.tags),
                        validation_checks=[],
                    )
                    results_by_index[idx] = error_result

                    with _print_lock:
                        print(
                            f"[{current}/{total_cases}] {case.id}... "
                            f"✗ error (execution failed: {e})"
                        )

        # Reconstruct results in original order
        test_results = [results_by_index[i] for i in range(total_cases)]

    # Criar e salvar batch
    batch = store.create_batch(test_results)
    batch_path = store.save_batch(batch)
    store.append_metrics(batch)

    # Set baseline se solicitado (Req 16.9)
    if args.set_baseline:
        store.set_baseline(batch.batch_id)
        print(f"Bateria {batch.batch_id} definida como baseline")

    # Exibir sumário (Req 16.6)
    print()
    print("=" * 60)
    print(f"Batch: {batch.batch_id}")
    print(
        f"Total: {batch.total_tests} | "
        f"Passed: {batch.passed} | "
        f"Partial: {batch.partial} | "
        f"Failed: {batch.failed} | "
        f"Timeout: {batch.timeout}"
    )
    print(
        f"MCP Used: {batch.metrics.pct_mcp_used:.1f}% | "
        f"Correct Tool: {batch.metrics.pct_correct_tool:.1f}%"
    )
    print("=" * 60)

    # Gerar dashboard se solicitado (Req 16.8)
    if args.report:
        import webbrowser
        from tests.e2e.queries.dashboard import QueryDashboard
        dashboard = QueryDashboard(results_dir, reports_dir)
        dashboard_path = dashboard.generate(
            batch_id=batch.batch_id,
            compare_with=args.compare,
        )
        print(f"Dashboard gerado: {dashboard_path}")
        # Abrir automaticamente no browser
        webbrowser.open(dashboard_path.as_uri())

    # Exit code (Req 16.7)
    # Exit code: 0 se não houve falhas reais (partial conta como sucesso parcial)
    return 0 if batch.failed == 0 and batch.timeout == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
