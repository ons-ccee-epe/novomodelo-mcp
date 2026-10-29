"""CLI do teste de carga do servidor MCP do novomodelo.

Uso:
    python -m novomodelo_mcp_e2e.load.run --concurrency 4 --duration 30
    python -m novomodelo_mcp_e2e.load.run --concurrency 2 --duration 10 --tools deck_list,docs_search
    python -m novomodelo_mcp_e2e.load.run --mode agent --mcp sem --group deck --concurrency 2 --duration 120

Modos: ``tools`` (padrão) chama as tools direto, sem agente; ``agent`` roda os casos do
``cases.yaml`` em N sessões de agente simultâneas, cada execução num container do executor
(``--mcp`` escolhe a imagem: ``sem`` ou a wheel do MCP; é preciso ter rodado ``preparar``).

Códigos de saída: 0 concluída, 1 falha (servidor não sobe, nenhum caso ou chamada
disponível, disco insuficiente para a cópia das fixtures), 2 uso inválido, 3 interrompida
pelo launcher (nada é gravado), 130 interrompida por Ctrl+C (grava o parcial com
``interrupted: true``).

As pastas das sessões (e as cópias das fixtures, no modo tools, se a seleção grava) ficam numa pasta
temporária do run, dentro de ``--work-dir``, apagada ao fim, inclusive em erro e Ctrl+C.
O launcher passa uma ``--work-dir`` própria e a apaga depois que a árvore do motor morre:
um cancelamento mata o motor sem dar tempo de limpar.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shlex
import signal
import sys
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any, TextIO

from novomodelo_mcp_e2e.config import carregar_config, verificar
from novomodelo_mcp_e2e.executor.imagens import ler_config_mcp, tag_imagem
from novomodelo_mcp_e2e.load.agent_cases import CaseSelection
from novomodelo_mcp_e2e.load.agent_engine import (
    MAX_AGENT_CONCURRENCY,
    PROVIDERS,
    AgentLoadConfig,
    AgentLoadRunner,
)
from novomodelo_mcp_e2e.load.agent_session import AGENTE_DO_PROVEDOR, default_run_root
from novomodelo_mcp_e2e.load.agent_setup import denied_tools, make_preflight, session_factory
from novomodelo_mcp_e2e.load.client import default_server_command, stdio_client_factory
from novomodelo_mcp_e2e.load.engine import (
    DEFAULT_TIMEOUT_S,
    MAX_CONCURRENCY,
    MAX_DURATION_S,
    LoadConfig,
    LoadError,
    LoadRunner,
)
from novomodelo_mcp_e2e.load.mix import ALLOWED_TOOLS, DEFAULT_TOOLS, select_specs
from novomodelo_mcp_e2e.load.resources import ResourceSampler, load_psutil
from novomodelo_mcp_e2e.load.sandbox import (
    ToolsSessions,
    check_disk,
    make_run_root,
    plan_for_specs,
    remove_tree,
)
from novomodelo_mcp_e2e.load.store import LoadStore, build_agent_record, build_record
from novomodelo_mcp_e2e.queries.mcp_workspace import workspace_roots
from novomodelo_mcp_e2e.queries.run_queries import _build_test_result

__all__ = ["build_parser", "format_agent_report", "format_report", "main", "stderr_tail"]

_E2E_DIR = Path(__file__).resolve().parent.parent
DEFAULT_FIXTURES = _E2E_DIR / "fixtures"
DEFAULT_RESULTS = _E2E_DIR / "results"

EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_CANCELLED = 3
EXIT_INTERRUPTED = 130

_HUMAN_PROGRESS_EVERY_S = 5.0
_SANDBOX_WORKSPACE = "cópia das fixtures por sessão"
_STDERR_TAIL_CHARS = 500


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="novomodelo_mcp_e2e.load.run",
        description=(
            "Carga no servidor MCP do novomodelo. Modo tools: N sessões, cada uma com o seu "
            "processo do servidor, chamando as tools do mix (as que gravam numa cópia das "
            "fixtures por sessão). Modo agent: N sessões de agente rodando em laço os casos do "
            "cases.yaml que podem rodar em paralelo."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=("tools", "agent"),
        default="tools",
        help="tools (padrão): chamadas diretas, sem agente; agent: casos por agente (gasta tokens).",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        required=True,
        help=(
            f"Sessões simultâneas (tools: 1..{MAX_CONCURRENCY}; agent: 1..{MAX_AGENT_CONCURRENCY})."
        ),
    )
    parser.add_argument(
        "--duration",
        type=float,
        required=True,
        help=f"Janela de carga em segundos (1..{MAX_DURATION_S:g}).",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=None,
        help=(
            "Por sessão: chamadas (tools) ou casos (agent); cada sessão para nisso ou ao fim "
            "da duração, o que vier primeiro."
        ),
    )
    parser.add_argument(
        "--tools",
        default=None,
        help=(
            "Só tools: tools do mix, separadas por vírgula (default: o mix padrão, "
            f"{', '.join(DEFAULT_TOOLS)}; permitidas: {', '.join(ALLOWED_TOOLS)})."
        ),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help=(
            f"tools: segundos sem resposta até contar timeout e recriar a sessão (default: "
            f"{DEFAULT_TIMEOUT_S:g}); agent: timeout de cada caso (default: o timeout_s do caso)."
        ),
    )
    parser.add_argument(
        "--provider",
        choices=PROVIDERS,
        default=None,
        help="Só agent: provedor de IA (default: claude).",
    )
    parser.add_argument(
        "--mcp",
        default=None,
        metavar="sem|WHEEL",
        help="Só agent: 'sem' (default) ou a wheel do MCP cuja imagem as sessões usam.",
    )
    parser.add_argument("--case", default=None, help="Só agent: um caso do cases.yaml, pelo id.")
    parser.add_argument(
        "--group", default=None, help="Só agent: um grupo (o da tool esperada: deck, docs, ...)."
    )
    parser.add_argument(
        "--tags",
        default=None,
        help="Só agent: tags separadas por vírgula (casos com qualquer uma).",
    )
    parser.add_argument(
        "--no-warmup",
        action="store_true",
        help="Não aquece cada cliente: as primeiras chamadas (frias) entram nas métricas.",
    )
    parser.add_argument("--no-save", action="store_true", help="Não grava em results/load/.")
    parser.add_argument(
        "--fixtures", type=Path, default=DEFAULT_FIXTURES, help="Raiz das fixtures."
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=DEFAULT_RESULTS,
        help="Pasta de results (grava em load/).",
    )
    parser.add_argument(
        "--server-command",
        default=None,
        help="Comando do servidor (default: o Python do .venv do projeto com -m novomodelo_mcp).",
    )
    parser.add_argument(
        "--server-log", type=Path, default=None, help="Arquivo para o stderr dos servidores."
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=None,
        help=(
            "Pasta onde o run cria a sua pasta temporária (sessões e cópias das fixtures), "
            "apagada ao fim (default: o TEMP)."
        ),
    )
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


_TOOLS_ONLY = {"tools": "--tools", "no_warmup": "--no-warmup", "server_command": "--server-command"}
_AGENT_ONLY = {
    "provider": "--provider",
    "mcp": "--mcp",
    "case": "--case",
    "group": "--group",
    "tags": "--tags",
}


def _misplaced(args: argparse.Namespace) -> list[str]:
    """Opções que não valem no modo escolhido."""
    wrong = _AGENT_ONLY if args.mode == "tools" else _TOOLS_ONLY
    return [flag for name, flag in wrong.items() if getattr(args, name)]


def _tools_config(args: argparse.Namespace) -> LoadConfig:
    return LoadConfig(
        concurrency=args.concurrency,
        duration_s=args.duration,
        iterations=args.iterations,
        tools=_parse_tools(args.tools),
        timeout_s=args.timeout if args.timeout is not None else DEFAULT_TIMEOUT_S,
        warmup=not args.no_warmup,
    )


def _agent_config(args: argparse.Namespace) -> AgentLoadConfig:
    return AgentLoadConfig(
        concurrency=args.concurrency,
        duration_s=args.duration,
        provider=args.provider,
        mcp=args.mcp,
        selection=CaseSelection(case_id=args.case, group=args.group, tags=_parse_tools(args.tags)),
        iterations=args.iterations,
        timeout_s=args.timeout,
    )


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


def _resources_line(resources: dict[str, Any], what: str) -> str:
    if resources["available"] and resources.get("samples"):
        return (
            f"{what}: CPU média {resources['avg_cpu_percent']:.0f}% (pico "
            f"{resources['peak_cpu_percent']:.0f}%), RSS de pico {resources['peak_rss_mb']:.0f} MB"
        )
    return f"{what}: CPU/RSS não medidos (instale psutil para medir)"


def _sandbox_lines(sandbox: dict[str, Any] | None) -> list[str]:
    if not sandbox or not sandbox.get("enabled"):
        return []
    copy_ms = sandbox.get("copy_ms_mean")
    final = sandbox.get("final_mb_max")
    return [
        f"Cópia por sessão: {sandbox['copy_mb']:.1f} MB ({', '.join(sandbox['subtrees']) or 'só scratch/'})"
        + (f", copiada em {copy_ms / 1000:.1f} s em média" if copy_ms is not None else "")
        + (f"; maior cópia ao fim: {final:.1f} MB" if final is not None else "")
    ]


def format_agent_report(record: dict[str, Any]) -> str:
    """Resumo legível de uma carga do modo agent (o mesmo conteúdo do JSON gravado)."""
    totals = record["totals"]
    sessions = record["sessions"]
    statuses = totals["statuses"]
    lines = [
        f"Carga {record['load_id']} (agent, {record['agent']['provider']}): "
        f"{sessions['requested']} sessão(ões), {record['cases']['selection']}, "
        f"{record['duration_seconds']:.1f} s"
        + (" (interrompida)" if record["interrupted"] else ""),
        f"Sessões: {sessions['started']}/{sessions['requested']} preparadas em "
        f"{sessions['setup_ms'] / 1000:.1f} s",
        f"Total: {totals['calls']} execuções; aprovados {statuses['pass']}, parciais "
        f"{statuses['partial']}, reprovados {statuses['fail']}, timeouts {statuses['timeout']}, "
        f"erros {statuses['error']}; aprovação {totals['pass_rate'] * 100:.1f}%; "
        f"vazão {totals['throughput_cpm']:.2f} casos/min",
        f"Latência ponta a ponta (ms, execuções completas): p50 {_ms(totals['p50_ms'])}, "
        f"p95 {_ms(totals['p95_ms'])}, p99 {_ms(totals['p99_ms'])}, máx {_ms(totals['max_ms'])}",
        "",
        f"{'caso':<34}{'exec':>6}{'pass':>6}{'fail':>6}{'t.out':>6}{'erro':>6}"
        f"{'p50':>8}{'p95':>8}{'tools':>7}",
    ]
    for case_id, row in record["per_case"].items():
        st = row["statuses"]
        mean_calls = row["tool_calls_mean"]
        lines.append(
            f"{case_id:<34}{row['calls']:>6}{st['pass']:>6}{st['fail'] + st['partial']:>6}"
            f"{st['timeout']:>6}{st['error']:>6}{_ms(row['p50_ms']):>8}{_ms(row['p95_ms']):>8}"
            f"{'-' if mean_calls is None else f'{mean_calls:.1f}':>7}"
        )
    excluded = record["cases"]["excluded"]
    if excluded:
        lines += ["", f"Fora da carga ({len(excluded)}):"]
        lines += [f"  {item['id']}: {item['reason']}" for item in excluded]
    for item in record["errors"]:
        lines.append(
            f"{item['status']} x{item['count']} [{item['case_id']}]: {item['message'] or '-'}"
        )
    lines.append(_resources_line(record["resources"], "Agentes + servidores"))
    lines += _sandbox_lines(record.get("sandbox"))
    return "\n".join(lines)


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
    lines.append(_resources_line(record["resources"], "Servidores"))
    lines += _sandbox_lines(record.get("sandbox"))
    return "\n".join(lines)


_PARENT_GONE = threading.Event()


def _watch_stdin(runner: LoadRunner | AgentLoadRunner) -> None:
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


def _progress_printer(json_mode: bool) -> Any:
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
        p95_text = "-" if p95 is None else f"{p95:.0f}ms"
        if snapshot.get("mode") == "agent":
            line = (
                f"execuções={snapshot['calls']} em curso={snapshot['sessions']['running']} "
                f"aprovação={snapshot['pass_rate'] * 100:.0f}% "
                f"erros={snapshot['errors'] + snapshot['timeouts']} p95={p95_text}"
            )
        else:
            line = (
                f"chamadas={snapshot['calls']} erros={snapshot['errors'] + snapshot['timeouts']} "
                f"vazão={snapshot['throughput_cps']:.1f}/s p95={p95_text}"
            )
        print(
            f"[{snapshot['phase']:>9}] {snapshot['elapsed_seconds']:6.1f}s  {line}",
            file=sys.stderr,
            flush=True,
        )

    return on_progress


@contextmanager
def _server_errlog(path: Path | None) -> Iterator[tuple[Path, TextIO]]:
    """Arquivo para o stderr dos servidores: o pedido ou um temporário apagado ao fim."""
    temporary = path is None
    if path is None:
        fd, name = tempfile.mkstemp(prefix="load-server-", suffix=".log")
        os.close(fd)
        path = Path(name)
    try:
        with open(path, "a", encoding="utf-8") as errlog:
            yield path, errlog
    finally:
        if temporary:
            path.unlink(missing_ok=True)


def _with_stderr_tail(exc: LoadError, log_path: Path) -> LoadError:
    tail = stderr_tail(log_path)
    return LoadError(f"{exc} | stderr do servidor: {tail}") if tail else exc


def _execute(
    config: LoadConfig, args: argparse.Namespace, command: str, command_args: list[str]
) -> tuple[LoadRunner, Any, dict[str, Any]]:
    """Roda a carga e devolve ``(runner, outcome, sandbox)``; levanta ``LoadError`` se não
    puder rodar."""
    json_mode: bool = args.json_progress
    fixtures: Path = args.fixtures.resolve()
    plan = plan_for_specs(fixtures, select_specs(fixtures, config.tools).specs)
    work_dir = args.work_dir or Path(tempfile.gettempdir())
    check_disk(plan, config.concurrency, work_dir)
    psutil = load_psutil()
    sessions = ToolsSessions(make_run_root(work_dir, f"novomodelo-load-tools-{os.getpid()}-"), plan)
    try:
        with _server_errlog(args.server_log) as (log_path, errlog):
            runner = LoadRunner(
                config,
                fixtures,
                stdio_client_factory(command, command_args, {}, errlog, env_for=sessions.env),
                on_progress=_progress_printer(json_mode),
                resource_sampler=ResourceSampler(psutil) if psutil else None,
                sessions=sessions,
            )
            _install_stop_handlers(runner, json_mode)
            try:
                outcome = asyncio.run(runner.run())
            except LoadError as exc:
                raise _with_stderr_tail(exc, log_path) from exc
        return runner, outcome, sessions.summary()
    finally:
        sessions.close()


def _execute_agent(
    config: AgentLoadConfig, args: argparse.Namespace
) -> tuple[AgentLoadRunner, Any, dict[str, Any]]:
    """Roda a carga do modo agent; devolve ``(runner, outcome, {"server", "sandbox"})``.

    Raises:
        LoadError: Se o ambiente do executor não está pronto, a imagem não é uma wheel
            do MCP existente ou nenhum caso pode rodar.
    """
    provider = config.provider or "claude"
    agente = AGENTE_DO_PROVEDOR[provider]
    try:
        config_mcp = ler_config_mcp(config.mcp or "sem")
    except ValueError as exc:
        raise LoadError(str(exc)) from exc
    cfg = carregar_config(os.environ)
    itens = {"motor", "cache", "token_claude" if agente == "claude" else "volume_kiro"}
    problemas = [p.mensagem for p in verificar(cfg) if p.item in itens]
    if problemas:
        raise LoadError("; ".join(problemas))
    config = replace(config, mcp=config_mcp.nome)
    fixtures: Path = args.fixtures.resolve()
    run_root = default_run_root(args.work_dir)
    try:
        runner = AgentLoadRunner(
            config,
            make_preflight(config, fixtures),
            session_factory(provider, config_mcp, cfg, run_root, config.timeout_s),
            build_result=_build_test_result,
            on_progress=_progress_printer(args.json_progress),
            resource_sampler=ResourceSampler(psutil) if (psutil := load_psutil()) else None,
        )
        _install_stop_handlers(runner, args.json_progress)
        outcome = runner.run()
    finally:
        remove_tree(run_root)
    server_info = {"image": tag_imagem(config_mcp, agente), "workspace": []}
    return runner, outcome, {"server": server_info, "sandbox": {"enabled": False}}


def stderr_tail(path: Path, max_lines: int = 3) -> str:
    """Últimas linhas não vazias do stderr dos servidores, para o erro dizer por que não subiram."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    filled = [line.strip() for line in lines if line.strip()]
    return " / ".join(filled[-max_lines:])[:_STDERR_TAIL_CHARS]


def _install_stop_handlers(runner: LoadRunner | AgentLoadRunner, json_mode: bool) -> None:
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


def _agent_info(provider: str, image: str, outcome: Any) -> dict[str, Any]:
    agente = AGENTE_DO_PROVEDOR[provider]
    return {
        "provider": provider,
        "label": f"{agente} no executor em container",
        "binary": image,
        "denied_tools": denied_tools(outcome.server_tools),
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    json_mode: bool = args.json_progress

    def fail(message: str, code: int) -> int:
        if json_mode:
            _emit("error", message=message)
        else:
            print(f"erro: {message}", file=sys.stderr)
        return code

    misplaced = _misplaced(args)
    if misplaced:
        return fail(f"{', '.join(misplaced)} não vale(m) no modo {args.mode}", EXIT_USAGE)
    try:
        if args.mode == "agent":
            config: LoadConfig | AgentLoadConfig = _agent_config(args)
        else:
            config = _tools_config(args)
            command, command_args = _server_command(args.server_command)
    except ValueError as exc:
        return fail(str(exc), EXIT_USAGE)

    previous_handler = signal.getsignal(signal.SIGINT)
    try:
        if isinstance(config, AgentLoadConfig):
            _runner, outcome, extra = _execute_agent(config, args)
        else:
            _runner, outcome, sandbox = _execute(config, args, command, command_args)
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
    if isinstance(config, AgentLoadConfig):
        record = build_agent_record(
            load_id,
            outcome,
            _agent_info(config.provider or "claude", extra["server"]["image"], outcome),
            server=extra["server"],
            sandbox=extra["sandbox"],
        )
        report = format_agent_report
    else:
        roots = [str(root) for root in workspace_roots(args.fixtures.resolve())]
        workspace = [_SANDBOX_WORKSPACE] if sandbox["enabled"] else roots
        server = {"command": [command, *command_args], "workspace": workspace}
        record = build_record(load_id, outcome, server=server, sandbox=sandbox)
        report = format_report
    path = None if args.no_save else store.save(record)
    if json_mode:
        if path is not None:
            _emit("saved", load_id=load_id, path=str(path))
    else:
        print(report(record))
        if path is not None:
            print(f"\nGravado em: {path}")
    return EXIT_INTERRUPTED if outcome.interrupted else 0


if __name__ == "__main__":
    sys.exit(main())
