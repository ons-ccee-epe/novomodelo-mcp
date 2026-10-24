"""Persistência das cargas em ``results/load/``: um JSON por carga e um ``index.json``.

O id segue o de ``queries.store.ResultStore``: ``{timestamp}_{git_short_sha}``. O
subdiretório mantém o ``index.json`` das baterias de agente intacto.
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

from tests.e2e.load.engine import LoadOutcome
from tests.e2e.load.resources import summarize_resources
from tests.e2e.load.stats import aggregate

__all__ = ["LOAD_SUBDIR", "LoadStore", "build_record", "git_sha", "index_entry", "package_version"]

LOAD_SUBDIR = "load"

_ID_PATTERN = re.compile(r"^\d{8}_\d{6}_[0-9a-z]+(_\d+)?$")
_TOP_ERRORS = 10


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
) -> dict[str, Any]:
    """JSON de uma carga: configuração, mix, subida, totais, por tool, série e recursos."""
    return {
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
        "duration_seconds": outcome.duration_s,
        "abandoned_calls": outcome.abandoned_calls,
        **aggregate(outcome.samples, outcome.duration_s),
        "errors": _error_summary(outcome),
        "resources": summarize_resources(outcome.resource_samples),
    }


def index_entry(record: dict[str, Any]) -> dict[str, Any]:
    """Resumo de uma carga para o ``index.json``."""
    totals = record["totals"]
    config = record["config"]
    return {
        "load_id": record["load_id"],
        "timestamp": record["timestamp"],
        "version": record["version"],
        "git_commit_sha": record["git_commit_sha"],
        "interrupted": record["interrupted"],
        "config": {
            "concurrency": config["concurrency"],
            "duration_seconds": config["duration_seconds"],
            "iterations": config["iterations"],
            "tools": config["tools"],
            "timeout_seconds": config["timeout_seconds"],
        },
        "summary": {
            key: totals[key]
            for key in (
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
        },
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
