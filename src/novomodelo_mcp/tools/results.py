"""Leitura e análise de resultados de um `novomodelo run` (pós-rodada).

Cada tool lê os arquivos documentados (metadata.json / parquet) e devolve
resultado moldado ao teto de saída. Sem regra de negócio.
"""

from __future__ import annotations

from ..adapters import budget
from ..adapters import results as R
from ..adapters.paths import ensure_in_workspace
from ..config import Settings
from .shaping import fit_to_budget, cap_envelope
from .annotations import READ_ONLY


def register_results(mcp, settings: Settings) -> None:
    """Registra as tools de leitura de resultados no servidor `mcp`."""

    @mcp.tool(annotations=READ_ONLY)
    def results_status(output_dir: str) -> dict:
        """Status, bounds e convergência de um run (o primeiro check pós-rodada).

        Lê `training/metadata.json` e, se houver, `simulation/metadata.json`.
        Devolve run_status, bounds (lower/upper), gap final, iterações, duração,
        dimensões do problema e o custo esperado da simulação (quando rodou).
        `_SUCCESS` só indica que a saída foi gravada; veja `treino.termination_reason`
        e `treino.converged_at` para saber se convergiu. Se o run falhou,
        `escalonamento` e, se for o caso, `diagnostico_heuristico` (ver run_status).
        """
        if err := ensure_in_workspace(output_dir, settings=settings):
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
            "software": t.get("software"),
            "software_version": t.get("software_version"),
            "simulation_ran": env["simulation_ran"],
            "simulation_cost": s.get("cost"),
            **R.termination_fields(t, env.get("simulation")),
        }
        if env.get("warnings"):
            out["warnings"] = env["warnings"]
        if out["treino"].get("termination_reason") == "error":
            out.update(R.numeric_diagnosis(output_dir))
        return cap_envelope(out, settings)

    @mcp.tool(annotations=READ_ONLY)
    def results_convergence(output_dir: str, tail: int = 20) -> dict:
        """Trajetória de convergência: iteração final + últimas `tail` iterações.

        Lê `training/convergence.parquet` (bounds e gap por iteração).
        """
        if err := ensure_in_workspace(output_dir, settings=settings) or R.folder_above_runs(
            output_dir
        ):
            return err
        return cap_envelope(
            fit_to_budget(R.convergence_summary(output_dir, tail=tail), settings, "tail"), settings
        )

    @mcp.tool(annotations=READ_ONLY)
    def results_stochastic(
        output_dir: str,
        hydro_id: int | None = None,
        stage: int | None = None,
        aberturas_do_estagio: int | None = None,
    ) -> dict:
        """Modelo estocástico ajustado no run: coeficientes do PAR(p) e árvore de aberturas.

        Lê pela biblioteca (`novomodelo.results.load_stochastic`) a pasta
        `stochastic/` da saída, que o run só grava com `exports.stochastic: true`
        no config.json. `par.linhas`: {hydro_id, stage_id, lag, coefficient}
        (lag a partir de 1), filtráveis por `hydro_id` e `stage`.
        `aberturas_do_estagio`: devolve também a árvore desse estágio (linha k =
        vetor de ruído da abertura k). Com teto de linhas.
        """
        if err := ensure_in_workspace(output_dir, settings=settings) or R.folder_above_runs(
            output_dir
        ):
            return err
        return cap_envelope(
            budget.shrink_to_budget(
                R.stochastic_query(
                    output_dir,
                    hydro_id=hydro_id,
                    stage=stage,
                    openings_stage=aberturas_do_estagio,
                    max_rows=budget.row_limit(settings),
                ),
                settings,
            ),
            settings,
        )

    @mcp.tool(annotations=READ_ONLY)
    def results_policy(
        output_dir: str, stage: int | None = None, policy_subdir: str = "policy"
    ) -> dict:
        """Resumo da política treinada (cortes de Benders) de um run, pela biblioteca.

        `metadata` (versão, data, estágios, iterações) e, por estágio, o número de
        cortes e de cortes ativos; os coeficientes não voltam. Com `stage`, até o
        teto de cortes daquele estágio (id, iteração, intercepto, ativo). Política
        maior que `NOVOMODELO_MCP_MAX_POLICY_BYTES` em disco é recusada sem ser
        carregada (a biblioteca lê a política inteira em memória).
        """
        if err := ensure_in_workspace(output_dir, settings=settings) or R.folder_above_runs(
            output_dir
        ):
            return err
        return cap_envelope(
            budget.shrink_to_budget(
                R.policy_summary(
                    output_dir, settings=settings, stage=stage, policy_subdir=policy_subdir
                ),
                settings,
            ),
            settings,
        )

    @mcp.tool(annotations=READ_ONLY)
    def results_list_entities(output_dir: str) -> dict:
        """Lista as entidades de simulação disponíveis (hydros, costs, thermals, buses, ...)."""
        if err := ensure_in_workspace(output_dir, settings=settings) or R.folder_above_runs(
            output_dir
        ):
            return err
        return {"status": "ok", "entities": R.list_entities(output_dir)}

    @mcp.tool(annotations=READ_ONLY)
    def results_query(
        output_dir: str,
        entity: str,
        columns: list[str] | None = None,
        group_by: list[str] | None = None,
        agg: str | None = None,
        scenario: int | None = None,
        limit: int | None = None,
    ) -> dict:
        """Consulta a simulação particionada `simulation/<entity>/` (por scenario_id).

        `entity`: hydros | costs | thermals | buses | ... (ver results_list_entities).
        Agregação entre cenários: passe `group_by` (ex.: ["hydro_id","stage_id"]),
        `agg` (mean|min|max|sum|median|std|p10|p90) e `columns` (colunas a agregar).
        Sem `group_by`: primeiras `limit` linhas, com filtro opcional por `scenario`.
        Sem `limit`, o que couber; nunca passa de NOVOMODELO_MCP_MAX_RESPONSE_KB
        (escolha só as colunas que precisa: linhas estreitas cabem às centenas).
        Varredura de todos os cenários (ex.: onde uma violação aparece, em que usina e
        estágio): use o `deck_sql` sobre
        read_parquet('<output_dir>/simulation/<entity>/**/*.parquet'), que agrega e
        filtra todas as partições; a resposta truncada traz o caminho pronto.
        """
        if err := ensure_in_workspace(output_dir, settings=settings) or R.folder_above_runs(
            output_dir
        ):
            return err
        n = limit or budget.row_limit(settings)
        out = R.simulation_query(
            output_dir,
            entity,
            settings=settings,
            columns=columns,
            group_by=group_by,
            agg=agg,
            scenario=scenario,
            limit=n,
            max_rows=budget.row_limit(settings),
        )
        return cap_envelope(out, settings)
