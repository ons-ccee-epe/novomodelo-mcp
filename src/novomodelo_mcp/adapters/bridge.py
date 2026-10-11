"""Adaptador da CLI do cobre-bridge.

`run_bridge` é a ÚNICA peça compartilhada por todas as ferramentas. Ela:
  - monta `cobre-bridge <argv> --json --no-color`;
  - executa como subprocesso (isolamento de processo);
  - NUNCA levanta exceção para o chamador — toda falha vira um envelope de erro;
  - devolve o envelope do bridge {schema_version, command, status, summary,
    diagnostics} acrescido de `exit_code`.

Nenhuma regra de conversão/validação mora aqui: só transporte e parsing.
"""
from __future__ import annotations

import json
import subprocess
from typing import Any

from ..config import Settings, load_settings
from ..names import BRIDGE_CLI
from .envelope import MAX_DETAIL_CHARS, error as _error
from .discovery import find_bridge
from .obs import log




def _parse_envelope(stdout: str, stderr: str) -> dict[str, Any]:
    """Interpreta a saída como o envelope JSON do bridge.

    Tolera logs impressos antes do JSON: se o parse direto falhar, procura a
    última linha que começa com '{' e tenta de novo.
    """
    text = (stdout or "").strip()
    if not text:
        return {"status": "error",
                "diagnostics": ["saída vazia da CLI", (stderr or "")[:MAX_DETAIL_CHARS]]}
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
        return {"status": "error",
                "diagnostics": ["saída não-JSON da CLI", text[:MAX_DETAIL_CHARS]]}


def run_bridge(argv: list[str], *, timeout: float | None = None,
               settings: Settings | None = None) -> dict[str, Any]:
    """Executa um subcomando do cobre-bridge e devolve o envelope + exit_code."""
    settings = settings or load_settings()
    binpath = find_bridge(settings)
    if binpath is None:
        return _error(127, f"{BRIDGE_CLI} não encontrado. Instale-o "
                           f"(uv tool install {BRIDGE_CLI}) ou defina NOVOMODELO_MCP_BRIDGE_BIN.")
    log(settings, "bridge", argv=argv)
    cmd = [binpath, *argv, "--json", "--no-color"]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout if timeout is not None else settings.default_timeout,
        )
    except FileNotFoundError:
        return _error(127, f"binário não encontrado/executável: {binpath}")
    except subprocess.TimeoutExpired:
        return _error(-1, f"timeout ao executar: {' '.join(cmd)}")
    except OSError as exc:  # pragma: no cover - defensivo
        return _error(-1, f"erro ao executar cobre-bridge: {exc}")

    envelope = _parse_envelope(proc.stdout, proc.stderr)
    envelope["exit_code"] = proc.returncode
    log(settings, "bridge.done", exit_code=envelope.get("exit_code"), status=envelope.get("status"))
    return envelope
