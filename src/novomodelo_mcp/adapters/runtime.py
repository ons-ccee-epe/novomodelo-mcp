"""Modelo de TEMPO DE EXECUÇÃO de um run (custo computacional — não custo de operação).

Tudo é MEDIDO nesta máquina, nunca constante. Cada run anterior vira um "ponto":

  threads              threads do run (distribution.threads_per_rank)
  treino.wall/solve    = duration_seconds / total_lp_solves   (training/metadata.json)
  simul.wall/solve     = duration_seconds / total_lp_solves   (simulation/metadata.json)
  s_per_solve          = segundos de solver somados nas threads / solves (só informativo)

O wall/solve já embute tudo o que o relógio vê: solver, espera entre threads
(barreiras do SDDP), seleção de cortes, setup. Previsão:

  tempo ≈ wall/solve(threads_alvo) × solves

e wall/solve(T) vem dos pontos medidos SEM extrapolar ganho:
  - T medido               -> o próprio ponto
  - T entre dois medidos   -> interpolação linear
  - T abaixo do menor      -> reescala linear (menos threads => proporcionalmente mais lento)
  - T acima do maior       -> NÃO assume ganho (CPU híbrida/memória podem até piorar)

Semelhança da referência (níveis): mesma modelagem (dimensões + assinatura do
config) > mesmas dimensões > outro caso. A assinatura do config ignora apenas os
knobs que o próprio plano varia (forward_passes, parada, simulação, sementes).

Fontes dos pontos:
  1. registro de calibração do MCP (`calibration.json` no state dir), alimentado
     por runs do run_start e indexado por `machine_id` (independe de hostname);
  2. `training/metadata.json` no workspace com o mesmo hostname NORMALIZADO.
Sem pontos: `calibration_probe` é o gancho (1dtoy, 1 iteração) — não implementado.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .machine import normalize_hostname
from .state import atomic_write_text, file_lock

#: Teto de entradas no registro de calibração (mantém as mais recentes).
MAX_CALIBRATIONS = 200
REGISTRY_VERSION = 2

#: Dimensões comparadas entre caso e referência (chaves de problem_dimensions).
DIM_KEYS = ("num_stages", "num_hydros", "num_thermals", "num_buses", "num_lines")

#: Partes do config.json que NÃO entram na assinatura: as que o plano varia ou
#: que não mudam o LP (saídas, sementes, simulação).
_SIG_EXCLUDE = (("$schema",), ("exports",), ("simulation",),
                ("training", "selection"), ("training", "stopping_rules"),
                ("training", "stopping_mode"), ("training", "scenario_source"),
                ("training", "tree_seed"))

LEVELS = {3: "mesma_modelagem", 2: "mesmas_dimensoes", 1: "outro_caso"}

#: Pastas que nunca contêm runs do Novomodelo (poda da busca).
_SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".ruff_cache",
              ".pytest_cache", "scenarios", "system", "simulation", "policy"}


# ── assinatura do caso ────────────────────────────────────────────────────────

def config_signature(config: dict[str, Any] | None) -> str | None:
    if not isinstance(config, dict):
        return None
    cfg = copy.deepcopy(config)
    for path in _SIG_EXCLUDE:
        node = cfg
        for key in path[:-1]:
            node = node.get(key) if isinstance(node, dict) else None
        if isinstance(node, dict):
            node.pop(path[-1], None)
    blob = json.dumps(cfg, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()[:12]


def dims_of(d: dict[str, Any] | None) -> dict[str, Any]:
    d = d or {}
    return {k: d.get(k) or 0 for k in DIM_KEYS}  # arquivo ausente (ex.: lines) == 0


# ── pontos medidos ────────────────────────────────────────────────────────────

def _phase(meta: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(meta, dict):
        return None
    stats = meta.get("solve_stats") or {}
    total = stats.get("total_lp_solves") or 0
    duration = meta.get("duration_seconds")
    if total <= 0 or not duration:
        return None
    solver_s = stats.get("solve_seconds")
    if solver_s is None:
        solver_s = (stats.get("forward_solve_seconds") or 0.0) + \
            (stats.get("backward_solve_seconds") or 0.0)
    return {"solves": total, "duration_s": duration,
            "wall_per_solve": duration / total,
            "s_per_solve": (solver_s / total) if solver_s else None}


def point_from_run(train_meta: dict[str, Any], sim_meta: dict[str, Any] | None = None, *,
                   source: str | None = None, config: dict[str, Any] | None = None,
                   config_sig: str | None = None) -> dict[str, Any] | None:
    """Um ponto (threads -> wall/solve de treino e simulação). None se não servir."""
    train = _phase(train_meta)
    if train is None:
        return None
    dist = train_meta.get("distribution") or {}
    stats = train_meta.get("solve_stats") or {}
    return {
        "source": source,
        "hostname": train_meta.get("hostname"),
        "threads": dist.get("threads_per_rank") or stats.get("parallelism") or 1,
        "ranks": dist.get("world_size") or 1,
        "completed_at": train_meta.get("completed_at"),
        "dims": dims_of(train_meta.get("problem_dimensions")),
        "config_sig": config_sig or config_signature(config),
        "train": train,
        "sim": _phase(sim_meta),
    }


def _load_json(p: Path) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_run(meta_path: Path, *, config_sig: str | None = None) -> dict[str, Any] | None:
    """Lê `<out>/training/metadata.json` (+ simulation/metadata.json e o config.json
    do caso, quando o output está dentro dele)."""
    train = _load_json(meta_path)
    if not isinstance(train, dict):
        return None
    out = meta_path.parent.parent
    sim = _load_json(out / "simulation" / "metadata.json")
    config = None if config_sig else _load_json(out.parent / "config.json")
    return point_from_run(train, sim, source=str(meta_path), config=config,
                          config_sig=config_sig)


def _iter_metadata(root: Path, max_depth: int):
    root_depth = len(root.parts)
    for dirpath, dirnames, filenames in os.walk(root):
        here = Path(dirpath)
        if here.name == "training" and "metadata.json" in filenames:
            yield here / "metadata.json"
            dirnames[:] = []
            continue
        if len(here.parts) - root_depth >= max_depth:
            dirnames[:] = []
            continue
        dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS
                             and not d.startswith("."))


def find_reference_runs(search_roots: list[str], hostname: str, *,
                        max_depth: int = 6) -> list[dict[str, Any]]:
    """Pontos de runs anteriores no MESMO hostname (normalizado), sem duplicatas."""
    seen: set[str] = set()
    found: list[dict[str, Any]] = []
    host = normalize_hostname(hostname)
    for r in search_roots:
        root = Path(r)
        if not root.is_dir():
            continue
        for meta_path in _iter_metadata(root.resolve(), max_depth):
            if str(meta_path) in seen:
                continue
            seen.add(str(meta_path))
            point = load_run(meta_path)
            if point and normalize_hostname(point["hostname"]) == host:
                found.append(point)
    return found


# ── registro de calibração (por machine_id) ───────────────────────────────────

def load_calibrations(path: Path, machine_id: str | None = None) -> list[dict[str, Any]]:
    data = _load_json(path)
    if not isinstance(data, dict) or data.get("version") != REGISTRY_VERSION:
        return []  # formato antigo/ausente: ignorado (os runs são recolhidos de novo)
    entries = [e for e in data.get("entries") or [] if isinstance(e, dict)]
    if machine_id is not None:
        entries = [e for e in entries if e.get("machine_id") == machine_id]
    return entries


def record_calibration(path: Path, machine_id: str, point: dict[str, Any]) -> None:
    """Grava/atualiza (por `source`) o ponto de um run desta máquina."""
    with file_lock(path.with_name(path.name + ".lock")):
        entries = [e for e in load_calibrations(path)
                   if e.get("source") != point.get("source")]
        entries.append({**point, "machine_id": machine_id, "origin": "run_start"})
        atomic_write_text(path, json.dumps(
            {"version": REGISTRY_VERSION, "entries": entries[-MAX_CALIBRATIONS:]},
            indent=1, ensure_ascii=False))


def calibration_probe(*_args, **_kwargs) -> dict[str, Any] | None:
    """GANCHO: medir a máquina rodando o template `1dtoy` por 1 iteração.

    Ainda não implementado — devolve None; o plano reporta "sem referência".
    Útil sobretudo como razão de velocidade ENTRE máquinas (o LP do 1dtoy é
    ordens de grandeza menor que o de um caso real).
    """
    return None


# ── seleção da referência ─────────────────────────────────────────────────────

def match_level(point: dict[str, Any], case_dims: dict[str, Any], case_sig: str | None,
                case_dir: str | None = None) -> int:
    if dims_of(point.get("dims")) != dims_of(case_dims):
        return 1
    psig = point.get("config_sig")
    if case_sig and psig == case_sig:
        return 3
    if psig is None and case_dir and point.get("source") and \
            Path(point["source"]).is_relative_to(Path(case_dir).resolve()):
        return 3  # run do próprio caso sem assinatura conhecida
    return 2


#: Entidades que crescem o LP de cada estágio (o nº de estágios já entra na conta
#: de solves). Proxy de tamanho para comparar casos DIFERENTES.
_SIZE_KEYS = ("num_hydros", "num_thermals", "num_buses", "num_lines")

#: Acima desta razão de tamanho (para mais ou para menos) a referência de outro
#: caso não serve: o plano devolve `indeterminado`.
MAX_SIZE_RATIO = 10.0


def lp_size(dims: dict[str, Any] | None) -> int:
    d = dims_of(dims)
    return max(1, sum(int(d[k]) for k in _SIZE_KEYS))


def size_ratio(point: dict[str, Any], case_dims: dict[str, Any]) -> float:
    """Quantas vezes o caso é maior (ou menor) que a referência; sempre ≥ 1."""
    a, b = lp_size(point.get("dims")), lp_size(case_dims)
    return max(a, b) / min(a, b)


def _is_own(point: dict[str, Any], case_dir: str | None) -> bool:
    return bool(case_dir and point.get("source")) and \
        Path(point["source"]).is_relative_to(Path(case_dir).resolve())


def select_reference(points: list[dict[str, Any]], case_dims: dict[str, Any],
                     case_sig: str | None, case_dir: str | None = None
                     ) -> dict[str, Any] | None:
    """Melhor nível disponível; dentro dele, UM ponto por nº de threads
    (próprio caso > mais recente). Devolve também os candidatos p/ a faixa."""
    if not points:
        return None
    scored = [(match_level(p, case_dims, case_sig, case_dir), p) for p in points]
    level = max(s for s, _ in scored)
    pool = [p for s, p in scored if s == level]
    if level == 1:
        # o de tamanho mais parecido, não o mais recente: o mais recente pode ser um
        # caso de brinquedo e subestimar o tempo em ordens de grandeza.
        best = min(size_ratio(p, case_dims) for p in pool)
        pool = [p for p in pool if size_ratio(p, case_dims) == best]
    by_threads: dict[int, dict[str, Any]] = {}
    for p in sorted(pool, key=lambda p: (_is_own(p, case_dir), p.get("completed_at") or "")):
        by_threads[int(p["threads"])] = p  # o último (melhor) vence
    chosen = [by_threads[t] for t in sorted(by_threads)]
    return {"level": level, "level_name": LEVELS[level], "points": chosen,
            "size_ratio": round(max(size_ratio(p, case_dims) for p in chosen), 2),
            "candidates": [p for s, p in scored if s >= 2] or [p for _, p in scored]}


# ── estimativa ────────────────────────────────────────────────────────────────

def wall_per_solve(points: list[dict[str, Any]], phase: str, threads: int
                   ) -> tuple[float, str] | None:
    """wall/solve no nº de threads alvo, sem extrapolar ganho. (valor, método)."""
    pts = sorted((int(p["threads"]), p[phase]["wall_per_solve"])
                 for p in points if p.get(phase))
    if not pts:
        return None
    t = max(1, int(threads))
    for tp, w in pts:
        if tp == t:
            return w, f"medido a {tp} threads"
    lo, hi = pts[0], pts[-1]
    if t < lo[0]:
        return lo[1] * lo[0] / t, (f"reescalado de {lo[0]} p/ {t} threads "
                                   "(linear, menos threads)")
    if t > hi[0]:
        return hi[1], (f"medido a {hi[0]} threads, SEM ganho assumido p/ {t} "
                       "(acima do maior ponto medido)")
    for (t0, w0), (t1, w1) in zip(pts, pts[1:], strict=False):
        if t0 < t < t1:
            return w0 + (w1 - w0) * (t - t0) / (t1 - t0), \
                f"interpolado entre {t0} e {t1} threads"
    return hi[1], "medido"  # inalcançável


def estimate(points: list[dict[str, Any]], threads: int, train_solves: int,
             sim_solves: int) -> dict[str, Any] | None:
    tr = wall_per_solve(points, "train", threads)
    if tr is None:
        return None
    notes = []
    sim = wall_per_solve(points, "sim", threads) if sim_solves else (0.0, "sem simulação")
    if sim is None:
        sim = tr
        notes.append("simulação sem medição: usando o wall/solve do treino")
    t_tr, t_sim = tr[0] * train_solves, sim[0] * sim_solves
    return {"training_solves": train_solves, "simulation_solves": sim_solves,
            "training_wall_per_solve": round(tr[0], 5), "training_method": tr[1],
            "simulation_wall_per_solve": round(sim[0], 5), "simulation_method": sim[1],
            "training_seconds": round(t_tr, 1), "simulation_seconds": round(t_sim, 1),
            "total_seconds": round(t_tr + t_sim, 1), "notes": notes,
            # valor sem arredondar, só para contas internas do plano (sai antes da resposta):
            # o arredondado vira 0.0 em casos minúsculos e quebrava divisões.
            "_exact_training_seconds": t_tr}


def training_solves(iters: int, forward_passes: int, openings: list[int]) -> int:
    """solves ≈ iters × forward_passes × Σ_estágios (1 + aberturas)."""
    return iters * forward_passes * sum(1 + o for o in openings)


def simulation_solves(num_scenarios: int, n_stages: int) -> int:
    return num_scenarios * n_stages
