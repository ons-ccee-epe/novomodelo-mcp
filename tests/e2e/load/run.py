"""CLI do teste de carga do servidor MCP do novomodelo.

Uso:
    python -m tests.e2e.load.run --concurrency 4 --duration 30
    python -m tests.e2e.load.run --concurrency 2 --duration 10 --tools deck_list,docs_search

Códigos de saída: 0 concluída, 1 falha (servidor não sobe, mix vazio), 2 uso
inválido, 3 interrompida pelo launcher (nada é gravado), 130 interrompida por
Ctrl+C (grava o parcial com ``interrupted: true``).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shlex
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any

from tests.e2e.load.client import default_server_command, stdio_client_factory
from tests.e2e.load.engine import (
    DEFAULT_TIMEOUT_S,
    MAX_CONCURRENCY,
    MAX_DURATION_S,
    LoadConfig,
    LoadError,
    LoadRunner,
)
from tests.e2e.load.mix import ALLOWED_TOOLS
from tests.e2e.load.resources import ResourceSampler, load_psutil
from tests.e2e.load.store import LoadStore, build_record
from tests.e2e.queries.mcp_workspace import WORKSPACE_ENV, workspace_roots

__all__ = ["build_parser", "format_report", "main"]

_E2E_DIR = Path(__file__).resolve().parent.parent
DEFAULT_FIXTURES = _E2E_DIR / "fixtures"
DEFAULT_RESULTS = _E2E_DIR / "results"

EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_CANCELLED = 3
EXIT_INTERRUPTED = 130

_HUMAN_PROGRESS_EVERY_S = 5.0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tests.e2e.load.run",
        description=(
            "Carga no servidor MCP do novomodelo: N clientes, cada um com o seu processo do "
            "servidor, chamando só tools somente leitura."
        ),
    )
    parser.add_argument(
        "--concurrency", type=int, required=True, help=f"Clientes concorrentes (1..{MAX_CONCURRENCY})."
    )
    parser.add_argument(
        "--duration", type=float, required=True, help=f"Janela de carga em segundos (1..{MAX_DURATION_S:g})."
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=None,
        help="Chamadas por cliente; cada cliente para nisso ou ao fim da duração, o que vier primeiro.",
    )
    parser.add_argument(
        "--tools",
        default=None,
        help=f"Tools do mix, separadas por vírgula (permitidas: {', '.join(ALLOWED_TOOLS)}).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_S,
        help="Segundos sem resposta até contar timeout e recriar o cliente (default: %(default)s).",
    )
    parser.add_argument(
        "--no-warmup",
        action="store_true",
        help="Não aquece cada cliente: as primeiras chamadas (frias) entram nas métricas.",
    )
    parser.add_argument("--no-save", action="store_true", help="Não grava em results/load/.")
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES, help="Raiz das fixtures.")
    parser.add_argument(
        "--results-dir", type=Path, default=DEFAULT_RESULTS, help="Pasta de results (grava em load/)."
    )
    parser.add_argument(
        "--server-command",
        default=None,
        help="Comando do servidor (default: o Python atual com -m novomodelo_mcp).",
    )
    parser.add_argument("--server-log", type=Path, default=None, help="Arquivo para o stderr dos servidores.")
    parser.add_argument(
        "--json-progress",
        action="store_true",
        help="Modo do launcher: eventos JSON em linhas no stdout; EOF no stdin interrompe a carga.",
    )
    return parser


def _parse_tools(raw: str | None) -> tuple[str, ...] | None:
    if raw is None:
        return None
    names = tuple(part.strip() for part in raw.split(",") if part.strip())
    return names or None


def _server_command(raw: str | None) -> tuple[str, list[str]]:
    if raw is None:
        return default_server_command()
    parts = shlex.split(raw, posix=os.name != "nt")
    if os.name == "nt":
        # No modo não-POSIX o shlex mantém as aspas no token: caminhos com espaço quebrariam.
        parts = [p[1:-1] if len(p) >= 2 and p[0] == p[-1] == '"' else p for p in parts]
    if not parts:
        raise ValueError("--server-command vazio")
    return parts[0], parts[1:]


def _emit(event: str, **fields: Any) -> None:
    print(json.dumps({"event": event, **fields}), flush=True)


def _ms(value: float | None) -> str:
    return "-" if value is None else f"{value:.0f}"


def format_report(record: dict[str, Any]) -> str:
    """Resumo legível de uma carga (o mesmo conteúdo do JSON gravado)."""
    totals = record["totals"]
    startup = record["startup"]
    lines = [
        f"Carga {record['load_id']}: {record['config']['concurrency']} cliente(s), "
        f"{record['duration_seconds']:.1f} s de carga"
        + (" (interrompida)" if record["interrupted"] else ""),
        f"Subida: {startup['started']}/{startup['clients']} cliente(s) em "
        f"{startup['wall_ms'] / 1000:.1f} s (por cliente: mín {_ms(startup['min_ms'])} / "
        f"méd {_ms(startup['mean_ms'])} / máx {_ms(startup['max_ms'])} ms); "
        f"recriações: {startup['respawns']}",
        f"Total: {totals['calls']} chamadas, {totals['ok']} ok, {totals['errors']} erro(s), "
        f"{totals['timeouts']} timeout(s); taxa de erro {totals['error_rate'] * 100:.1f}%; "
        f"vazão {totals['throughput_cps']:.2f} chamadas/s",
        f"Latência (ms, só chamadas ok): mín {_ms(totals['min_ms'])}, méd {_ms(totals['mean_ms'])}, "
        f"p50 {_ms(totals['p50_ms'])}, p95 {_ms(totals['p95_ms'])}, p99 {_ms(totals['p99_ms'])}, "
        f"máx {_ms(totals['max_ms'])}",
        "",
        f"{'tool':<24}{'chamadas':>9}{'ok':>7}{'erro':>6}{'t.out':>6}{'cps':>8}"
        f"{'p50':>7}{'p95':>7}{'p99':>7}{'máx':>7}",
    ]
    for tool, row in record["per_tool"].items():
        lines.append(
            f"{tool:<24}{row['calls']:>9}{row['ok']:>7}{row['errors']:>6}{row['timeouts']:>6}"
            f"{row['throughput_cps']:>8.2f}{_ms(row['p50_ms']):>7}{_ms(row['p95_ms']):>7}"
            f"{_ms(row['p99_ms']):>7}{_ms(row['max_ms']):>7}"
        )
    excluded = record["mix"]["excluded"]
    if excluded:
        lines += ["", f"Fora do mix ({len(excluded)}):"]
        lines += [f"  {item['id']}: {item['reason']}" for item in excluded]
    for item in record["errors"]:
        lines.append(f"Erro x{item['count']} [{item['tool']}/{item['outcome']}]: {item['message']}")
    resources = record["resources"]
    if resources["available"] and resources.get("samples"):
        lines.append(
            f"Servidores: CPU média {resources['avg_cpu_percent']:.0f}% (pico "
            f"{resources['peak_cpu_percent']:.0f}%), RSS de pico {resources['peak_rss_mb']:.0f} MB"
        )
    else:
        lines.append("Servidores: CPU/RSS não medidos (instale psutil para medir)")
    return "\n".join(lines)


_PARENT_GONE = threading.Event()


def _watch_stdin(runner: LoadRunner) -> None:
    """EOF no stdin = o launcher saiu ou cancelou: interrompe sem gravar."""

    def watch() -> None:
        try:
            while sys.stdin.readline():
                pass
        except (OSError, ValueError):
            pass
        _PARENT_GONE.set()
        runner.request_stop()

    threading.Thread(target=watch, name="stdin-watch", daemon=True).start()


def _execute(
    config: LoadConfig, args: argparse.Namespace, command: str, command_args: list[str]
) -> tuple[LoadRunner, Any]:
    """Roda a carga e devolve ``(runner, outcome)``; levanta ``LoadError`` se não puder rodar."""
    json_mode: bool = args.json_progress
    fixtures: Path = args.fixtures.resolve()
    roots = workspace_roots(fixtures)
    env = {WORKSPACE_ENV: os.pathsep.join(str(root) for root in roots)}
    psutil = load_psutil()
    last_human_line = 0.0

    def on_progress(snapshot: dict[str, Any]) -> None:
        nonlocal last_human_line
        if json_mode:
            _emit("progress", **snapshot)
            return
        now = time.monotonic()
        if now - last_human_line < _HUMAN_PROGRESS_EVERY_S:
            return
        last_human_line = now
        p95 = snapshot["p95_ms"]
        print(
            f"[{snapshot['phase']:>9}] {snapshot['elapsed_seconds']:6.1f}s  "
            f"chamadas={snapshot['calls']} erros={snapshot['errors'] + snapshot['timeouts']} "
            f"vazão={snapshot['throughput_cps']:.1f}/s p95={'-' if p95 is None else f'{p95:.0f}ms'}",
            file=sys.stderr,
            flush=True,
        )

    with open(args.server_log or os.devnull, "a", encoding="utf-8") as errlog:
        runner = LoadRunner(
            config,
            fixtures,
            stdio_client_factory(command, command_args, env, errlog),
            on_progress=on_progress,
            resource_sampler=ResourceSampler(psutil) if psutil else None,
        )
        _install_stop_handlers(runner, json_mode)
        return runner, asyncio.run(runner.run())


def _install_stop_handlers(runner: LoadRunner, json_mode: bool) -> None:
    interrupts = 0

    def on_sigint(_signum: int, _frame: Any) -> None:
        nonlocal interrupts
        interrupts += 1
        if interrupts > 1:
            raise KeyboardInterrupt
        runner.request_stop()

    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGINT, on_sigint)
    if json_mode:
        _watch_stdin(runner)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    json_mode: bool = args.json_progress

    def fail(message: str, code: int) -> int:
        if json_mode:
            _emit("error", message=message)
        else:
            print(f"erro: {message}", file=sys.stderr)
        return code

    try:
        config = LoadConfig(
            concurrency=args.concurrency,
            duration_s=args.duration,
            iterations=args.iterations,
            tools=_parse_tools(args.tools),
            timeout_s=args.timeout,
            warmup=not args.no_warmup,
        )
        command, command_args = _server_command(args.server_command)
    except ValueError as exc:
        return fail(str(exc), EXIT_USAGE)

    previous_handler = signal.getsignal(signal.SIGINT)
    try:
        _runner, outcome = _execute(config, args, command, command_args)
    except LoadError as exc:
        return fail(str(exc), EXIT_FAILED)
    finally:
        if threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGINT, previous_handler)

    if _PARENT_GONE.is_set():
        _emit("cancelled")
        return EXIT_CANCELLED

    store = LoadStore(args.results_dir)
    load_id = store.new_id()
    roots = workspace_roots(args.fixtures.resolve())
    server = {"command": [command, *command_args], "workspace": [str(root) for root in roots]}
    record = build_record(load_id, outcome, server=server)
    path = None if args.no_save else store.save(record)
    if json_mode:
        if path is not None:
            _emit("saved", load_id=load_id, path=str(path))
    else:
        print(format_report(record))
        if path is not None:
            print(f"\nGravado em: {path}")
    return EXIT_INTERRUPTED if outcome.interrupted else 0


if __name__ == "__main__":
    sys.exit(main())
