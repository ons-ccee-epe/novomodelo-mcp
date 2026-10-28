"""Persistência das cargas em ``results/load/``: um JSON por carga e um ``index.json``.

O id segue o de ``queries.store.ResultStore``: ``{timestamp}_{git_short_sha}``. O
subdiretório mantém o ``index.json`` das baterias de agente intacto. Cada registro
traz ``mode`` (``tools`` ou ``agent``); um JSON gravado antes do modo agent não tem o
campo e é lido como ``tools``. O bloco ``sandbox`` (cópia das fixtures por sessão) também
pode faltar nos JSONs antigos, que não tinham cópia.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from tests.e2e.load.agent_cases import case_group
from tests.e2e.load.agent_engine import AGENT_BUCKET_SECONDS, AgentOutcome, AgentSample
from tests.e2e.load.engine import LoadOutcome
from tests.e2e.load.mix import is_heavy_tool
from tests.e2e.load.resources import summarize_resources
from tests.e2e.load.stats import aggregate, summarize, time_series

__all__ = [
    "AGENT_STATUSES",
    "LOAD_SUBDIR",
    "LoadStore",
    "build_agent_record",
    "build_record",
    "git_sha",
    "index_entry",
    "package_version",
    "record_is_heavy",
    "record_mode",
]

LOAD_SUBDIR = "load"

_ID_PATTERN = re.compile(r"^\d{8}_\d{6}_[0-9a-z]+(_\d+)?$")
_TOP_ERRORS = 10

AGENT_STATUSES = ("pass", "partial", "fail", "timeout", "error")
_SUMMARY_KEYS = (
    "calls",
    "ok",
    "errors",
    "timeouts",
    "error_rate",
    "throughput_cps",
    "p50_ms",
    "p95_ms",
    "p99_ms",
)


def record_mode(record: dict[str, Any]) -> str:
    """``tools`` ou ``agent``; registros sem o campo são do modo tools."""
    return "agent" if record.get("mode") == "agent" else "tools"


def record_is_heavy(record: dict[str, Any]) -> bool:
    """True se a carga rodou alguma tool pesada (bridge/solver): no modo tools, as chamadas
    que passaram do pré-voo; no agent, as tools esperadas dos casos selecionados."""
    if record_mode(record) == "agent":
        selected = (record.get("cases") or {}).get("selected") or []
        tools = [t for c in selected for t in str(c.get("tool") or "").split("/") if t]
    else:
        tools = [str(c.get("tool") or "") for c in (record.get("mix") or {}).get("calls") or []]
    return any(is_heavy_tool(tool) for tool in tools)


def git_sha() -> str:
    try:
        # stdin=DEVNULL: no modo do launcher o stdin herdado é um pipe com uma leitura
        # pendente (o vigia de EOF); o git trava ao consultá-lo e estoura o timeout.
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=5,
            cwd=Path(__file__).parent,
        )
    except Exception:  # noqa: BLE001 - sem git o registro usa "unknown"
        return "unknown"
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else "unknown"


def package_version() -> str:
    try:
        from importlib.metadata import version

        return version("novomodelo-mcp")
    except Exception:  # noqa: BLE001 - sem metadados a versão fica "unknown"
        return "unknown"


def _startup_summary(outcome: LoadOutcome) -> dict[str, Any]:
    initial = [s for s in outcome.startups if s["kind"] == "initial"]
    ok = [s for s in initial if s["ok"]]
    times = [s["ms"] for s in ok]
    warmups = [s["warmup_ms"] for s in ok if s["warmup_ms"] is not None]
    preflight = next((s["ms"] for s in outcome.startups if s["kind"] == "preflight"), None)
    return {
        "clients": outcome.config.concurrency,
        "started": len(ok),
        "failed": len(initial) - len(ok),
        "wall_ms": outcome.startup_wall_s * 1000.0,
        "min_ms": min(times) if times else None,
        "mean_ms": sum(times) / len(times) if times else None,
        "max_ms": max(times) if times else None,
        "warmup_mean_ms": sum(warmups) / len(warmups) if warmups else None,
        "preflight_ms": preflight,
        "respawns": sum(1 for s in outcome.startups if s["kind"] == "respawn"),
        "events": outcome.startups,
    }


def _error_summary(outcome: LoadOutcome) -> list[dict[str, Any]]:
    counts = Counter(
        (s.tool, s.outcome, s.error or "") for s in outcome.samples if s.outcome != "ok"
    )
    return [
        {"tool": tool, "outcome": kind, "message": message, "count": count}
        for (tool, kind, message), count in counts.most_common(_TOP_ERRORS)
    ]


def build_record(
    load_id: str,
    outcome: LoadOutcome,
    server: dict[str, Any] | None = None,
    environment: str = "local",
    sandbox: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """JSON de uma carga: configuração, mix, subida, cópia por sessão, totais, por tool,
    série e recursos."""
    return {
        "mode": "tools",
        "load_id": load_id,
        "timestamp": outcome.started_at,
        "ended_at": outcome.ended_at,
        "version": package_version(),
        "git_commit_sha": git_sha(),
        "environment": environment,
        "interrupted": outcome.interrupted,
        "config": outcome.config.to_dict(),
        "server": server or {},
        "mix": {
            "calls": [{"id": s.id, "tool": s.tool} for s in outcome.selection.specs],
            "excluded": [
                {"id": e.id, "tool": e.tool, "reason": e.reason} for e in outcome.selection.excluded
            ],
        },
        "startup": _startup_summary(outcome),
        "sandbox": sandbox or {"enabled": False},
        "duration_seconds": outcome.duration_s,
        "abandoned_calls": outcome.abandoned_calls,
        **aggregate(outcome.samples, outcome.duration_s),
        "errors": _error_summary(outcome),
        "resources": summarize_resources(outcome.resource_samples),
    }


def _mean(values: list[int]) -> float | None:
    return sum(values) / len(values) if values else None


def _agent_stats(samples: list[AgentSample], duration_s: float) -> dict[str, Any]:
    """Os campos de ``stats.summarize`` (transporte) mais aprovação e tool-calls."""
    stats = summarize([s.as_sample() for s in samples], duration_s)
    statuses = Counter(s.status for s in samples)
    completed = [s for s in samples if s.outcome == "ok"]
    return {
        **stats,
        "throughput_cpm": stats["throughput_cps"] * 60.0,
        "statuses": {status: statuses.get(status, 0) for status in AGENT_STATUSES},
        "pass_rate": statuses.get("pass", 0) / len(samples) if samples else 0.0,
        "tool_calls_mean": _mean([s.tool_calls for s in completed]),
        "mcp_calls_mean": _mean([s.mcp_calls for s in completed]),
    }


def _agent_series(samples: list[AgentSample], duration_s: float) -> list[dict[str, Any]]:
    series = time_series([s.as_sample() for s in samples], duration_s, AGENT_BUCKET_SECONDS)
    passed = Counter(
        int(s.as_sample().ended_s // AGENT_BUCKET_SECONDS) for s in samples if s.status == "pass"
    )
    return [{**point, "passed": passed.get(index, 0)} for index, point in enumerate(series)]


def _agent_errors(samples: list[AgentSample]) -> list[dict[str, Any]]:
    counts = Counter(
        (s.case_id, s.status, s.outcome, s.error or "") for s in samples if s.status != "pass"
    )
    return [
        {"case_id": case_id, "status": status, "outcome": outcome, "message": message, "count": n}
        for (case_id, status, outcome, message), n in counts.most_common(_TOP_ERRORS)
    ]


def _expected_tool(case: Any) -> str | None:
    if case.expected.tool:
        return case.expected.tool
    return "/".join(case.expected.tools) if case.expected.tools else None


def build_agent_record(
    load_id: str,
    outcome: AgentOutcome,
    agent: dict[str, Any],
    server: dict[str, Any] | None = None,
    environment: str = "local",
    sandbox: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """JSON de uma carga do modo agent: configuração, casos, sessões, totais, por caso e série."""
    samples = outcome.samples
    by_case: dict[str, list[AgentSample]] = {}
    for sample in samples:
        by_case.setdefault(sample.case_id, []).append(sample)
    sessions = outcome.sessions
    started = [s for s in sessions if s["ok"]]
    return {
        "mode": "agent",
        "load_id": load_id,
        "timestamp": outcome.started_at,
        "ended_at": outcome.ended_at,
        "version": package_version(),
        "git_commit_sha": git_sha(),
        "environment": environment,
        "interrupted": outcome.interrupted,
        "config": outcome.config.to_dict(),
        "agent": agent,
        "server": server or {},
        "cases": {
            "selection": outcome.config.selection.describe(),
            "selected": [
                {"id": c.id, "group": case_group(c), "tool": _expected_tool(c)}
                for c in outcome.selection.cases
            ],
            "excluded": [
                {"id": e.id, "tool": e.tool, "reason": e.reason} for e in outcome.selection.excluded
            ],
        },
        "sessions": {
            "requested": outcome.config.concurrency,
            "started": len(started),
            "failed": len(sessions) - len(started),
            "setup_ms": outcome.setup_s * 1000.0,
            "events": sessions,
        },
        "sandbox": sandbox or {"enabled": False},
        "duration_seconds": outcome.duration_s,
        "abandoned_calls": outcome.abandoned_calls,
        "series_bucket_seconds": AGENT_BUCKET_SECONDS,
        "totals": _agent_stats(samples, outcome.duration_s),
        "per_case": {
            case_id: {
                "group": by_case[case_id][0].group,
                **_agent_stats(by_case[case_id], outcome.duration_s),
            }
            for case_id in sorted(by_case)
        },
        "series": _agent_series(samples, outcome.duration_s),
        "errors": _agent_errors(samples),
        "resources": summarize_resources(outcome.resource_samples),
    }


def index_entry(record: dict[str, Any]) -> dict[str, Any]:
    """Resumo de uma carga para o ``index.json``; o que entra em ``config`` depende do ``mode``."""
    totals = record["totals"]
    config = record["config"]
    mode = record_mode(record)
    entry_config: dict[str, Any] = {
        "mode": mode,
        "concurrency": config["concurrency"],
        "duration_seconds": config["duration_seconds"],
        "iterations": config["iterations"],
        "timeout_seconds": config["timeout_seconds"],
    }
    summary = {key: totals[key] for key in _SUMMARY_KEYS}
    if mode == "agent":
        agent = record.get("agent") or {}
        entry_config["provider"] = agent.get("provider") or config.get("provider")
        entry_config["selection"] = config.get("selection")
        summary["throughput_cpm"] = totals["throughput_cpm"]
        summary["pass_rate"] = totals["pass_rate"]
    else:
        entry_config["tools"] = config["tools"]
    return {
        "mode": mode,
        "load_id": record["load_id"],
        "timestamp": record["timestamp"],
        "version": record["version"],
        "git_commit_sha": record["git_commit_sha"],
        "interrupted": record["interrupted"],
        "config": entry_config,
        "summary": summary,
    }


def _write_json_atomic(path: Path, payload: Any) -> None:
    # A UI lê estes arquivos enquanto a carga grava: sem o replace ela pegaria JSON pela metade.
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


class LoadStore:
    """Grava e lê cargas em ``<results_dir>/load/``."""

    def __init__(self, results_dir: str | Path) -> None:
        self.load_dir = Path(results_dir) / LOAD_SUBDIR
        self.index_path = self.load_dir / "index.json"

    def new_id(self) -> str:
        """``{timestamp}_{git_short_sha}``, com ``_2``, ``_3``... se o id já existir."""
        base = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{git_sha()[:7]}"
        candidate, attempt = base, 1
        while (self.load_dir / f"{candidate}.json").exists():
            attempt += 1
            candidate = f"{base}_{attempt}"
        return candidate

    def save(self, record: dict[str, Any]) -> Path:
        """Grava o JSON da carga e atualiza o índice."""
        self.load_dir.mkdir(parents=True, exist_ok=True)
        path = self.load_dir / f"{record['load_id']}.json"
        _write_json_atomic(path, record)

        runs = [r for r in self._read_index() if r.get("load_id") != record["load_id"]]
        runs.append(index_entry(record))
        _write_json_atomic(self.index_path, {"runs": runs})
        return path

    def list_runs(self) -> list[dict[str, Any]]:
        """Resumos do índice, mais recente primeiro."""
        return sorted(self._read_index(), key=lambda r: r.get("timestamp", ""), reverse=True)

    def load(self, load_id: str) -> dict[str, Any]:
        """JSON completo de uma carga.

        Raises:
            ValueError: Se ``load_id`` não tem o formato de um id gerado por ``new_id``.
            FileNotFoundError: Se a carga não existe.
        """
        if not _ID_PATTERN.match(load_id):
            raise ValueError(f"id de carga inválido: {load_id!r}")
        path = self.load_dir / f"{load_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"carga não encontrada: {load_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def _read_index(self) -> list[dict[str, Any]]:
        if not self.index_path.exists():
            return []
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
        except ValueError:
            return self._rebuild_index()
        runs = data.get("runs") if isinstance(data, dict) else None
        return runs if isinstance(runs, list) else self._rebuild_index()

    def _rebuild_index(self) -> list[dict[str, Any]]:
        runs: list[dict[str, Any]] = []
        for path in sorted(self.load_dir.glob("*.json")):
            if path.name == self.index_path.name:
                continue
            try:
                runs.append(index_entry(json.loads(path.read_text(encoding="utf-8"))))
            except (ValueError, KeyError):
                continue
        return runs
