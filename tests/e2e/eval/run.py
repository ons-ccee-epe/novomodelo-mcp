"""CLI Runner para execução de testes e2e do <repositório anterior>.

Uso:
    python -m tests.e2e.eval.run              # Executa todos os testes
    python -m tests.e2e.eval.run --check      # Apenas verifica pré-requisitos
    python -m tests.e2e.eval.run --tool deck_list  # Filtra por tool
    python -m tests.e2e.eval.run --tag functional  # Filtra por tag
    python -m tests.e2e.eval.run --no-browser      # Não abre dashboard
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from .client import MCPClient
from .metrics import MetricStore
from .models import ExecutionResult
from .prerequisites import check_prerequisites, print_prerequisites_status
from .registry import TestRegistry, discover_cases
from .reporter import format_summary_text, generate_json_report
from .validator import validate


# Caminhos relativos ao diretório e2e
E2E_ROOT = Path(__file__).parent.parent
CASES_DIR = E2E_ROOT / "cases"
REPORTS_DIR = E2E_ROOT / "reports"


def run_tests(
    client: MCPClient,
    registry: TestRegistry,
    tool_filter: str | None = None,
    tag_filter: str | None = None,
    verbose: bool = True,
) -> list[ExecutionResult]:
    """Executa os testes e retorna resultados.

    Args:
        client: Cliente MCP configurado
        registry: Registry com casos carregados
        tool_filter: Filtrar por nome de tool específica
        tag_filter: Filtrar por tag
        verbose: Imprime progresso no stdout

    Returns:
        Lista de ExecutionResult
    """
    # Seleciona casos
    if tool_filter:
        cases = registry.get_by_tool(tool_filter)
    elif tag_filter:
        cases = registry.get_by_tag(tag_filter)
    else:
        cases = registry.get_all()

    if not cases:
        if verbose:
            print("Nenhum caso de teste encontrado com os filtros especificados.")
        return []

    if verbose:
        print(f"Executando {len(cases)} caso(s) de teste...\n")

    results = []
    for case in cases:
        if verbose:
            print(f"  {case.tool_name}/{case.case_id}...", end=" ", flush=True)

        try:
            # Chama a tool
            envelope, elapsed_ms = client.call_tool(
                case.tool_name,
                **case.parameters,
            )

            # Valida resultado
            validation = validate(case, envelope)

            if validation["valid"]:
                status = "passed"
                failure_reason = None
                validation_details = None
            else:
                status = "failed"
                failure_reason = validation["reason"]
                validation_details = validation.get("details")

            result = ExecutionResult(
                test_case=case,
                envelope=envelope,
                execution_time_ms=elapsed_ms,
                status=status,
                timestamp=datetime.now(),
                failure_reason=failure_reason,
                validation_details=validation_details,
            )

        except Exception as e:
            result = ExecutionResult(
                test_case=case,
                envelope={"error": str(e)},
                execution_time_ms=0,
                status="error",
                timestamp=datetime.now(),
                failure_reason=f"Exceção: {type(e).__name__}: {e}",
            )

        results.append(result)

        if verbose:
            icon = "✓" if result.status == "passed" else "✗"
            time_str = f"({result.execution_time_ms:.0f}ms)" if result.execution_time_ms > 0 else ""
            print(f"{icon} {time_str}")
            if result.failure_reason and result.status != "passed":
                print(f"      └─ {result.failure_reason}")

    return results


def main() -> None:
    """Entry point do CLI."""
    parser = argparse.ArgumentParser(
        description="<repositório anterior> Tool Evaluation Framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python -m tests.e2e.eval.run                    # Executa todos os testes
  python -m tests.e2e.eval.run --check            # Verifica pré-requisitos
  python -m tests.e2e.eval.run --tool deck_list   # Testa tool específica
  python -m tests.e2e.eval.run --tag functional   # Filtra por tag
  python -m tests.e2e.eval.run --no-browser       # Sem abrir dashboard
        """,
    )
    parser.add_argument(
        "--target",
        help="MCP target: 'local' (default) ou URL do servidor remoto",
        default=None,
    )
    parser.add_argument(
        "--tool",
        help="Filtrar por nome de tool específica",
        default=None,
    )
    parser.add_argument(
        "--tag",
        help="Filtrar por tag (ex: functional, newave, decomp)",
        default=None,
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Apenas verificar pré-requisitos sem executar testes",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Não abrir dashboard no browser após execução",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Modo silencioso (apenas sumário final)",
    )
    parser.add_argument(
        "--skip-cli-check",
        action="store_true",
        help="Pula verificação de cobre/cobre-bridge (útil para rodar só testes funcionais)",
    )

    args = parser.parse_args()
    target = args.target or "local"

    # Banner
    if not args.quiet:
        print("=" * 60)
        print("🔬 <repositório anterior> Tool Evaluation Framework")
        print("=" * 60)
        print()

    # Verificar pré-requisitos
    prereq_ok = check_prerequisites(target, skip_cli=args.skip_cli_check)
    if not args.quiet:
        print_prerequisites_status(target, skip_cli=args.skip_cli_check)
        print()

    if not prereq_ok:
        print("❌ Pré-requisitos não atendidos. Corrija os problemas acima.")
        if not args.skip_cli_check:
            print("   Dica: use --skip-cli-check para rodar testes que não precisam de cobre/cobre-bridge")
        sys.exit(1)

    if args.check:
        print("✓ Pré-requisitos OK")
        sys.exit(0)

    # Carregar casos de teste
    registry = TestRegistry()
    discovered = discover_cases(registry, CASES_DIR)

    if not args.quiet:
        print(f"Descobertos {discovered} caso(s) de teste em {CASES_DIR.name}/")
        print()

    if registry.count() == 0:
        print("⚠️  Nenhum caso de teste encontrado.")
        print(f"   Adicione arquivos test_*.py em {CASES_DIR}")
        sys.exit(1)

    # Inicializar cliente
    try:
        client = MCPClient(target)
    except Exception as e:
        print(f"❌ Falha ao inicializar cliente MCP: {e}")
        sys.exit(1)

    # Executar testes
    results = run_tests(
        client=client,
        registry=registry,
        tool_filter=args.tool,
        tag_filter=args.tag,
        verbose=not args.quiet,
    )

    if not results:
        sys.exit(0)

    # Buscar run anterior para comparação ANTES de salvar o atual
    metric_store = MetricStore()
    previous = metric_store.read_last_run()

    # Persistir métricas do run atual
    metric_store.append_batch(results, environment=target)

    # Gerar relatórios
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    report = generate_json_report(
        results,
        REPORTS_DIR / "latest.json",
        environment=target,
        previous_records=previous if previous else None,
    )

    # Sumário
    print()
    print(format_summary_text(report))
    print()
    print(f"Relatorio JSON: {REPORTS_DIR / 'latest.json'}")
    print()
    print("Dashboard: frontend Vite em tests/e2e/frontend (consome os JSON).")
    print("  cd tests/e2e/frontend && npm run dev   # http://127.0.0.1:5174")

    # Exit code
    passed = sum(1 for r in results if r.status == "passed")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
