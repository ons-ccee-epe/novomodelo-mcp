"""Quantas sessões simultâneas esta máquina aguenta, por modo, provedor e seleção.

Fórmula, com o custo por sessão medido nas cargas gravadas do mesmo modo (e provedor) e do
mesmo perfil de seleção, ou, sem histórico, a estimativa conservadora de ``DEFAULT_COST``:

    memória = piso(MB disponíveis × (1 − MEMORY_HEADROOM) ÷ MB por sessão)
    CPU     = piso((núcleos lógicos − RESERVED_CORES) ÷ núcleos por sessão)
    disco   = piso(MB livres na pasta do run × (1 − DISK_HEADROOM) ÷ MB de disco por sessão)
    recomendado = max(1, min(teto do modo, memória, CPU, disco))

O perfil é ``pesada`` quando a seleção tem tool que sobe o bridge ou a CLI do solver
(``mix.is_heavy_tool``) e ``leve`` no resto; o histórico de um perfil não estima o outro.
O disco só entra quando a seleção grava: cada sessão copia as subárvores das fixtures que a
seleção usa (o tamanho medido agora) e reserva ``SANDBOX_GROWTH`` a mais para o que as tools
gravam na cópia.

O custo por sessão de uma carga gravada é o pico de RSS (e a CPU média) da árvore de
processos dividido pelas sessões que subiram; entre as cargas recentes vale o maior, para
errar para menos sessões. Memória e disco livres são instantâneos do momento da consulta.
Sem psutil só os núcleos (e o disco) entram, com um aviso.
"""
from __future__ import annotations

import math
import os
import shutil
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tests.e2e.load.agent_cases import expected_tools, plan_for_cases
from tests.e2e.load.agent_engine import MAX_AGENT_CONCURRENCY
from tests.e2e.load.engine import MAX_CONCURRENCY
from tests.e2e.load.mix import is_heavy_tool, select_specs, writes_files
from tests.e2e.load.resources import load_psutil
from tests.e2e.load.sandbox import DISK_HEADROOM, SANDBOX_GROWTH, SandboxPlan, plan_for_specs
from tests.e2e.load.store import LoadStore, record_is_heavy, record_mode
from tests.e2e.queries.models import QueryTestCase

__all__ = [
    "DEFAULT_COST",
    "HARD_CAPS",
    "HISTORY_RUNS",
    "MEMORY_HEADROOM",
    "RESERVED_CORES",
    "SelectionProfile",
    "SessionCost",
    "cases_profile",
    "estimate_capacity",
    "history_cost",
    "tools_profile",
]

HARD_CAPS: dict[str, int] = {"tools": MAX_CONCURRENCY, "agent": MAX_AGENT_CONCURRENCY}
MEMORY_HEADROOM = 0.25
RESERVED_CORES = 1
HISTORY_RUNS = 10
_MB = 1024 * 1024
# Num empate, o teto fixo explica melhor o número do que um recurso que só coincide com ele.
_TIE_ORDER = ("teto do modo", "memória", "CPU", "disco")
_PROFILES = {False: "leve", True: "pesada"}


@dataclass(frozen=True)
class SessionCost:
    """Custo de uma sessão: RSS em MB e fração de um núcleo lógico."""

    rss_mb: float
    cpu_cores: float
    source: str
    runs: int = 0


@dataclass(frozen=True)
class SelectionProfile:
    """O que a seleção pede da máquina: tools pesadas, tools que gravam e a cópia por sessão."""

    heavy_tools: tuple[str, ...] = ()
    write_tools: tuple[str, ...] = ()
    sandbox: SandboxPlan | None = None

    @property
    def heavy(self) -> bool:
        return bool(self.heavy_tools)

    @property
    def writes(self) -> bool:
        return self.sandbox is not None and self.sandbox.enabled

    def describe(self) -> dict[str, Any]:
        plan = self.sandbox
        return {
            "heavy": self.heavy,
            "writes": self.writes,
            "heavy_tools": list(self.heavy_tools),
            "write_tools": list(self.write_tools),
            "copy_mb": plan.copy_mb if plan is not None and plan.enabled else 0.0,
            "subtrees": list(plan.subtrees) if plan is not None else [],
        }


def tools_profile(fixtures_dir: str | Path, tools: Iterable[str] | None) -> SelectionProfile:
    """Perfil do mix do modo tools (``None`` = o mix padrão), com as fontes presentes.

    Raises:
        ValueError: Se ``tools`` pede algo fora do catálogo.
    """
    specs = select_specs(fixtures_dir, tools).specs
    return SelectionProfile(
        heavy_tools=tuple(sorted({s.tool for s in specs if s.heavy})),
        write_tools=tuple(sorted({s.tool for s in specs if s.writes})),
        sandbox=plan_for_specs(fixtures_dir, specs),
    )


def cases_profile(fixtures_dir: str | Path, cases: Iterable[QueryTestCase]) -> SelectionProfile:
    """Perfil dos casos elegíveis de uma seleção do modo agent."""
    cases = list(cases)
    tools = {tool for case in cases for tool in expected_tools(case)}
    return SelectionProfile(
        heavy_tools=tuple(sorted(t for t in tools if is_heavy_tool(t))),
        write_tools=tuple(sorted(t for t in tools if writes_files(t))),
        sandbox=plan_for_cases(fixtures_dir, cases),
    )


# Sem histórico, por modo e perfil (False = leve, True = pesada). tools leve: um servidor
# MCP em Python com pyarrow/duckdb carregados, chamado sem pausa (ocupa um núcleo). tools
# pesada: o servidor e o bridge que ele sobe; medido numa conversão NEWAVE, os dois passam
# de 350 MB e de um núcleo nos picos. agent leve: o CLI do agente (node/Rust), o
# servidor MCP e os filhos do CLI, quase sempre esperando o modelo; agent pesada: isso e o
# bridge enquanto ele converte.
DEFAULT_COST: dict[tuple[str, bool], SessionCost] = {
    ("tools", False): SessionCost(rss_mb=150.0, cpu_cores=1.0, source="estimativa"),
    ("tools", True): SessionCost(rss_mb=500.0, cpu_cores=1.5, source="estimativa"),
    ("agent", False): SessionCost(rss_mb=600.0, cpu_cores=0.5, source="estimativa"),
    ("agent", True): SessionCost(rss_mb=1100.0, cpu_cores=1.0, source="estimativa"),
}


def _sessions_started(record: dict[str, Any]) -> int:
    if record_mode(record) == "agent":
        return int((record.get("sessions") or {}).get("started") or 0)
    return int((record.get("startup") or {}).get("started") or 0)


def history_cost(records: Iterable[dict[str, Any]]) -> SessionCost | None:
    """Maior custo por sessão entre as cargas com recursos medidos; None se nenhuma serve."""
    rss: list[float] = []
    cpu: list[float] = []
    for record in records:
        resources = record.get("resources") or {}
        started = _sessions_started(record)
        peak = resources.get("peak_rss_mb")
        if not resources.get("available") or not started or not peak:
            continue
        rss.append(float(peak) / started)
        cpu.append(float(resources.get("avg_cpu_percent") or 0.0) / 100.0 / started)
    if not rss:
        return None
    return SessionCost(rss_mb=max(rss), cpu_cores=max(cpu), source="histórico", runs=len(rss))


def _matching_records(
    store: LoadStore,
    mode: str,
    provider: str | None,
    heavy: bool,
    limit: int = HISTORY_RUNS,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for entry in store.list_runs():
        if record_mode(entry) != mode:
            continue
        if mode == "agent" and provider and (entry.get("config") or {}).get("provider") != provider:
            continue
        try:
            record = store.load(entry["load_id"])
        except (OSError, ValueError, KeyError):
            continue
        if record_is_heavy(record) != heavy:
            continue
        records.append(record)
        if len(records) >= limit:
            break
    return records


def _fmt(value: float) -> str:
    return f"{value:.0f}" if value >= 10 else f"{value:.1f}".replace(".", ",")


def _disk(profile: SelectionProfile, work_dir: str, disk_usage: Callable[[str], Any]):
    plan = profile.sandbox
    if plan is None or not plan.enabled:
        return None, None
    free_mb = disk_usage(work_dir).free / _MB
    per_session = max(plan.per_session_mb, 1.0)
    limit = max(math.floor(free_mb * (1 - DISK_HEADROOM) / per_session), 0)
    info = {
        "path": work_dir,
        "free_mb": free_mb,
        "copy_mb": plan.copy_mb,
        "growth": SANDBOX_GROWTH,
        "per_session_mb": plan.per_session_mb,
        "headroom": DISK_HEADROOM,
    }
    return info, limit


def _detail(factor, mode, hard_cap, cores, cost, memory, disk) -> str:
    headroom_pct = round(MEMORY_HEADROOM * 100)
    if factor == "memória" and memory is not None:
        return (
            f"limitado por memória ({_fmt(memory['available_mb'])} MB livres × "
            f"{100 - headroom_pct}% ÷ {_fmt(cost.rss_mb)} MB/sessão, folga de {headroom_pct}%)"
        )
    if factor == "CPU":
        return (
            f"limitado por CPU ({cores} núcleos lógicos − {RESERVED_CORES} reservado ÷ "
            f"{_fmt(cost.cpu_cores)} núcleo/sessão)"
        )
    if factor == "disco" and disk is not None:
        disk_pct = round(DISK_HEADROOM * 100)
        return (
            f"limitado por disco ({_fmt(disk['free_mb'])} MB livres × {100 - disk_pct}% ÷ "
            f"{_fmt(disk['per_session_mb'])} MB/sessão: cópia de {_fmt(disk['copy_mb'])} MB "
            f"das fixtures + {round(SANDBOX_GROWTH * 100)}% para o que as tools gravam)"
        )
    return f"limitado pelo teto do modo {mode} ({hard_cap})"


def estimate_capacity(
    mode: str,
    provider: str | None = None,
    store: LoadStore | None = None,
    psutil_loader: Callable[[], Any] = load_psutil,
    cpu_count: Callable[[], int | None] = os.cpu_count,
    profile: SelectionProfile | None = None,
    work_dir: str | None = None,
    disk_usage: Callable[[str], Any] = shutil.disk_usage,
) -> dict[str, Any]:
    """Máximo recomendado de sessões simultâneas, o fator que o limita e a explicação.

    Args:
        profile: O que a seleção pede (pesada, grava, cópia); None = seleção leve, sem cópia.
        work_dir: Pasta onde as sessões copiam as fixtures (default: o TEMP).

    Raises:
        ValueError: Se ``mode`` não é ``tools`` nem ``agent``.
    """
    if mode not in HARD_CAPS:
        raise ValueError(f"modo desconhecido: {mode} (aceitos: {', '.join(HARD_CAPS)})")
    profile = profile or SelectionProfile()
    hard_cap = HARD_CAPS[mode]
    warnings: list[str] = []
    profile_name = _PROFILES[profile.heavy]

    cost = history_cost(_matching_records(store, mode, provider, profile.heavy)) if store else None
    if cost is None:
        cost = DEFAULT_COST[(mode, profile.heavy)]
        scope = f"{mode}/{provider}" if mode == "agent" and provider else mode
        warnings.append(
            f"sem carga gravada com recursos medidos para {scope} com seleção {profile_name}: "
            "custo por sessão estimado"
        )

    cores = cpu_count() or 1
    usable_cores = max(cores - RESERVED_CORES, 1)
    cpu_limit = max(math.floor(usable_cores / cost.cpu_cores), 0) if cost.cpu_cores > 0 else hard_cap

    psutil = psutil_loader()
    memory: dict[str, float] | None = None
    memory_limit: int | None = None
    if psutil is None:
        warnings.append("psutil não instalado: a memória não entra no limite (pip install psutil)")
    else:
        vm = psutil.virtual_memory()
        memory = {"total_mb": vm.total / _MB, "available_mb": vm.available / _MB}
        budget = memory["available_mb"] * (1 - MEMORY_HEADROOM)
        memory_limit = max(math.floor(budget / cost.rss_mb), 0)

    disk, disk_limit = _disk(profile, work_dir or tempfile.gettempdir(), disk_usage)

    limits = {"teto do modo": hard_cap, "CPU": cpu_limit}
    if memory_limit is not None:
        limits["memória"] = memory_limit
    if disk_limit is not None:
        limits["disco"] = disk_limit
    factor = min(limits, key=lambda name: (limits[name], _TIE_ORDER.index(name)))
    lowest = min(limits.values())
    recommended = max(1, lowest)
    if lowest < 1:
        warnings.append(f"{factor} insuficiente até para 1 sessão: a carga pode degradar a máquina")

    detail = _detail(factor, mode, hard_cap, cores, cost, memory, disk)
    origin = (
        f"custo de seleção {profile_name} medido em {cost.runs} carga(s) gravada(s)"
        if cost.source == "histórico"
        else f"custo por sessão de seleção {profile_name} estimado, sem histórico"
    )
    return {
        "mode": mode,
        "provider": provider if mode == "agent" else None,
        "hard_cap": hard_cap,
        "recommended": recommended,
        "limiting_factor": factor,
        "limits": {
            "hard_cap": hard_cap,
            "cpu": cpu_limit,
            "memory": memory_limit,
            "disk": disk_limit,
        },
        "explanation": f"≈ {recommended} sessões: {detail}; {origin}.",
        "cpu": {"logical_cores": cores, "reserved_cores": RESERVED_CORES},
        "memory": memory,
        "per_session": {
            "rss_mb": cost.rss_mb,
            "cpu_cores": cost.cpu_cores,
            "source": cost.source,
            "runs": cost.runs,
            "profile": profile_name,
        },
        "selection": profile.describe(),
        "disk": disk,
        "memory_headroom": MEMORY_HEADROOM,
        "warnings": warnings,
    }
