"""Leitura de resultados de um `cobre run`, pelo contrato documentado.

Fontes (docs): reference/output-format.mdx e running/interpreting-results.mdx.
- metadados: training/metadata.json e simulation/metadata.json (JSON, stdlib)
- séries: training/convergence.parquet e simulation/<entidade>/ (Parquet via Polars)

Sem regra de negócio: só leitura, agregação e teto de saída. Polars é importado
de forma preguiçosa (o módulo carrega mesmo sem ele).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_AGGS = {"mean", "min", "max", "sum", "median", "std", "p10", "p90"}


def _read_json(path: Path) -> Any:
    with open(path) as fh:
        return json.load(fh)


def read_metadata(output_dir: str) -> dict[str, Any]:
    """Lê training/metadata.json (obrigatório) e simulation/metadata.json (opcional)."""
    root = Path(output_dir)
    tmeta = root / "training" / "metadata.json"
    if not tmeta.exists():
        return {"status": "error",
                "diagnostics": [f"nao parece pasta de resultados (falta "
                                f"training/metadata.json): {output_dir}"]}
    training = _read_json(tmeta)
    smeta = root / "simulation" / "metadata.json"
    simulation = _read_json(smeta) if smeta.exists() else None
    return {"status": "ok", "training": training, "simulation": simulation,
            "simulation_ran": simulation is not None}


def _pl():
    import polars as pl
    return pl


def convergence_summary(output_dir: str, tail: int = 20) -> dict[str, Any]:
    """Resumo de training/convergence.parquet: iteração final + cauda da trajetória."""
    p = Path(output_dir) / "training" / "convergence.parquet"
    if not p.exists():
        return {"status": "error", "diagnostics": [f"arquivo ausente: {p}"]}
    pl = _pl()
    df = pl.read_parquet(p)
    last = df.tail(1).to_dicts()
    return {"status": "ok", "columns": df.columns, "n_iterations": df.height,
            "final": last[0] if last else None,
            "tail": df.tail(max(1, min(tail, 200))).to_dicts()}


def list_entities(output_dir: str) -> list[str]:
    sim = Path(output_dir) / "simulation"
    if not sim.is_dir():
        return []
    return sorted(d.name for d in sim.iterdir() if d.is_dir())


def _agg_exprs(pl, agg: str, cols: list[str]):
    def one(c: str):
        col = pl.col(c)
        if agg == "p10":
            return col.quantile(0.1).alias(f"{c}_p10")
        if agg == "p90":
            return col.quantile(0.9).alias(f"{c}_p90")
        return getattr(col, agg)().alias(f"{c}_{agg}")
    return [one(c) for c in cols]


def simulation_query(output_dir: str, entity: str, *, columns: list[str] | None = None,
                     group_by: list[str] | None = None, agg: str | None = None,
                     scenario: int | None = None, limit: int = 50,
                     max_rows: int = 200) -> dict[str, Any]:
    """Consulta simulation/<entity>/ (particionado por scenario_id).

    Com group_by+agg+columns: agrega (média, p10/p90, ...) sobre as `columns`.
    Sem group_by: primeiras `limit` linhas (com filtro opcional por `scenario`).
    Nunca devolve o dataset inteiro — sempre com teto de linhas.
    """
    base = Path(output_dir) / "simulation" / entity
    if not base.exists():
        return {"status": "error",
                "diagnostics": [f"entidade inexistente: simulation/{entity}",
                                f"disponiveis: {list_entities(output_dir)}"]}
    pl = _pl()
    lf = pl.scan_parquet(str(base / "**" / "*.parquet"))
    if scenario is not None:
        lf = lf.filter(pl.col("scenario_id") == scenario)

    cap = max(1, min(limit, max_rows))
    if group_by:
        if agg not in _AGGS:
            return {"status": "error",
                    "diagnostics": [f"agg invalido: {agg!r}", f"use um de {sorted(_AGGS)}"]}
        if not columns:
            return {"status": "error",
                    "diagnostics": ["com group_by, informe 'columns' (colunas a agregar)"]}
        out = lf.group_by(group_by).agg(_agg_exprs(pl, agg, columns)).sort(group_by)
        df = out.limit(cap).collect()
    else:
        if columns:
            lf = lf.select(columns)
        df = lf.limit(cap).collect()

    return {"status": "ok", "entity": entity, "columns": df.columns,
            "row_count": df.height, "truncated": df.height >= cap,
            "rows": df.to_dicts()}
