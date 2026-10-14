"""Geração de dashboard HTML interativo para resultados de testes."""
from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import ExecutionResult

TEMPLATE = '''<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title><repositório anterior> Eval Dashboard</title>
    <style>
        :root {{
            --pass: #22c55e;
            --fail: #ef4444;
            --error: #f59e0b;
            --skip: #94a3b8;
            --bg: #f8fafc;
            --card: #ffffff;
            --border: #e2e8f0;
            --text: #1e293b;
            --text-muted: #64748b;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.5;
            padding: 2rem;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ font-size: 1.75rem; margin-bottom: 0.5rem; }}
        .subtitle {{ color: var(--text-muted); margin-bottom: 2rem; }}
        
        /* Summary Cards */
        .summary {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }}
        .card {{
            background: var(--card);
            border-radius: 8px;
            padding: 1.25rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            border-left: 4px solid var(--border);
        }}
        .card.pass {{ border-left-color: var(--pass); }}
        .card.fail {{ border-left-color: var(--fail); }}
        .card.rate {{ border-left-color: #3b82f6; }}
        .card.time {{ border-left-color: #8b5cf6; }}
        .card-value {{ font-size: 2rem; font-weight: 700; }}
        .card-label {{ font-size: 0.875rem; color: var(--text-muted); }}
        
        /* Tables */
        .section {{ margin-bottom: 2rem; }}
        .section-title {{ font-size: 1.25rem; margin-bottom: 1rem; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background: var(--card);
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        th, td {{ padding: 0.75rem 1rem; text-align: left; }}
        th {{ background: #f1f5f9; font-weight: 600; font-size: 0.875rem; }}
        tr:not(:last-child) td {{ border-bottom: 1px solid var(--border); }}
        tr:hover td {{ background: #f8fafc; }}
        
        /* Status badges */
        .status {{
            display: inline-block;
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
        }}
        .status.passed {{ background: #dcfce7; color: #166534; }}
        .status.failed {{ background: #fee2e2; color: #991b1b; }}
        .status.error {{ background: #fef3c7; color: #92400e; }}
        .status.skipped {{ background: #f1f5f9; color: #475569; }}
        
        /* Progress bar */
        .progress-bar {{
            height: 8px;
            background: #e2e8f0;
            border-radius: 4px;
            overflow: hidden;
        }}
        .progress-fill {{
            height: 100%;
            background: var(--pass);
            transition: width 0.3s;
        }}
        
        /* Failures section */
        .failure-item {{
            background: var(--card);
            border-radius: 8px;
            margin-bottom: 0.75rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        .failure-header {{
            padding: 1rem;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .failure-header:hover {{ background: #f8fafc; }}
        .failure-title {{ font-weight: 600; }}
        .failure-reason {{ color: var(--fail); font-size: 0.875rem; }}
        .failure-details {{
            display: none;
            padding: 1rem;
            background: #f8fafc;
            border-top: 1px solid var(--border);
        }}
        .failure-item.open .failure-details {{ display: block; }}
        pre {{
            background: #1e293b;
            color: #e2e8f0;
            padding: 1rem;
            border-radius: 4px;
            overflow-x: auto;
            font-size: 0.8rem;
        }}
        
        /* All passed message */
        .all-passed {{
            background: #dcfce7;
            color: #166534;
            padding: 1.5rem;
            border-radius: 8px;
            text-align: center;
            font-size: 1.125rem;
        }}
        .all-passed::before {{ content: "✓ "; }}
        
        /* Comparison section */
        .comparison-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 1rem;
        }}
        .comparison-card {{
            background: var(--card);
            border-radius: 8px;
            padding: 1rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        .comparison-card h4 {{
            font-size: 0.875rem;
            color: var(--text-muted);
            margin-bottom: 0.5rem;
        }}
        .delta {{
            font-size: 1.5rem;
            font-weight: 700;
        }}
        .delta.positive {{ color: var(--pass); }}
        .delta.negative {{ color: var(--fail); }}
        .delta.neutral {{ color: var(--text-muted); }}
        .regression-list, .improvement-list {{
            margin-top: 0.5rem;
            padding: 0.75rem;
            border-radius: 4px;
            font-size: 0.875rem;
        }}
        .regression-list {{
            background: #fee2e2;
            color: #991b1b;
        }}
        .improvement-list {{
            background: #dcfce7;
            color: #166534;
        }}
        .no-comparison {{
            color: var(--text-muted);
            font-style: italic;
            padding: 1rem;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🔬 <repositório anterior> Evaluation Dashboard</h1>
        <p class="subtitle">Executado em {timestamp} | Ambiente: {environment}</p>
        
        <div class="summary">
            <div class="card">
                <div class="card-value">{total}</div>
                <div class="card-label">Total</div>
            </div>
            <div class="card pass">
                <div class="card-value">{passed}</div>
                <div class="card-label">Passed</div>
            </div>
            <div class="card fail">
                <div class="card-value">{failed}</div>
                <div class="card-label">Failed</div>
            </div>
            <div class="card rate">
                <div class="card-value">{pass_rate:.0%}</div>
                <div class="card-label">Pass Rate</div>
            </div>
            <div class="card time">
                <div class="card-value">{duration:.1f}s</div>
                <div class="card-label">Duration</div>
            </div>
        </div>
        
        <div class="section">
            <h2 class="section-title">Results by Tool</h2>
            <table>
                <thead>
                    <tr>
                        <th>Tool</th>
                        <th>Total</th>
                        <th>Passed</th>
                        <th>Progress</th>
                        <th>Avg Time</th>
                    </tr>
                </thead>
                <tbody>
                    {tool_rows}
                </tbody>
            </table>
        </div>
        
        {comparison_html}
        
        <div class="section">
            <h2 class="section-title">Failures</h2>
            {failures_html}
        </div>
    </div>
    
    <script>
        document.querySelectorAll('.failure-header').forEach(header => {{
            header.addEventListener('click', () => {{
                header.parentElement.classList.toggle('open');
            }});
        }});
    </script>
</body>
</html>'''


def generate_dashboard(
    results: list[ExecutionResult],
    output_path: Path,
    environment: str = "local",
    comparison: dict[str, Any] | None = None,
) -> None:
    """Gera dashboard HTML standalone a partir dos resultados.

    Args:
        results: Lista de resultados da execução
        output_path: Caminho para salvar o HTML
        environment: "local" ou URL do servidor
        comparison: Dados de comparação com run anterior (opcional)
    """
    from collections import defaultdict

    # Agrupa por tool
    by_tool: dict[str, list[ExecutionResult]] = defaultdict(list)
    for r in results:
        by_tool[r.test_case.tool_name].append(r)

    # Sumário
    total = len(results)
    passed = sum(1 for r in results if r.status == "passed")
    failed = total - passed
    duration = sum(r.execution_time_ms for r in results) / 1000
    pass_rate = passed / total if total > 0 else 0

    # Linhas da tabela por tool
    tool_rows = []
    for tool_name, tool_results in sorted(by_tool.items()):
        t_passed = sum(1 for r in tool_results if r.status == "passed")
        t_total = len(tool_results)
        t_rate = t_passed / t_total if t_total else 0
        t_avg = sum(r.execution_time_ms for r in tool_results) / t_total if t_total else 0

        row = f'''<tr>
            <td><strong>{html.escape(tool_name)}</strong></td>
            <td>{t_total}</td>
            <td><span class="status {'passed' if t_passed == t_total else 'failed'}">{t_passed}</span></td>
            <td>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: {t_rate * 100}%"></div>
                </div>
            </td>
            <td>{t_avg:.0f}ms</td>
        </tr>'''
        tool_rows.append(row)

    # Seção de falhas
    failures = [r for r in results if r.status != "passed"]
    if failures:
        failures_html_parts = []
        for f in failures:
            details = f.validation_details or f.envelope
            details_json = json.dumps(details, ensure_ascii=False, indent=2)
            
            status_class = f.status
            reason = html.escape(f.failure_reason or "Erro desconhecido")
            
            item = f'''<div class="failure-item">
                <div class="failure-header">
                    <div>
                        <span class="failure-title">{html.escape(f.test_case.tool_name)}/{html.escape(f.test_case.case_id)}</span>
                        <span class="status {status_class}">{status_class}</span>
                    </div>
                    <span class="failure-reason">{reason}</span>
                </div>
                <div class="failure-details">
                    <p><strong>Descrição:</strong> {html.escape(f.test_case.description)}</p>
                    <p><strong>Parâmetros:</strong></p>
                    <pre>{html.escape(json.dumps(f.test_case.parameters, ensure_ascii=False, indent=2))}</pre>
                    <p><strong>Detalhes:</strong></p>
                    <pre>{html.escape(details_json)}</pre>
                </div>
            </div>'''
            failures_html_parts.append(item)
        failures_html = "\n".join(failures_html_parts)
    else:
        failures_html = '<div class="all-passed">Todos os testes passaram!</div>'

    # Seção de comparação com run anterior
    if comparison:
        delta_passed = comparison["delta"]["passed"]
        delta_failed = comparison["delta"]["failed"]
        time_change = comparison.get("time_change_percent", 0)
        comparable = comparison.get("comparable_tests", 0)
        prev_total = comparison["previous_run"]["total"]
        
        # Classes para deltas
        passed_class = "positive" if delta_passed > 0 else ("negative" if delta_passed < 0 else "neutral")
        failed_class = "negative" if delta_failed > 0 else ("positive" if delta_failed < 0 else "neutral")
        time_class = "negative" if time_change > 10 else ("positive" if time_change < -10 else "neutral")
        
        # Formata deltas
        passed_str = f"+{delta_passed}" if delta_passed > 0 else str(delta_passed)
        failed_str = f"+{delta_failed}" if delta_failed > 0 else str(delta_failed)
        time_str = f"+{time_change:.1f}%" if time_change > 0 else f"{time_change:.1f}%"
        
        comparison_html = f'''<div class="section">
            <h2 class="section-title">📊 Comparação com Run Anterior</h2>
            <p style="color: var(--text-muted); margin-bottom: 1rem;">
                Run anterior: {prev_total} testes | Comparáveis: {comparable} testes
            </p>
            <div class="comparison-grid">
                <div class="comparison-card">
                    <h4>Delta Passed</h4>
                    <div class="delta {passed_class}">{passed_str}</div>
                </div>
                <div class="comparison-card">
                    <h4>Delta Failed</h4>
                    <div class="delta {failed_class}">{failed_str}</div>
                </div>
                <div class="comparison-card">
                    <h4>Tempo Médio</h4>
                    <div class="delta {time_class}">{time_str}</div>
                </div>
            </div>'''
        
        # Regressões (passavam, agora falham)
        if comparison.get("new_failures"):
            regression_items = "<br>".join(f"• {html.escape(f)}" for f in comparison["new_failures"])
            comparison_html += f'''
            <div class="regression-list">
                <strong>⚠️ Regressões (antes passavam, agora falham):</strong><br>
                {regression_items}
            </div>'''
        
        # Melhorias (falhavam, agora passam)
        if comparison.get("new_passes"):
            improvement_items = "<br>".join(f"• {html.escape(f)}" for f in comparison["new_passes"])
            comparison_html += f'''
            <div class="improvement-list">
                <strong>✓ Melhorias (antes falhavam, agora passam):</strong><br>
                {improvement_items}
            </div>'''
        
        # Testes novos (não existiam no run anterior)
        if comparison.get("new_tests"):
            new_items = ", ".join(html.escape(f) for f in comparison["new_tests"][:10])
            more = f" (+{len(comparison['new_tests']) - 10} mais)" if len(comparison["new_tests"]) > 10 else ""
            comparison_html += f'''
            <div style="margin-top: 0.5rem; padding: 0.75rem; background: #e0f2fe; color: #0369a1; border-radius: 4px; font-size: 0.875rem;">
                <strong>🆕 Testes novos:</strong> {new_items}{more}
            </div>'''
        
        # Testes removidos (existiam no run anterior, não no atual)
        if comparison.get("removed_tests"):
            removed_items = ", ".join(html.escape(f) for f in comparison["removed_tests"][:10])
            more = f" (+{len(comparison['removed_tests']) - 10} mais)" if len(comparison["removed_tests"]) > 10 else ""
            comparison_html += f'''
            <div style="margin-top: 0.5rem; padding: 0.75rem; background: #fef3c7; color: #92400e; border-radius: 4px; font-size: 0.875rem;">
                <strong>🗑️ Não executados neste run:</strong> {removed_items}{more}
            </div>'''
        
        # Se não há mudanças de status
        if not comparison.get("new_failures") and not comparison.get("new_passes") and comparable > 0:
            comparison_html += '''
            <div style="margin-top: 0.5rem; padding: 0.75rem; background: #f1f5f9; color: #475569; border-radius: 4px; font-size: 0.875rem; text-align: center;">
                Nenhuma mudança de status nos testes comparáveis.
            </div>'''
        
        comparison_html += "</div>"
    else:
        comparison_html = '''<div class="section">
            <h2 class="section-title">📊 Comparação com Run Anterior</h2>
            <div class="no-comparison">Nenhum run anterior encontrado para comparação.</div>
        </div>'''

    # Renderiza template
    html_content = TEMPLATE.format(
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        environment=html.escape(environment),
        total=total,
        passed=passed,
        failed=failed,
        pass_rate=pass_rate,
        duration=duration,
        tool_rows="\n".join(tool_rows),
        comparison_html=comparison_html,
        failures_html=failures_html,
    )

    # Salva arquivo
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_content, encoding="utf-8")
