"""Estatísticas da carga: percentis, agregação por tool e série temporal.

A latência (min/média/percentis/max) abrange só as chamadas ``ok``: o tempo de
uma chamada que estourou o timeout é o próprio limite, não o de uma resposta, e
uma falha rápida puxaria a média para baixo. Erros e timeouts entram na taxa de
erro, que é ``(erros + timeouts) / chamadas``.
"""

from __future__ import annotations

import math
from bisect import insort
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

__all__ = [
    "BUCKET_SECONDS",
    "LiveStats",
    "Outcome",
    "Sample",
    "aggregate",
    "percentile",
    "summarize",
    "time_series",
]

Outcome = Literal["ok", "error", "timeout"]

BUCKET_SECONDS = 1.0

_LATENCY_KEYS = ("min_ms", "mean_ms", "p50_ms", "p95_ms", "p99_ms", "max_ms")


@dataclass(frozen=True)
class Sample:
    """Uma chamada concluída: ``started_s`` conta a partir do início da carga."""

    tool: str
    started_s: float
    latency_ms: float
    outcome: Outcome
    error: str | None = None

    @property
    def ended_s(self) -> float:
        return self.started_s + self.latency_ms / 1000.0


def percentile(sorted_values: Sequence[float], p: float) -> float:
    """Percentil ``p`` (0..100) por interpolação linear entre postos vizinhos.

    Mesma definição do default do numpy: posto ``p/100 * (n - 1)``. Para ``n == 1``
    devolve o único valor.

    Raises:
        ValueError: Sem valores, ou ``p`` fora de 0..100.
    """
    if not sorted_values:
        raise ValueError("percentil de uma lista vazia")
    if not 0 <= p <= 100:
        raise ValueError(f"percentil fora de 0..100: {p}")
    rank = p / 100.0 * (len(sorted_values) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return float(sorted_values[low])
    fraction = rank - low
    return float(sorted_values[low] + (sorted_values[high] - sorted_values[low]) * fraction)


def _latency_stats(latencies_ms: Iterable[float]) -> dict[str, float | None]:
    ordered = sorted(latencies_ms)
    if not ordered:
        return dict.fromkeys(_LATENCY_KEYS)
    return {
        "min_ms": float(ordered[0]),
        "mean_ms": sum(ordered) / len(ordered),
        "p50_ms": percentile(ordered, 50),
        "p95_ms": percentile(ordered, 95),
        "p99_ms": percentile(ordered, 99),
        "max_ms": float(ordered[-1]),
    }


def summarize(samples: Sequence[Sample], duration_s: float) -> dict[str, Any]:
    """Contagens, taxa de erro, vazão (chamadas/s) e latência de um conjunto de chamadas."""
    calls = len(samples)
    ok = sum(1 for s in samples if s.outcome == "ok")
    errors = sum(1 for s in samples if s.outcome == "error")
    timeouts = sum(1 for s in samples if s.outcome == "timeout")
    return {
        "calls": calls,
        "ok": ok,
        "errors": errors,
        "timeouts": timeouts,
        "error_rate": (errors + timeouts) / calls if calls else 0.0,
        "throughput_cps": calls / duration_s if duration_s > 0 else 0.0,
        **_latency_stats(s.latency_ms for s in samples if s.outcome == "ok"),
    }


def time_series(
    samples: Sequence[Sample], duration_s: float, bucket_s: float = BUCKET_SECONDS
) -> list[dict[str, Any]]:
    """Buckets de ``bucket_s`` pelo instante de conclusão, com os vazios incluídos.

    Cada ponto: ``t`` (início do bucket, em s), ``calls`` (vazão do bucket),
    ``failed`` (erros + timeouts) e ``p50_ms``/``p95_ms`` das chamadas ok.
    """
    last = max((int(s.ended_s // bucket_s) for s in samples), default=0)
    count = max(last + 1, math.ceil(duration_s / bucket_s), 1)
    buckets: dict[int, list[Sample]] = defaultdict(list)
    for sample in samples:
        buckets[int(sample.ended_s // bucket_s)].append(sample)

    series: list[dict[str, Any]] = []
    for index in range(count):
        inside = buckets.get(index, [])
        latencies = sorted(s.latency_ms for s in inside if s.outcome == "ok")
        series.append(
            {
                "t": index * bucket_s,
                "calls": len(inside),
                "failed": sum(1 for s in inside if s.outcome != "ok"),
                "p50_ms": percentile(latencies, 50) if latencies else None,
                "p95_ms": percentile(latencies, 95) if latencies else None,
            }
        )
    return series


def aggregate(samples: Sequence[Sample], duration_s: float) -> dict[str, Any]:
    """Resultado completo: ``totals``, ``per_tool`` (ordenado por nome) e ``series``."""
    by_tool: dict[str, list[Sample]] = defaultdict(list)
    for sample in samples:
        by_tool[sample.tool].append(sample)
    return {
        "totals": summarize(samples, duration_s),
        "per_tool": {tool: summarize(by_tool[tool], duration_s) for tool in sorted(by_tool)},
        "series": time_series(samples, duration_s),
    }


class LiveStats:
    """Acumulador incremental para o progresso ao vivo.

    Recalcular ``summarize`` sobre todas as amostras a cada segundo travaria o
    event loop do motor e distorceria a latência medida; aqui cada ``add`` é
    barato e os percentis saem de uma lista já ordenada.
    """

    def __init__(self, bucket_s: float = BUCKET_SECONDS) -> None:
        self.bucket_s = bucket_s
        self.calls = 0
        self.ok = 0
        self.errors = 0
        self.timeouts = 0
        self._ok_latencies: list[float] = []
        self._calls_by_bucket: dict[int, int] = defaultdict(int)
        self._failed_by_bucket: dict[int, int] = defaultdict(int)
        self._ok_by_bucket: dict[int, list[float]] = defaultdict(list)

    def add(self, sample: Sample) -> None:
        self.calls += 1
        bucket = int(sample.ended_s // self.bucket_s)
        self._calls_by_bucket[bucket] += 1
        if sample.outcome == "ok":
            self.ok += 1
            insort(self._ok_latencies, sample.latency_ms)
            insort(self._ok_by_bucket[bucket], sample.latency_ms)
            return
        self._failed_by_bucket[bucket] += 1
        if sample.outcome == "error":
            self.errors += 1
        else:
            self.timeouts += 1

    def summary(self, elapsed_s: float) -> dict[str, Any]:
        latencies = self._ok_latencies
        failed = self.errors + self.timeouts
        stats: dict[str, float | None] = dict.fromkeys(_LATENCY_KEYS)
        if latencies:
            stats = {
                "min_ms": latencies[0],
                "mean_ms": sum(latencies) / len(latencies),
                "p50_ms": percentile(latencies, 50),
                "p95_ms": percentile(latencies, 95),
                "p99_ms": percentile(latencies, 99),
                "max_ms": latencies[-1],
            }
        return {
            "calls": self.calls,
            "ok": self.ok,
            "errors": self.errors,
            "timeouts": self.timeouts,
            "error_rate": failed / self.calls if self.calls else 0.0,
            "throughput_cps": self.calls / elapsed_s if elapsed_s > 0 else 0.0,
            **stats,
        }

    def recent_series(self, now_s: float, window: int) -> list[dict[str, Any]]:
        """Últimos ``window`` buckets completos ou em curso, no mesmo formato de ``time_series``."""
        current = int(now_s // self.bucket_s)
        series: list[dict[str, Any]] = []
        for index in range(max(0, current - window + 1), current + 1):
            latencies = self._ok_by_bucket.get(index, [])
            series.append(
                {
                    "t": index * self.bucket_s,
                    "calls": self._calls_by_bucket.get(index, 0),
                    "failed": self._failed_by_bucket.get(index, 0),
                    "p50_ms": percentile(latencies, 50) if latencies else None,
                    "p95_ms": percentile(latencies, 95) if latencies else None,
                }
            )
        return series
