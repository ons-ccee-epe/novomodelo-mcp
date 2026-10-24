"""QueryRunner multi-provedor.

Estende o QueryRunner existente para rodar o prompt em kiro-cli OU claude,
conforme o provedor resolvido. Sobrescreve:
  - _validate_kiro_cli(): valida o binario do provedor escolhido (nao so kiro-cli)
  - _build_command():      monta o comando headless do provedor (via providers.build_command)
  - _parse_tool_calls / _read_mcp_response_log / _extract_agent_response:
        dispatchers por provedor. Tanto claude quanto kiro-cli usam
        --output-format stream-json, mas com schemas diferentes (Anthropic-style
        vs ACP). Cada metodo despacha para o helper correto (*_claude / *_acp) e,
        para qualquer outro provedor, delega ao parser verbose/arquivo da base.

A execucao via subprocess e a captura de stdout/stderr sao herdadas sem
alteracao. O frontend ve exatamente a mesma bateria, qualquer que seja o provedor.
"""
from __future__ import annotations

import json
from pathlib import Path

from tests.e2e.launcher.providers import ProviderInfo, build_command
from tests.e2e.queries.mcp_workspace import tool_timeout_ms
from tests.e2e.queries.models import ToolCall
from tests.e2e.queries.runner import QueryRunner

__all__ = ["ProviderQueryRunner"]


class ProviderQueryRunner(QueryRunner):
    """QueryRunner que dispara o prompt no provedor de IA escolhido."""

    def __init__(
        self,
        provider: ProviderInfo,
        timeout_seconds: float | None = None,
        api_key: str | None = None,
        response_log_dir: str | None = None,
        workspace_dir: str | Path | None = None,
    ) -> None:
        """Inicializa o runner para um provedor especifico.

        Args:
            provider: Provedor resolvido (installed=True garantido).
            timeout_seconds: Timeout por query (herda o default do QueryRunner).
            api_key: Chave de API opcional.
            response_log_dir: Diretorio de logs de resposta MCP.
            workspace_dir: Raiz do path guard do MCP e cwd do agente.
        """
        self._provider = provider
        self._mcp_config_files: list[Path] = []
        super().__init__(
            timeout_seconds=timeout_seconds,
            api_key=api_key,
            response_log_dir=response_log_dir,
            workspace_dir=workspace_dir,
        )

    def _validate_kiro_cli(self) -> None:
        """Valida o binario do provedor escolhido (nao fixo em kiro-cli).

        O nome do metodo e herdado por compatibilidade; a validacao agora cobre
        qualquer provedor. O ProviderInfo ja garante installed=True na resolucao,
        entao aqui apenas reafirmamos.

        Raises:
            RuntimeError: Se o provedor nao estiver instalado.
        """
        if not self._provider.installed or not self._provider.path:
            raise RuntimeError(
                f"Provedor {self._provider.id!r} nao esta instalado "
                f"(binario {self._provider.binary!r} ausente no PATH)."
            )

    def _build_command(self, query: str) -> list[str]:
        """Monta o comando headless do provedor escolhido.

        Args:
            query: Prompt em linguagem natural.

        Returns:
            Lista de argumentos para subprocess.
        """
        cmd = build_command(self._provider, query, workspace=self.workspace_dir)
        if "--mcp-config" in cmd:
            self._mcp_config_files.append(Path(cmd[cmd.index("--mcp-config") + 1]))
        return cmd

    def _agent_env(self) -> dict[str, str]:
        # O claude não lê "timeout" do --mcp-config; o limite por tool vem desta variável.
        if self._provider.id == "claude":
            return {"MCP_TOOL_TIMEOUT": str(tool_timeout_ms())}
        return {}

    def execute(self, test_case):
        # Cada query do claude grava um mcp-config temporario com o env do
        # usuario; apagar ao fim para nao acumular copias em %TEMP%.
        try:
            return super().execute(test_case)
        finally:
            for cfg in self._mcp_config_files:
                cfg.unlink(missing_ok=True)
            self._mcp_config_files.clear()

    # ------------------------------------------------------------------
    # Parsing de saida estruturada (stream-json) por provedor
    #
    # O QueryRunner base parseia o log verbose (regex) e le os envelopes de um
    # arquivo JSONL (NOVOMODELO_MCP_RESPONSE_LOG). Aqui generalizamos: tanto o
    # claude quanto o kiro-cli emitem --output-format stream-json (um JSON por
    # linha), mas com schemas DIFERENTES:
    #   - claude (Anthropic-style): type "assistant"/"user" com message.content[]
    #     de tool_use / tool_result; nome prefixado mcp__<server>__<tool>; a
    #     resposta final vem no evento type "result".
    #   - kiro-cli (ACP): type "sessionUpdate" com subtipos tool_call /
    #     tool_call_update / agent_message_chunk, e type "runFinished" com
    #     finalText; nome bare em _meta.kiro.toolName; o envelope vem em
    #     rawOutput.items[].Json.content[].text.
    #
    # Cada metodo (_parse_tool_calls, _read_mcp_response_log,
    # _extract_agent_response) e um dispatcher:
    #   claude   -> helper *_claude (comportamento historico, preservado)
    #   kiro-cli -> helper *_acp    (novo, escrito contra o schema ACP real)
    #   outro    -> super()...      (parser verbose/arquivo da base, intacto)
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

        Cobre os dois prefixos observados:
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
        # Guarda o log do claude para o _read_mcp_response_log extrair os
        # envelopes dos eventos tool_result (o claude nao grava no arquivo
        # NOVOMODELO_MCP_RESPONSE_LOG — o envelope vem no proprio stream).
        self._claude_log = log_content

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

    def _read_mcp_response_log(self, log_file, offset: int = 0):
        """Le os envelopes MCP, despachando por provedor.

        claude e kiro-cli extraem os envelopes do proprio stream-json (nenhum
        grava no arquivo NOVOMODELO_MCP_RESPONSE_LOG); os demais delegam ao
        leitor de arquivo herdado.
        """
        if self._provider.id == "claude":
            return self._read_mcp_response_log_claude(log_file, offset=offset)
        if self._provider.id == "kiro-cli":
            return self._read_mcp_response_log_acp(log_file, offset=offset)
        return super()._read_mcp_response_log(log_file, offset=offset)

    def _read_mcp_response_log_claude(self, log_file, offset: int = 0):
        """Envelopes MCP do claude: extraidos dos eventos tool_result."""
        log = getattr(self, "_claude_log", "") or ""
        # Mapeia tool_use_id -> nome da tool (para rotular o envelope).
        id_to_tool: dict[str, str] = {}
        envelopes: list[dict] = []
        for line in log.splitlines():
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                continue
            etype = evt.get("type")
            if etype == "assistant":
                for block in evt.get("message", {}).get("content", []):
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        id_to_tool[block.get("id", "")] = self._strip_mcp_prefix(
                            block.get("name", "")
                        )
            elif etype == "user":
                for block in evt.get("message", {}).get("content", []):
                    if not isinstance(block, dict) or block.get("type") != "tool_result":
                        continue
                    tool_use_id = block.get("tool_use_id", "")
                    tool_name = id_to_tool.get(tool_use_id)
                    if not tool_name:
                        continue
                    result = self._extract_tool_result_payload(block.get("content"))
                    envelopes.append(
                        {
                            "tool": tool_name,
                            "arguments": {},
                            "result": result,
                            "duration_ms": None,
                        }
                    )
        return envelopes

    @staticmethod
    def _extract_tool_result_payload(content):
        """Extrai o payload (dict/str) do content de um tool_result do claude."""
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text", "")
                    try:
                        return json.loads(text)
                    except (json.JSONDecodeError, TypeError):
                        return text
        if isinstance(content, str):
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return content
        return content

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
        # Guarda o log para _read_mcp_response_log_acp reler os envelopes.
        self._kiro_log = log_content

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

    def _read_mcp_response_log_acp(self, log_file, offset: int = 0):
        """Envelopes MCP do kiro-cli: extraidos dos eventos tool_call_update ACP.

        O stream-json e self-contained; ignoramos o arquivo
        NOVOMODELO_MCP_RESPONSE_LOG. Reusa self._kiro_log (gravado em
        _parse_tool_calls_acp); se ausente (chamado isolado), le de log_file.
        """
        log = getattr(self, "_kiro_log", "") or ""

        # Mapeia toolCallId -> nome bare da tool (dos eventos tool_call).
        id_to_tool: dict[str, str] = {}
        envelopes: list[dict] = []
        for evt in self._iter_acp_events(log):
            if evt.get("type") != "sessionUpdate":
                continue
            update = evt.get("data", {}).get("update", {})
            if not isinstance(update, dict):
                continue
            subtype = update.get("sessionUpdate")
            if subtype == "tool_call":
                tool_id = update.get("toolCallId", "")
                if tool_id:
                    id_to_tool[tool_id] = self._acp_tool_name(update)
            elif subtype == "tool_call_update":
                tool_id = update.get("toolCallId", "")
                tool_name = id_to_tool.get(tool_id) or self._acp_tool_name(update)
                if not tool_name:
                    continue
                result = self._extract_acp_output_payload(update.get("rawOutput"))
                raw_input = update.get("rawInput")
                envelopes.append(
                    {
                        "tool": tool_name,
                        "arguments": raw_input if isinstance(raw_input, dict) else {},
                        "result": result,
                        "duration_ms": None,
                    }
                )
        return envelopes

    @staticmethod
    def _extract_acp_output_payload(raw_output):
        """Extrai o payload do rawOutput de um tool_call_update ACP.

        Forma observada: {"items": [{"Json": {"content": [{"type":"text",
        "text": "<json-string>"}], "isError": false}}]}. Parseia o text como
        JSON quando possivel; cai para a string/objeto bruto caso contrario.
        """
        if not isinstance(raw_output, dict):
            return raw_output
        items = raw_output.get("items")
        if not isinstance(items, list):
            return raw_output
        for item in items:
            if not isinstance(item, dict):
                continue
            payload = item.get("Json") or item.get("json")
            if not isinstance(payload, dict):
                continue
            content = payload.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text", "")
                        try:
                            return json.loads(text)
                        except (json.JSONDecodeError, TypeError):
                            return text
            # Sem content textual: devolve o proprio payload Json.
            return payload
        return raw_output

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
                if isinstance(update, dict) and update.get("sessionUpdate") == "agent_message_chunk":
                    content = update.get("content", {})
                    if isinstance(content, dict) and isinstance(content.get("text"), str):
                        chunks.append(content["text"])
        if final_text.strip():
            return final_text.strip()
        return "".join(chunks).strip()
