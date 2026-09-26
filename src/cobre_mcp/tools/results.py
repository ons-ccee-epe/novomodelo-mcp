"""Leitura e análise de resultados de um `cobre run` (pós-rodada).

Cada tool lê os arquivos documentados (metadata.json / parquet) e devolve
resultado moldado ao teto de saída. Sem regra de negócio.
"""
from __future__ import annotations

from ..adapters import results as R
from ..adapters.paths import ensure_in_workspace
from ..config import Settings
from .shaping import cap_envelope


def register_results(mcp, settings: Settings) -> None:
    """Registra as tools de leitura de resultados no servidor `mcp`."""

    @mcp.tool()
    def results_status(output_dir: str) -> dict:
        """Status, bounds e convergência de um run (o primeiro check pós-rodada).

        Lê `training/metadata.json` e, se houver, `simulation/metadata.json`.
        Devolve run_status, bounds (lower/upper), gap final, iterações, duração,
        dimensões do problema e o custo esperado da simulação (quando rodou).
        """
        if (err := ensure_in_workspace(output_dir, settings=settings)):
            return err
        env = R.read_metadata(output_dir)
        if env.get("status") != "ok":
            return env
        t = env["training"]
        s = env.get("simulation") or {}
        out = {
            "status": "ok",
            "run_status": t.get("status"),
            "bounds": t.get("bounds"),
            "convergence": t.get("convergence"),
            "iterations": t.get("iterations"),
            "duration_seconds": t.get("duration_seconds"),
            "problem_dimensions": t.get("problem_dimensions"),
            "cobre_version": t.get("cobre_version"),
            "simulation_ran": env["simulation_ran"],
            "simulation_cost": s.get("cost"),
        }
        return cap_envelope(out, settings)

    @mcp.tool()
    def results_convergence(output_dir: str, tail: int = 20) -> dict:
        """Trajetória de convergência: iteração final + últimas `tail` iterações.

        Lê `training/convergence.parquet` (bounds e gap por iteração).
        """
        if (err := ensure_in_workspace(output_dir, settings=settings)):
            return err
        return cap_envelope(R.convergence_summary(output_dir, tail=tail), settings)

    @mcp.tool()
    def results_list_entities(output_dir: str) -> dict:
        """Lista as entidades de simulação disponíveis (hydros, costs, thermals, buses, ...)."""
        if (err := ensure_in_workspace(output_dir, settings=settings)):
            return err
        return {"status": "ok", "entities": R.list_entities(output_dir)}

    @mcp.tool()
    def results_query(output_dir: str, entity: str, columns: list[str] | None = None,
                      group_by: list[str] | None = None, agg: str | None = None,
                      scenario: int | None = None, limit: int | None = None) -> dict:
        """Consulta a simulação particionada `simulation/<entity>/` (por scenario_id).

        `entity`: hydros | costs | thermals | buses | ... (ver results_list_entities).
        Agregação entre cenários: passe `group_by` (ex.: ["hydro_id","stage_id"]),
        `agg` (mean|min|max|sum|median|std|p10|p90) e `columns` (colunas a agregar).
        Sem `group_by`: primeiras `limit` linhas, com filtro opcional por `scenario`.
        Nunca devolve o dataset inteiro.
        """
        if (err := ensure_in_workspace(output_dir, settings=settings)):
            return err
        n = limit or settings.max_inline_rows
        out = R.simulation_query(output_dir, entity, columns=columns,
                                 group_by=group_by, agg=agg, scenario=scenario,
                                 limit=n, max_rows=settings.max_inline_rows)
        return cap_envelope(out, settings)
