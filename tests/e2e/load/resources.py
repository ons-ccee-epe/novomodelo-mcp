"""CPU e memória dos processos do servidor durante a carga (opcional, via psutil).

O motor é o único pai dos servidores, então os descendentes dele são exatamente
a árvore de servidores medida. Sem psutil o relatório diz ``available: false`` e
a carga segue normalmente.
"""
from __future__ import annotations

import os
from types import ModuleType
from typing import Any

__all__ = ["ResourceSampler", "load_psutil", "summarize_resources"]

_MB = 1024 * 1024


def load_psutil() -> ModuleType | None:
    try:
        import psutil
    except ImportError:
        return None
    return psutil


class ResourceSampler:
    """Soma CPU% e RSS dos descendentes de ``root_pid`` a cada ``sample()``."""

    def __init__(self, psutil_module: Any, root_pid: int | None = None) -> None:
        self._psutil = psutil_module
        self._root_pid = root_pid if root_pid is not None else os.getpid()
        # cpu_percent é relativo à chamada anterior no mesmo objeto Process.
        self._known: dict[int, Any] = {}

    def sample(self) -> dict[str, float | int] | None:
        """``cpu_percent`` (soma, pode passar de 100), ``rss_mb`` e ``processes``; None se falhar."""
        psutil = self._psutil
        try:
            children = psutil.Process(self._root_pid).children(recursive=True)
        except psutil.Error:
            return None

        alive: dict[int, Any] = {}
        cpu = 0.0
        rss = 0
        for child in children:
            process = self._known.get(child.pid, child)
            try:
                cpu += process.cpu_percent(interval=None)
                rss += process.memory_info().rss
            except psutil.Error:
                continue
            alive[child.pid] = process
        self._known = alive
        return {"cpu_percent": cpu, "rss_mb": rss / _MB, "processes": len(alive)}


def summarize_resources(samples: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Bloco ``resources`` do resultado; ``samples`` é None quando não há psutil."""
    if samples is None:
        return {"available": False, "reason": "psutil não instalado"}
    if not samples:
        return {"available": True, "samples": [], "reason": "nenhuma amostra coletada"}
    cpu = [s["cpu_percent"] for s in samples]
    return {
        "available": True,
        "samples": samples,
        "avg_cpu_percent": sum(cpu) / len(cpu),
        "peak_cpu_percent": max(cpu),
        "peak_rss_mb": max(s["rss_mb"] for s in samples),
        "peak_processes": max(s["processes"] for s in samples),
    }
