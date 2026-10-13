"""Leitura de resultados de um `novomodelo run`, pelo contrato documentado.

Fontes (docs): reference/output/ (index, training, simulation…) e running/interpreting-results.mdx.
- metadados: training/metadata.json e simulation/metadata.json (JSON, stdlib)
- séries: training/convergence.parquet e simulation/<entidade>/ (Parquet via Polars)

Sem regra de negócio: só leitura, agregação e teto de saída. Polars é importado
de forma preguiçosa (o módulo carrega mesmo sem ele).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..config import Settings
from .envelope import error
from .paths import ensure_in_workspace

#: `entity` é o NOME de uma pasta de `simulation/`, nunca um caminho.
_ENTITY_NAME = re.compile(r"^[A-Za-z0-9_-]+$")

_AGGS = {"mean", "min", "max", "sum", "median", "std", "p10", "p90"}


def _read_json(path: Path) -> Any:
    with open(path) as fh:
        return json.load(fh)


def _first_line(exc: BaseException) -> str:
    text = str(exc).strip()
    return text.splitlines()[0] if text else type(exc).__name__


def _read_object(path: Path) -> dict[str, Any] | str:
    """O objeto JSON do arquivo, ou o motivo de não conseguir lê-lo."""
    try:
        obj = _read_json(path)
    except (OSError, ValueError) as exc:
        return _first_line(exc)
    return obj if isinstance(obj, dict) else "não é um objeto JSON"


def read_metadata(output_dir: str) -> dict[str, Any]:
    """Lê training/metadata.json (obrigatório) e simulation/metadata.json (opcional).

    Treino ilegível é erro; simulação ilegível vira `simulation: None` + aviso.
    """
    root = Path(output_dir)
    tmeta = root / "training" / "metadata.json"
    if not tmeta.exists():
        return error(2, f"nao parece pasta de resultados (falta training/metadata.json): "
                        f"{output_dir}")
    training = _read_object(tmeta)
    if isinstance(training, str):
        return error(2, f"não foi possível ler {tmeta}", training)
    smeta = root / "simulation" / "metadata.json"
    simulation, warnings = None, []
    if smeta.exists():
        simulation = _read_object(smeta)
        if isinstance(simulation, str):
            warnings.append(f"simulation/metadata.json ilegível ({simulation}); "
                            "simulação ignorada")
            simulation = None
    env = {"status": "ok", "training": training, "simulation": simulation,
           "simulation_ran": simulation is not None}
    if warnings:
        env["warnings"] = warnings
    return env


def termination_fields(training: dict[str, Any] | None,
                       simulation: dict[str, Any] | None) -> dict[str, Any]:
    """`treino`/`simulacao`: como a rodada terminou, copiado do metadata sem interpretar.

    Nomes da 0.18: `convergence.termination_reason`, `iterations.converged_at` e
    `iterations.completed`; campo ausente (runs ≤ 0.17) vira None.
    """
    t = training if isinstance(training, dict) else {}
    conv = t.get("convergence") if isinstance(t.get("convergence"), dict) else {}
    its = t.get("iterations")
    out: dict[str, Any] = {"treino": {
        "status": t.get("status"),
        "termination_reason": conv.get("termination_reason"),
        "converged_at": its.get("converged_at") if isinstance(its, dict) else None,
        "iterations": its.get("completed") if isinstance(its, dict) else its,
    }}
    if isinstance(simulation, dict):
        out["simulacao"] = {"status": simulation.get("status")}
    return out


def _pl():
    import polars as pl
    return pl


def convergence_summary(output_dir: str, tail: int = 20) -> dict[str, Any]:
    """Resumo de training/convergence.parquet: iteração final + cauda da trajetória."""
    p = Path(output_dir) / "training" / "convergence.parquet"
    if not p.exists():
        return error(2, f"arquivo ausente: {p}")
    pl = _pl()
    try:
        df = pl.read_parquet(p)
    except (OSError, pl.exceptions.PolarsError) as exc:
        return error(2, f"não foi possível ler {p}", _first_line(exc))
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


def simulation_query(output_dir: str, entity: str, *, settings: Settings,
                     columns: list[str] | None = None,
                     group_by: list[str] | None = None, agg: str | None = None,
                     scenario: int | None = None, limit: int = 50,
                     max_rows: int = 200) -> dict[str, Any]:
    """Consulta simulation/<entity>/ (particionado por scenario_id).

    Com group_by+agg+columns: agrega (média, p10/p90, ...) sobre as `columns`.
    Sem group_by: primeiras `limit` linhas (com filtro opcional por `scenario`).
    Nunca devolve o dataset inteiro — sempre com teto de linhas.
    """
    if not _ENTITY_NAME.match(entity or ""):
        return error(13, f"entidade inválida: {entity!r}",
                     "use um nome de results_list_entities (letras, números, _ e -)")
    # resolve() antes de comparar: um nome válido pode ser link simbólico para fora
    # de simulation/, e o guard de output_dir não alcança o que vem depois dele.
    sim = (Path(output_dir) / "simulation").resolve()
    base = (sim / entity).resolve()
    if not base.is_relative_to(sim):
        return error(13, f"entidade fora da pasta de resultados: {entity!r}")
    if (err := ensure_in_workspace(str(base), settings=settings)):
        return err
    if not base.exists():
        return error(2, f"entidade inexistente: simulation/{entity}",
                     f"disponiveis: {list_entities(output_dir)}")
    if group_by and agg not in _AGGS:
        return error(22, f"agg invalido: {agg!r}", f"use um de {sorted(_AGGS)}")
    if group_by and not columns:
        return error(22, "com group_by, informe 'columns' (colunas a agregar)")
    pl = _pl()
    cap = max(1, min(limit, max_rows))
    try:
        lf = pl.scan_parquet(str(base / "**" / "*.parquet"))
        if scenario is not None:
            lf = lf.filter(pl.col("scenario_id") == scenario)
        if group_by:
            lf = lf.group_by(group_by).agg(_agg_exprs(pl, agg, columns)).sort(group_by)
        elif columns:
            lf = lf.select(columns)
        df = lf.limit(cap).collect()
    except (OSError, pl.exceptions.PolarsError) as exc:
        return error(2, f"não foi possível ler simulation/{entity}", _first_line(exc))

    return {"status": "ok", "entity": entity, "columns": df.columns,
            "row_count": df.height, "truncated": df.height >= cap,
            "rows": df.to_dicts()}
