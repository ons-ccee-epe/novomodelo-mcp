"""Geração de dashboard HTML interativo para resultados de query tests.

Este módulo implementa o QueryDashboard que gera dashboards HTML standalone
para visualização de resultados de baterias de testes E2E via query.

Implements:
- Req 13.7: Chart.js via CDN para gráficos
- Req 20.3: Reaproveitar templates HTML de eval/dashboard.py como base
"""
from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from tests.e2e.queries.models import BatchResult
from tests.e2e.queries.store import ResultStore, TOOL_GROUPS

__all__ = ["QueryDashboard"]


# Chart.js CDN URL (Req 13.7)
CHARTJS_CDN = "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"


# Base HTML template (Req 20.3: reaproveitado e expandido de eval/dashboard.py)
BASE_TEMPLATE = '''<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Query E2E Test Dashboard</title>
    <script src="{chartjs_cdn}"></script>
    <style>
        :root {{
            --pass: #22c55e;
            --fail: #ef4444;
            --error: #f59e0b;
            --skip: #94a3b8;
            --timeout: #8b5cf6;
            --bg: #f8fafc;
            --card: #ffffff;
            --border: #e2e8f0;
            --text: #1e293b;
            --text-muted: #64748b;
            --primary: #3b82f6;
            --secondary: #8b5cf6;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.5;
            padding: 2rem;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        h1 {{ font-size: 1.75rem; margin-bottom: 0.5rem; }}
        h2 {{ font-size: 1.25rem; margin-bottom: 1rem; color: var(--text); }}
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
        .card.timeout {{ border-left-color: var(--timeout); }}
        .card.rate {{ border-left-color: var(--primary); }}
        .card.time {{ border-left-color: var(--secondary); }}
        .card.mcp {{ border-left-color: #06b6d4; }}
        .card-value {{ font-size: 2rem; font-weight: 700; }}
        .card-label {{ font-size: 0.875rem; color: var(--text-muted); }}
        
        /* Section */
        .section {{ margin-bottom: 2rem; }}
        .section-title {{ 
            font-size: 1.25rem; 
            margin-bottom: 1rem;
            padding-bottom: 0.5rem;
            border-bottom: 2px solid var(--border);
        }}
        
        /* Tables */
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
        .status.pass {{ background: #dcfce7; color: #166534; }}
        .status.fail {{ background: #fee2e2; color: #991b1b; }}
        .status.timeout {{ background: #f3e8ff; color: #6b21a8; }}
        .status.skip {{ background: #f1f5f9; color: #475569; }}
        
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
        
        /* Charts */
        .charts-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }}
        .chart-container {{
            background: var(--card);
            border-radius: 8px;
            padding: 1.5rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        .chart-title {{
            font-size: 1rem;
            font-weight: 600;
            margin-bottom: 1rem;
            color: var(--text);
        }}
        .chart-wrapper {{
            position: relative;
            height: 250px;
        }}
        
        /* Period selector buttons (Req 13.5) */
        .period-selector {{
            font-weight: normal;
        }}
        .period-btn {{
            padding: 0.25rem 0.5rem;
            font-size: 0.75rem;
            border: 1px solid var(--border);
            border-radius: 4px;
            background: var(--card);
            cursor: pointer;
            transition: all 0.2s;
            color: var(--text-muted);
        }}
        .period-btn:hover {{
            background: #f1f5f9;
            border-color: var(--primary);
            color: var(--primary);
        }}
        .period-btn.active {{
            background: var(--primary);
            color: white;
            border-color: var(--primary);
        }}
        
        /* Alerts */
        .alert-banner {{
            padding: 1rem;
            border-radius: 8px;
            margin-bottom: 1.5rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}
        .alert-banner.healthy {{
            background: #dcfce7;
            color: #166534;
        }}
        .alert-banner.warning {{
            background: #fef3c7;
            color: #92400e;
        }}
        .alert-banner.critical {{
            background: #fee2e2;
            color: #991b1b;
        }}
        
        /* Alert Thresholds Configuration Section (Req 15.6) */
        .alert-section {{
            margin-bottom: 1.5rem;
        }}
        .alert-section .alert-banner {{
            margin-bottom: 0.5rem;
        }}
        .thresholds-toggle {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
            font-size: 0.75rem;
            color: var(--text-muted);
            cursor: pointer;
            padding: 0.5rem;
            background: #f1f5f9;
            border-radius: 0 0 8px 8px;
            border: none;
            width: 100%;
            transition: background 0.2s;
        }}
        .thresholds-toggle:hover {{
            background: #e2e8f0;
        }}
        .thresholds-toggle::before {{
            content: '⚙️';
        }}
        .thresholds-config {{
            display: none;
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 1rem;
            margin-top: 0.5rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        .thresholds-config.expanded {{
            display: block;
        }}
        .thresholds-config h4 {{
            font-size: 0.875rem;
            margin-bottom: 0.75rem;
            color: var(--text);
        }}
        .thresholds-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
        }}
        .threshold-item {{
            display: flex;
            flex-direction: column;
            padding: 0.75rem;
            background: #f8fafc;
            border-radius: 6px;
            border-left: 3px solid var(--primary);
        }}
        .threshold-item.warning {{
            border-left-color: #f59e0b;
        }}
        .threshold-item.critical {{
            border-left-color: #ef4444;
        }}
        .threshold-item.performance {{
            border-left-color: #8b5cf6;
        }}
        .threshold-label {{
            font-size: 0.75rem;
            color: var(--text-muted);
            margin-bottom: 0.25rem;
        }}
        .threshold-value {{
            font-weight: 600;
            font-size: 0.875rem;
        }}
        .threshold-desc {{
            font-size: 0.7rem;
            color: var(--text-muted);
            margin-top: 0.25rem;
        }}
        
        /* Comparison */
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
        
        /* Export JSON Button (Req 12.7) */
        .export-json-btn {{
            float: right;
            padding: 0.375rem 0.75rem;
            font-size: 0.75rem;
            border-radius: 4px;
            cursor: pointer;
            border: 1px solid var(--border);
            background: var(--card);
            color: var(--text);
            transition: all 0.2s;
            font-weight: normal;
            margin-left: 0.5rem;
        }}
        .export-json-btn:hover {{
            background: #f1f5f9;
            border-color: var(--primary);
            color: var(--primary);
        }}
        
        /* Metrics by group/tag */
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 1rem;
        }}
        .metrics-card {{
            background: var(--card);
            border-radius: 8px;
            padding: 1rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            cursor: pointer;
            transition: all 0.2s ease;
            border: 2px solid transparent;
        }}
        .metrics-card:hover {{
            box-shadow: 0 4px 6px rgba(0,0,0,0.15);
            transform: translateY(-2px);
        }}
        .metrics-card.active {{
            border-color: var(--primary);
            background: #f0f9ff;
        }}
        .metrics-card h4 {{
            font-size: 1rem;
            font-weight: 600;
            margin-bottom: 0.75rem;
            text-transform: capitalize;
        }}
        .metric-row {{
            display: flex;
            justify-content: space-between;
            padding: 0.25rem 0;
            font-size: 0.875rem;
        }}
        .metric-label {{ color: var(--text-muted); }}
        .metric-value {{ font-weight: 500; }}
        .metric-value.degraded {{ color: var(--fail); }}
        
        /* Batch list */
        .batch-list {{
            background: var(--card);
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            max-height: 300px;
            overflow-y: auto;
        }}
        .batch-item {{
            padding: 0.75rem 1rem;
            border-bottom: 1px solid var(--border);
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .batch-item:hover {{ background: #f8fafc; }}
        .batch-item.selected {{ background: #e0f2fe; border-left: 3px solid var(--primary); }}
        .batch-item.compare-selected {{ background: #fef3c7; border-left: 3px solid #f59e0b; }}
        .batch-item.selected.compare-selected {{ background: #e0f2fe; }}
        .batch-item:last-child {{ border-bottom: none; }}
        .batch-id {{ font-weight: 500; font-family: monospace; font-size: 0.875rem; }}
        .batch-summary {{ font-size: 0.75rem; color: var(--text-muted); }}
        
        /* Batch comparison controls (Req 12.1) */
        .batch-controls {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 0.75rem;
            flex-wrap: wrap;
            gap: 0.75rem;
        }}
        .compare-toggle {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
            font-size: 0.875rem;
        }}
        .compare-toggle input[type="checkbox"] {{
            width: 1rem;
            height: 1rem;
            cursor: pointer;
        }}
        .compare-toggle label {{
            cursor: pointer;
            user-select: none;
        }}
        .compare-status {{
            font-size: 0.75rem;
            color: var(--text-muted);
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            background: #f1f5f9;
        }}
        .compare-status.active {{
            background: #fef3c7;
            color: #92400e;
        }}
        .compare-actions {{
            display: flex;
            gap: 0.5rem;
        }}
        .compare-btn {{
            padding: 0.375rem 0.75rem;
            font-size: 0.75rem;
            border-radius: 4px;
            cursor: pointer;
            border: 1px solid var(--border);
            background: var(--card);
            transition: all 0.2s;
        }}
        .compare-btn:hover {{
            background: #f1f5f9;
        }}
        .compare-btn.primary {{
            background: var(--primary);
            color: white;
            border-color: var(--primary);
        }}
        .compare-btn.primary:hover {{
            background: #2563eb;
        }}
        .compare-btn.primary:disabled {{
            opacity: 0.5;
            cursor: not-allowed;
        }}
        .batch-compare-link {{
            font-size: 0.7rem;
            color: #f59e0b;
            cursor: pointer;
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            background: transparent;
            border: 1px solid transparent;
            transition: all 0.2s;
            white-space: nowrap;
        }}
        .batch-compare-link:hover {{
            background: #fef3c7;
            border-color: #fbbf24;
        }}
        .batch-compare-link.selected {{
            background: #fef3c7;
            border-color: #f59e0b;
            font-weight: 600;
        }}
        .compare-mode .batch-item {{
            position: relative;
        }}
        .compare-badge {{
            position: absolute;
            top: 0.25rem;
            right: 0.25rem;
            font-size: 0.625rem;
            padding: 0.125rem 0.375rem;
            border-radius: 3px;
            font-weight: 600;
            text-transform: uppercase;
        }}
        .compare-badge.primary {{
            background: var(--primary);
            color: white;
        }}
        .compare-badge.compare {{
            background: #f59e0b;
            color: white;
        }}
        
        /* No data */
        .no-data {{
            text-align: center;
            padding: 2rem;
            color: var(--text-muted);
            font-style: italic;
        }}
        
        /* Test row highlights (Req 11.7, 11.8) */
        .test-row.no-mcp {{ background: #fef2f2 !important; }}
        .test-row.no-mcp:hover {{ background: #fee2e2 !important; }}
        .test-row.wrong-tool {{ background: #fffbeb !important; }}
        .test-row.wrong-tool:hover {{ background: #fef3c7 !important; }}
        
        /* Filter controls (Req 11.4, 11.5, 11.6) */
        .filter-section {{
            display: flex;
            flex-wrap: wrap;
            gap: 1rem;
            margin-bottom: 1rem;
            padding: 1rem;
            background: var(--card);
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        .filter-group {{
            display: flex;
            flex-direction: column;
            gap: 0.25rem;
        }}
        .filter-group label {{
            font-size: 0.75rem;
            font-weight: 600;
            color: var(--text-muted);
            text-transform: uppercase;
        }}
        .filter-group select,
        .filter-group input {{
            padding: 0.5rem 0.75rem;
            border: 1px solid var(--border);
            border-radius: 4px;
            font-size: 0.875rem;
            min-width: 150px;
        }}
        .filter-group select:focus,
        .filter-group input:focus {{
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
        }}
        .tag-filter {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
            max-width: 400px;
        }}
        .tag-checkbox {{
            display: flex;
            align-items: center;
            gap: 0.25rem;
            padding: 0.25rem 0.5rem;
            background: #f1f5f9;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.75rem;
            transition: background 0.2s;
        }}
        .tag-checkbox:hover {{
            background: #e2e8f0;
        }}
        .tag-checkbox input {{
            margin: 0;
            cursor: pointer;
        }}
        .tag-checkbox.active {{
            background: #dbeafe;
            color: var(--primary);
        }}
        .filter-reset {{
            padding: 0.5rem 1rem;
            border: 1px solid var(--border);
            border-radius: 4px;
            background: var(--card);
            cursor: pointer;
            font-size: 0.875rem;
            align-self: flex-end;
            transition: background 0.2s;
        }}
        .filter-reset:hover {{
            background: #f1f5f9;
        }}
        .filter-count {{
            font-size: 0.875rem;
            color: var(--text-muted);
            align-self: flex-end;
            padding: 0.5rem 0;
        }}
        .hidden {{
            display: none !important;
        }}
        
        /* Expandable Test Details (Req 11.3) */
        .test-results-table .test-row {{
            cursor: pointer;
            transition: background 0.2s;
        }}
        .test-results-table .test-row:hover td {{
            background: #f0f9ff;
        }}
        .test-results-table .detail-row {{
            display: none;
        }}
        .test-results-table .detail-row.expanded {{
            display: table-row;
        }}
        .test-results-table .detail-row td {{
            padding: 0;
            background: #fafbfc;
        }}
        
        /* Test Details Panel */
        .test-details {{
            margin: 0;
            border: none;
        }}
        .test-details[open] .details-summary {{
            border-bottom: 1px solid var(--border);
        }}
        .details-summary {{
            padding: 0.75rem 1rem;
            cursor: pointer;
            font-weight: 600;
            color: var(--primary);
            list-style: none;
            display: flex;
            align-items: center;
            gap: 0.5rem;
            transition: background 0.2s;
        }}
        .details-summary:hover {{
            background: #e0f2fe;
        }}
        .details-summary::-webkit-details-marker {{
            display: none;
        }}
        .details-summary::before {{
            content: '▶';
            font-size: 0.75rem;
            transition: transform 0.2s;
        }}
        .test-details[open] .details-summary::before {{
            transform: rotate(90deg);
        }}
        .details-content {{
            padding: 1rem;
            display: flex;
            flex-direction: column;
            gap: 1rem;
        }}
        
        /* Detail Sections */
        .detail-section {{
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 0.75rem 1rem;
        }}
        .detail-section.error-section {{
            background: #fef2f2;
            border-color: #fecaca;
        }}
        .detail-label {{
            font-size: 0.75rem;
            font-weight: 600;
            color: var(--text-muted);
            text-transform: uppercase;
            margin-bottom: 0.5rem;
        }}
        
        /* Query Full Display */
        .query-full {{
            background: #f8fafc;
            border: 1px solid var(--border);
            border-radius: 4px;
            padding: 0.75rem;
            font-family: 'Monaco', 'Consolas', monospace;
            font-size: 0.8125rem;
            white-space: pre-wrap;
            word-break: break-word;
            max-height: 150px;
            overflow-y: auto;
            margin: 0;
        }}
        
        /* Tool Comparison */
        .tool-comparison {{
            display: flex;
            align-items: center;
            gap: 1rem;
            padding: 0.5rem;
            border-radius: 4px;
            background: #f8fafc;
        }}
        .tool-comparison.tool-mismatch {{
            background: #fef3c7;
            border: 1px solid #fbbf24;
        }}
        .tool-comparison.tool-match {{
            background: #dcfce7;
            border: 1px solid #86efac;
        }}
        .tool-expected, .tool-actual {{
            flex: 1;
        }}
        .tool-label {{
            font-size: 0.75rem;
            color: var(--text-muted);
            display: block;
            margin-bottom: 0.25rem;
        }}
        .tool-comparison code {{
            background: var(--card);
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            font-size: 0.875rem;
        }}
        .tool-arrow {{
            font-size: 1.25rem;
            color: var(--text-muted);
        }}
        
        /* Tool Calls List */
        .tool-calls-list {{
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
            max-height: 300px;
            overflow-y: auto;
        }}
        .no-tool-calls {{
            color: var(--text-muted);
            padding: 0.5rem;
        }}
        .tool-call-item {{
            background: #f8fafc;
            border: 1px solid var(--border);
            border-radius: 4px;
            overflow: hidden;
        }}
        .tool-call-header {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.5rem 0.75rem;
            background: #f1f5f9;
        }}
        .tool-call-number {{
            background: var(--primary);
            color: white;
            font-size: 0.625rem;
            font-weight: 600;
            padding: 0.125rem 0.375rem;
            border-radius: 3px;
        }}
        .tool-call-name {{
            font-weight: 600;
            color: var(--text);
        }}
        .tool-id {{
            font-size: 0.625rem;
            color: var(--text-muted);
            font-family: monospace;
            margin-left: auto;
        }}
        .tool-call-args-details {{
            margin: 0;
        }}
        .args-summary {{
            padding: 0.5rem 0.75rem;
            cursor: pointer;
            font-size: 0.75rem;
            color: var(--text-muted);
            list-style: none;
        }}
        .args-summary::-webkit-details-marker {{
            display: none;
        }}
        .args-summary::before {{
            content: '+ ';
            font-weight: bold;
        }}
        .tool-call-args-details[open] .args-summary::before {{
            content: '− ';
        }}
        .tool-call-args {{
            margin: 0;
            padding: 0.5rem 0.75rem;
            background: #ffffff;
            font-size: 0.75rem;
            font-family: 'Monaco', 'Consolas', monospace;
            white-space: pre-wrap;
            word-break: break-all;
            border-top: 1px solid var(--border);
            max-height: 200px;
            overflow-y: auto;
        }}
        
        /* Agent Response */
        .agent-response-details {{
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 6px;
            overflow: hidden;
        }}
        .response-summary {{
            padding: 0.75rem 1rem;
            cursor: pointer;
            font-size: 0.875rem;
            color: var(--text);
            list-style: none;
            background: #f8fafc;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}
        .response-summary::-webkit-details-marker {{
            display: none;
        }}
        .response-summary::after {{
            content: '(clique para expandir)';
            font-size: 0.75rem;
            color: var(--text-muted);
            margin-left: auto;
        }}
        .agent-response-details[open] .response-summary::after {{
            content: '(clique para colapsar)';
        }}
        .agent-response-content {{
            max-height: 400px;
            overflow-y: auto;
        }}
        .agent-response {{
            margin: 0;
            padding: 1rem;
            font-family: 'Monaco', 'Consolas', monospace;
            font-size: 0.8125rem;
            white-space: pre-wrap;
            word-break: break-word;
            background: #fafbfc;
        }}
        
        /* Error Message */
        .error-message {{
            background: #ffffff;
            border: 1px solid #fecaca;
            border-radius: 4px;
            padding: 0.75rem;
            font-family: monospace;
            font-size: 0.8125rem;
            color: #991b1b;
            white-space: pre-wrap;
            word-break: break-word;
        }}
        
        /* Timing Details */
        .timing-details {{
            display: flex;
            flex-wrap: wrap;
            gap: 1.5rem;
        }}
        .timing-item {{
            font-size: 0.875rem;
        }}
        .timing-item strong {{
            color: var(--text-muted);
            margin-right: 0.25rem;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Query E2E Test Dashboard</h1>
        <p class="subtitle">
            Batch: <strong>{batch_id}</strong> | 
            Gerado em {generated_at} | 
            Ambiente: {environment}
        </p>
        
        {alerts_html}
        
        {batch_list_html}
        
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
            <div class="card timeout">
                <div class="card-value">{timeout}</div>
                <div class="card-label">Timeout</div>
            </div>
            <div class="card mcp">
                <div class="card-value">{pct_mcp_used:.1f}%</div>
                <div class="card-label">MCP Used</div>
            </div>
            <div class="card rate">
                <div class="card-value">{pct_correct_tool:.1f}%</div>
                <div class="card-label">Correct Tool</div>
            </div>
            <div class="card time">
                <div class="card-value">{avg_latency_ms:.0f}ms</div>
                <div class="card-label">Avg Latency</div>
            </div>
        </div>
        
        {comparison_html}
        
        {charts_html}
        
        {metrics_by_group_html}
        
        {metrics_by_tag_html}
        
        {test_table_html}
    </div>
    
    {chart_scripts}
</body>
</html>'''


class QueryDashboard:
    """Gera dashboard HTML para resultados de query tests.

    O QueryDashboard é responsável por:
    - Gerar HTML standalone com visualizações de resultados
    - Incluir gráficos de tendência com Chart.js
    - Suportar comparação entre baterias
    - Exibir métricas por grupo e tag

    Implements:
    - Req 13.7: Chart.js via CDN para gráficos
    - Req 20.3: Reaproveitar templates HTML de eval/dashboard.py como base

    Attributes:
        results_dir: Diretório com arquivos de resultados JSON.
        reports_dir: Diretório para salvar dashboards gerados.
        store: ResultStore para carregar baterias e métricas.

    Example:
        >>> dashboard = QueryDashboard(results_dir, reports_dir)
        >>> path = dashboard.generate(batch_id="20241215_143052_abc1234")
        >>> print(f"Dashboard gerado em: {path}")
    """

    def __init__(self, results_dir: Path, reports_dir: Path) -> None:
        """Inicializa o QueryDashboard.

        Args:
            results_dir: Diretório com arquivos de resultados JSON.
            reports_dir: Diretório para salvar dashboards gerados.
        """
        self.results_dir = Path(results_dir)
        self.reports_dir = Path(reports_dir)
        self.store = ResultStore(results_dir, results_dir.parent / "metrics")

    def generate(
        self,
        batch_id: str | None = None,
        compare_with: str | None = None,
    ) -> Path:
        """Gera dashboard HTML.

        Implements:
        - Req 10.4: Destacar bateria mais recente como seleção padrão
        - Req 12.1-12.7: Comparação entre baterias

        Args:
            batch_id: ID da bateria a exibir (default: mais recente).
            compare_with: ID da bateria para comparação (opcional).

        Returns:
            Caminho do dashboard.html gerado.

        Raises:
            FileNotFoundError: Se a bateria especificada não existe.
            ValueError: Se não há baterias disponíveis.
        """
        # Get batch to display (Req 10.4: default to most recent)
        if batch_id is None:
            batches = self.store.list_batches()
            if not batches:
                raise ValueError("Nenhuma bateria disponível para gerar dashboard")
            batch_id = batches[0]["batch_id"]

        # Load main batch
        batch = self.store.load_batch(batch_id)

        # Load comparison batch if specified
        comparison_batch: BatchResult | None = None
        if compare_with:
            comparison_batch = self.store.load_batch(compare_with)

        # Load baseline for alerts
        baseline = self.store.get_baseline()

        # Render sections
        alerts_html = self._render_alerts(batch, baseline)
        batch_list_html = self._render_batch_list(batch.batch_id, compare_with)
        comparison_html = self._render_comparison(
            batch, comparison_batch
        ) if comparison_batch else ""
        charts_html = self._render_trend_charts()
        metrics_by_group_html = self._render_metrics_by_group(batch, comparison_batch)
        metrics_by_tag_html = self._render_metrics_by_tag(batch, comparison_batch)
        test_table_html = self._render_test_table(batch)
        chart_scripts = self._render_chart_scripts(batch, compare_with)

        # Render full dashboard
        html_content = BASE_TEMPLATE.format(
            chartjs_cdn=CHARTJS_CDN,
            batch_id=html.escape(batch.batch_id),
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            environment=html.escape(batch.environment),
            total=batch.total_tests,
            passed=batch.passed,
            failed=batch.failed,
            timeout=batch.timeout,
            pct_mcp_used=batch.metrics.pct_mcp_used,
            pct_correct_tool=batch.metrics.pct_correct_tool,
            avg_latency_ms=batch.metrics.avg_latency_ms,
            alerts_html=alerts_html,
            batch_list_html=batch_list_html,
            comparison_html=comparison_html,
            charts_html=charts_html,
            metrics_by_group_html=metrics_by_group_html,
            metrics_by_tag_html=metrics_by_tag_html,
            test_table_html=test_table_html,
            chart_scripts=chart_scripts,
        )

        # Save dashboard
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.reports_dir / "dashboard.html"
        output_path.write_text(html_content, encoding="utf-8")

        return output_path

    def _render_alerts(
        self,
        batch: BatchResult,
        baseline: BatchResult | None,
    ) -> str:
        """Renderiza banner de alertas com seção de configuração de thresholds.

        Implements:
        - Req 15.1: Alerta amarelo quando pct_mcp_used cai >5%
        - Req 15.2: Alerta vermelho quando pct_mcp_used cai >10%
        - Req 15.3: Alerta quando pct_correct_tool cai >5% vs baseline
        - Req 15.4: Alerta de performance quando latência aumenta >20%
        - Req 15.5: Banner no topo com resumo de alertas
        - Req 15.6: Permitir configurar thresholds via seção de configuração
        - Req 15.7: Indicador verde quando não há alertas

        Args:
            batch: Bateria atual.
            baseline: Bateria baseline para comparação.

        Returns:
            HTML do banner de alertas com seção de thresholds.
        """
        alerts: list[str] = []

        # Get previous batch for comparison
        history = self.store.load_metrics_history(limit=2)
        previous = history[1] if len(history) > 1 else None

        if previous:
            prev_mcp = previous.get("pct_mcp_used", 0.0)
            curr_mcp = batch.metrics.pct_mcp_used

            # Req 15.1 and 15.2: MCP usage alerts
            if prev_mcp > 0:
                drop_pct = ((prev_mcp - curr_mcp) / prev_mcp) * 100
                if drop_pct > 10:
                    alerts.append(f"⚠️ CRÍTICO: MCP usage caiu {drop_pct:.1f}% vs anterior")
                elif drop_pct > 5:
                    alerts.append(f"⚡ AVISO: MCP usage caiu {drop_pct:.1f}% vs anterior")

        # Req 15.3: Alert vs baseline
        if baseline:
            base_correct = baseline.metrics.pct_correct_tool
            curr_correct = batch.metrics.pct_correct_tool
            if base_correct > 0:
                drop_pct = ((base_correct - curr_correct) / base_correct) * 100
                if drop_pct > 5:
                    alerts.append(f"📉 Correct tool caiu {drop_pct:.1f}% vs baseline")

        # Req 15.4: Performance alert when latency increases >20% vs rolling average of last 5
        history_5 = self.store.load_metrics_history(limit=5)
        if len(history_5) > 1:
            # Calculate rolling average of latency from last 5 batches (excluding current)
            past_latencies = [
                h.get("avg_latency_ms", 0.0) for h in history_5[1:]
                if h.get("avg_latency_ms", 0.0) > 0
            ]
            if past_latencies:
                avg_past_latency = sum(past_latencies) / len(past_latencies)
                curr_latency = batch.metrics.avg_latency_ms
                if avg_past_latency > 0 and curr_latency > 0:
                    increase_pct = ((curr_latency - avg_past_latency) / avg_past_latency) * 100
                    if increase_pct > 20:
                        alerts.append(
                            f"🐢 Performance: latência aumentou {increase_pct:.1f}% "
                            f"({curr_latency:.0f}ms vs média {avg_past_latency:.0f}ms)"
                        )

        # Req 15.6: Thresholds configuration section
        thresholds_html = '''
        <button class="thresholds-toggle" onclick="toggleThresholds()">
            Ver/Configurar Thresholds de Alerta
        </button>
        <div class="thresholds-config" id="thresholds-config">
            <h4>⚙️ Configuração de Thresholds de Alerta</h4>
            <div class="thresholds-grid">
                <div class="threshold-item warning">
                    <span class="threshold-label">MCP Usage - Aviso</span>
                    <span class="threshold-value">> 5% queda</span>
                    <span class="threshold-desc">Comparado com bateria anterior</span>
                </div>
                <div class="threshold-item critical">
                    <span class="threshold-label">MCP Usage - Crítico</span>
                    <span class="threshold-value">> 10% queda</span>
                    <span class="threshold-desc">Comparado com bateria anterior</span>
                </div>
                <div class="threshold-item warning">
                    <span class="threshold-label">Correct Tool</span>
                    <span class="threshold-value">> 5% queda</span>
                    <span class="threshold-desc">Comparado com baseline (se definido)</span>
                </div>
                <div class="threshold-item performance">
                    <span class="threshold-label">Latência</span>
                    <span class="threshold-value">> 20% aumento</span>
                    <span class="threshold-desc">Comparado com média das últimas 5 baterias</span>
                </div>
            </div>
        </div>
        <script>
            function toggleThresholds() {
                const config = document.getElementById('thresholds-config');
                config.classList.toggle('expanded');
            }
        </script>'''

        # Req 15.7: Green indicator when no alerts
        if not alerts:
            return f'''<div class="alert-section">
                <div class="alert-banner healthy">
                    ✓ Sistema saudável - nenhum alerta ativo
                </div>
                {thresholds_html}
            </div>'''

        # Determine severity
        has_critical = any("CRÍTICO" in a for a in alerts)
        banner_class = "critical" if has_critical else "warning"

        alerts_list = "<br>".join(alerts)
        return f'''<div class="alert-section">
            <div class="alert-banner {banner_class}">
                {alerts_list}
            </div>
            {thresholds_html}
        </div>'''

    def _render_batch_list(
        self,
        current_batch_id: str,
        compare_with_id: str | None = None,
    ) -> str:
        """Renderiza lista de baterias ordenada por data com suporte a comparação.

        Implements:
        - Req 10.1: Lista ordenada por data (mais recente primeiro)
        - Req 10.2: Mostrar batch_id, timestamp, version, totais, barra de progresso
        - Req 10.3: Carregar e exibir detalhes da bateria selecionada
        - Req 10.4: Destacar bateria mais recente como seleção padrão
        - Req 12.1: Permitir selecionar duas baterias para comparação lado-a-lado

        Args:
            current_batch_id: ID da bateria atualmente selecionada.
            compare_with_id: ID da bateria selecionada para comparação (opcional).

        Returns:
            HTML da lista de baterias com controles de comparação.
        """
        # Get all batches sorted by date (Req 10.1 - list_batches already sorts)
        batches = self.store.list_batches()

        if not batches:
            return '''<div class="section">
                <h2 class="section-title">📋 Baterias</h2>
                <div class="no-data">Nenhuma bateria disponível</div>
            </div>'''

        # Build comparison controls (Req 12.1)
        has_compare = compare_with_id is not None
        compare_mode_class = "compare-mode" if has_compare else ""
        compare_status_class = "active" if has_compare else ""
        compare_status_text = f"Comparando com: {compare_with_id[:20]}..." if has_compare else "Modo comparação desativado"

        compare_controls = f'''<div class="batch-controls">
            <div class="compare-toggle">
                <input type="checkbox" id="compare-mode-toggle" 
                       {"checked" if has_compare else ""} 
                       onchange="toggleCompareMode(this.checked)">
                <label for="compare-mode-toggle">🔀 Modo Comparação</label>
            </div>
            <span class="compare-status {compare_status_class}" id="compare-status">
                {compare_status_text}
            </span>
            <div class="compare-actions" id="compare-actions" style="display: {"flex" if has_compare else "none"};">
                <button class="compare-btn" onclick="clearCompareSelection()">Limpar</button>
            </div>
        </div>'''

        items: list[str] = []
        for i, batch_info in enumerate(batches):
            batch_id = batch_info.get("batch_id", "")
            timestamp_raw = batch_info.get("timestamp", "")
            version = batch_info.get("version", "unknown")
            summary = batch_info.get("summary", {})

            total = summary.get("total", 0)
            passed = summary.get("passed", 0)
            failed = summary.get("failed", 0)
            skipped = summary.get("skipped", 0)
            timeout = summary.get("timeout", 0)

            # Format timestamp as human readable (Req 10.2)
            try:
                dt = datetime.fromisoformat(timestamp_raw.replace("Z", "+00:00"))
                timestamp_display = dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, AttributeError):
                timestamp_display = timestamp_raw[:16] if timestamp_raw else "—"

            # Calculate pass rate for progress bar (Req 10.2)
            pass_rate = (passed / total * 100) if total > 0 else 0

            # Determine if this is the selected batch (Req 10.4)
            is_selected = batch_id == current_batch_id
            is_compare_selected = batch_id == compare_with_id
            # First batch is most recent (Req 10.4)
            is_most_recent = i == 0

            # Build class list
            item_classes = ["batch-item"]
            if is_selected:
                item_classes.append("selected")
            if is_compare_selected:
                item_classes.append("compare-selected")

            # Build badges for visual indication (Req 12.1)
            badges_html = ""
            if is_selected:
                badges_html += '<span class="compare-badge primary">Principal</span>'
            if is_compare_selected:
                badges_html += '<span class="compare-badge compare">Comparação</span>'

            # Build compare link (Req 12.1 - "Compare with..." button/link)
            compare_link_html = ""
            if not is_selected:
                link_selected_class = "selected" if is_compare_selected else ""
                compare_link_html = f'''<span class="batch-compare-link {link_selected_class}" 
                    onclick="event.stopPropagation(); selectForComparison('{html.escape(batch_id)}')"
                    title="Comparar com esta bateria">
                    {"✓ Selecionada" if is_compare_selected else "Comparar"}
                </span>'''

            # Build batch item HTML (Req 10.2, 12.1)
            item = f'''<div class="{" ".join(item_classes)}" 
                    data-batch-id="{html.escape(batch_id)}"
                    onclick="selectBatch('{html.escape(batch_id)}')">
                {badges_html}
                <div style="flex: 1;">
                    <div class="batch-id">
                        {html.escape(batch_id)}
                        {' <span style="color: var(--primary); font-size: 0.75rem;">(mais recente)</span>' if is_most_recent else ''}
                    </div>
                    <div class="batch-summary">
                        {timestamp_display} | v{html.escape(version)} | 
                        ✓{passed} ✗{failed} ⏱{timeout} ⊘{skipped}
                    </div>
                </div>
                <div style="display: flex; align-items: center; gap: 0.5rem;">
                    {compare_link_html}
                    <div style="width: 60px;">
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: {pass_rate:.0f}%;"></div>
                        </div>
                        <div style="font-size: 0.65rem; color: var(--text-muted); text-align: center; margin-top: 2px;">
                            {pass_rate:.0f}%
                        </div>
                    </div>
                </div>
            </div>'''
            items.append(item)

        return f'''<div class="section">
            <h2 class="section-title">📋 Baterias Executadas</h2>
            {compare_controls}
            <div class="batch-list {compare_mode_class}" id="batch-list">
                {"".join(items)}
            </div>
        </div>'''

    def _render_comparison(
        self,
        current: BatchResult,
        previous: BatchResult,
    ) -> str:
        """Renderiza seção de comparação entre baterias.

        Implements:
        - Req 12.2: Mostrar testes que melhoraram/regrediram
        - Req 12.3: Mostrar testes novos e removidos
        - Req 12.4: Calcular e exibir delta de métricas agregadas
        - Req 12.5: Colorir verde com seta ↑ quando melhora
        - Req 12.6: Colorir vermelho com seta ↓ quando piora
        - Req 12.7: Permitir exportar comparação como JSON

        Args:
            current: Bateria atual.
            previous: Bateria anterior para comparação.

        Returns:
            HTML da seção de comparação.
        """
        # Calculate deltas (Req 12.4)
        delta_mcp = current.metrics.pct_mcp_used - previous.metrics.pct_mcp_used
        delta_tool = current.metrics.pct_correct_tool - previous.metrics.pct_correct_tool
        delta_result = current.metrics.pct_correct_result - previous.metrics.pct_correct_result
        delta_latency = current.metrics.avg_latency_ms - previous.metrics.avg_latency_ms

        # Helper to format delta with color and arrows (Req 12.5, 12.6)
        # - Positive delta = improvement = green with ↑ (Req 12.5)
        # - Negative delta = degradation = red with ↓ (Req 12.6)
        # - For latency, LOWER is better, so we invert the logic
        def format_delta(value: float, invert: bool = False) -> str:
            """Format delta value with color and arrow indicator.

            Args:
                value: The delta value (positive or negative).
                invert: If True, invert the interpretation (used for latency
                       where lower is better, so positive delta = bad).

            Returns:
                HTML string with colored delta and directional arrow.
            """
            # For inverted metrics (like latency), positive delta is bad
            is_improvement = value > 0 if not invert else value < 0
            is_degradation = value < 0 if not invert else value > 0

            if is_improvement:
                # Req 12.5: positive (improvement) in green with arrow up
                arrow = "↑"
                css_class = "positive"
                display_value = f"+{abs(value):.1f}"
            elif is_degradation:
                # Req 12.6: negative (degradation) in red with arrow down
                arrow = "↓"
                css_class = "negative"
                display_value = f"-{abs(value):.1f}"
            else:
                # No change
                arrow = "→"
                css_class = "neutral"
                display_value = "0"

            return f'<span class="delta {css_class}">{arrow} {display_value}</span>'

        # Find regressions and improvements (Req 12.2)
        # Find new and removed tests (Req 12.3)
        current_results = {tr.test_id: tr.status for tr in current.test_results}
        previous_results = {tr.test_id: tr.status for tr in previous.test_results}

        regressions: list[str] = []
        improvements: list[str] = []
        new_tests: list[str] = []
        removed_tests: list[str] = []

        for test_id, status in current_results.items():
            if test_id not in previous_results:
                new_tests.append(test_id)
            elif previous_results[test_id] == "pass" and status != "pass":
                regressions.append(test_id)
            elif previous_results[test_id] != "pass" and status == "pass":
                improvements.append(test_id)

        for test_id in previous_results:
            if test_id not in current_results:
                removed_tests.append(test_id)

        # Helper to render a diff section with expandable content
        def render_diff_section(
            tests: list[str],
            title: str,
            icon: str,
            bg_color: str,
            text_color: str,
            description: str,
        ) -> str:
            if not tests:
                return ""

            count = len(tests)
            visible_limit = 10
            has_more = count > visible_limit

            # Render visible items
            visible_items = "<br>".join(
                f"• {html.escape(t)}" for t in tests[:visible_limit]
            )

            if has_more:
                # Render as expandable details element
                hidden_items = "<br>".join(
                    f"• {html.escape(t)}" for t in tests[visible_limit:]
                )
                return f'''
            <div style="background: {bg_color}; color: {text_color}; padding: 0.75rem; border-radius: 4px; margin-top: 0.5rem;">
                <strong>{icon} {title} ({count}):</strong> <span style="font-size: 0.85em; font-weight: normal;">{description}</span><br>
                {visible_items}
                <details style="margin-top: 0.5rem;">
                    <summary style="cursor: pointer; font-size: 0.875rem; color: {text_color}; opacity: 0.8;">
                        Mostrar mais {count - visible_limit} itens...
                    </summary>
                    <div style="margin-top: 0.5rem;">
                        {hidden_items}
                    </div>
                </details>
            </div>'''
            else:
                return f'''
            <div style="background: {bg_color}; color: {text_color}; padding: 0.75rem; border-radius: 4px; margin-top: 0.5rem;">
                <strong>{icon} {title} ({count}):</strong> <span style="font-size: 0.85em; font-weight: normal;">{description}</span><br>
                {visible_items}
            </div>'''

        # Build comparison data for JSON export (Req 12.7)
        comparison_data = {
            "current_batch_id": current.batch_id,
            "previous_batch_id": previous.batch_id,
            "current_timestamp": current.timestamp,
            "previous_timestamp": previous.timestamp,
            "metrics": {
                "delta_pct_mcp_used": round(delta_mcp, 2),
                "delta_pct_correct_tool": round(delta_tool, 2),
                "delta_pct_correct_result": round(delta_result, 2),
                "delta_avg_latency_ms": round(delta_latency, 2),
                "current": {
                    "pct_mcp_used": round(current.metrics.pct_mcp_used, 2),
                    "pct_correct_tool": round(current.metrics.pct_correct_tool, 2),
                    "pct_correct_result": round(current.metrics.pct_correct_result, 2),
                    "avg_latency_ms": round(current.metrics.avg_latency_ms, 2),
                },
                "previous": {
                    "pct_mcp_used": round(previous.metrics.pct_mcp_used, 2),
                    "pct_correct_tool": round(previous.metrics.pct_correct_tool, 2),
                    "pct_correct_result": round(previous.metrics.pct_correct_result, 2),
                    "avg_latency_ms": round(previous.metrics.avg_latency_ms, 2),
                },
            },
            "test_changes": {
                "regressions": regressions,
                "improvements": improvements,
                "new_tests": new_tests,
                "removed_tests": removed_tests,
            },
            "summary": {
                "total_regressions": len(regressions),
                "total_improvements": len(improvements),
                "total_new_tests": len(new_tests),
                "total_removed_tests": len(removed_tests),
            },
        }
        comparison_json = json.dumps(comparison_data, indent=2, ensure_ascii=False)

        # Build HTML
        comparison_html = f'''<div class="section" id="comparison-section">
            <h2 class="section-title">
                📊 Comparação: {html.escape(current.batch_id)} vs {html.escape(previous.batch_id)}
                <button class="export-json-btn" onclick="exportComparisonJSON()" title="Exportar comparação como JSON (Req 12.7)">
                    📥 Exportar JSON
                </button>
            </h2>
            <script id="comparison-data" type="application/json">{html.escape(comparison_json)}</script>
            <div class="comparison-grid">
                <div class="comparison-card">
                    <h4>Δ MCP Used</h4>
                    <div class="delta-value">{format_delta(delta_mcp)}%</div>
                </div>
                <div class="comparison-card">
                    <h4>Δ Correct Tool</h4>
                    <div class="delta-value">{format_delta(delta_tool)}%</div>
                </div>
                <div class="comparison-card">
                    <h4>Δ Correct Result</h4>
                    <div class="delta-value">{format_delta(delta_result)}%</div>
                </div>
                <div class="comparison-card">
                    <h4>Δ Latency</h4>
                    <div class="delta-value">{format_delta(delta_latency, invert=True)}ms</div>
                </div>
            </div>'''

        # Regressions in RED (Req 12.2) - tests that broke
        comparison_html += render_diff_section(
            tests=regressions,
            title="Regressões",
            icon="⚠️",
            bg_color="#fee2e2",
            text_color="#991b1b",
            description="testes que quebraram (passavam → falharam)",
        )

        # Improvements in GREEN (Req 12.2) - tests that started working
        comparison_html += render_diff_section(
            tests=improvements,
            title="Melhorias",
            icon="✓",
            bg_color="#dcfce7",
            text_color="#166534",
            description="testes que passaram a funcionar (falhavam → passaram)",
        )

        # New tests in INFO/NEUTRAL color (Req 12.3)
        comparison_html += render_diff_section(
            tests=new_tests,
            title="Novos Testes",
            icon="➕",
            bg_color="#dbeafe",
            text_color="#1e40af",
            description="testes adicionados nesta bateria",
        )

        # Removed tests in WARNING color (Req 12.3)
        comparison_html += render_diff_section(
            tests=removed_tests,
            title="Testes Removidos",
            icon="➖",
            bg_color="#fef3c7",
            text_color="#92400e",
            description="testes que não existem mais",
        )

        comparison_html += "</div>"
        return comparison_html

    def _render_trend_charts(self) -> str:
        """Renderiza placeholders para gráficos de tendência com seletor de período.

        Os dados são injetados via JavaScript no _render_chart_scripts().

        Implements:
        - Req 13.5: Permitir selecionar período: 5, 10, 20, ou todas as baterias

        Returns:
            HTML com containers para os gráficos e seletor de período.
        """
        return '''<div class="section">
            <h2 class="section-title">
                📈 Tendências
                <div class="period-selector" style="display: inline-flex; margin-left: 1rem; gap: 0.25rem;">
                    <button class="period-btn" data-period="5" onclick="updateChartPeriod(5)">5</button>
                    <button class="period-btn" data-period="10" onclick="updateChartPeriod(10)">10</button>
                    <button class="period-btn active" data-period="20" onclick="updateChartPeriod(20)">20</button>
                    <button class="period-btn" data-period="all" onclick="updateChartPeriod('all')">Todas</button>
                </div>
            </h2>
            <div class="charts-grid">
                <div class="chart-container">
                    <div class="chart-title">MCP Usage (%)</div>
                    <div class="chart-wrapper">
                        <canvas id="chart-mcp-usage"></canvas>
                    </div>
                </div>
                <div class="chart-container">
                    <div class="chart-title">Correct Tool (%)</div>
                    <div class="chart-wrapper">
                        <canvas id="chart-correct-tool"></canvas>
                    </div>
                </div>
                <div class="chart-container">
                    <div class="chart-title">Correct Result (%)</div>
                    <div class="chart-wrapper">
                        <canvas id="chart-correct-result"></canvas>
                    </div>
                </div>
                <div class="chart-container">
                    <div class="chart-title">Average Latency (ms)</div>
                    <div class="chart-wrapper">
                        <canvas id="chart-latency"></canvas>
                    </div>
                </div>
            </div>
        </div>'''

    def _render_chart_scripts(
        self,
        batch: BatchResult,
        compare_with: str | None = None,
    ) -> str:
        """Renderiza scripts JavaScript para inicializar gráficos Chart.js.

        Implements:
        - Req 13.1-13.4: Gráficos de linha para cada métrica
        - Req 13.5: Permitir selecionar período: 5, 10, 20, ou todas as baterias
        - Req 13.6: Linha horizontal de baseline sempre visível na legenda;
                    quando baseline não está definido, legenda mostra "não definido"
        - Req 13.8: Tooltips com valores exatos
        - Req 12.1: JavaScript para seleção de baterias para comparação

        Args:
            batch: Bateria atual sendo exibida.
            compare_with: ID da bateria selecionada para comparação (opcional).

        Returns:
            HTML com scripts para Chart.js e interatividade de comparação.
        """
        # Load ALL history for charts (Req 13.5: support all periods including "all")
        all_history = self.store.load_metrics_history(limit=None)

        # Reverse to show oldest first (left to right)
        all_history = list(reversed(all_history))

        # Extract data for charts (all data)
        all_labels = [h.get("batch_id", "")[:15] for h in all_history]
        all_mcp_data = [h.get("pct_mcp_used", 0) for h in all_history]
        all_tool_data = [h.get("pct_correct_tool", 0) for h in all_history]
        all_result_data = [h.get("pct_correct_result", 0) for h in all_history]
        all_latency_data = [h.get("avg_latency_ms", 0) for h in all_history]

        # Get baseline for reference line (Req 13.6)
        # Baseline legend is ALWAYS shown; when no baseline, shows "não definido"
        baseline = self.store.get_baseline()
        baseline_mcp = baseline.metrics.pct_mcp_used if baseline else None
        baseline_tool = baseline.metrics.pct_correct_tool if baseline else None
        baseline_result = baseline.metrics.pct_correct_result if baseline else None
        baseline_latency = baseline.metrics.avg_latency_ms if baseline else None
        has_baseline = baseline is not None

        return f'''<script>
        // ===== Batch Comparison State (Req 12.1) =====
        let currentBatchId = "{batch.batch_id}";
        let compareBatchId = {f'"{compare_with}"' if compare_with else 'null'};
        let compareModeEnabled = {str(compare_with is not None).lower()};
        
        /**
         * Toggle comparison mode on/off (Req 12.1)
         * @param {{boolean}} enabled - Whether comparison mode is enabled
         */
        function toggleCompareMode(enabled) {{
            compareModeEnabled = enabled;
            const batchList = document.getElementById('batch-list');
            const compareActions = document.getElementById('compare-actions');
            const compareStatus = document.getElementById('compare-status');
            
            if (enabled) {{
                batchList.classList.add('compare-mode');
                compareActions.style.display = 'flex';
                if (compareBatchId) {{
                    compareStatus.textContent = 'Comparando com: ' + compareBatchId.substring(0, 20) + '...';
                    compareStatus.classList.add('active');
                }} else {{
                    compareStatus.textContent = 'Selecione uma bateria para comparar';
                    compareStatus.classList.remove('active');
                }}
            }} else {{
                batchList.classList.remove('compare-mode');
                compareActions.style.display = 'none';
                compareStatus.textContent = 'Modo comparação desativado';
                compareStatus.classList.remove('active');
                clearCompareSelection();
            }}
        }}
        
        /**
         * Select a batch for comparison (Req 12.1)
         * Loads a new page with comparison data
         * @param {{string}} batchId - Batch ID to compare with
         */
        function selectForComparison(batchId) {{
            if (batchId === currentBatchId) {{
                alert('Não é possível comparar uma bateria consigo mesma');
                return;
            }}
            
            // Enable compare mode if not already enabled
            const toggleCheckbox = document.getElementById('compare-mode-toggle');
            if (toggleCheckbox && !toggleCheckbox.checked) {{
                toggleCheckbox.checked = true;
                toggleCompareMode(true);
            }}
            
            compareBatchId = batchId;
            
            // Update visual indication
            document.querySelectorAll('.batch-item').forEach(item => {{
                item.classList.remove('compare-selected');
                const badge = item.querySelector('.compare-badge.compare');
                if (badge) badge.remove();
            }});
            
            document.querySelectorAll('.batch-compare-link').forEach(link => {{
                link.classList.remove('selected');
                link.textContent = 'Comparar';
            }});
            
            const selectedItem = document.querySelector(`.batch-item[data-batch-id="${{batchId}}"]`);
            if (selectedItem) {{
                selectedItem.classList.add('compare-selected');
                const badge = document.createElement('span');
                badge.className = 'compare-badge compare';
                badge.textContent = 'Comparação';
                selectedItem.appendChild(badge);
                
                const compareLink = selectedItem.querySelector('.batch-compare-link');
                if (compareLink) {{
                    compareLink.classList.add('selected');
                    compareLink.textContent = '✓ Selecionada';
                }}
            }}
            
            // Update status
            const compareStatus = document.getElementById('compare-status');
            compareStatus.textContent = 'Comparando com: ' + batchId.substring(0, 20) + '...';
            compareStatus.classList.add('active');
            
            // Reload page with comparison parameter
            const url = new URL(window.location.href);
            url.searchParams.set('compare', batchId);
            window.location.href = url.toString();
        }}
        
        /**
         * Clear comparison selection (Req 12.1)
         */
        function clearCompareSelection() {{
            compareBatchId = null;
            
            // Update visual indication
            document.querySelectorAll('.batch-item').forEach(item => {{
                item.classList.remove('compare-selected');
                const badge = item.querySelector('.compare-badge.compare');
                if (badge) badge.remove();
            }});
            
            document.querySelectorAll('.batch-compare-link').forEach(link => {{
                link.classList.remove('selected');
                link.textContent = 'Comparar';
            }});
            
            // Update status
            const compareStatus = document.getElementById('compare-status');
            if (compareModeEnabled) {{
                compareStatus.textContent = 'Selecione uma bateria para comparar';
            }} else {{
                compareStatus.textContent = 'Modo comparação desativado';
            }}
            compareStatus.classList.remove('active');
            
            // Reload page without comparison parameter
            const url = new URL(window.location.href);
            url.searchParams.delete('compare');
            window.location.href = url.toString();
        }}
        
        /**
         * Export comparison data as JSON file (Req 12.7)
         * Downloads a JSON file with the comparison data for external analysis.
         */
        function exportComparisonJSON() {{
            const dataScript = document.getElementById('comparison-data');
            if (!dataScript) {{
                alert('Dados de comparação não disponíveis');
                return;
            }}
            
            try {{
                const data = JSON.parse(dataScript.textContent);
                const jsonStr = JSON.stringify(data, null, 2);
                
                // Create filename with batch IDs
                const filename = `comparison_${{data.current_batch_id}}_vs_${{data.previous_batch_id}}.json`;
                
                // Create download link
                const blob = new Blob([jsonStr], {{ type: 'application/json' }});
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            }} catch (e) {{
                console.error('Erro ao exportar JSON:', e);
                alert('Erro ao exportar comparação: ' + e.message);
            }}
        }}
        
        /**
         * Select a batch as the main/primary batch
         * @param {{string}} batchId - Batch ID to select
         */
        function selectBatch(batchId) {{
            if (batchId === currentBatchId) return;
            
            // Keep compare parameter if set
            const url = new URL(window.location.href);
            url.searchParams.set('batch', batchId);
            window.location.href = url.toString();
        }}
        
        // ===== Chart Data and Period Selection (Req 13.5) =====
        
        // Store ALL data for different period selections
        const allChartData = {{
            labels: {json.dumps(all_labels)},
            mcp: {json.dumps(all_mcp_data)},
            tool: {json.dumps(all_tool_data)},
            result: {json.dumps(all_result_data)},
            latency: {json.dumps(all_latency_data)}
        }};
        
        // Baseline values (Req 13.6)
        const baselineValues = {{
            mcp: {baseline_mcp if baseline_mcp is not None else 'null'},
            tool: {baseline_tool if baseline_tool is not None else 'null'},
            result: {baseline_result if baseline_result is not None else 'null'},
            latency: {baseline_latency if baseline_latency is not None else 'null'}
        }};
        const hasBaseline = {str(has_baseline).lower()};
        
        // Current period selection (default: 20)
        let currentPeriod = 20;
        
        // Store chart instances globally for updates
        let chartInstances = {{}};
        
        /**
         * Get data sliced to the specified period (Req 13.5)
         * @param {{number|string}} period - Number of batches or 'all'
         * @returns {{object}} Sliced data for all metrics
         */
        function getDataForPeriod(period) {{
            const totalBatches = allChartData.labels.length;
            
            if (period === 'all' || period >= totalBatches) {{
                return {{
                    labels: allChartData.labels,
                    mcp: allChartData.mcp,
                    tool: allChartData.tool,
                    result: allChartData.result,
                    latency: allChartData.latency,
                    count: totalBatches
                }};
            }}
            
            // Slice to get the most recent N batches (from the end)
            const start = Math.max(0, totalBatches - period);
            return {{
                labels: allChartData.labels.slice(start),
                mcp: allChartData.mcp.slice(start),
                tool: allChartData.tool.slice(start),
                result: allChartData.result.slice(start),
                latency: allChartData.latency.slice(start),
                count: period
            }};
        }}
        
        /**
         * Creates baseline dataset configuration (Req 13.6)
         * Always shows in legend; shows horizontal line only when baseline is defined.
         * When no baseline, legend shows "Baseline: não definido" in muted gray.
         * @param {{number|null}} baselineValue - The baseline value, or null if not defined
         * @param {{number}} numPoints - Number of data points for the baseline line
         * @returns {{object}} Chart.js dataset configuration for baseline
         */
        function createBaselineDataset(baselineValue, numPoints) {{
            if (baselineValue !== null) {{
                // Baseline defined: show active horizontal line
                return {{
                    label: `Baseline: ${{baselineValue.toFixed(1)}}`,
                    data: Array(numPoints).fill(baselineValue),
                    borderColor: '#94a3b8',
                    borderDash: [5, 5],
                    borderWidth: 2,
                    pointRadius: 0,
                    pointHoverRadius: 0,
                    fill: false,
                    tension: 0
                }};
            }} else {{
                // No baseline: show placeholder in legend with inactive styling
                return {{
                    label: 'Baseline: não definido',
                    data: [],  // Empty data, no line drawn
                    borderColor: '#d1d5db',  // Muted gray
                    borderDash: [5, 5],
                    borderWidth: 1,
                    pointRadius: 0,
                    fill: false,
                    hidden: false  // Show in legend even though no data
                }};
            }}
        }}
        
        /**
         * Update chart period selection (Req 13.5)
         * @param {{number|string}} period - 5, 10, 20, or 'all'
         */
        function updateChartPeriod(period) {{
            currentPeriod = period;
            
            // Update button states
            document.querySelectorAll('.period-btn').forEach(btn => {{
                const btnPeriod = btn.getAttribute('data-period');
                const isActive = (btnPeriod === String(period)) || (btnPeriod === 'all' && period === 'all');
                btn.classList.toggle('active', isActive);
            }});
            
            // Get data for selected period
            const periodData = getDataForPeriod(period);
            
            // Update each chart
            updateChartData('chart-mcp-usage', periodData.labels, periodData.mcp, baselineValues.mcp, periodData.count);
            updateChartData('chart-correct-tool', periodData.labels, periodData.tool, baselineValues.tool, periodData.count);
            updateChartData('chart-correct-result', periodData.labels, periodData.result, baselineValues.result, periodData.count);
            updateChartData('chart-latency', periodData.labels, periodData.latency, baselineValues.latency, periodData.count);
        }}
        
        /**
         * Update a single chart with new data
         * @param {{string}} chartId - Canvas element ID
         * @param {{array}} labels - X-axis labels
         * @param {{array}} data - Y-axis data
         * @param {{number|null}} baselineValue - Baseline value
         * @param {{number}} numPoints - Number of data points
         */
        function updateChartData(chartId, labels, data, baselineValue, numPoints) {{
            const chart = chartInstances[chartId];
            if (!chart) return;
            
            // Update labels
            chart.data.labels = labels;
            
            // Update main data series (first dataset)
            chart.data.datasets[0].data = data;
            
            // Update baseline dataset (second dataset)
            const baselineDataset = createBaselineDataset(baselineValue, numPoints);
            chart.data.datasets[1] = baselineDataset;
            
            // Refresh the chart
            chart.update('none');  // 'none' disables animation for smoother updates
        }}
        
        // Chart.js configuration (Req 13.6, 13.8)
        // Legend is ALWAYS shown to display baseline status
        const chartOptions = {{
            responsive: true,
            maintainAspectRatio: false,
            plugins: {{
                legend: {{ 
                    display: true,
                    position: 'bottom',
                    labels: {{
                        usePointStyle: true,
                        padding: 15,
                        font: {{ size: 11 }}
                    }}
                }},
                tooltip: {{
                    mode: 'index',
                    intersect: false,
                }}
            }},
            scales: {{
                y: {{ beginAtZero: false }}
            }}
        }};
        
        // Initialize with default period (20 batches)
        const initialData = getDataForPeriod(20);
        
        // MCP Usage chart (Req 13.1, 13.6)
        chartInstances['chart-mcp-usage'] = new Chart(document.getElementById('chart-mcp-usage'), {{
            type: 'line',
            data: {{
                labels: initialData.labels,
                datasets: [
                    {{
                        label: 'MCP Usage %',
                        data: initialData.mcp,
                        borderColor: '#06b6d4',
                        backgroundColor: 'rgba(6, 182, 212, 0.1)',
                        fill: true,
                        tension: 0.3
                    }},
                    createBaselineDataset(baselineValues.mcp, initialData.count)
                ]
            }},
            options: chartOptions
        }});
        
        // Correct Tool chart (Req 13.2, 13.6)
        chartInstances['chart-correct-tool'] = new Chart(document.getElementById('chart-correct-tool'), {{
            type: 'line',
            data: {{
                labels: initialData.labels,
                datasets: [
                    {{
                        label: 'Correct Tool %',
                        data: initialData.tool,
                        borderColor: '#3b82f6',
                        backgroundColor: 'rgba(59, 130, 246, 0.1)',
                        fill: true,
                        tension: 0.3
                    }},
                    createBaselineDataset(baselineValues.tool, initialData.count)
                ]
            }},
            options: chartOptions
        }});
        
        // Correct Result chart (Req 13.3, 13.6)
        chartInstances['chart-correct-result'] = new Chart(document.getElementById('chart-correct-result'), {{
            type: 'line',
            data: {{
                labels: initialData.labels,
                datasets: [
                    {{
                        label: 'Correct Result %',
                        data: initialData.result,
                        borderColor: '#22c55e',
                        backgroundColor: 'rgba(34, 197, 94, 0.1)',
                        fill: true,
                        tension: 0.3
                    }},
                    createBaselineDataset(baselineValues.result, initialData.count)
                ]
            }},
            options: chartOptions
        }});
        
        // Latency chart (Req 13.4, 13.6)
        chartInstances['chart-latency'] = new Chart(document.getElementById('chart-latency'), {{
            type: 'line',
            data: {{
                labels: initialData.labels,
                datasets: [
                    {{
                        label: 'Avg Latency (ms)',
                        data: initialData.latency,
                        borderColor: '#8b5cf6',
                        backgroundColor: 'rgba(139, 92, 246, 0.1)',
                        fill: true,
                        tension: 0.3
                    }},
                    createBaselineDataset(baselineValues.latency, initialData.count)
                ]
            }},
            options: chartOptions
        }});
        
        // ===== Filter Functions (Req 11.4, 11.5, 11.6) =====
        
        /**
         * Filter rows by status (Req 11.4)
         * @param {{string}} status - Status to filter by ('all', 'pass', 'fail', 'timeout', 'skip')
         * @param {{NodeList}} rows - Test rows to filter
         * @returns {{Set}} Set of row IDs that match the status filter
         */
        function filterByStatus(status, rows) {{
            const matching = new Set();
            rows.forEach(row => {{
                const rowStatus = row.getAttribute('data-status');
                if (status === 'all' || rowStatus === status) {{
                    matching.add(row.getAttribute('data-row-id'));
                }}
            }});
            return matching;
        }}
        
        /**
         * Filter rows by query text (case-insensitive) (Req 11.5)
         * @param {{string}} searchText - Text to search for
         * @param {{NodeList}} rows - Test rows to filter
         * @returns {{Set}} Set of row IDs that match the query search
         */
        function filterByQuery(searchText, rows) {{
            const matching = new Set();
            const search = searchText.toLowerCase().trim();
            rows.forEach(row => {{
                const query = row.getAttribute('data-query') || '';
                if (search === '' || query.includes(search)) {{
                    matching.add(row.getAttribute('data-row-id'));
                }}
            }});
            return matching;
        }}
        
        /**
         * Filter rows by tags (Req 11.6)
         * Shows rows matching any selected tag (OR logic)
         * @param {{Array<string>}} selectedTags - List of selected tags
         * @param {{NodeList}} rows - Test rows to filter
         * @returns {{Set}} Set of row IDs that match any selected tag
         */
        function filterByTags(selectedTags, rows) {{
            const matching = new Set();
            rows.forEach(row => {{
                const tagsStr = row.getAttribute('data-tags') || '';
                const rowTags = tagsStr ? tagsStr.split(',') : [];
                
                // If no tags selected, match all rows
                if (selectedTags.length === 0) {{
                    matching.add(row.getAttribute('data-row-id'));
                }} else {{
                    // Match if row has any of the selected tags (OR logic)
                    const hasMatch = selectedTags.some(tag => rowTags.includes(tag));
                    if (hasMatch) {{
                        matching.add(row.getAttribute('data-row-id'));
                    }}
                }}
            }});
            return matching;
        }}
        
        /**
         * Filter rows by tool group (Req 14.4)
         * Shows rows matching the selected group
         * @param {{string}} group - Selected group name
         * @param {{NodeList}} rows - Test rows to filter
         * @returns {{Set}} Set of row IDs that match the group
         */
        function filterByGroup(group, rows) {{
            const matching = new Set();
            rows.forEach(row => {{
                const rowGroup = row.getAttribute('data-group') || 'other';
                
                // If no group selected (empty string), match all rows
                if (!group || rowGroup === group) {{
                    matching.add(row.getAttribute('data-row-id'));
                }}
            }});
            return matching;
        }}
        
        // Track currently selected group for filtering (Req 14.4)
        let selectedGroup = '';
        
        /**
         * Handle click on metrics card to filter by group (Req 14.4)
         * @param {{string}} group - Group name to filter by
         */
        function filterByGroupClick(group) {{
            // Toggle selection: if same group clicked, deselect
            if (selectedGroup === group) {{
                selectedGroup = '';
            }} else {{
                selectedGroup = group;
            }}
            
            // Update card visual states
            document.querySelectorAll('.metrics-card[data-group]').forEach(card => {{
                const cardGroup = card.getAttribute('data-group');
                card.classList.toggle('active', cardGroup === selectedGroup);
            }});
            
            // Scroll to test table
            const testTable = document.getElementById('test-table');
            if (testTable && selectedGroup) {{
                testTable.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
            }}
            
            // Re-apply all filters including group filter
            applyFilters();
        }}
        
        /**
         * Apply all filters with AND logic between filter types
         * (row must match all filter criteria to be shown)
         */
        function applyFilters() {{
            const statusFilter = document.getElementById('status-filter');
            const queryFilter = document.getElementById('query-filter');
            const tagCheckboxes = document.querySelectorAll('.tag-filter input[type="checkbox"]:checked');
            
            const status = statusFilter ? statusFilter.value : 'all';
            const searchText = queryFilter ? queryFilter.value : '';
            const selectedTags = Array.from(tagCheckboxes).map(cb => cb.value);
            
            // Get all test rows (excluding detail rows)
            const testRows = document.querySelectorAll('tr.test-row');
            
            // Get matching row IDs from each filter
            const statusMatches = filterByStatus(status, testRows);
            const queryMatches = filterByQuery(searchText, testRows);
            const tagMatches = filterByTags(selectedTags, testRows);
            const groupMatches = filterByGroup(selectedGroup, testRows);
            
            // Apply AND logic: row must be in all matching sets
            let visibleCount = 0;
            testRows.forEach(row => {{
                const rowId = row.getAttribute('data-row-id');
                const isVisible = statusMatches.has(rowId) && queryMatches.has(rowId) && tagMatches.has(rowId) && groupMatches.has(rowId);
                
                // Show/hide test row
                row.classList.toggle('hidden', !isVisible);
                
                // Also show/hide corresponding detail row
                const detailRow = document.querySelector(`tr.detail-row[data-detail-for="${{rowId}}"]`);
                if (detailRow) {{
                    detailRow.classList.toggle('hidden', !isVisible);
                }}
                
                if (isVisible) visibleCount++;
            }});
            
            // Update filter count display
            const filterCount = document.getElementById('filter-count');
            if (filterCount) {{
                const total = testRows.length;
                filterCount.textContent = `Mostrando ${{visibleCount}} de ${{total}} testes`;
            }}
            
            // Update tag checkbox styling
            document.querySelectorAll('.tag-checkbox').forEach(label => {{
                const checkbox = label.querySelector('input[type="checkbox"]');
                label.classList.toggle('active', checkbox && checkbox.checked);
            }});
        }}
        
        /**
         * Reset all filters to their default values
         */
        function resetFilters() {{
            // Reset status filter
            const statusFilter = document.getElementById('status-filter');
            if (statusFilter) statusFilter.value = 'all';
            
            // Reset query search
            const queryFilter = document.getElementById('query-filter');
            if (queryFilter) queryFilter.value = '';
            
            // Uncheck all tag checkboxes
            document.querySelectorAll('.tag-filter input[type="checkbox"]').forEach(cb => {{
                cb.checked = false;
            }});
            
            // Reset group filter (Req 14.4)
            selectedGroup = '';
            document.querySelectorAll('.metrics-card[data-group]').forEach(card => {{
                card.classList.remove('active');
            }});
            
            // Re-apply filters (will show all rows)
            applyFilters();
        }}
        
        // Initialize filter count on page load
        document.addEventListener('DOMContentLoaded', function() {{
            applyFilters();
        }});
    </script>'''

    def _render_metrics_by_group(
        self,
        batch: BatchResult,
        comparison_batch: BatchResult | None = None,
    ) -> str:
        """Renderiza seção de métricas por grupo de tools.

        Implements:
        - Req 14.1: Métricas por grupo (bridge, deck, docs, etc.)
        - Req 14.2: Mostrar total, pct_pass, pct_mcp_used, etc.
        - Req 14.4: Permitir clicar em grupo para filtrar tabela
        - Req 14.6: Destacar apenas o valor específico em vermelho quando >10% piora

        Args:
            batch: Bateria com métricas por grupo.
            comparison_batch: Bateria para comparação (opcional).

        Returns:
            HTML da seção de métricas por grupo.
        """
        if not batch.metrics_by_group:
            return '''<div class="section">
                <h2 class="section-title">📁 Métricas por Grupo</h2>
                <div class="no-data">Nenhuma métrica por grupo disponível</div>
            </div>'''

        # Build comparison data if available (for degradation detection, Req 14.6)
        comparison_group_metrics: dict[str, dict[str, float]] = {}
        if comparison_batch and comparison_batch.metrics_by_group:
            for group_name, group_metrics in comparison_batch.metrics_by_group.items():
                comparison_group_metrics[group_name] = {
                    "pct_pass": group_metrics.pct_pass,
                    "pct_mcp_used": group_metrics.pct_mcp_used,
                    "pct_correct_tool": group_metrics.pct_correct_tool,
                    "avg_latency_ms": group_metrics.avg_latency_ms,
                }

        def is_degraded(current: float, previous: float | None, invert: bool = False) -> bool:
            """Check if metric degraded by more than 10%.

            For normal metrics (pass rate, mcp usage, correct tool):
                degradation = current < previous by >10%

            For inverted metrics (latency):
                degradation = current > previous by >10%

            Args:
                current: Current metric value.
                previous: Previous metric value (None if no comparison).
                invert: If True, higher is worse (for latency).

            Returns:
                True if degraded by more than 10%.
            """
            if previous is None or previous == 0:
                return False
            if invert:
                # For latency: higher is worse
                if previous > 0:
                    degradation_pct = ((current - previous) / previous) * 100
                    return degradation_pct > 10
            else:
                # For percentages: lower is worse
                degradation_pct = ((previous - current) / previous) * 100
                return degradation_pct > 10
            return False

        def format_metric_value(
            value: float,
            fmt: str,
            prev_value: float | None,
            invert: bool = False,
        ) -> str:
            """Format metric value with degradation highlighting (Req 14.6).

            Args:
                value: Current metric value.
                fmt: Format string for the value.
                prev_value: Previous value for comparison.
                invert: If True, higher is worse (for latency).

            Returns:
                HTML span with .degraded class if degraded by >10%.
            """
            formatted = fmt.format(value)
            if is_degraded(value, prev_value, invert):
                return f'<span class="metric-value degraded">{formatted}</span>'
            return f'<span class="metric-value">{formatted}</span>'

        cards: list[str] = []
        for group, metrics in sorted(batch.metrics_by_group.items()):
            # Get previous metrics for comparison (Req 14.6)
            prev = comparison_group_metrics.get(group, {})
            prev_pass = prev.get("pct_pass")
            prev_mcp = prev.get("pct_mcp_used")
            prev_tool = prev.get("pct_correct_tool")
            prev_latency = prev.get("avg_latency_ms")

            # Req 14.4: Add click handler and data-group attribute for filtering
            group_escaped = html.escape(group)

            # Format values with degradation highlighting (Req 14.6)
            pass_value = format_metric_value(metrics.pct_pass, "{:.1f}%", prev_pass)
            mcp_value = format_metric_value(metrics.pct_mcp_used, "{:.1f}%", prev_mcp)
            tool_value = format_metric_value(metrics.pct_correct_tool, "{:.1f}%", prev_tool)
            latency_value = format_metric_value(
                metrics.avg_latency_ms, "{:.0f}ms", prev_latency, invert=True
            )

            card = f'''<div class="metrics-card" data-group="{group_escaped}" onclick="filterByGroupClick('{group_escaped}')" title="Clique para filtrar testes do grupo {group_escaped}">
                <h4>{group_escaped}</h4>
                <div class="metric-row">
                    <span class="metric-label">Total</span>
                    <span class="metric-value">{metrics.total}</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Pass Rate</span>
                    {pass_value}
                </div>
                <div class="metric-row">
                    <span class="metric-label">MCP Used</span>
                    {mcp_value}
                </div>
                <div class="metric-row">
                    <span class="metric-label">Correct Tool</span>
                    {tool_value}
                </div>
                <div class="metric-row">
                    <span class="metric-label">Avg Latency</span>
                    {latency_value}
                </div>
            </div>'''
            cards.append(card)

        return f'''<div class="section">
            <h2 class="section-title">📁 Métricas por Grupo <small style="font-size: 0.75rem; color: var(--text-muted); font-weight: normal;">(clique para filtrar)</small></h2>
            <div class="metrics-grid">
                {"".join(cards)}
            </div>
        </div>'''

    def _render_metrics_by_tag(
        self,
        batch: BatchResult,
        comparison_batch: BatchResult | None = None,
    ) -> str:
        """Renderiza seção de métricas por tag.

        Implements:
        - Req 14.3: Métricas agregadas por tag
        - Req 14.5: Mostrar delta de métricas por tag quando comparando baterias
        - Req 14.7: Mostrar indicador de tendência (↑ ↓ →) para cada tag

        Args:
            batch: Bateria com métricas por tag.
            comparison_batch: Bateria para comparação (opcional).

        Returns:
            HTML da seção de métricas por tag.
        """
        if not batch.metrics_by_tag:
            return '''<div class="section">
                <h2 class="section-title">🏷️ Métricas por Tag</h2>
                <div class="no-data">Nenhuma métrica por tag disponível</div>
            </div>'''

        # Load historical data for trend calculation (Req 14.7)
        history = self.store.load_metrics_history(limit=5)

        # Calculate historical averages per tag for trends
        tag_history: dict[str, list[dict[str, float]]] = {}
        for record in history:
            metrics_by_tag = record.get("metrics_by_tag", {})
            for tag_name, tag_metrics in metrics_by_tag.items():
                if tag_name not in tag_history:
                    tag_history[tag_name] = []
                total = tag_metrics.get("total", 0)
                if total > 0:
                    tag_history[tag_name].append({
                        "pass_rate": tag_metrics.get("passed", 0) / total * 100,
                        "mcp_rate": tag_metrics.get("mcp_used", 0) / total * 100,
                        "tool_rate": tag_metrics.get("correct_tool", 0) / total * 100,
                    })

        def calc_trend(current_val: float, history_vals: list[float]) -> str:
            """Calculate trend based on current value vs historical average.

            Returns:
                'improving' (↑), 'stable' (→), or 'degrading' (↓)
            """
            if not history_vals:
                return "stable"
            avg = sum(history_vals) / len(history_vals)
            if avg == 0:
                return "stable"
            threshold = avg * 0.05  # 5% threshold
            if current_val > avg:
                return "improving"
            elif current_val < avg - threshold:
                return "degrading"
            return "stable"

        def format_trend(trend: str) -> str:
            """Format trend as HTML with colored arrow."""
            if trend == "improving":
                return '<span style="color: #22c55e;" title="Melhora">↑</span>'
            elif trend == "degrading":
                return '<span style="color: #ef4444;" title="Piora">↓</span>'
            return '<span style="color: #94a3b8;" title="Estável">→</span>'

        def format_delta(current: float, previous: float) -> str:
            """Format delta value with color and arrow (Req 14.5)."""
            delta = current - previous
            if abs(delta) < 0.05:  # Essentially no change
                return '<span class="delta neutral">→ 0.0</span>'
            elif delta > 0:
                return f'<span class="delta positive">↑ +{delta:.1f}</span>'
            else:
                return f'<span class="delta negative">↓ {delta:.1f}</span>'

        def is_degraded_pct(current: float, previous: float | None) -> bool:
            """Check if metric degraded by more than 10% (Req 14.6).

            For percentage metrics: degradation = current < previous by >10%

            Args:
                current: Current metric value.
                previous: Previous metric value (None if no comparison).

            Returns:
                True if degraded by more than 10%.
            """
            if previous is None or previous == 0:
                return False
            degradation_pct = ((previous - current) / previous) * 100
            return degradation_pct > 10

        def format_value_with_degradation(
            value: float,
            previous: float | None,
            delta_html: str,
        ) -> str:
            """Format value with degradation highlighting (Req 14.6).

            Only the specific value is highlighted in red when >10% piora,
            not the entire cell.

            Args:
                value: Current metric value.
                previous: Previous value for comparison.
                delta_html: Formatted delta HTML string.

            Returns:
                HTML with value (optionally with .degraded class) and delta.
            """
            if is_degraded_pct(value, previous):
                return f'<span class="metric-value degraded">{value:.1f}%</span> {delta_html}'
            return f'{value:.1f}% {delta_html}'

        # Build comparison data if available
        comparison_tag_metrics: dict[str, dict[str, float]] = {}
        if comparison_batch and comparison_batch.metrics_by_tag:
            for tag_name, tag_metrics in comparison_batch.metrics_by_tag.items():
                total = tag_metrics.total
                if total > 0:
                    comparison_tag_metrics[tag_name] = {
                        "pass_rate": tag_metrics.passed / total * 100,
                        "mcp_rate": tag_metrics.mcp_used / total * 100,
                        "tool_rate": tag_metrics.correct_tool / total * 100,
                    }

        rows: list[str] = []
        for tag, metrics in sorted(batch.metrics_by_tag.items()):
            pass_rate = (metrics.passed / metrics.total * 100) if metrics.total > 0 else 0
            mcp_rate = (metrics.mcp_used / metrics.total * 100) if metrics.total > 0 else 0
            tool_rate = (metrics.correct_tool / metrics.total * 100) if metrics.total > 0 else 0

            # Calculate trends (Req 14.7)
            tag_hist = tag_history.get(tag, [])
            trend_pass = calc_trend(pass_rate, [h["pass_rate"] for h in tag_hist])
            trend_mcp = calc_trend(mcp_rate, [h["mcp_rate"] for h in tag_hist])
            trend_tool = calc_trend(tool_rate, [h["tool_rate"] for h in tag_hist])

            # Build delta cells if comparing (Req 14.5, 14.6)
            if comparison_batch and tag in comparison_tag_metrics:
                prev = comparison_tag_metrics[tag]
                delta_pass = format_delta(pass_rate, prev["pass_rate"])
                delta_mcp = format_delta(mcp_rate, prev["mcp_rate"])
                delta_tool = format_delta(tool_rate, prev["tool_rate"])
                # Req 14.6: Apply degradation highlighting to specific values only
                pass_cell = format_value_with_degradation(pass_rate, prev["pass_rate"], delta_pass)
                mcp_cell = format_value_with_degradation(mcp_rate, prev["mcp_rate"], delta_mcp)
                tool_cell = format_value_with_degradation(tool_rate, prev["tool_rate"], delta_tool)
            else:
                pass_cell = f'{pass_rate:.1f}%'
                mcp_cell = f'{mcp_rate:.1f}%'
                tool_cell = f'{tool_rate:.1f}%'

            row = f'''<tr>
                <td><strong>{html.escape(tag)}</strong></td>
                <td>{metrics.total}</td>
                <td>{metrics.passed}</td>
                <td>{metrics.failed}</td>
                <td>{pass_cell} {format_trend(trend_pass)}</td>
                <td>{mcp_cell} {format_trend(trend_mcp)}</td>
                <td>{tool_cell} {format_trend(trend_tool)}</td>
            </tr>'''
            rows.append(row)

        # Add header explanation for delta mode
        header_note = ""
        if comparison_batch:
            header_note = f'''<p style="font-size: 0.875rem; color: #64748b; margin-bottom: 0.75rem;">
                Comparando com <code>{html.escape(comparison_batch.batch_id)}</code>.
                Deltas mostram diferença (atual - anterior).
            </p>'''

        return f'''<div class="section">
            <h2 class="section-title">🏷️ Métricas por Tag</h2>
            {header_note}
            <table>
                <thead>
                    <tr>
                        <th>Tag</th>
                        <th>Total</th>
                        <th>Passed</th>
                        <th>Failed</th>
                        <th>Pass Rate</th>
                        <th>MCP Used %</th>
                        <th>Correct Tool %</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(rows)}
                </tbody>
            </table>
        </div>'''

    def _render_test_table(self, batch: BatchResult) -> str:
        """Renderiza tabela de resultados de testes com painéis de detalhes expansíveis.

        Implements:
        - Req 11.1: Tabela com todos os TestResults
        - Req 11.2: Colunas test_id, query (truncada ~50 chars com tooltip),
                    expected_tool, actual_tool, status (badge com ícone), latency_ms
        - Req 11.3: Painel de detalhes expansível mostrando:
                    - Query completa enviada
                    - Tool esperada vs tool chamada (com highlight se diferente)
                    - Lista de todas as Tool_Calls registradas (com nome e argumentos)
                    - Resposta completa do agente (em área expansível)
                    - Mensagem de erro (se status é fail ou timeout)
                    - Tempo de execução detalhado
        - Req 11.7: Destacar em vermelho testes que não usaram MCP quando deveria
        - Req 11.8: Destacar em laranja testes com tool diferente da esperada
        - Req 11.4: Filtrar por status (all, pass, fail, timeout, skip)
        - Req 11.5: Buscar por texto na query (case-insensitive)
        - Req 11.6: Filtrar por tags selecionando uma ou mais

        Args:
            batch: Bateria com resultados de testes.

        Returns:
            HTML da tabela de testes com painéis expansíveis e filtros.
        """
        if not batch.test_results:
            return '''<div class="section">
                <h2 class="section-title">🧪 Resultados dos Testes</h2>
                <div class="no-data">Nenhum resultado de teste disponível</div>
            </div>'''

        # Status icons mapping (Req 11.2: colored badges with icons)
        status_icons = {
            "pass": "✓",
            "fail": "✗",
            "timeout": "⏱",
            "skip": "⏭",
        }

        # Collect all unique tags for the filter (Req 11.6)
        all_tags: set[str] = set()
        for tr in batch.test_results:
            all_tags.update(tr.tags)

        # Build filter controls HTML (Req 11.4, 11.5, 11.6)
        filter_html = self._render_filter_controls(sorted(all_tags))

        rows: list[str] = []
        for idx, tr in enumerate(batch.test_results):
            # Truncate query to ~50 chars for display (Req 11.2)
            query_display = tr.query[:50] + "..." if len(tr.query) > 50 else tr.query
            query_escaped = html.escape(tr.query)

            # Get expected tool display
            if tr.expected_tool:
                expected = tr.expected_tool
            elif tr.expected_tools:
                expected = " | ".join(tr.expected_tools[:2])
                if len(tr.expected_tools) > 2:
                    expected += f" (+{len(tr.expected_tools) - 2})"
            else:
                expected = "-"

            # Status class and icon (Req 11.2: badge with icon)
            status_class = tr.status
            status_icon = status_icons.get(tr.status, "?")
            status_text = f"{status_icon} {tr.status}"

            # Build expandable detail panel (Req 11.3)
            detail_panel = self._render_test_detail_panel(tr, expected)

            # Data attributes for filtering (Req 11.4, 11.5, 11.6)
            tags_data = ",".join(tr.tags) if tr.tags else ""
            query_lower = tr.query.lower()

            # Determine tool group for group filtering (Req 14.4)
            tool_for_group = tr.expected_tool
            if not tool_for_group and tr.expected_tools:
                tool_for_group = tr.expected_tools[0]
            group_name = TOOL_GROUPS.get(tool_for_group, "other") if tool_for_group else "other"

            # Determine row highlight classes (Req 11.7, 11.8)
            row_classes = ["test-row"]

            # Req 11.7: Red highlight when MCP should have been used but wasn't
            # Check validation_checks for uses_mcp with expected=True
            expected_mcp = False
            for check in tr.validation_checks:
                if check.get("name") == "uses_mcp":
                    expected_mcp = check.get("expected") is True
                    break

            if expected_mcp and not tr.mcp_used:
                row_classes.append("no-mcp")
            # Req 11.8: Orange highlight when MCP was used but wrong tool called
            # Only if not already highlighted as no-mcp
            elif not tr.correct_tool and tr.actual_tool is not None and (
                tr.expected_tool is not None or tr.expected_tools is not None
            ):
                row_classes.append("wrong-tool")

            row_class_str = " ".join(row_classes)

            row = f'''<tr class="{row_class_str}" data-row-id="{idx}" data-status="{html.escape(tr.status)}" data-tags="{html.escape(tags_data)}" data-query="{html.escape(query_lower)}" data-group="{html.escape(group_name)}">
                <td><code>{html.escape(tr.test_id)}</code></td>
                <td title="{query_escaped}">{html.escape(query_display)}</td>
                <td>{html.escape(expected)}</td>
                <td>{html.escape(tr.actual_tool or "-")}</td>
                <td><span class="status {status_class}">{status_text}</span></td>
                <td>{tr.latency_ms:.0f}ms</td>
            </tr>
            <tr class="detail-row" data-detail-for="{idx}" data-status="{html.escape(tr.status)}" data-tags="{html.escape(tags_data)}" data-query="{html.escape(query_lower)}" data-group="{html.escape(group_name)}">
                <td colspan="6">
                    {detail_panel}
                </td>
            </tr>'''
            rows.append(row)

        return f'''<div class="section">
            <h2 class="section-title">🧪 Resultados dos Testes</h2>
            {filter_html}
            <table class="test-results-table" id="test-table">
                <thead>
                    <tr>
                        <th>Test ID</th>
                        <th>Query</th>
                        <th>Expected Tool</th>
                        <th>Actual Tool</th>
                        <th>Status</th>
                        <th>Latency</th>
                    </tr>
                </thead>
                <tbody id="test-table-body">
                    {"".join(rows)}
                </tbody>
            </table>
        </div>'''

    def _render_filter_controls(self, tags: list[str]) -> str:
        """Renderiza controles de filtro para a tabela de testes.

        Implements:
        - Req 11.4: Filtrar por status (all, pass, fail, timeout, skip)
        - Req 11.5: Buscar por texto na query (case-insensitive)
        - Req 11.6: Filtrar por tags selecionando uma ou mais

        Args:
            tags: Lista de tags únicas disponíveis para filtro.

        Returns:
            HTML dos controles de filtro.
        """
        # Build tag checkboxes (Req 11.6)
        tag_checkboxes = ""
        if tags:
            tag_items = []
            for tag in tags:
                tag_items.append(
                    f'''<label class="tag-checkbox">
                        <input type="checkbox" value="{html.escape(tag)}" onchange="applyFilters()">
                        {html.escape(tag)}
                    </label>'''
                )
            tag_checkboxes = f'''
                <div class="filter-group">
                    <label>Tags</label>
                    <div class="tag-filter">
                        {"".join(tag_items)}
                    </div>
                </div>'''

        return f'''<div class="filter-section">
            <div class="filter-group">
                <label for="status-filter">Status</label>
                <select id="status-filter" onchange="applyFilters()">
                    <option value="all">All</option>
                    <option value="pass">Pass</option>
                    <option value="fail">Fail</option>
                    <option value="timeout">Timeout</option>
                    <option value="skip">Skip</option>
                </select>
            </div>
            <div class="filter-group">
                <label for="query-filter">Buscar Query</label>
                <input type="text" id="query-filter" placeholder="Digite para buscar..." oninput="applyFilters()">
            </div>
            {tag_checkboxes}
            <button class="filter-reset" onclick="resetFilters()">Limpar Filtros</button>
            <span class="filter-count" id="filter-count"></span>
        </div>'''

    def _render_test_detail_panel(self, tr: Any, expected_display: str) -> str:
        """Renderiza painel de detalhes expansível para um teste individual.

        Implements Req 11.3: Painel de detalhes com:
        - Query completa
        - Tool esperada vs chamada (highlight se diferente)
        - Lista de Tool_Calls com argumentos
        - Resposta do agente
        - Mensagem de erro
        - Tempo detalhado

        Args:
            tr: TestResult com dados do teste.
            expected_display: String formatada da tool esperada.

        Returns:
            HTML do painel de detalhes.
        """
        # Determine if tool mismatch for highlighting (Req 11.3)
        actual_tool = tr.actual_tool or "-"
        tool_match = False
        if tr.expected_tool:
            tool_match = tr.actual_tool == tr.expected_tool
        elif tr.expected_tools:
            tool_match = tr.actual_tool in tr.expected_tools

        tool_comparison_class = "tool-match" if tool_match else "tool-mismatch"

        # Format all tool calls with arguments (Req 11.3)
        tool_calls_html = self._format_tool_calls(tr.all_tool_calls)

        # Format agent response in scrollable area (Req 11.3)
        agent_response_escaped = html.escape(tr.agent_response) if tr.agent_response else "<em>Nenhuma resposta</em>"

        # Format error message if present (Req 11.3)
        error_html = ""
        if tr.error_message:
            error_html = f'''
            <div class="detail-section error-section">
                <div class="detail-label">❌ Mensagem de Erro</div>
                <div class="error-message">{html.escape(tr.error_message)}</div>
            </div>'''

        # Format detailed timing (Req 11.3)
        timing_html = f'''
        <div class="detail-section">
            <div class="detail-label">⏱️ Tempo de Execução</div>
            <div class="timing-details">
                <span class="timing-item">
                    <strong>Total:</strong> {tr.latency_ms:.0f}ms
                </span>'''

        if hasattr(tr, 'tool_latency_ms') and tr.tool_latency_ms is not None:
            timing_html += f'''
                <span class="timing-item">
                    <strong>Tool:</strong> {tr.tool_latency_ms:.0f}ms
                </span>'''

        timing_html += '''
            </div>
        </div>'''

        return f'''<details class="test-details">
            <summary class="details-summary">📋 Ver Detalhes do Teste</summary>
            <div class="details-content">
                <div class="detail-section">
                    <div class="detail-label">📝 Query Completa</div>
                    <pre class="query-full">{html.escape(tr.query)}</pre>
                </div>

                <div class="detail-section">
                    <div class="detail-label">🔧 Tool Esperada vs Chamada</div>
                    <div class="tool-comparison {tool_comparison_class}">
                        <div class="tool-expected">
                            <span class="tool-label">Esperada:</span>
                            <code>{html.escape(expected_display)}</code>
                        </div>
                        <div class="tool-arrow">→</div>
                        <div class="tool-actual">
                            <span class="tool-label">Chamada:</span>
                            <code>{html.escape(actual_tool)}</code>
                        </div>
                    </div>
                </div>

                <div class="detail-section">
                    <div class="detail-label">📞 Todas as Tool Calls ({len(tr.all_tool_calls)})</div>
                    {tool_calls_html}
                </div>

                <details class="agent-response-details">
                    <summary class="response-summary">💬 Resposta do Agente (clique para expandir)</summary>
                    <div class="agent-response-content">
                        <pre class="agent-response">{agent_response_escaped}</pre>
                    </div>
                </details>

                {error_html}

                {timing_html}
            </div>
        </details>'''

    def _format_tool_calls(self, tool_calls: list[dict[str, Any]]) -> str:
        """Formata lista de tool calls com argumentos em JSON.

        Args:
            tool_calls: Lista de dicts com informações das tool calls.

        Returns:
            HTML formatado das tool calls.
        """
        if not tool_calls:
            return '<div class="no-tool-calls"><em>Nenhuma tool call registrada</em></div>'

        items: list[str] = []
        for i, tc in enumerate(tool_calls, 1):
            name = tc.get("name", "unknown")
            args = tc.get("args", {})
            tool_id = tc.get("tool_id", "")

            # Format arguments as JSON (pretty printed, truncated if too long)
            try:
                args_json = json.dumps(args, indent=2, ensure_ascii=False)
                if len(args_json) > 500:
                    args_json = args_json[:500] + "\n... (truncado)"
            except (TypeError, ValueError):
                args_json = str(args)

            tool_id_html = f'<span class="tool-id">ID: {html.escape(tool_id)}</span>' if tool_id else ""

            item = f'''<div class="tool-call-item">
                <div class="tool-call-header">
                    <span class="tool-call-number">#{i}</span>
                    <code class="tool-call-name">{html.escape(name)}</code>
                    {tool_id_html}
                </div>
                <details class="tool-call-args-details">
                    <summary class="args-summary">Argumentos</summary>
                    <pre class="tool-call-args">{html.escape(args_json)}</pre>
                </details>
            </div>'''
            items.append(item)

        return f'<div class="tool-calls-list">{"".join(items)}</div>'

    def _get_chart_data(self, metric: str, limit: int = 20) -> dict[str, Any]:
        """Obtém dados para gráfico de tendência.

        Implements Req 13.5: Permitir selecionar período.

        Args:
            metric: Nome da métrica (pct_mcp_used, pct_correct_tool, etc.).
            limit: Número máximo de baterias a incluir.

        Returns:
            Dict com labels e data para Chart.js.
        """
        history = self.store.load_metrics_history(limit=limit)

        # Reverse to show oldest first
        history = list(reversed(history))

        return {
            "labels": [h.get("batch_id", "")[:15] for h in history],
            "data": [h.get(metric, 0) for h in history],
        }
