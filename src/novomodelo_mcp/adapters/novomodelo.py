"""Adaptador da CLI do `novomodelo` (Rust). Usado pelas tools de prontidão/execução.

Mesma filosofia do adaptador do bridge: transporte puro, sem regra de domínio.
O flag global `--color never` vem ANTES do subcomando (contrato da CLI do novomodelo).
"""
from __future__ import annotations

import importlib
import json
import re
import subprocess
from typing import Any

from ..config import Settings, load_settings
from ..names import BINDING_DIST, BINDING_MODULE, SOLVER_CLI
from .envelope import MAX_DETAIL_CHARS, error as _error
from .discovery import find_novomodelo
from .obs import log

_NOT_FOUND = f"{SOLVER_CLI} não encontrado no PATH (defina NOVOMODELO_MCP_SOLVER_BIN)."


def run_novomodelo(subargv: list[str], *, timeout: float | None = None,
              settings: Settings | None = None, parse_json: bool = True) -> dict[str, Any]:
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
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout if timeout is not None else settings.default_timeout,
        )
    except subprocess.TimeoutExpired:
        return _error(-1, f"timeout ao executar: {' '.join(cmd)}")
    except OSError as exc:
        return _error(-1, f"erro ao executar novomodelo: {exc}")

    text = (proc.stdout or "").strip()
    env: dict[str, Any]
    if not parse_json:
        env = {"status": "ok" if proc.returncode == 0 else "error",
               "stdout": text[:MAX_DETAIL_CHARS],
               "stderr": (proc.stderr or "").strip()[:MAX_DETAIL_CHARS],
               "diagnostics": []}
    elif not text:
        env = {
            "status": "ok" if proc.returncode == 0 else "error",
            "diagnostics": [(proc.stderr or "")[:MAX_DETAIL_CHARS]] if proc.stderr else [],
        }
    else:
        try:
            env = json.loads(text)
        except json.JSONDecodeError:
            env = {"status": "error",
                   "diagnostics": ["saída não-JSON da CLI", text[:MAX_DETAIL_CHARS]]}
    env["exit_code"] = proc.returncode
    log(settings, "novomodelo.done", exit_code=env.get("exit_code"), status=env.get("status"))
    return env


def validate_deck_binding(case_dir: str, *, settings: Settings | None = None) -> dict[str, Any]:
    """Valida um deck pelo binding `novomodelo.io.validate` — saida ESTRUTURADA.

    Retorna {"valid": bool, "errors": [{kind,message,file,entity}], "warnings": [...]}.
    Sem parsing de texto e sem depender do binario Rust. Transporte puro.
    """
    log(settings, "validate_deck_binding", case_dir=case_dir)
    try:
        _cio = importlib.import_module(f"{BINDING_MODULE}.io")
    except ImportError:
        return _error(127, f"{BINDING_DIST} ausente no venv; rode: uv sync --system-certs")
    try:
        report = _cio.validate(case_dir)
    except FileNotFoundError as exc:
        return _error(2, f"caso nao encontrado: {exc}")
    except Exception as exc:  # noqa: BLE001 - repassa como erro, nao derruba o servidor
        return {"status": "error", "exit_code": 1,
                "diagnostics": [f"{type(exc).__name__}: {exc}"]}
    if not isinstance(report, dict):
        return {"status": "ok", "exit_code": 0, "report": report}
    valid = bool(report.get("valid", True))
    errors = report.get("errors", []) or []
    warnings = report.get("warnings", []) or []
    return {"status": "ok" if valid else "error", "exit_code": 0 if valid else 1,
            "valid": valid, "n_errors": len(errors), "n_warnings": len(warnings),
            "errors": errors, "warnings": warnings}

def validate_deck_cli(case_dir: str, *, settings: Settings | None = None) -> dict[str, Any]:
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
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=settings.default_timeout)
    except subprocess.TimeoutExpired:
        return _error(-1, f"timeout ao executar: {' '.join(cmd)}")
    except OSError as exc:
        return _error(-1, f"erro ao executar novomodelo: {exc}")

    text = (proc.stdout or "")
    if proc.stderr:
        text += ("\n" + proc.stderr)
    text = text.strip()

    def _count(pattern: str) -> int | None:
        m = re.search(pattern, text, re.IGNORECASE)
        return int(m.group(1)) if m else None

    cap = settings.max_summary_chars
    truncated = len(text) > cap
    report = text[:cap] + ("\n... [relatorio truncado]" if truncated else "")

    return {
        "status": "ok" if proc.returncode == 0 else "error",
        "exit_code": proc.returncode,
        "errors": _count(r"(\d+)\s+error"),
        "warnings": _count(r"(\d+)\s+warning"),
        "report_truncated": truncated,
        "report": report,
    }


def version_cli(*, settings: Settings | None = None) -> dict[str, Any]:
    """Roda `novomodelo version` em modo TEXTO e devolve os campos parseados + o texto bruto.

    A CLI real não aceita `--json` em `version` (clap rejeita com exit 2); a saída
    é texto humano, uma `label: valor` por linha, exceto a primeira que separa por
    espaço (ex.: `novomodelo   v0.17.0`). Transporte puro, sem regra de domínio.
    """
    settings = settings or load_settings()
    binpath = find_novomodelo(settings)
    if binpath is None:
        return _error(127, _NOT_FOUND)
    cmd = [binpath, "--color", "never", "version"]
    # never-raise: falhas de transporte viram Error_Envelope (127 ausente / -1 timeout), nunca propagam ao stdio.
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=settings.default_timeout)
    except subprocess.TimeoutExpired:
        return _error(-1, f"timeout ao executar: {' '.join(cmd)}")
    except OSError as exc:
        return _error(-1, f"erro ao executar novomodelo: {exc}")

    stdout = (proc.stdout or "").strip()
    if proc.returncode != 0:
        detail = (proc.stderr or stdout or "")[:MAX_DETAIL_CHARS]
        return _error(proc.returncode, "novomodelo version encerrou com erro", detail)

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
