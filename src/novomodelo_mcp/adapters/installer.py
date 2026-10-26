"""Instalação do executável oficial do novomodelo pelo instalador do release.

Só o instalador do release `v<versão esperada>` de `ons-ccee-epe/novomodelo`, com o
SHA-256 conferido contra o `digest` que a API do GitHub publica para o arquivo (o
instalador não tem `.sha256` próprio). Nunca levanta: falha vira envelope com o
comando manual.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from . import versions
from .discovery import tool_version
from .envelope import error
from .subproc import NO_WINDOW

#: Variáveis que fazem o instalador oficial baixar de outro lugar: nunca repassadas.
SCRUBBED_ENV = ("NOVOMODELO_CLI_DOWNLOAD_URL", "INSTALLER_DOWNLOAD_URL",
                "NOVOMODELO_CLI_INSTALLER_GITHUB_BASE_URL",
                "NOVOMODELO_CLI_INSTALLER_GHE_BASE_URL")
_RELEASE_API = "https://api.github.com/repos/ons-ccee-epe/novomodelo/releases/tags/v{}"
_DOWNLOAD_TIMEOUT_S = 60
_INSTALL_TIMEOUT_S = 300


def _installer_name() -> str:
    return "novomodelo-cli-installer." + ("ps1" if sys.platform == "win32" else "sh")


def installer_url(version: str) -> str:
    return f"{versions.CLI_RELEASES}/download/v{version}/{_installer_name()}"


def _binary_dir(pasta: str | None) -> Path:
    """Onde o instalador põe o binário (layout `cargo-home`: `<raiz>/bin`)."""
    root = (pasta or os.environ.get("NOVOMODELO_CLI_INSTALL_DIR")
            or os.environ.get("CARGO_DIST_FORCE_INSTALL_DIR")
            or os.environ.get("CARGO_HOME") or str(Path.home() / ".cargo"))
    return Path(root) / "bin"


def _changes_path() -> bool:
    return not any(os.environ.get(v) for v in (
        "NOVOMODELO_CLI_NO_MODIFY_PATH", "INSTALLER_NO_MODIFY_PATH",
        "NOVOMODELO_CLI_UNMANAGED_INSTALL"))


def _expected_sha256(version: str) -> str | dict[str, str]:
    body = versions.fetch_bytes(_RELEASE_API.format(version), timeout=_DOWNLOAD_TIMEOUT_S)
    if isinstance(body, dict):
        return body
    try:
        assets = json.loads(body).get("assets") or []
    except (ValueError, AttributeError):
        return {"aviso_rede": "resposta da API do GitHub ilegível"}
    digest = next((a.get("digest") for a in assets if a.get("name") == _installer_name()), None)
    if not (digest or "").startswith("sha256:"):
        return {"erro": f"o release v{version} não publica o SHA-256 de {_installer_name()}"}
    return digest.split(":", 1)[1]


def _run_installer(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace",
                          **NO_WINDOW, **kwargs)


def _installer_env(pasta: str | None) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in SCRUBBED_ENV}
    if pasta:
        env["NOVOMODELO_CLI_INSTALL_DIR"] = pasta
    return env


def _fail(code: int, message: str, manual: str, detail: str = "", **extra) -> dict[str, Any]:
    return {**error(code, message, detail), "comando_manual": manual, **extra}


def install(*, confirmar: bool = False, pasta: str | None = None) -> dict[str, Any]:
    version = versions.expected_version()
    if not version:
        return error(2, "versão esperada desconhecida (pacote do MCP sem metadados)")
    manual = versions.cli_install_command(version)
    if pasta is not None and not Path(pasta).is_absolute():
        return _fail(22, f"`pasta` precisa ser caminho absoluto: {pasta!r}", manual)
    url, dest = installer_url(version), _binary_dir(pasta)
    sha = _expected_sha256(version)
    if isinstance(sha, dict):
        if "aviso_rede" in sha:
            return _fail(2, "não foi possível consultar o release oficial", manual,
                         aviso_rede=sha["aviso_rede"])
        return _fail(2, sha["erro"], manual)
    plan = {"versao": version, "url": url, "sha256": sha, "destino": str(dest),
            "altera_path": _changes_path()}
    if not confirmar:
        return {"status": "ok", "executado": False, "plano": plan, "comando_manual": manual,
                "diagnostics": ["nada foi baixado; chame com confirmar=True para instalar"]}

    body = versions.fetch_bytes(url, timeout=_DOWNLOAD_TIMEOUT_S)
    if isinstance(body, dict):
        return _fail(2, "não foi possível baixar o instalador", manual, plano=plan,
                     aviso_rede=body["aviso_rede"])
    got = hashlib.sha256(body).hexdigest()
    if got != sha:
        return _fail(13, "hash do instalador não confere; nada foi executado", manual,
                     f"esperado {sha}, obtido {got}", plano=plan)

    workdir = tempfile.mkdtemp(prefix="novomodelo-installer-")
    try:
        script = Path(workdir) / _installer_name()
        script.write_bytes(body)
        cmd = (["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script)]
               if sys.platform == "win32" else ["sh", str(script)])
        try:
            proc = _run_installer(cmd, env=_installer_env(pasta), timeout=_INSTALL_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            return _fail(-1, f"o instalador passou de {_INSTALL_TIMEOUT_S} s", manual, plano=plan)
        except OSError as exc:
            return _fail(127, "não foi possível executar o instalador", manual, str(exc),
                         plano=plan)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    if proc.returncode != 0:
        return _fail(proc.returncode, "o instalador oficial terminou com erro", manual,
                     (proc.stderr or proc.stdout or "")[-2000:], plano=plan)

    binary = dest / ("novomodelo.exe" if sys.platform == "win32" else "novomodelo")
    line = tool_version(str(binary)) if binary.exists() else None
    installed = versions.normalize_version(line.split()[-1]) if line else None
    if installed != version:
        return _fail(1, f"depois da instalação, {binary} responde {installed!r}, não {version}",
                     manual, plano=plan)
    versions.reset_caches()
    return {"status": "ok", "executado": True, "versao_instalada": installed,
            "caminho": str(binary), "plano": plan,
            "configuracao": f'"NOVOMODELO_MCP_SOLVER_BIN": "{binary}"',
            "diagnostics": [(proc.stdout or "").strip()[-2000:]]}
