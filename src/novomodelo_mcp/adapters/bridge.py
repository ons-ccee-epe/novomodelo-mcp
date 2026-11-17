"""Adaptador da CLI do novomodelo-bridge.

`run_bridge` é a ÚNICA peça compartilhada por todas as ferramentas. Ela:
  - monta `novomodelo-bridge <argv> --json --no-color`;
  - executa como subprocesso (isolamento de processo);
  - NUNCA levanta exceção para o chamador — toda falha vira um envelope de erro;
  - devolve o envelope do bridge {schema_version, command, status, summary,
    diagnostics} acrescido de `exit_code`.

Nenhuma regra de conversão/validação mora aqui: só transporte e parsing.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any

from ..config import Settings, load_settings
from ..names import BRIDGE_CLI
from .discovery import find_bridge
from .envelope import error as _error
from .obs import log
from .subproc import NO_WINDOW


def _parse_envelope(stdout: str, stderr: str, returncode: int) -> dict[str, Any]:
    """Interpreta a saída como o envelope JSON do bridge.

    Tolera logs impressos antes do JSON: se o parse direto falhar, procura a
    última linha que começa com '{' e tenta de novo.
    """
    text = (stdout or "").strip()
    if not text:
        return _error(returncode, "saída vazia da CLI", stderr or "")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        for line in reversed(text.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        return _error(returncode, "saída não-JSON da CLI", text)


def run_bridge(
    argv: list[str], *, timeout: float | None = None, settings: Settings | None = None
) -> dict[str, Any]:
    """Executa um subcomando do novomodelo-bridge e devolve o envelope + exit_code."""
    settings = settings or load_settings()
    binpath = find_bridge(settings)
    if binpath is None:
        return _error(
            127,
            f"{BRIDGE_CLI} não encontrado. Instale-o "
            f"(uv tool install {BRIDGE_CLI}) ou defina NOVOMODELO_MCP_BRIDGE_BIN.",
        )
    log(settings, "bridge", argv=argv)
    cmd = [binpath, *argv, "--json", "--no-color"]
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
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                **NO_WINDOW,
            )
        )
    except FileNotFoundError:
        return _error(127, f"binário não encontrado/executável: {binpath}")
    except subprocess.TimeoutExpired:
        return _error(-1, f"timeout ao executar: {' '.join(cmd)}")
    except OSError as exc:  # pragma: no cover - defensivo
        return _error(-1, f"erro ao executar novomodelo-bridge: {exc}")

    envelope = _parse_envelope(proc.stdout, proc.stderr, proc.returncode)
    envelope["exit_code"] = proc.returncode
    log(settings, "bridge.done", exit_code=envelope.get("exit_code"), status=envelope.get("status"))
    return envelope
