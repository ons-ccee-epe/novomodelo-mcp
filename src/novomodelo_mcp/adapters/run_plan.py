"""Plano de execução local: lê os knobs do caso e estima tempo/memória. NÃO executa.

Fachada: só LÊ os arquivos do deck (config.json, stages.json, system/*.json) e
compõe o modelo de TEMPO de execução (`runtime.py`) com a máquina (`machine.py`).
"Custo" aqui é computacional (segundos), nunca custo de operação. As sugestões
são reduções mecânicas de knobs para caber num orçamento de tempo — não são
recomendação de modelagem.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from . import runtime

#: Knobs de config.json que o plano sabe sugerir/aplicar -> caminho no JSON.
CONFIG_KNOBS = {
    "forward_passes": "training.selection.forward_passes",
    "iteration_limit": "training.stopping_rules[type=iteration_limit].limit",
    "simulation_scenarios": "simulation.selection.num_scenarios",
    "simulation_enabled": "simulation.enabled",
}

#: Pisos das reduções sugeridas (abaixo disso o run perde sentido mecânico).
MIN_FORWARD_PASSES = 1
MIN_ITERATIONS = 2
MIN_OPENINGS = 2
#: Simulação: no máximo esta fração do orçamento; abaixo do piso de cenários, desliga.
SIM_MAX_SHARE = 0.5
MIN_SIM_SCENARIOS = 10

#: Gate fraco de memória: fração da RAM que dispara alerta / "não cabe".
MEM_WARN_FRACTION = 0.5
MEM_FAIL_FRACTION = 0.8

CONVERGENCE_WARNING = (
    "AVISO: um run local pequeno PODE NÃO CONVERGIR. Serve para validar a "
    "mecânica do caso e comparar variantes entre si nas MESMAS condições — "
    "não para obter uma política convergida."
)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def iteration_limit_of(config: dict[str, Any]) -> int | None:
    for rule in (config.get("training") or {}).get("stopping_rules") or []:
        if isinstance(rule, dict) and rule.get("type") == "iteration_limit":
            return rule.get("limit")
    return None


def read_case_params(case_dir: str) -> dict[str, Any]:
    """Knobs que dirigem o tempo de execução, lidos do caso (sem interpretação)."""
    root = Path(case_dir)
    config = _load(root / "config.json")
    stages_doc = _load(root / "stages.json")
    training = config.get("training") or {}
    selection = training.get("selection") or {}
    simulation = config.get("simulation") or {}
    sim_sel = simulation.get("selection") or {}
    stages = stages_doc.get("stages") or []
    openings = [int(s.get("num_openings") or 0) for s in stages]

    dims: dict[str, Any] = {"num_stages": len(stages)}
    system = root / "system"
    if system.is_dir():
        for f in sorted(system.glob("*.json")):
            try:
                doc = _load(f)
            except (OSError, ValueError):
                continue
            if isinstance(doc, dict):
                for key, value in doc.items():
                    if isinstance(value, list):
                        dims[f"num_{key}"] = len(value)

    sim_enabled = bool(simulation.get("enabled", False))
    return {
        "forward_passes": selection.get("forward_passes"),
        "selection_method": selection.get("method"),
        "iteration_limit": iteration_limit_of(config),
        "stopping_mode": training.get("stopping_mode"),
        "simulation_enabled": sim_enabled,
        "simulation_scenarios": sim_sel.get("num_scenarios") if sim_enabled else 0,
        "num_stages": len(stages),
        "openings_per_stage": openings,
        "openings": {"min": min(openings, default=0), "max": max(openings, default=0),
                     "mean": round(sum(openings) / len(openings), 2) if openings else 0},
        "max_order": (config.get("estimation") or {}).get("max_order", 6),
        "dimensions": dims,
        "config_sig": runtime.config_signature(config),
    }


def _public(est: dict[str, Any]) -> dict[str, Any]:
    """A estimativa sem os campos internos (prefixo `_`), para a resposta da tool."""
    return {k: v for k, v in est.items() if not k.startswith("_")}


def _cap_openings(openings: list[int], cap: int) -> list[int]:
    return [min(o, cap) for o in openings]


def _times(params: dict[str, Any], points: list[dict[str, Any]], threads: int,
           fwd: int, iters: int, openings: list[int], sim: int | None = None) -> dict[str, Any]:
    scen = (params["simulation_scenarios"] or 0) if sim is None else sim
    return runtime.estimate(
        points, threads, runtime.training_solves(iters, fwd, openings),
        runtime.simulation_solves(scen, params["num_stages"]))


def choose_threads(machine: dict[str, Any], ref: dict[str, Any] | None,
                   requested: int | None) -> tuple[int, str]:
    """Threads-alvo e a justificativa. Informado > medido mais rápido > hardware."""
    if requested:
        return int(requested), "informado"
    cores = machine.get("cpu_count") or 1
    if machine.get("performance_cpus"):
        t, basis = int(machine["performance_cpus"]), "núcleos de performance (CPU híbrida)"
    else:
        t, basis = max(1, cores - 1), "cores − 1"
    if ref and ref["level"] == 3 and len(ref["points"]) > 1:
        w_t = runtime.wall_per_solve(ref["points"], "train", t)
        best = min(ref["points"], key=lambda p: p["train"]["wall_per_solve"])
        if w_t and best["train"]["wall_per_solve"] < 0.97 * w_t[0]:
            t = int(best["threads"])
            basis = f"medido: {t} threads foi o mais rápido nesta máquina"
    return t, basis


def _range(params, candidates, threads, fwd, iters, openings) -> dict[str, Any] | None:
    """Estimativa por GRUPO de modelagem (assinatura do config) entre os candidatos.

    Cada grupo usa todos os seus pontos (um por nº de threads, o mais recente),
    como a referência principal — a dispersão reflete a modelagem, não artefato
    de reescalonamento de um ponto isolado.
    """
    groups: dict[str, dict[int, dict[str, Any]]] = {}
    for c in sorted(candidates, key=lambda c: c.get("completed_at") or ""):
        groups.setdefault(c.get("config_sig") or f"?{c.get('source')}", {})[
            int(c["threads"])] = c
    ests = []
    for pts in groups.values():
        e = _times(params, list(pts.values()), threads, fwd, iters, openings)
        if e:
            ests.append((e["total_seconds"], next(iter(pts.values()))))
    if not ests:
        return None
    lo, hi = min(ests, key=lambda x: x[0]), max(ests, key=lambda x: x[0])
    return {"min_seconds": lo[0], "max_seconds": hi[0], "n_groups": len(ests),
            "min_source": lo[1].get("source"), "max_source": hi[1].get("source"),
            "note": "estimativa por modelagem entre runs de mesmas dimensões; a "
                    "dispersão mostra o quanto a escolha da referência pesa"}


def _point_summary(p: dict[str, Any]) -> dict[str, Any]:
    return {"source": p.get("source"), "origin": p.get("origin", "workspace"),
            "threads": p["threads"], "completed_at": p.get("completed_at"),
            "training_wall_per_solve": round(p["train"]["wall_per_solve"], 5),
            "training_s_per_solve": p["train"].get("s_per_solve"),
            "simulation_wall_per_solve": round(p["sim"]["wall_per_solve"], 5)
            if p.get("sim") else None}


def estimate_memory(params: dict[str, Any], machine: dict[str, Any], threads: int,
                    fwd: int, iters: int) -> dict[str, Any]:
    """Gate FRACO: só o pool de cortes (cortes × coeficientes × cópias por thread).

    cortes ≈ fwd × iters × estágios; coeficientes ≈ hidros × (1 + max_order) + 1.
    Ignora LPs-base, árvore de cenários e buffers — é um piso, não um pico real.
    """
    hydros = params["dimensions"].get("num_hydros", 0)
    n_state = hydros * (1 + int(params.get("max_order") or 0))
    cuts = fwd * iters * params["num_stages"]
    pool = cuts * (n_state + 1) * 8 * (threads + 1)
    ram = machine.get("ram_bytes")
    frac = pool / ram if ram else None
    level = "ok"
    if frac is not None and frac >= MEM_FAIL_FRACTION:
        level = "nao_cabe"
    elif frac is not None and frac >= MEM_WARN_FRACTION:
        level = "alerta"
    return {"model": "cortes × (hidros×(1+max_order)+1) × 8 B × (threads+1)",
            "cuts": cuts, "state_dim": n_state, "cut_pool_bytes": pool,
            "cut_pool_gib": round(pool / 1024 ** 3, 3),
            "ram_fraction": round(frac, 4) if frac is not None else None,
            "level": level}


def build_plan(params: dict[str, Any], machine: dict[str, Any],
               ref: dict[str, Any] | None, time_budget_s: float,
               threads: int | None = None) -> dict[str, Any]:
    """Veredito determinístico a partir de (parâmetros, máquina, referência selecionada).

    `ref` é o resultado de `runtime.select_reference` (ou None sem pontos medidos).
    """
    fwd = params.get("forward_passes")
    iters = params.get("iteration_limit")
    openings = params["openings_per_stage"]
    warnings = [CONVERGENCE_WARNING]
    target, basis = choose_threads(machine, ref, threads)
    perf = machine.get("performance_cpus")
    if perf and target > perf:
        warnings.append(f"{target} threads > {perf} núcleos de performance: as threads "
                        "extras rodam em núcleos de eficiência e tendem a ATRASAR o run")

    current = {"forward_passes": fwd, "iteration_limit": iters,
               "openings": params["openings"],
               "simulation_scenarios": params["simulation_scenarios"],
               "threads": None}
    plan: dict[str, Any] = {
        "status": "ok", "machine": machine, "time_budget_s": time_budget_s,
        "params_current": current, "warnings": warnings,
        "dimensions": params["dimensions"], "target_threads": target,
        "threads_basis": basis,
    }

    if params.get("selection_method") not in (None, "sampled") or not fwd:
        plan.update(verdict="indeterminado", reference=None)
        warnings.append(f"seleção '{params.get('selection_method')}' sem forward_passes — "
                        "modelo de tempo só novomodelo 'sampled'")
        return plan
    if not iters:
        plan.update(verdict="indeterminado", reference=None)
        warnings.append("sem regra iteration_limit no config.json — duração ilimitada; "
                        "defina iteration_limit (run_apply) para estimar")
        return plan
    if ref is None:
        plan.update(verdict="indeterminado", reference=None)
        warnings.append("sem run anterior nesta máquina para medir o tempo por solve; "
                        "probe de calibração (1dtoy, 1 iteração) ainda não implementado. "
                        "Rode um caso uma vez nesta máquina (run_start) e replaneje.")
        return plan

    points = ref["points"]
    if ref["level"] == 2:
        warnings.append("nenhum run com a MESMA modelagem; referência tem só as mesmas "
                        "dimensões — o tempo por solve pode diferir (ver `time.range`)")
    elif ref["level"] == 1:
        warnings.append("nenhum run com as mesmas dimensões; referência é OUTRO caso — "
                        f"estimativa grosseira (o de tamanho mais parecido: "
                        f"{ref.get('size_ratio', '?')}× de diferença no tamanho do LP)")

    now = _times(params, points, target, fwd, iters, openings)
    sim0 = params["simulation_scenarios"] or 0
    s_fwd, s_iters, s_open, s_sim = fwd, iters, openings, sim0
    budget = float(time_budget_s)
    reduced: list[str] = []

    # 0) simulação: limitada a SIM_MAX_SHARE do orçamento (abaixo do piso, desligada)
    if now["total_seconds"] > budget and sim0 and \
            now["simulation_seconds"] > SIM_MAX_SHARE * budget:
        per_scen = now["simulation_seconds"] / sim0
        s_sim = math.floor(SIM_MAX_SHARE * budget / per_scen)
        if s_sim < MIN_SIM_SCENARIOS:
            s_sim = 0
        reduced.append("simulation_scenarios" if s_sim else "simulation_enabled")

    def t(f, i, o):
        return _times(params, points, target, f, i, o, s_sim)

    base = t(fwd, iters, openings)
    train_budget = budget - base["simulation_seconds"]
    base_train = base["_exact_training_seconds"]
    if base["total_seconds"] > budget and train_budget > 0 and base_train > 0:
        ratio = train_budget / base_train
        # 1) forward_passes e iterações reduzidos de forma balanceada (√ratio cada)
        s_fwd = max(MIN_FORWARD_PASSES, min(fwd, math.floor(fwd * math.sqrt(ratio))))
        per_iter = t(s_fwd, 1, openings)["_exact_training_seconds"]
        s_iters = (max(MIN_ITERATIONS, min(iters, math.floor(train_budget / per_iter)))
                   if per_iter > 0 else iters)
        if s_fwd != fwd:
            reduced.append("forward_passes")
        if s_iters != iters:
            reduced.append("iteration_limit")
        # 2) se ainda não cabe: teto de aberturas por estágio (stages.json)
        if t(s_fwd, s_iters, s_open)["total_seconds"] > budget:
            for cap in range(max(openings, default=0) - 1, MIN_OPENINGS - 1, -1):
                s_open = _cap_openings(openings, cap)
                if t(s_fwd, s_iters, s_open)["total_seconds"] <= budget:
                    break
            if s_open != openings:
                reduced.append("num_openings")

    sug = t(s_fwd, s_iters, s_open)
    mem = estimate_memory(params, machine, target, s_fwd, s_iters)
    fits_time = sug["total_seconds"] <= budget
    too_different = ref["level"] == 1 and \
        (ref.get("size_ratio") or 1) > runtime.MAX_SIZE_RATIO
    if too_different:
        warnings.append(f"a referência mais parecida tem tamanho {ref['size_ratio']}× "
                        f"diferente (> {runtime.MAX_SIZE_RATIO:.0f}×): o tempo não é "
                        "estimável. Rode o caso uma vez com poucas iterações "
                        "(run_apply iteration_limit=2) e replaneje.")
    if mem["level"] == "nao_cabe":
        verdict = "nao_cabe"
    elif too_different:            # tempo não estimável: não afirmar cabe nem não cabe
        verdict = "indeterminado"
    elif not fits_time:
        verdict = "nao_cabe"
    elif reduced:
        verdict = "cabe_com_ajustes"
    else:
        verdict = "cabe"
    if not fits_time and not too_different:
        warnings.append(f"nem com os pisos (fwd={MIN_FORWARD_PASSES}, iters={MIN_ITERATIONS}, "
                        f"aberturas={MIN_OPENINGS}, simulação ≤ {SIM_MAX_SHARE:.0%} do "
                        "orçamento) cabe; aumente time_budget_s")
    if mem["level"] != "ok":
        warnings.append(f"memória: pool de cortes estimado em {mem['cut_pool_gib']} GiB "
                        f"({mem['ram_fraction']:.0%} da RAM) — nível '{mem['level']}'")
    if "SEM ganho" in now["training_method"]:
        warnings.append(f"{target} threads acima do maior nº medido: estimativa assume que "
                        "mais threads NÃO aceleram (conservador)")
    warnings.extend(now["notes"])

    apply_overrides = {}
    if s_fwd != fwd:
        apply_overrides["forward_passes"] = s_fwd
    if s_iters != iters:
        apply_overrides["iteration_limit"] = s_iters
    if s_sim != sim0:
        if s_sim:
            apply_overrides["simulation_scenarios"] = s_sim
        else:
            apply_overrides["simulation_enabled"] = False
        warnings.append(f"simulação reduzida de {sim0} para {s_sim or 'nenhum'} cenário(s): "
                        "estatísticas de operação menos representativas")
    if reduced:
        warnings.append("parâmetros diferentes dos de outros runs/variantes tornam os "
                        "resultados NÃO comparáveis entre si — reduza todos igualmente")
    non_config = []
    if s_open != openings:
        non_config.append({"file": "stages.json", "path": "stages[*].num_openings",
                           "value": max(s_open),
                           "note": "fora do run_apply (não é knob de config); "
                                   "editar via deck_edit_json se desejado"})

    calc = (f"treino {sug['training_wall_per_solve']:.4f} s/solve × {sug['training_solves']}"
            f" + simulação {sug['simulation_wall_per_solve']:.4f} s/solve × "
            f"{sug['simulation_solves']} ≈ {sug['total_seconds']:.0f} s a {target} threads")
    plan.update({
        "verdict": verdict,
        "reference": {"level": ref["level_name"],
                      "points": [_point_summary(p) for p in points]},
        "time": {
            "model": "tempo ≈ (duração ÷ solves, medido nesta máquina) × solves; "
                     "solves_treino ≈ iters × fwd × Σ_estágios(1 + aberturas); "
                     "solves_sim ≈ cenários × estágios",
            "threads_rule": "nº de threads medido -> direto; entre dois medidos -> "
                            "interpolado; abaixo -> reescala linear; acima -> sem ganho",
            "target_threads": target,
            "current": _public(now),
            "suggested": _public(sug),
            "range": _range(params, ref["candidates"], target, s_fwd, s_iters, s_open),
            "calculation": calc,
        },
        "memory": mem,
        "params_suggested": {"forward_passes": s_fwd, "iteration_limit": s_iters,
                             "openings_max": max(s_open, default=0),
                             "simulation_scenarios": s_sim,
                             "threads": target},
        "reduced": reduced,
        "apply_overrides": apply_overrides,
        "non_config_changes": non_config,
        "alternatives": ([{"description": "parâmetros de treino atuais, simulação desligada",
                           "apply_overrides": {"simulation_enabled": False},
                           "total_seconds": now["training_seconds"]}] if sim0 else []),
    })
    return plan
