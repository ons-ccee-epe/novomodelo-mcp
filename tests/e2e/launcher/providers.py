"""Deteccao do provedor de IA disponivel e construcao do comando por provedor.

O launcher nao assume qual CLI existe: ele detecta no PATH. Suporta:
  - kiro-cli  (modo headless: chat --no-interactive --output-format stream-json)
  - claude    (Claude Code CLI, modo headless: -p / --print)

A escolha de qual usar vem do frontend (seletor), mas sempre validada contra o
que de fato esta instalado. O QueryRunner existente ja fala kiro-cli; para o
claude, montamos o comando equivalente e reaproveitamos o mesmo parsing de
tool-calls do log (o QueryRunner le stdout+stderr combinados).
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from tests.e2e.queries.mcp_workspace import (
    SERVER_NAME,
    load_server_config,
    server_config_for_workspace,
)

Provider = Literal["kiro-cli", "claude"]

__all__ = ["Provider", "ProviderInfo", "detect_providers", "resolve_provider", "build_command"]


@dataclass(frozen=True)
class ProviderInfo:
    """Um provedor de IA e se esta instalado nesta maquina.

    Attributes:
        id: Identificador do provedor ("kiro-cli" ou "claude").
        label: Nome amigavel para a UI.
        binary: Nome do executavel procurado no PATH.
        installed: True se o binario foi encontrado.
        path: Caminho absoluto do binario, ou None.
    """

    id: Provider
    label: str
    binary: str
    installed: bool
    path: str | None


# Ordem = prioridade de deteccao automatica (kiro primeiro, por ordem de detecção).
_CANDIDATES: list[tuple[Provider, str, str]] = [
    ("kiro-cli", "Kiro CLI", "kiro-cli"),
    ("claude", "Claude Code", "claude"),
]


def detect_providers() -> list[ProviderInfo]:
    """Detecta quais provedores de IA estao instalados no PATH.

    Returns:
        Lista de ProviderInfo (sempre todos os candidatos, com installed=True/False),
        na ordem de prioridade.
    """
    infos: list[ProviderInfo] = []
    for pid, label, binary in _CANDIDATES:
        path = shutil.which(binary)
        infos.append(
            ProviderInfo(
                id=pid,
                label=label,
                binary=binary,
                installed=path is not None,
                path=path,
            )
        )
    return infos


def resolve_provider(requested: str | None) -> ProviderInfo:
    """Resolve qual provedor usar, validando contra o que esta instalado.

    Args:
        requested: Provedor pedido pelo frontend ("kiro-cli"/"claude"), ou None
            para deteccao automatica (primeiro instalado na ordem de prioridade).

    Returns:
        ProviderInfo do provedor escolhido (installed=True garantido).

    Raises:
        RuntimeError: Se o provedor pedido nao esta instalado, ou se nenhum
            provedor esta disponivel.
    """
    infos = detect_providers()
    by_id = {i.id: i for i in infos}

    if requested:
        info = by_id.get(requested)  # type: ignore[arg-type]
        if info is None:
            raise RuntimeError(f"Provedor desconhecido: {requested!r}")
        if not info.installed:
            raise RuntimeError(
                f"Provedor {requested!r} nao esta instalado nesta maquina "
                f"(binario {info.binary!r} nao encontrado no PATH)."
            )
        return info

    # Deteccao automatica: primeiro instalado na ordem de prioridade.
    for info in infos:
        if info.installed:
            return info

    raise RuntimeError(
        "Nenhum provedor de IA instalado. Instale o kiro-cli ou o claude (Claude Code) "
        "e garanta que o binario esteja no PATH."
    )


def _novomodelo_mcp_config(workspace: Path | None = None) -> dict | None:
    """Le a definicao do servidor MCP 'novomodelo' do mcp.json do Kiro.

    O claude nao conhece o servidor 'novomodelo' por padrao (ele tem seu proprio
    registro MCP). Para o claude enxergar as tools novomodelo::*, injetamos a
    config via --mcp-config. Reaproveitamos a MESMA definicao que o kiro-cli usa.

    Args:
        workspace: Se dado, a raiz do path guard do servidor passa a ser ele.

    Returns:
        Dict no formato {"mcpServers": {"novomodelo": {...}}} pronto para
        --mcp-config, ou None se o mcp.json nao tiver o servidor.
    """
    server = server_config_for_workspace(workspace) if workspace else load_server_config()
    if not server:
        return None
    # Mantem so os campos que o claude --mcp-config aceita.
    clean = {"command": server.get("command"), "args": server.get("args", [])}
    if server.get("env"):
        clean["env"] = server["env"]
    return {"mcpServers": {SERVER_NAME: clean}}


def _write_claude_mcp_config(workspace: Path | None = None) -> str | None:
    """Grava a config MCP do novomodelo num arquivo temp para o claude --mcp-config.

    Returns:
        Caminho do arquivo JSON, ou None se o servidor novomodelo nao foi achado.
    """
    cfg = _novomodelo_mcp_config(workspace)
    if cfg is None:
        return None
    fd, path = tempfile.mkstemp(prefix="claude_novomodelo_mcp_", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(cfg, f)
    return path


def build_command(
    provider: ProviderInfo,
    query: str,
    workspace: Path | None = None,
) -> list[str]:
    """Constroi o comando headless do provedor para rodar um prompt.

    kiro-cli: chat --no-interactive --trust-all-tools
              --output-format stream-json "<query>"

              O stream-json emite os eventos ACP do kiro-cli como JSON Lines no
              stdout (um evento autodescritivo por linha). O parser do
              ProviderQueryRunner reconhece os sessionUpdate (tool_call /
              tool_call_update / agent_message_chunk) e o runFinished, extraindo
              tool calls, envelopes MCP e a resposta final direto do stream
              (sem depender do log verbose nem do NOVOMODELO_MCP_RESPONSE_LOG).
              `--output-format stream-json` ja implica `--no-interactive`;
              mantemos `--no-interactive` e `--trust-all-tools` explicitos.
    claude:   --print --verbose --output-format stream-json
              --dangerously-skip-permissions --mcp-config <cfg> --strict-mcp-config
              "<query>"

              VALIDADO (claude 2.1.302): sem --mcp-config o claude NAO ve o
              servidor novomodelo (registro MCP proprio, separado do kiro). Com a
              config injetada, ele conecta o novomodelo e chama as tools como
              mcp__novomodelo__<tool>. O --output-format stream-json emite um
              JSON por linha; o parser do ProviderQueryRunner reconhece os eventos
              tool_use/tool_result e normaliza o prefixo mcp__novomodelo__.

    Args:
        provider: Provedor resolvido (installed=True).
        query: Prompt em linguagem natural.
        workspace: Raiz do path guard do MCP para o claude. O kiro-cli a recebe
            pelo cwd (``<workspace>/.kiro/settings/mcp.json``), nao pelo comando.

    Returns:
        Lista de argumentos para subprocess.
    """
    if provider.id == "kiro-cli":
        return [
            provider.path or provider.binary,
            "chat",
            "--no-interactive",
            "--trust-all-tools",
            "--output-format",
            "stream-json",
            query,
        ]
    if provider.id == "claude":
        cmd = [
            provider.path or provider.binary,
            "--print",
            "--verbose",
            "--output-format",
            "stream-json",
            "--dangerously-skip-permissions",
        ]
        mcp_cfg = _write_claude_mcp_config(workspace)
        if mcp_cfg:
            cmd += ["--mcp-config", mcp_cfg, "--strict-mcp-config"]
        cmd.append(query)
        return cmd
    raise RuntimeError(f"Provedor sem comando definido: {provider.id!r}")
