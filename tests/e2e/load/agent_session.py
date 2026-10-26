"""Isolamento de uma sessão de agente da carga: nada que uma sessão grava é lido por outra.

Cada sessão tem uma pasta própria sob a raiz temporária do run:

- ``tmp/``: TEMP/TMP/TMPDIR do agente e do servidor MCP. O servidor exporta os schemas
  para ``<TEMP>/novomodelo_mcp_schemas`` na primeira chamada; com o TEMP comum, um
  servidor leria arquivos que outro ainda está gravando.
- ``mcp-state/``: NOVOMODELO_MCP_STATE_DIR (jobs e calibração), longe do state dir do usuário.
- ``mcp-responses.jsonl``: NOVOMODELO_MCP_RESPONSE_LOG da sessão, mesmo que o ambiente do
  launcher defina outro.
- kiro-cli: ``workspace/.kiro/settings/mcp.json`` e esse ``workspace`` como cwd. O kiro lê a
  definição do servidor do cwd; só assim o ambiente acima chega ao servidor sem depender
  de o kiro repassar o próprio ambiente, e o ``mcp.json`` das fixtures (o da esteira)
  não é regravado.
- claude: ``claude-mcp.json`` para o ``--mcp-config`` e ``--no-session-persistence``. O cwd
  fica nas fixtures, como na esteira: o claude procura o CLAUDE.md subindo a partir do
  cwd, e um cwd temporário mudaria o contexto do agente.
- ``fixtures/``: a cópia das fixtures (``sandbox.SessionSandbox``) quando a seleção tem caso
  que grava. O servidor da sessão só enxerga a cópia (``NOVOMODELO_MCP_WORKSPACE``), o
  prompt de cada caso é reescrito para ela e, antes de cada execução depois da primeira, ela
  volta ao estado da subida: o caso seguinte não encontra o que o anterior gravou.

O servidor de toda sessão roda com ``NOVOMODELO_MCP_MAX_JOBS=0``: nenhum agente dispara o
solver, nem por conta própria.

O agente espera a subida do servidor MCP tanto quanto o modo tools espera
(``client.STARTUP_TIMEOUT_S``): com N servidores subindo juntos, o limite padrão do
claude estoura, o agente fica sem as tools do MCP e a carga mediria isso, não o
servidor.
"""
from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from tests.e2e.launcher.provider_runner import ProviderQueryRunner
from tests.e2e.launcher.providers import ProviderInfo, build_command, claude_mcp_config
from tests.e2e.load.client import STARTUP_TIMEOUT_S
from tests.e2e.load.sandbox import (
    MAX_JOBS_ENV,
    STATE_DIR_ENV,
    TEMP_VARS,
    SandboxPlan,
    SessionSandbox,
    make_run_root,
)
from tests.e2e.queries.mcp_workspace import SERVER_NAME, WORKSPACE_ENV
from tests.e2e.queries.models import QueryResult, QueryTestCase

__all__ = [
    "AgentSessionRunner",
    "SessionPaths",
    "default_run_root",
    "prepare_session",
    "session_server_config",
]

RESPONSE_LOG_ENV = "NOVOMODELO_MCP_RESPONSE_LOG"
MCP_STARTUP_TIMEOUT_MS = int(STARTUP_TIMEOUT_S * 1000)
# Limite de subida dos servidores MCP: variável do claude e chave do mcp.json do kiro-cli.
_CLAUDE_STARTUP_ENV = "MCP_TIMEOUT"
_KIRO_STARTUP_KEY = "initializationTimeout"


@dataclass(frozen=True)
class SessionPaths:
    """Arquivos e pastas exclusivos de uma sessão."""

    index: int
    root: Path
    tmp: Path
    state: Path
    response_log: Path
    kiro_workspace: Path
    claude_config: Path
    sandbox: SessionSandbox | None = None

    @classmethod
    def under(cls, run_root: Path, index: int) -> SessionPaths:
        root = Path(run_root) / f"s{index}"
        return cls(
            index=index,
            root=root,
            tmp=root / "tmp",
            state=root / "mcp-state",
            response_log=root / "mcp-responses.jsonl",
            kiro_workspace=root / "workspace",
            claude_config=root / "claude-mcp.json",
        )

    def env(self) -> dict[str, str]:
        """Variáveis que isolam a sessão: TEMP, state dir e log de respostas do MCP."""
        values = {RESPONSE_LOG_ENV: str(self.response_log), STATE_DIR_ENV: str(self.state)}
        values.update(dict.fromkeys(TEMP_VARS, str(self.tmp)))
        return values


def session_server_config(server: dict[str, Any], paths: SessionPaths) -> dict[str, Any]:
    """Cópia da definição do servidor com o ambiente da sessão por cima do original.

    Com a cópia das fixtures, o path guard da sessão é só ela: manter as fixtures originais
    como raiz deixaria um caso que grava alterá-las.
    """
    env = {**(server.get("env") or {}), **paths.env(), MAX_JOBS_ENV: "0"}
    if paths.sandbox is not None and paths.sandbox.enabled:
        env[WORKSPACE_ENV] = paths.sandbox.workspace_env()
    return {**server, "env": env}


def prepare_session(
    run_root: Path,
    index: int,
    server: dict[str, Any],
    provider_id: str,
    sandbox_plan: SandboxPlan | None = None,
) -> SessionPaths:
    """Cria a pasta da sessão ``index`` (e a cópia das fixtures, se o plano pede) e grava a
    config MCP que só ela lê."""
    paths = SessionPaths.under(run_root, index)
    for folder in (paths.tmp, paths.state):
        folder.mkdir(parents=True, exist_ok=True)
    if sandbox_plan is not None and sandbox_plan.enabled:
        sandbox = SessionSandbox(sandbox_plan, paths.root)
        sandbox.create()
        paths = replace(paths, sandbox=sandbox)
    session_server = session_server_config(server, paths)
    if provider_id == "kiro-cli":
        settings = paths.kiro_workspace / ".kiro" / "settings"
        settings.mkdir(parents=True, exist_ok=True)
        session_server.setdefault(_KIRO_STARTUP_KEY, MCP_STARTUP_TIMEOUT_MS)
        payload: dict[str, Any] = {"mcpServers": {SERVER_NAME: session_server}}
        (settings / "mcp.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    else:
        paths.claude_config.write_text(
            json.dumps(claude_mcp_config(session_server), indent=2), encoding="utf-8"
        )
    return paths


class AgentSessionRunner(ProviderQueryRunner):
    """``ProviderQueryRunner`` de uma sessão: cwd, config MCP, TEMP e log de respostas próprios.

    Uma instância roda um caso por vez (o processo em curso é estado da instância);
    cada sessão da carga tem a sua.
    """

    def __init__(
        self,
        provider: ProviderInfo,
        paths: SessionPaths,
        fixtures_dir: str | Path,
        timeout_seconds: float | None = None,
        denied_tools: Iterable[str] = (),
    ) -> None:
        self._paths = paths
        self._denied_tools = tuple(denied_tools)
        self._executions = 0
        super().__init__(
            provider=provider,
            timeout_seconds=timeout_seconds,
            response_log_dir=str(paths.root),
            workspace_dir=None,
        )
        self.workspace_dir = (
            paths.kiro_workspace if provider.id == "kiro-cli" else Path(fixtures_dir).resolve()
        )

    @property
    def paths(self) -> SessionPaths:
        return self._paths

    @property
    def copy_ms(self) -> float | None:
        """Tempo da cópia das fixtures da sessão, à parte do preparo; None sem cópia."""
        sandbox = self._paths.sandbox
        if sandbox is None or sandbox.copy_seconds is None:
            return None
        return sandbox.copy_seconds * 1000.0

    def execute(self, test_case: QueryTestCase) -> QueryResult:
        """Roda o caso na cópia da sessão, se houver: prompt e fontes apontam para ela."""
        sandbox = self._paths.sandbox
        if sandbox is not None and sandbox.enabled:
            if self._executions:
                sandbox.reset()
            self._executions += 1
            test_case = replace(
                test_case,
                query=sandbox.rewrite(test_case.query),
                requires=tuple(sandbox.rewrite(source) for source in test_case.requires),
            )
        return super().execute(test_case)

    def _response_log_file(self, test_case: QueryTestCase) -> Path:
        return self._paths.response_log

    def _agent_env(self) -> dict[str, str]:
        env = {**super()._agent_env(), **self._paths.env()}
        if self._provider.id == "claude":
            env[_CLAUDE_STARTUP_ENV] = os.environ.get(
                _CLAUDE_STARTUP_ENV, str(MCP_STARTUP_TIMEOUT_MS)
            )
        return env

    def _build_command(self, query: str) -> list[str]:
        if self._provider.id != "claude":
            return build_command(self._provider, query)
        return build_command(
            self._provider,
            query,
            mcp_config_path=self._paths.claude_config,
            persist_session=False,
            disallowed_tools=[f"mcp__{SERVER_NAME}__{tool}" for tool in self._denied_tools],
        )


def default_run_root(work_dir: str | Path | None = None) -> Path:
    """Pasta-raiz temporária das sessões de um run, em ``work_dir`` (ou no TEMP do motor)."""
    return make_run_root(work_dir, f"novomodelo-load-agent-{os.getpid()}-")
