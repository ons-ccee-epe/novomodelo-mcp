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
from . import budget
from .budget import fit_to_budget
from .envelope import error
from .paths import ensure_in_workspace

#: `entity` é o NOME de uma pasta de `simulation/`, nunca um caminho.
_ENTITY_NAME = re.compile(r"^[A-Za-z0-9_-]+$")

_AGGS = {"mean", "min", "max", "sum", "median", "std", "p10", "p90"}


def _read_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as fh:
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


#: Até onde a busca de rodadas desce abaixo da pasta recebida, e quantas pastas
#: visita: a pasta pode ser a de um estudo inteiro, e a busca não pode travar a tool.
_RUN_SEARCH_DEPTH = 4
_RUN_SEARCH_MAX_DIRS = 5000
_RUNS_LISTED = 20


def _is_run(path: Path) -> bool:
    return (path / "training" / "metadata.json").is_file()


def find_runs(folder: Path) -> list[Path]:
    """Rodadas abaixo de `folder`, reconhecidas pelo `training/metadata.json`, com
    qualquer nome de pasta.

    Não desce dentro de uma rodada nem segue link simbólico: um link levaria a busca
    para fora da pasta que o guard aprovou.
    """
    runs: list[Path] = []
    level, visited = [folder], 0
    for _ in range(_RUN_SEARCH_DEPTH):
        below: list[Path] = []
        for d in level:
            try:
                children = sorted(
                    c
                    for c in d.iterdir()
                    if c.is_dir() and not c.is_symlink() and not c.name.startswith(".")
                )
            except OSError:
                continue
            for c in children:
                visited += 1
                if visited > _RUN_SEARCH_MAX_DIRS:
                    return runs
                (runs if _is_run(c) else below).append(c)
        level = below
    return runs


def folder_above_runs(output_dir: str) -> dict[str, Any] | None:
    """Recusa uma pasta que contém rodadas (a do caso, a do estudo) no lugar da rodada.

    Com uma rodada, sugere ela em `suggested_output`; com várias, só lista, porque a
    escolha é do usuário. Sem rodada abaixo, devolve None e cada tool segue com o
    próprio erro.
    """
    root = Path(output_dir)
    if _is_run(root) or not root.is_dir():
        return None
    runs = [str(r) for r in find_runs(root)]
    if not runs:
        return None
    if len(runs) == 1:
        return error(
            2,
            f"{output_dir} não é a pasta de uma rodada; a rodada encontrada nela "
            f"está em suggested_output",
            suggested_output=runs[0],
            runs=runs,
        )
    return error(
        2,
        f"{output_dir} não é a pasta de uma rodada e tem {len(runs)} rodadas",
        "pergunte ao usuário qual rodada usar e passe a pasta dela em output_dir",
        runs=runs[:_RUNS_LISTED],
        runs_total=len(runs),
    )


def read_metadata(output_dir: str) -> dict[str, Any]:
    """Lê training/metadata.json (obrigatório) e simulation/metadata.json (opcional).

    Treino ilegível é erro; simulação ilegível vira `simulation: None` + aviso.
    """
    if err := folder_above_runs(output_dir):
        return err
    root = Path(output_dir)
    tmeta = root / "training" / "metadata.json"
    if not tmeta.exists():
        return error(
            2, f"nao parece pasta de resultados (falta training/metadata.json): {output_dir}"
        )
    training = _read_object(tmeta)
    if isinstance(training, str):
        return error(2, f"não foi possível ler {tmeta}", training)
    smeta = root / "simulation" / "metadata.json"
    simulation, warnings = None, []
    if smeta.exists():
        simulation = _read_object(smeta)
        if isinstance(simulation, str):
            warnings.append(f"simulation/metadata.json ilegível ({simulation}); simulação ignorada")
            simulation = None
    env = {
        "status": "ok",
        "training": training,
        "simulation": simulation,
        "simulation_ran": simulation is not None,
    }
    if warnings:
        env["warnings"] = warnings
    return env


def termination_fields(
    training: dict[str, Any] | None, simulation: dict[str, Any] | None
) -> dict[str, Any]:
    """`training`/`simulation`: como a rodada terminou, copiado do metadata sem interpretar.

    Nomes da 0.18: `convergence.termination_reason`, `iterations.converged_at` e
    `iterations.completed`; campo ausente vira None.
    """
    t = training if isinstance(training, dict) else {}
    conv = raw if isinstance(raw := t.get("convergence"), dict) else {}
    its = t.get("iterations")
    out: dict[str, Any] = {
        "training": {
            "status": t.get("status"),
            "termination_reason": conv.get("termination_reason"),
            "converged_at": its.get("converged_at") if isinstance(its, dict) else None,
            "iterations": its.get("completed") if isinstance(its, dict) else its,
        }
    }
    if isinstance(simulation, dict):
        out["simulation"] = {"status": simulation.get("status")}
    return out


#: Acima desta razão entre o maior e o menor coeficiente da matriz (antes do
#: escalonamento), a nota heurística sugere problema numérico. Rótulo de heurística,
#: não regra: o executável não decide nada com esse número.
HEURISTIC_RATIO = 1e12

_HEURISTIC_NOTE = (
    "Heurística: a faixa de coeficientes da matriz é muito larga e costuma levar o solver "
    "a falhar. Coeficientes muito pequenos na FPHA são a origem mais comum. Tente planos "
    'FPHA prontos (source: "precomputed") ou rodar em outra máquina. Não é a causa '
    "confirmada da falha."
)


def numeric_diagnosis(output_dir: str) -> dict[str, Any]:
    """`scaling` (copiado de training/scaling_report.json) e, acima de
    `HEURISTIC_RATIO`, `heuristic_diagnosis`. Relatório ausente ou ilegível → {}."""
    report = _read_object(Path(output_dir) / "training" / "scaling_report.json")
    if isinstance(report, str):
        return {}
    summary = raw if isinstance(raw := report.get("summary"), dict) else {}
    worst = summary.get("worst_pre_scaling_matrix_ratio")
    if not isinstance(worst, (int, float)):
        return {}
    stages = raw if isinstance(raw := report.get("stages"), list) else []
    stage = next(
        (
            s
            for s in stages
            if isinstance(s, dict)
            and (s.get("pre_scaling") or {}).get("matrix_coeff_ratio") == worst
        ),
        {},
    )
    coeff_range = (stage.get("pre_scaling") or {}).get("matrix_coeff_range")
    out: dict[str, Any] = {
        "scaling": {
            "pre_ratio": worst,
            "post_ratio": summary.get("worst_post_scaling_matrix_ratio"),
            "stage": stage.get("stage_id"),
            "range": coeff_range,
        }
    }
    if worst > HEURISTIC_RATIO:
        out["heuristic_diagnosis"] = {
            "ratio": worst,
            "range": coeff_range,
            "stage": stage.get("stage_id"),
            "note": _HEURISTIC_NOTE,
        }
    return out


_PAR_COLUMNS = ("hydro_id", "stage_id", "lag", "coefficient")


def stochastic_query(
    output_dir: str,
    *,
    hydro_id: int | None = None,
    stage: int | None = None,
    openings_stage: int | None = None,
    max_rows: int = 50,
) -> dict[str, Any]:
    """PAR(p) e árvore de aberturas por `novomodelo.results.load_stochastic`, com teto."""
    try:
        from novomodelo import results as nm_results
    except ImportError:
        return error(127, "novomodelo-python (com numpy) ausente no ambiente do MCP")
    try:
        stoch = nm_results.load_stochastic(output_dir)
        rows = [
            dict(zip(_PAR_COLUMNS, (int(h), int(s), int(lag), float(c)), strict=True))
            for h, s, lag, c in stoch.par_coefficients().tolist()
            if (hydro_id is None or int(h) == hydro_id) and (stage is None or int(s) == stage)
        ]
        out: dict[str, Any] = {
            "status": "ok",
            "par": {
                "rows": rows[:max_rows],
                "total": len(rows),
                "truncated": len(rows) > max_rows,
            },
        }
        if openings_stage is not None:
            tree = stoch.opening_tree(openings_stage)
            n, dim = (tree.shape + (1,))[:2]
            out["openings"] = {
                "stage": openings_stage,
                "n_openings": int(n),
                "dim": int(dim),
                "rows": tree[:max_rows].tolist(),
                "truncated": n > max_rows,
            }
        return out
    except FileNotFoundError as exc:
        return error(
            2,
            "o run não gravou o modelo estocástico: ligue exports.stochastic no "
            "config.json e rode de novo",
            _first_line(exc),
        )
    except IndexError as exc:
        return error(
            22, f"estágio inexistente na árvore de aberturas: {openings_stage}", _first_line(exc)
        )
    except (OSError, ValueError) as exc:
        return error(
            2, f"não foi possível ler o modelo estocástico de {output_dir}", _first_line(exc)
        )


def _policy_dir(output_dir: str, policy_subdir: str, settings: Settings) -> Path | dict[str, Any]:
    if not _ENTITY_NAME.match(policy_subdir or ""):
        return error(
            13,
            f"policy_subdir inválido: {policy_subdir!r}",
            "use o nome da subpasta da política (letras, números, _ e -)",
        )
    root = Path(output_dir).resolve()
    policy = (root / policy_subdir).resolve()
    if not policy.is_relative_to(root):
        return error(13, f"policy_subdir fora da pasta de resultados: {policy_subdir!r}")
    if err := ensure_in_workspace(str(policy), settings=settings):
        return err
    if not policy.is_dir():
        return error(2, f"política inexistente: {policy}")
    return policy


def _cut_row(cut: dict[str, Any]) -> dict[str, Any]:
    return {
        "cut_id": cut.get("cut_id"),
        "iteration": cut.get("iteration"),
        "forward_pass_index": cut.get("forward_pass_index"),
        "intercept": cut.get("intercept"),
        "is_active": cut.get("is_active"),
        "n_coefficients": len(cut.get("coefficients") or []),
    }


def policy_summary(
    output_dir: str, *, settings: Settings, stage: int | None = None, policy_subdir: str = "policy"
) -> dict[str, Any]:
    """Resumo de `novomodelo.results.load_policy`: metadata e cortes por estágio, sem os
    coeficientes. Acima de `settings.max_policy_bytes` em disco, recusa sem carregar:
    a biblioteca monta a política inteira em memória."""
    policy = _policy_dir(output_dir, policy_subdir, settings)
    if isinstance(policy, dict):
        return policy
    size = sum(f.stat().st_size for f in policy.rglob("*") if f.is_file())
    if size > settings.max_policy_bytes:
        return error(
            13,
            f"política com {size / 1024**3:.1f} GiB em disco: acima do teto "
            f"NOVOMODELO_MCP_MAX_POLICY_BYTES ({settings.max_policy_bytes} bytes)",
            "a biblioteca carrega a política inteira em memória; o teto protege a "
            "máquina (heurística, não regra do novomodelo)",
        )
    try:
        from novomodelo import results as nm_results
    except ImportError:
        return error(127, "novomodelo-python ausente no ambiente do MCP")
    try:
        loaded = nm_results.load_policy(output_dir, policy_subdir=policy_subdir)
    except Exception as exc:  # noqa: BLE001 - erros da biblioteca (OutputError, OSError) viram envelope
        return error(2, f"não foi possível ler a política em {policy}", _first_line(exc))
    meta = dict(loaded.get("metadata") or {})
    graph = meta.get("graph_manifest")
    if isinstance(graph, dict):
        meta["graph_manifest"] = {
            "n_pools": graph.get("n_pools"),
            "n_nodes": len(graph.get("nodes") or []),
            "n_edges": len(graph.get("edges") or []),
        }
    stages = loaded.get("stage_cuts") or []
    rows = [
        {
            "stage_id": s.get("stage_id"),
            "populated_count": s.get("populated_count"),
            "capacity": s.get("capacity"),
            "warm_start_count": s.get("warm_start_count"),
            "state_dimension": s.get("state_dimension"),
            "n_cuts": len(s.get("cuts") or []),
            "n_active": sum(1 for c in s.get("cuts") or [] if c.get("is_active")),
        }
        for s in stages
    ]
    cap = budget.row_limit(settings)
    out: dict[str, Any] = {
        "status": "ok",
        "metadata": meta,
        "stages": rows[:cap],
        "stages_truncated": len(rows) > cap,
    }
    if stage is not None:
        chosen = next((s for s in stages if s.get("stage_id") == stage), None)
        if chosen is None:
            return error(22, f"estágio inexistente na política: {stage}")
        cuts = chosen.get("cuts") or []
        n = budget.row_limit(settings)
        out["cuts"] = {
            "stage": stage,
            "rows": [_cut_row(c) for c in cuts[:n]],
            "total": len(cuts),
            "truncated": len(cuts) > n,
        }
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
    return {
        "status": "ok",
        "columns": df.columns,
        "n_iterations": df.height,
        "final": last[0] if last else None,
        "tail": df.tail(max(1, min(tail, 200))).to_dicts(),
    }


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


def simulation_query(
    output_dir: str,
    entity: str,
    *,
    settings: Settings,
    columns: list[str] | None = None,
    group_by: list[str] | None = None,
    agg: str | None = None,
    scenario: int | None = None,
    limit: int = 50,
    max_rows: int = 200,
) -> dict[str, Any]:
    """Consulta simulation/<entity>/ (particionado por scenario_id).

    Com group_by+agg+columns: agrega (média, p10/p90, ...) sobre as `columns`.
    Sem group_by: primeiras `limit` linhas (com filtro opcional por `scenario`).
    Nunca devolve o dataset inteiro — sempre com teto de linhas.
    """
    if not _ENTITY_NAME.match(entity or ""):
        return error(
            13,
            f"entidade inválida: {entity!r}",
            "use um nome de results_list_entities (letras, números, _ e -)",
        )
    # resolve() antes de comparar: um nome válido pode ser link simbólico para fora
    # de simulation/, e o guard de output_dir não alcança o que vem depois dele.
    sim = (Path(output_dir) / "simulation").resolve()
    base = (sim / entity).resolve()
    if not base.is_relative_to(sim):
        return error(13, f"entidade fora da pasta de resultados: {entity!r}")
    if err := ensure_in_workspace(str(base), settings=settings):
        return err
    if not base.exists():
        return error(
            2,
            f"entidade inexistente: simulation/{entity}",
            f"disponiveis: {list_entities(output_dir)}",
        )
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
        if group_by and agg and columns:
            lf = lf.group_by(group_by).agg(_agg_exprs(pl, agg, columns)).sort(group_by)
        elif columns:
            lf = lf.select(columns)
        df = lf.limit(cap).collect()
    except (OSError, pl.exceptions.PolarsError) as exc:
        return error(2, f"não foi possível ler simulation/{entity}", _first_line(exc))

    out: dict[str, Any] = {
        "status": "ok",
        "entity": entity,
        "columns": df.columns,
        "row_count": df.height,
        "truncated": df.height >= cap,
        "rows": df.to_dicts(),
    }
    if limit > max_rows:
        out["limit_applied"] = max_rows
    glob = f"{base.as_posix()}/**/*.parquet".replace("'", "''")
    next_step = (
        "o recorte não coube na resposta. Escolha menos colunas ou, para varrer todos os "
        f"cenários, use o deck_sql sobre read_parquet('{glob}'): agregue (GROUP BY) ou filtre "
        "(WHERE) para achar os casos que interessam e depois detalhe só esses."
    )
    out = fit_to_budget(out, settings, "rows", reserve=len(next_step.encode("utf-8")) + 64)
    if out["truncated"]:
        out["next"] = next_step
    return out
