"""QueryRunner multi-provedor: leitura da saída stream-json de claude e kiro-cli.

Estende o QueryRunner com o parsing da saída estruturada de cada provedor:
  - _parse_tool_calls / _extract_agent_response: despachantes por provedor
    (claude: eventos Anthropic-style; kiro-cli: eventos ACP; outro: parser verbose
    da base).

A execução do agente não acontece aqui: passa pelo executor em container.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.e2e.launcher.providers import ProviderInfo
from tests.e2e.queries.models import ToolCall
from tests.e2e.queries.runner import QueryRunner

__all__ = ["ProviderQueryRunner"]


class ProviderQueryRunner(QueryRunner):
    """QueryRunner que interpreta a saída do provedor de IA escolhido."""

    def __init__(
        self,
        provider: ProviderInfo,
        timeout_seconds: float | None = None,
        api_key: str | None = None,
        workspace_dir: str | Path | None = None,
    ) -> None:
        """Inicializa o runner para um provedor especifico.

        Args:
            provider: Provedor resolvido.
            timeout_seconds: Timeout por query (herda o default do QueryRunner).
            api_key: Chave de API opcional.
            workspace_dir: Raiz do path guard do MCP.
        """
        self._provider = provider
        super().__init__(
            timeout_seconds=timeout_seconds,
            api_key=api_key,
            workspace_dir=workspace_dir,
        )

    # ------------------------------------------------------------------
    # Parsing de saida estruturada (stream-json) por provedor
    #
    # O QueryRunner base parseia o log verbose (regex). Aqui generalizamos: tanto o
    # claude quanto o kiro-cli emitem --output-format stream-json (um JSON por
    # linha), mas com schemas DIFERENTES:
    #   - claude (Anthropic-style): type "assistant"/"user" com message.content[]
    #     de tool_use / tool_result; nome prefixado mcp__<server>__<tool>; a
    #     resposta final vem no evento type "result".
    #   - kiro-cli (ACP): type "sessionUpdate" com subtipos tool_call /
    #     tool_call_update / agent_message_chunk, e type "runFinished" com
    #     finalText; nome bare em _meta.kiro.toolName.
    #
    # Cada metodo (_parse_tool_calls, _extract_agent_response) e um dispatcher:
    #   claude   -> helper *_claude
    #   kiro-cli -> helper *_acp    (escrito contra o schema ACP real)
    #   outro    -> super()...      (parser verbose da base, intacto)
    #
    # VALIDADO:
    #   - claude 2.1.302: tool_use carrega name "mcp__novomodelo__<tool>" e o
    #     tool_result traz o envelope em content[].text.
    #   - kiro-cli 2.33.0: ver tests/e2e/.agents/tasks/kiro-cli-streamjson/
    #     acp_schema_notes.md (amostra real em acp_sample.jsonl).
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_mcp_prefix(name: str) -> str:
        """Normaliza o nome da tool para o nome bare (casa com MCP_TOOLS).

        Novomodelo os dois prefixos observados:
          - claude:   mcp__<server>__<tool>  -> <tool>
          - kiro-cli: @<server>/<tool>       -> <tool>
        """
        if not name:
            return name
        if name.startswith("mcp__"):
            return name.split("__")[-1]
        if "/" in name:
            # "@novomodelo/server_info" ou "novomodelo/server_info"
            return name.rsplit("/", 1)[-1]
        return name

    def _parse_tool_calls(self, log_content: str) -> list[ToolCall]:
        """Extrai tool calls, despachando por provedor.

        claude -> eventos stream-json Anthropic-style; kiro-cli -> eventos ACP;
        demais -> parser verbose herdado do QueryRunner.
        """
        if self._provider.id == "claude":
            return self._parse_tool_calls_claude(log_content)
        if self._provider.id == "kiro-cli":
            return self._parse_tool_calls_acp(log_content)
        return super()._parse_tool_calls(log_content)

    def _parse_tool_calls_claude(self, log_content: str) -> list[ToolCall]:
        """Parser de tool calls do claude (stream-json Anthropic-style)."""
        tool_calls: list[ToolCall] = []
        for line in log_content.splitlines():
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                continue
            if evt.get("type") != "assistant":
                continue
            content = evt.get("message", {}).get("content", [])
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    name = self._strip_mcp_prefix(block.get("name", ""))
                    # Ignora a tool interna ToolSearch do claude (nao e MCP).
                    if not name or name.lower() == "toolsearch":
                        continue
                    tool_calls.append(
                        ToolCall(
                            name=name,
                            args=block.get("input", {}) or {},
                            tool_id=block.get("id"),
                        )
                    )
        return tool_calls

    def _extract_agent_response(self, stdout: str) -> str:
        """Extrai a resposta final do agente, despachando por provedor.

        claude -> campo result do evento type=result; kiro-cli -> finalText do
        runFinished (fallback: concatenacao dos agent_message_chunk); demais ->
        extrator verbose herdado.
        """
        if self._provider.id == "claude":
            return self._extract_agent_response_claude(stdout)
        if self._provider.id == "kiro-cli":
            return self._extract_agent_response_acp(stdout)
        return super()._extract_agent_response(stdout)

    def _extract_agent_response_claude(self, stdout: str) -> str:
        """Resposta final do claude: campo result do evento type=result."""
        result_text = ""
        for line in stdout.splitlines():
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                continue
            if evt.get("type") == "result" and isinstance(evt.get("result"), str):
                result_text = evt["result"]
        return result_text.strip()

    # ------------------------------------------------------------------
    # Helpers do schema ACP (kiro-cli --output-format stream-json)
    #
    # Ver tests/e2e/.agents/tasks/kiro-cli-streamjson/acp_schema_notes.md para o
    # schema real capturado (acp_sample.jsonl). Resumo:
    #   - tool_call:        data.update.sessionUpdate == "tool_call"
    #                       nome bare em data.update._meta.kiro.toolName
    #                       id em data.update.toolCallId; args em data.update.rawInput
    #   - tool_call_update: data.update.sessionUpdate == "tool_call_update"
    #                       envelope em data.update.rawOutput.items[].Json.content[].text
    #   - resposta final:   type == "runFinished" -> data.finalText
    #                       (fallback: concat de agent_message_chunk)
    # ------------------------------------------------------------------

    @staticmethod
    def _iter_acp_events(log_content: str):
        """Itera os eventos ACP (um objeto JSON por linha) do stream-json."""
        for line in log_content.splitlines():
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue

    @classmethod
    def _acp_tool_name(cls, update: dict) -> str:
        """Nome bare da tool a partir de um update de tool_call ACP.

        Preferencia: data.update._meta.kiro.toolName (ja bare). Fallback: extrai
        do title ("Running: @novomodelo/server_info") e normaliza o prefixo.
        """
        meta = update.get("_meta", {})
        if isinstance(meta, dict):
            kiro = meta.get("kiro", {})
            if isinstance(kiro, dict):
                name = kiro.get("toolName")
                if name:
                    return cls._strip_mcp_prefix(name)
        title = update.get("title", "") or ""
        # "Running: @novomodelo/server_info" -> "@novomodelo/server_info"
        candidate = title.split(":", 1)[-1].strip() if ":" in title else title.strip()
        return cls._strip_mcp_prefix(candidate)

    def _parse_tool_calls_acp(self, log_content: str) -> list[ToolCall]:
        """Extrai tool calls do stream ACP do kiro-cli."""
        tool_calls: list[ToolCall] = []
        seen_ids: set[str] = set()
        for evt in self._iter_acp_events(log_content):
            if evt.get("type") != "sessionUpdate":
                continue
            update = evt.get("data", {}).get("update", {})
            if not isinstance(update, dict) or update.get("sessionUpdate") != "tool_call":
                continue
            tool_id = update.get("toolCallId")
            if tool_id and tool_id in seen_ids:
                continue
            if tool_id:
                seen_ids.add(tool_id)
            name = self._acp_tool_name(update)
            if not name:
                continue
            raw_input = update.get("rawInput")
            args = raw_input if isinstance(raw_input, dict) else {}
            tool_calls.append(ToolCall(name=name, args=args, tool_id=tool_id))
        return tool_calls

    def _extract_agent_response_acp(self, stdout: str) -> str:
        """Resposta final do kiro-cli: finalText do runFinished.

        Fallback: concatena os agent_message_chunk se finalText faltar.
        """
        final_text = ""
        chunks: list[str] = []
        for evt in self._iter_acp_events(stdout):
            etype = evt.get("type")
            if etype == "runFinished":
                text = evt.get("data", {}).get("finalText")
                if isinstance(text, str):
                    final_text = text
            elif etype == "sessionUpdate":
                update = evt.get("data", {}).get("update", {})
                if (
                    isinstance(update, dict)
                    and update.get("sessionUpdate") == "agent_message_chunk"
                ):
                    content = update.get("content", {})
                    if isinstance(content, dict) and isinstance(content.get("text"), str):
                        chunks.append(content["text"])
        if final_text.strip():
            return final_text.strip()
        return "".join(chunks).strip()
