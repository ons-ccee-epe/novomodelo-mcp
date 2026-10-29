"""Adaptador da CLI do `novomodelo` (Rust). Usado pelas tools de prontidão/execução.

Mesma filosofia do adaptador do bridge: transporte puro, sem regra de domínio.
O flag global `--color never` vem ANTES do subcomando (contrato da CLI do novomodelo).
"""

from __future__ import annotations

import json
import re
import subprocess
from typing import Any

from ..config import Settings, load_settings
from ..names import BINDING_DIST, SOLVER_CLI
from .discovery import find_novomodelo
from .envelope import MAX_DETAIL_CHARS, as_error
from .envelope import error as _error
from .obs import log
from .subproc import NO_WINDOW

_NOT_FOUND = f"{SOLVER_CLI} não encontrado no PATH (defina NOVOMODELO_MCP_SOLVER_BIN)."


def run_novomodelo(
    subargv: list[str],
    *,
    timeout: float | None = None,
    settings: Settings | None = None,
    parse_json: bool = True,
) -> dict[str, Any]:
    """Executa `novomodelo --color never <subargv>` esperando saída JSON (use --json).

    `parse_json=False` para subcomandos sem `--json` (ex.: `init`): devolve o
    stdout/stderr como texto (truncados), com status pelo código de saída.
    """
    settings = settings or load_settings()
    binpath = find_novomodelo(settings)
    if binpath is None:
        return _error(127, _NOT_FOUND)
    log(settings, "novomodelo", subargv=subargv)
    cmd = [binpath, "--color", "never", *subargv]
    try:
        # argv em lista e sem shell: os caminhos do agente, já validados pelo guard, chegam
        # como argumentos literais, nunca interpretados.
        proc = (
            subprocess.run(  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit
                cmd,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout if timeout is not None else settings.default_timeout,
                **NO_WINDOW,
            )
        )
    except subprocess.TimeoutExpired:
        return _error(-1, f"timeout ao executar: {' '.join(cmd)}")
    except OSError as exc:
        return _error(-1, f"erro ao executar novomodelo: {exc}")

    env = _interpret(proc, parse_json=parse_json)
    env["exit_code"] = proc.returncode
    log(settings, "novomodelo.done", exit_code=env.get("exit_code"), status=env.get("status"))
    return env


def _interpret(proc: subprocess.CompletedProcess, *, parse_json: bool) -> dict[str, Any]:
    text = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    failed = proc.returncode != 0
    if not parse_json:
        streams = {"stdout": text[:MAX_DETAIL_CHARS], "stderr": stderr[:MAX_DETAIL_CHARS]}
        if failed:
            return _error(
                proc.returncode, f"{SOLVER_CLI} encerrou com código {proc.returncode}", **streams
            )
        return {"status": "ok", **streams, "diagnostics": []}
    if not text:
        if failed:
            return _error(proc.returncode, "saída vazia da CLI", stderr)
        return {"status": "ok", "diagnostics": [stderr[:MAX_DETAIL_CHARS]] if stderr else []}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return _error(proc.returncode, "saída não-JSON da CLI", text)


def validate_deck_binding(
    case_dir: str, *, output_dir: str | None = None, settings: Settings | None = None
) -> dict[str, Any]:
    """Valida um deck pelo binding `novomodelo.io.validate` — saida ESTRUTURADA.

    Retorna {"valid": bool, "errors": [{kind,message,file,entity}], "warnings": [...]}.
    Sem parsing de texto e sem depender do binario Rust. Transporte puro.
    """
    settings = settings or load_settings()
    log(settings, "validate_deck_binding", case_dir=case_dir, output_dir=output_dir)
    try:
        # Import literal (não dinâmico): o nome do módulo é fixo e o rename o reescreve.
        import novomodelo.io as _cio
    except ImportError:
        return _error(127, f"{BINDING_DIST} ausente no venv; rode: uv sync --system-certs")
    try:
        report = _cio.validate(case_dir, **({"output_dir": output_dir} if output_dir else {}))
    except FileNotFoundError as exc:
        return _error(2, f"caso nao encontrado: {exc}")
    except Exception as exc:  # noqa: BLE001 - repassa como erro, nao derruba o servidor
        return as_error(exc)
    if not isinstance(report, dict):
        return {"status": "ok", "exit_code": 0, "report": report}
    valid = bool(report.get("valid", True))
    errors = report.get("errors", []) or []
    warnings = report.get("warnings", []) or []
    fields = {
        "valid": valid,
        "n_errors": len(errors),
        "n_warnings": len(warnings),
        "errors": errors,
        "warnings": warnings,
    }
    if not valid:
        return _error(1, f"o caso não passou na validação ({len(errors)} erro(s))", **fields)
    return {"status": "ok", "exit_code": 0, **fields}


#: Lista do `model.System` (o nome na resposta) → atributo de contagem, se houver.
_SYSTEM_KINDS = {
    "buses": "n_buses",
    "lines": "n_lines",
    "hydros": "n_hydros",
    "thermals": "n_thermals",
    "contracts": None,
    "pumping_stations": None,
    "non_controllable_sources": None,
}


def case_summary_binding(
    case_dir: str, *, max_items: int, settings: Settings | None = None
) -> dict[str, Any]:
    """O caso lido por `novomodelo.io.load_case`: contagens e `{id, name}` por tipo.

    Só `load_case`, nunca `Study`: o `Study` grava arquivos na pasta de saída do caso.
    """
    settings = settings or load_settings()
    log(settings, "case_summary_binding", case_dir=case_dir)
    try:
        import novomodelo.io as _cio
    except ImportError:
        return _error(127, f"{BINDING_DIST} ausente no venv; rode: uv sync --system-certs")
    try:
        system = _cio.load_case(case_dir)
    except Exception as exc:  # noqa: BLE001 - caso inválido (ValueError/OSError) vira envelope
        return _error(1, "o novomodelo não conseguiu ler o caso", f"{type(exc).__name__}: {exc}")
    counts: dict[str, Any] = {}
    items: dict[str, Any] = {}
    for kind, count_attr in _SYSTEM_KINDS.items():
        entries = list(getattr(system, kind, None) or [])
        counts[kind] = getattr(system, count_attr) if count_attr else len(entries)
        items[kind] = {
            "entries": [{"id": e.id, "name": e.name} for e in entries[:max_items]],
            "truncated": len(entries) > max_items,
        }
    counts["stages"] = getattr(system, "n_stages", None)
    return {"status": "ok", "exit_code": 0, "counts": counts, "items": items}


def validate_deck_cli(
    case_dir: str, *, output_dir: str | None = None, settings: Settings | None = None
) -> dict[str, Any]:
    """Valida um deck rodando `novomodelo validate` em modo TEXTO (relatorio completo).

    O `--json` do novomodelo devolve apenas a reconciliacao de boundary; o relatorio
    real (contagem de erros/avisos) so sai no modo humano. Capturamos esse texto,
    extraimos as contagens e devolvemos o relatorio (truncado ao teto de saida).
    """
    settings = settings or load_settings()
    binpath = find_novomodelo(settings)
    if binpath is None:
        return _error(127, _NOT_FOUND)
    cmd = [binpath, "--color", "never", "validate", case_dir]
    if output_dir:
        cmd += ["--output", output_dir]
    try:
        # argv em lista e sem shell; case_dir e output_dir já passaram pelo guard.
        proc = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            encoding="utf-8",
            errors="replace",  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit
            timeout=settings.default_timeout,
            **NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        return _error(-1, f"timeout ao executar: {' '.join(cmd)}")
    except OSError as exc:
        return _error(-1, f"erro ao executar novomodelo: {exc}")

    text = proc.stdout or ""
    if proc.stderr:
        text += "\n" + proc.stderr
    text = text.strip()

    def _count(pattern: str) -> int | None:
        m = re.search(pattern, text, re.IGNORECASE)
        return int(m.group(1)) if m else None

    cap = settings.max_summary_chars
    truncated = len(text) > cap
    fields = {
        "errors": _count(r"(\d+)\s+error"),
        "warnings": _count(r"(\d+)\s+warning"),
        "report_truncated": truncated,
        "report": text[:cap] + ("\n... [relatorio truncado]" if truncated else ""),
    }
    if proc.returncode != 0:
        return _error(
            proc.returncode,
            f"{SOLVER_CLI} validate encerrou com código {proc.returncode}; veja `report`",
            **fields,
        )
    return {"status": "ok", "exit_code": 0, **fields}


def version_cli(*, settings: Settings | None = None) -> dict[str, Any]:
    """Roda `novomodelo version` em modo TEXTO e devolve os campos parseados + o texto bruto.

    A CLI real não aceita `--json` em `version` (clap rejeita com exit 2); a saída
    é texto humano, uma `label: valor` por linha, exceto a primeira que separa por
    espaço (ex.: `novomodelo   v0.19.0`). Transporte puro, sem regra de domínio.
    """
    settings = settings or load_settings()
    binpath = find_novomodelo(settings)
    if binpath is None:
        return _error(127, _NOT_FOUND)
    cmd = [binpath, "--color", "never", "version"]
    # never-raise: falhas de transporte viram Error_Envelope (127 ausente / -1 timeout),
    # nunca propagam ao stdio.
    try:
        # argv fixa, sem shell: nada vem do agente.
        proc = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            encoding="utf-8",
            errors="replace",  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit
            timeout=settings.default_timeout,
            **NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        return _error(-1, f"timeout ao executar: {' '.join(cmd)}")
    except OSError as exc:
        return _error(-1, f"erro ao executar novomodelo: {exc}")

    stdout = (proc.stdout or "").strip()
    if proc.returncode != 0:
        return _error(
            proc.returncode, "novomodelo version encerrou com erro", proc.stderr or stdout or ""
        )

    fields: dict[str, Any] = {}
    lines = stdout.splitlines()
    if lines:
        # 1ª linha: "<programa>   v<versão>". Lê por posição, sem comparar o nome
        # do programa, para não quebrar em renames do produto.
        first = lines[0].split()
        if len(first) > 1:
            fields["program"] = first[0]
            fields["version"] = first[1]
    for line in lines[1:]:
        if ":" in line:
            key, _, value = line.partition(":")
            fields[key.strip().lower()] = value.strip()

    # `raw` é a fonte de verdade: a saída é texto humano e pode mudar de formato;
    # se o parsing não achar `version`, ainda devolvemos ok com o texto autoritativo.
    return {"status": "ok", "exit_code": 0, **fields, "raw": stdout}
