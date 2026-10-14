"""Geração de relatórios JSON de execução de testes."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import ExecutionResult, MetricRecord


def generate_json_report(
    results: list[ExecutionResult],
    output_path: Path,
    environment: str = "local",
    previous_records: list[MetricRecord] | None = None,
) -> dict[str, Any]:
    """Gera relatório JSON com sumário e resultados agrupados por tool.

    Args:
        results: Lista de resultados da execução atual
        output_path: Caminho para salvar o relatório
        environment: "local" ou URL do servidor
        previous_records: Registros do run anterior para comparação

    Returns:
        O relatório gerado (mesmo conteúdo salvo no arquivo).
    """
    now = datetime.now()
    
    # Sumário geral
    total = len(results)
    passed = sum(1 for r in results if r.status == "passed")
    failed = sum(1 for r in results if r.status == "failed")
    errors = sum(1 for r in results if r.status == "error")
    skipped = sum(1 for r in results if r.status == "skipped")
    
    total_time_ms = sum(r.execution_time_ms for r in results)
    
    # Agrupar por tool
    by_tool: dict[str, list[ExecutionResult]] = defaultdict(list)
    for r in results:
        by_tool[r.test_case.tool_name].append(r)
    
    tool_summaries = []
    for tool_name, tool_results in sorted(by_tool.items()):
        t_total = len(tool_results)
        t_passed = sum(1 for r in tool_results if r.status == "passed")
        t_failed = sum(1 for r in tool_results if r.status == "failed")
        t_errors = sum(1 for r in tool_results if r.status == "error")
        t_time = sum(r.execution_time_ms for r in tool_results)
        
        failures = []
        for r in tool_results:
            if r.status != "passed":
                failures.append({
                    "case_id": r.test_case.case_id,
                    "status": r.status,
                    "reason": r.failure_reason,
                    "details": r.validation_details,
                })
        
        tool_summaries.append({
            "tool_name": tool_name,
            "total": t_total,
            "passed": t_passed,
            "failed": t_failed,
            "errors": t_errors,
            "pass_rate": t_passed / t_total if t_total > 0 else 0,
            "total_time_ms": round(t_time, 2),
            "avg_time_ms": round(t_time / t_total, 2) if t_total > 0 else 0,
            "failures": failures,
        })
    
    # Comparação com run anterior
    comparison = None
    if previous_records:
        comparison = _compare_with_previous(results, previous_records)
    
    report = {
        "run_id": now.isoformat(timespec="seconds"),
        "timestamp": now.isoformat(),
        "environment": environment,
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "skipped": skipped,
            "pass_rate": passed / total if total > 0 else 0,
            "duration_ms": round(total_time_ms, 2),
            "duration_seconds": round(total_time_ms / 1000, 2),
        },
        "by_tool": tool_summaries,
        "comparison": comparison,
        "all_passed": passed == total,
    }
    
    # Salvar arquivo
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    return report


def _compare_with_previous(
    current: list[ExecutionResult],
    previous: list[MetricRecord],
) -> dict[str, Any]:
    """Compara run atual com o anterior.

    Returns:
        Dict com delta de falhas e mudanças de tempo.
    """
    # Indexa por (tool, case_id)
    prev_by_key: dict[tuple[str, str], MetricRecord] = {}
    for rec in previous:
        key = (rec.tool_name, rec.case_id)
        prev_by_key[key] = rec
    
    curr_by_key: dict[tuple[str, str], ExecutionResult] = {}
    for res in current:
        key = (res.test_case.tool_name, res.test_case.case_id)
        curr_by_key[key] = res
    
    # Identifica conjuntos
    prev_keys = set(prev_by_key.keys())
    curr_keys = set(curr_by_key.keys())
    
    common_keys = prev_keys & curr_keys
    new_tests = curr_keys - prev_keys  # No atual, não no anterior
    removed_tests = prev_keys - curr_keys  # No anterior, não no atual
    
    # Conta apenas os testes comparáveis (existem em ambos)
    prev_passed_comparable = sum(1 for k in common_keys if prev_by_key[k].status == "passed")
    curr_passed_comparable = sum(1 for k in common_keys if curr_by_key[k].status == "passed")
    
    # Casos que mudaram de status
    new_failures = []
    new_passes = []
    
    for key in common_keys:
        prev = prev_by_key[key]
        curr = curr_by_key[key]
        
        full_id = f"{key[0]}/{key[1]}"
        
        if curr.status == "passed" and prev.status != "passed":
            new_passes.append(full_id)
        elif curr.status != "passed" and prev.status == "passed":
            new_failures.append(full_id)
    
    # Totais gerais (para contexto)
    prev_passed_total = sum(1 for r in previous if r.status == "passed")
    curr_passed_total = sum(1 for r in current if r.status == "passed")
    
    # Tempo médio (só dos comparáveis)
    if common_keys:
        prev_avg_time = sum(prev_by_key[k].execution_time_ms for k in common_keys) / len(common_keys)
        curr_avg_time = sum(curr_by_key[k].execution_time_ms for k in common_keys) / len(common_keys)
        time_change = ((curr_avg_time - prev_avg_time) / prev_avg_time * 100) if prev_avg_time > 0 else 0
    else:
        prev_avg_time = 0
        curr_avg_time = 0
        time_change = 0
    
    return {
        "previous_run": {
            "total": len(previous),
            "passed": prev_passed_total,
            "failed": len(previous) - prev_passed_total,
        },
        "comparable_tests": len(common_keys),
        "new_tests": [f"{k[0]}/{k[1]}" for k in sorted(new_tests)],
        "removed_tests": [f"{k[0]}/{k[1]}" for k in sorted(removed_tests)],
        "delta": {
            "passed": curr_passed_comparable - prev_passed_comparable,
            "failed": (len(common_keys) - curr_passed_comparable) - (len(common_keys) - prev_passed_comparable),
        },
        "new_failures": sorted(new_failures),
        "new_passes": sorted(new_passes),
        "time_change_percent": round(time_change, 1),
    }


def format_summary_text(report: dict[str, Any]) -> str:
    """Formata sumário do relatório para exibição em terminal.

    Args:
        report: Relatório gerado por generate_json_report

    Returns:
        Texto formatado para stdout.
    """
    s = report["summary"]
    lines = [
        "=" * 60,
        f"<repositório anterior> Tool Evaluation - {report['run_id']}",
        "=" * 60,
        f"Environment: {report['environment']}",
        f"Duration: {s['duration_seconds']:.1f}s",
        "",
        f"Total: {s['total']} | Passed: {s['passed']} | Failed: {s['failed']} | Errors: {s['errors']}",
        f"Pass Rate: {s['pass_rate']:.1%}",
        "",
    ]
    
    # Por tool
    lines.append("Results by Tool:")
    for tool in report["by_tool"]:
        status = "✓" if tool["passed"] == tool["total"] else "✗"
        lines.append(
            f"  {status} {tool['tool_name']}: "
            f"{tool['passed']}/{tool['total']} ({tool['pass_rate']:.0%}) "
            f"avg {tool['avg_time_ms']:.0f}ms"
        )
    
    # Comparação
    if report.get("comparison"):
        comp = report["comparison"]
        lines.append("")
        lines.append("Comparison with previous run:")
        delta_p = comp["delta"]["passed"]
        delta_f = comp["delta"]["failed"]
        lines.append(f"  Passed: {'+' if delta_p >= 0 else ''}{delta_p}")
        lines.append(f"  Failed: {'+' if delta_f >= 0 else ''}{delta_f}")
        if comp["new_failures"]:
            lines.append(f"  New failures: {', '.join(comp['new_failures'])}")
        if comp["new_passes"]:
            lines.append(f"  Now passing: {', '.join(comp['new_passes'])}")
    
    lines.append("=" * 60)
    return "\n".join(lines)
