"""Confina o servidor MCP novomodelo ao diretório de fixtures durante os testes E2E.

O path guard do novomodelo-mcp recusa tudo fora de NOVOMODELO_MCP_WORKSPACE, e a
config pessoal do Kiro aponta essa raiz para uma pasta do usuário. A definição do
servidor (comando, args, env) é reaproveitada da config pessoal, porque o local de
instalação varia por máquina; só a raiz é trocada. O kiro-cli, rodando com
cwd=<workspace>, prefere <workspace>/.kiro/settings/mcp.json à config global; o
claude recebe o mesmo servidor via --mcp-config.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

__all__ = [
    "SERVER_NAME",
    "WORKSPACE_ENV",
    "load_server_config",
    "server_config_for_workspace",
    "prepare_workspace",
    "tool_timeout_ms",
    "workspace_roots",
]

SERVER_NAME = "novomodelo"
WORKSPACE_ENV = "NOVOMODELO_MCP_WORKSPACE"

# Raiz do repositório: um link sob fixtures/ só vira raiz do path guard se
# apontar para dentro dele. fixtures/ é gitignored (ninguém revisa); um link
# para C:\ liberaria o disco inteiro às tools de escrita do MCP.
_REPO_ROOT = Path(__file__).resolve().parents[3]

_log = logging.getLogger(__name__)

# Espelha o default de NOVOMODELO_MCP_TIMEOUT (Settings.default_timeout do servidor).
MCP_CLI_TIMEOUT_DEFAULT_S = 900.0
# Folga para o MCP devolver o próprio envelope de timeout antes do agente desistir.
TOOL_TIMEOUT_MARGIN_S = 60.0


def _mcp_json_candidates() -> list[Path]:
    # Só a config do usuário: um .kiro/settings/mcp.json no cwd (de um repo
    # qualquer) definiria o comando que o runner executa.
    return [Path.home() / ".kiro" / "settings" / "mcp.json"]


def load_server_config() -> dict[str, Any] | None:
    """Definição do servidor 'novomodelo' no mcp.json do Kiro, ou None."""
    for path in _mcp_json_candidates():
        if not path.exists():
            continue
        try:
            with open(path, encoding="utf-8") as f:
                cfg = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        server = cfg.get("mcpServers", {}).get(SERVER_NAME)
        if server:
            return server
    return None


def _is_link(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def _link_targets(root: Path) -> list[Path]:
    """Destinos dos symlinks/junctions de diretório sob ``root``.

    O path guard faz ``resolve()`` e recusa um link cujo alvo cai fora da raiz,
    então cada alvo entra como raiz explícita — liberar o pai do alvo abriria
    mais do que o link aponta.
    """
    targets: list[Path] = []
    if not root.is_dir():
        return targets
    for dirpath, dirnames, _ in os.walk(root):
        for name in list(dirnames):
            entry = Path(dirpath) / name
            if _is_link(entry):
                dirnames.remove(name)
                target = entry.resolve()
                if target.is_relative_to(_REPO_ROOT):
                    targets.append(target)
                else:
                    _log.warning("link %s aponta para fora do repo (%s); ignorado", entry, target)
    return targets


def tool_timeout_ms(server: dict[str, Any] | None = None) -> int:
    """Quanto o agente espera por uma tool do novomodelo: o timeout de CLI do MCP + folga.

    Os CLIs de agente têm limite próprio por tool (kiro-cli: 120 s), menor que o
    do MCP; sem alinhar, uma conversão longa é cortada pelo agente no meio.
    """
    env = (server or load_server_config() or {}).get("env") or {}
    try:
        cli_timeout = float(env.get("NOVOMODELO_MCP_TIMEOUT", MCP_CLI_TIMEOUT_DEFAULT_S))
    except ValueError:
        cli_timeout = MCP_CLI_TIMEOUT_DEFAULT_S
    return int((cli_timeout + TOOL_TIMEOUT_MARGIN_S) * 1000)


def workspace_roots(workspace: str | Path) -> list[Path]:
    """Raízes do path guard para ``workspace``: ele próprio e os alvos dos links dentro dele."""
    root = Path(workspace).resolve()
    return [root, *_link_targets(root)]


def server_config_for_workspace(workspace: str | Path) -> dict[str, Any] | None:
    """Cópia da definição do servidor com o path guard restrito a ``workspace``.

    As raízes são o workspace e os alvos dos links dentro dele, separadas por
    ``os.pathsep`` (formato aceito por NOVOMODELO_MCP_WORKSPACE).
    """
    server = load_server_config()
    if server is None:
        return None
    roots = workspace_roots(workspace)
    env = dict(server.get("env") or {})
    env[WORKSPACE_ENV] = os.pathsep.join(str(r) for r in roots)
    # "timeout" (ms) é o limite por tool que o kiro-cli lê do mcp.json.
    return {**server, "env": env, "timeout": tool_timeout_ms(server)}


def prepare_workspace(workspace: str | Path) -> Path:
    """Grava ``<workspace>/.kiro/settings/mcp.json`` e devolve o workspace absoluto.

    O retorno é o cwd do agente: fora dele o kiro-cli volta à config global.

    Raises:
        RuntimeError: Se o servidor novomodelo não está no mcp.json do Kiro.
    """
    root = Path(workspace).resolve()
    server = server_config_for_workspace(root)
    if server is None:
        raise RuntimeError(
            f"Servidor MCP '{SERVER_NAME}' não encontrado em "
            "~/.kiro/settings/mcp.json. Configure-o antes de rodar os testes E2E."
        )
    cfg_path = root / ".kiro" / "settings" / "mcp.json"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(
        json.dumps({"mcpServers": {SERVER_NAME: server}}, indent=2),
        encoding="utf-8",
    )
    return root
