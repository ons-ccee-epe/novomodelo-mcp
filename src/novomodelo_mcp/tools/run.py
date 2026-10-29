"""Ferramentas de scaffold e execução: `novomodelo init`, plano, ajuste de config e run assíncrono.

Fachada: `case_init` e `run_start` envelopam a CLI do novomodelo; o plano só
LÊ o caso e estima; `run_apply` só edita knobs de config.json via
deck_io.edit_json (schema + backup + atômico). Zero regra de negócio.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..adapters import deck_io, jobs, runtime
from ..adapters.discovery import find_novomodelo
from ..adapters.envelope import as_error, error
from ..adapters.machine import detect_machine
from ..adapters.novomodelo import run_novomodelo, version_cli
from ..adapters.obs import log
from ..adapters.paths import allowed_roots, ensure_in_workspace
from ..adapters.reference import schemas_root
from ..adapters.results import numeric_diagnosis, read_metadata, termination_fields
from ..adapters.run_plan import CONFIG_KNOBS, build_plan, read_case_params
from ..adapters.state import state_dir
from ..config import Settings
from .annotations import DESTRUCTIVE, READ_ONLY, WRITES
from .shaping import attach_artifact, cap_envelope


def _calibration_file(settings: Settings) -> Path:
    return state_dir(settings) / "calibration.json"


def harvest_calibrations(settings: Settings) -> int:
    """Registra no registro de calibração os runs concluídos via run_start.

    Idempotente: cada job é colhido uma vez (`calibration_recorded` no job.json).
    A assinatura de modelagem usada é a gravada no START (o config pode ter mudado).
    """
    n = 0
    for j in jobs.list_jobs(settings):
        if j["state"] != "succeeded" or j.get("calibration_recorded") or not j.get("machine_id"):
            continue
        meta_path = Path(j.get("output") or "") / "training" / "metadata.json"
        point = runtime.load_run(meta_path, config_sig=j.get("config_sig"))
        if point:
            runtime.record_calibration(_calibration_file(settings), j["machine_id"], point)
            n += 1
        jobs.update_meta(settings, j["job_id"], calibration_recorded=True)
    return n


_TEMPLATE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _cli_path(path: str) -> str:
    """Caminho ABSOLUTO para a argv da CLI: um relativo iniciado por `-` seria lido
    pelo novomodelo como opção (injeção de argumento)."""
    return str(Path(path).resolve())


def make_plan(
    case_dir: str,
    settings: Settings,
    *,
    time_budget_s: float = 900,
    threads: int | None = None,
    machine: dict | None = None,
) -> dict:
    """Compõe máquina + pontos medidos + parâmetros do caso num plano (sem gravar)."""
    try:
        params = read_case_params(case_dir)
    except (OSError, ValueError) as exc:
        return error(2, f"não foi possível ler o caso: {case_dir}", str(exc))
    machine = machine or detect_machine()
    harvest_calibrations(settings)
    roots = [case_dir] + [str(r) for r in allowed_roots(settings)]
    if len(roots) == 1:
        roots.append(str(Path(case_dir).resolve().parent))
    points = runtime.load_calibrations(_calibration_file(settings), machine["machine_id"])
    known = {p.get("source") for p in points}
    points += [
        p
        for p in runtime.find_reference_runs(roots, machine["hostname"])
        if p.get("source") not in known
    ]
    installed = version_cli(settings=settings)
    version = (
        runtime.normalize_version(installed.get("version"))
        if installed.get("status") == "ok"
        else None
    )
    ref = runtime.select_reference(
        points, params["dimensions"], params["config_sig"], case_dir, version=version
    )
    plan = build_plan(params, machine, ref, time_budget_s, threads)
    if ref and ref.get("version_mismatch"):
        plan.setdefault("warnings", []).append(
            "estimativa baseada em runs de outra versão do novomodelo "
            f"({', '.join(ref['versions_used'])}); pode não refletir a versão "
            f"instalada ({version})"
        )
    plan["case_dir"] = case_dir
    plan["reference_candidates"] = len(points)
    return plan


def _completed_run(output: Path) -> bool:
    return any((output / phase / "_SUCCESS").exists() for phase in ("training", "simulation"))


def _free_output(output: Path) -> Path:
    n = 2
    while (candidate := output.with_name(f"{output.name}-{n}")).exists():
        n += 1
    return candidate


def _knob_changes(config: dict, overrides: dict) -> list[dict] | dict:
    changes = []
    for knob, value in overrides.items():
        if knob not in CONFIG_KNOBS:
            return error(22, f"knob não suportado: {knob}", f"permitidos: {sorted(CONFIG_KNOBS)}")
        if knob == "simulation_enabled":
            if not isinstance(value, bool):
                return error(22, f"{knob} deve ser booleano")
            changes.append({"path": "simulation.enabled", "value": value})
            continue
        if isinstance(value, bool) or not isinstance(value, int):
            return error(22, f"{knob} deve ser inteiro (recebido {value!r})")
        if knob == "iteration_limit":
            rules = list((config.get("training") or {}).get("stopping_rules") or [])
            idx = next(
                (
                    i
                    for i, r in enumerate(rules)
                    if isinstance(r, dict) and r.get("type") == "iteration_limit"
                ),
                None,
            )
            if idx is None:
                rules.append({"type": "iteration_limit", "limit": value})
                changes.append({"path": "training.stopping_rules", "value": rules})
            else:
                changes.append({"path": f"training.stopping_rules[{idx}].limit", "value": value})
        else:
            changes.append({"path": CONFIG_KNOBS[knob], "value": value})
    return changes


def register_run(mcp, settings: Settings) -> None:
    """Registra as tools de scaffold/execução no servidor `mcp`."""

    @mcp.tool(annotations=WRITES)
    def case_init(
        directory: str | None = None,
        template: str | None = None,
        list: bool = False,
        force: bool = False,
    ) -> dict:
        """Cria um caso a partir de um template embutido (`novomodelo init`).

        `list=True` lista os templates disponíveis (ex.: `1dtoy`) e sai.
        Senão, `directory` + `template` escrevem o caso. `force=True`
        (sobrescrever arquivos existentes) só é aceito com NOVOMODELO_MCP_ALLOW_FORCE=1.
        """
        if list:
            env = run_novomodelo(["init", "--list"], settings=settings, parse_json=False)
            templates = []
            for line in (env.get("stdout") or "").splitlines():
                name, _, desc = line.strip().partition(" ")
                if name:
                    templates.append({"name": name, "description": desc.strip()})
            env["templates"] = templates
            return cap_envelope(env, settings)
        if not directory or not template:
            return error(22, "informe `directory` e `template` (ou use list=True)")
        if not _TEMPLATE_NAME_RE.match(template):
            return error(22, f"nome de template inválido: {template!r}")
        if err := ensure_in_workspace(directory, settings=settings):
            return err
        if force and not settings.allow_force:
            return error(
                13,
                "force=True desabilitado",
                "defina NOVOMODELO_MCP_ALLOW_FORCE=1 para sobrescrever arquivos",
            )
        argv = ["init", "--template", template]
        if force:
            argv.append("--force")
        argv.append(_cli_path(directory))
        env = run_novomodelo(argv, settings=settings, parse_json=False)
        if env.get("exit_code") == 0:
            attach_artifact(env, "case_dir", directory)
        return cap_envelope(env, settings)

    @mcp.tool(annotations=READ_ONLY)
    def run_plan(case_dir: str, time_budget_s: float = 900, threads: int | None = None) -> dict:
        """Planeja um run LOCAL do caso: estima tempo e memória. NÃO executa, NÃO grava.

        Lê config.json (forward_passes, iteration_limit, simulação), stages.json
        (estágios, num_openings) e system/*.json (dimensões). O tempo por solve
        (treino e simulação, separados) é MEDIDO em runs anteriores NESTA máquina:
        registro do MCP (runs via run_start, por machine_id) e, depois,
        metadata.json do workspace com o mesmo hostname. Prefere runs com a mesma
        modelagem; `time.range` mostra a dispersão entre candidatos. Threads:
        núcleos de performance em CPU híbrida (senão cores−1), ou o nº medido
        mais rápido; acima do maior nº medido NÃO assume ganho. Se não couber em
        `time_budget_s`, sugere reduzir forward_passes/iterações/aberturas
        (`apply_overrides` serve direto no run_apply).
        Veredito: cabe | cabe_com_ajustes | nao_cabe | indeterminado.
        Run local pequeno PODE NÃO CONVERGIR — serve p/ mecânica/comparação.
        """
        if err := ensure_in_workspace(case_dir, settings=settings):
            return err
        try:
            return make_plan(case_dir, settings, time_budget_s=time_budget_s, threads=threads)
        except Exception as exc:  # noqa: BLE001 - repassa como erro, não derruba
            return as_error(exc)

    @mcp.tool(annotations=DESTRUCTIVE)
    def run_apply(case_dir: str, overrides: dict, dry_run: bool = False) -> dict:
        """Aplica knobs de execução no config.json do caso (só config; nada mais).

        `overrides`: {"forward_passes": 2, "iteration_limit": 3,
        "simulation_scenarios": 20, "simulation_enabled": true} — tipicamente o
        `apply_overrides` devolvido pelo run_plan. Via deck_io.edit_json:
        valida contra o schema, backup `.bak` + escrita atômica. `dry_run` não grava.
        """
        if err := ensure_in_workspace(case_dir, settings=settings):
            return err
        if not overrides:
            return error(22, "`overrides` vazio")
        path = str(Path(case_dir) / "config.json")
        try:
            config = deck_io.read_json(path)
        except (OSError, ValueError) as exc:
            return error(2, f"não foi possível ler {path}", str(exc))
        changes = _knob_changes(config, overrides)
        if isinstance(changes, dict):
            return changes
        log(settings, "run_apply", path=path, changes=changes)
        return deck_io.edit_json(path, changes, schemas_dir=schemas_root(settings), dry_run=dry_run)

    @mcp.tool(annotations=DESTRUCTIVE)
    def run_start(
        case_dir: str,
        threads: int | None = None,
        output: str | None = None,
        time_budget_s: float = 900,
        override: bool = False,
        overwrite: bool = False,
    ) -> dict:
        """Dispara `novomodelo run` em BACKGROUND e devolve `job_id` na hora.

        Comando: `novomodelo run <case> --output <output> --threads N --comm-backend
        local`. `threads` default = o do plano (núcleos de performance em
        CPU híbrida, ou o nº medido mais rápido); `output` default =
        `<case_dir>/output`. Antes de lançar roda o run_plan: se o veredito
        for `nao_cabe`, RECUSA (salvo `override=True`). Um `output` com rodada
        concluída também é RECUSADO, com `suggested_output`: rodar de novo nele
        apaga a rodada anterior. `overwrite=True` só quando a pessoa pediu para
        substituir (ou para `resume`/`warm_start`/simulação da política salva nele).
        Acompanhe com run_status / run_logs; interrompa com run_cancel.
        """
        output = output or str(Path(case_dir) / "output")
        if err := ensure_in_workspace(case_dir, output, settings=settings):
            return err
        if not overwrite and _completed_run(Path(output)):
            return error(
                17,
                f"já há uma rodada concluída em {output}",
                "rodar de novo nela apaga a rodada anterior: use suggested_output, ou "
                "overwrite=True se a pessoa pediu para substituir",
                suggested_output=str(_free_output(Path(output))),
            )
        binpath = find_novomodelo(settings)
        if binpath is None:
            return error(
                127, "novomodelo não encontrado no PATH (defina NOVOMODELO_MCP_SOLVER_BIN)."
            )
        if threads is not None and threads < 1:
            return error(22, "threads deve ser >= 1")
        machine = detect_machine()
        try:
            plan = make_plan(
                case_dir, settings, time_budget_s=time_budget_s, threads=threads, machine=machine
            )
        except Exception as exc:  # noqa: BLE001
            return as_error(exc)
        if plan.get("status") != "ok":
            return plan
        if plan["verdict"] == "nao_cabe" and not override:
            return error(
                28,
                "plano diz 'nao_cabe' — run recusado",
                "ajuste com run_apply ou passe override=True",
                plan=plan,
            )
        n = threads or plan.get("target_threads") or 1
        cmd = [
            binpath,
            "--color",
            "never",
            "run",
            _cli_path(case_dir),
            "--output",
            _cli_path(output),
            "--threads",
            str(n),
            "--comm-backend",
            "local",
        ]
        jobs.prune_jobs(settings)
        try:
            meta = jobs.start_job(
                settings,
                cmd,
                max_running=settings.max_jobs,
                info={
                    "case_dir": case_dir,
                    "output": output,
                    "threads": n,
                    "machine_id": machine["machine_id"],
                    "plan_verdict": plan["verdict"],
                    "config_sig": read_case_params(case_dir)["config_sig"],
                    "estimated_seconds": ((plan.get("time") or {}).get("current") or {}).get(
                        "total_seconds"
                    ),
                },
            )
        except RuntimeError as busy:
            return error(
                16,
                f"limite de runs simultâneos atingido (NOVOMODELO_MCP_MAX_JOBS="
                f"{settings.max_jobs})",
                f"em andamento: {busy}",
            )
        except (OSError, TimeoutError) as exc:
            return as_error(exc)
        log(settings, "run_start", job_id=meta["job_id"], cmd=cmd)
        return {"status": "ok", **meta, "warnings": plan.get("warnings", [])}

    @mcp.tool(annotations=READ_ONLY)
    def run_status(job_id: str) -> dict:
        """Estado de um run: running | succeeded | failed | cancelled | lost.

        Inclui tempo decorrido, estimativa do plano e marcos de saída
        (`training/_SUCCESS`, `simulation/_SUCCESS`). `_SUCCESS` só indica que a
        saída foi gravada; veja `training.termination_reason` e `training.converged_at`
        para saber se convergiu. Se o run falhou, `scaling` repassa a razão de
        coeficientes do executável e, se for extrema, `heuristic_diagnosis`
        sugere a causa provável (heurística). Com o run concluído, use results_status /
        results_convergence no `output`.
        """
        st = jobs.job_state(settings, job_id)
        if st is None:
            return error(2, f"job inexistente: {job_id}")
        out = Path(st.get("output") or "")
        st["milestones"] = {
            phase: (out / phase / "_SUCCESS").exists() for phase in ("training", "simulation")
        }
        if (out / "training" / "metadata.json").is_file():
            try:
                meta = read_metadata(str(out))
            except (OSError, ValueError):  # metadata ainda sendo gravado: tenta na próxima
                meta = {}
            if meta.get("status") == "ok":
                st.update(termination_fields(meta["training"], meta.get("simulation")))
        if (
            st["state"] == "failed"
            or (st.get("training") or {}).get("termination_reason") == "error"
        ):
            st.update(numeric_diagnosis(str(out)))
        if st["state"] in ("failed", "lost"):
            st["stderr_tail"] = jobs.job_stderr(settings, job_id, lines=20)
        if st["state"] == "succeeded":
            harvest_calibrations(settings)
        return {"status": "ok", **st}

    @mcp.tool(annotations=READ_ONLY)
    def run_logs(job_id: str, lines: int = 100) -> dict:
        """Últimas `lines` linhas da saída do run (com teto de caracteres).

        `log` junta o stdout e o stderr do novomodelo na ordem de chegada, com as
        linhas do stderr marcadas `[stderr] `: o relatório do run (banner, progresso,
        resumos) sai no stderr até a 0.18.0 e no stdout a partir da 0.18.1; avisos e
        erros saem no stderr. Jobs de antes dessa junção trazem `stdout` e `stderr`.
        """
        logs = jobs.job_logs(
            settings, job_id, lines=max(1, lines), max_chars=settings.max_summary_chars
        )
        if logs is None:
            return error(2, f"job inexistente: {job_id}")
        return {"status": "ok", "job_id": job_id, **logs}

    @mcp.tool(annotations=DESTRUCTIVE)
    def run_cancel(job_id: str) -> dict:
        """Interrompe um run em andamento (encerra a árvore de processos; força se não sair).

        Funciona igual em Windows, macOS e Linux. Pode levar alguns segundos.
        """
        st = jobs.cancel_job(settings, job_id)
        if st is None:
            return error(2, f"job inexistente: {job_id}")
        return {"status": "ok", **st}
