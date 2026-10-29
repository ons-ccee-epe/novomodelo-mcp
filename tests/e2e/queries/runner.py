"""Parsers de saída de agente e o ponto de entrada de execução da bateria.

O QueryRunner não executa agente no host: a execução passa pelo executor em
container. ``execute`` recusa com ``EXECUCAO_SO_NO_EXECUTOR``; o que fica aqui é a
leitura da saída de um agente (tool calls e resposta final) e o cálculo de timeout
por caso.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, ClassVar

from tests.e2e.queries.mcp_workspace import prepare_workspace
from tests.e2e.queries.models import (
    QueryResult,
    QueryTestCase,
    ToolCall,
)
from tests.e2e.queries.validator import (
    MCP_TOOLS,
    NATIVE_TOOLS,
    classify_tool,
)

__all__ = [
    "DEFAULT_TIMEOUT_S",
    "EXECUCAO_SO_NO_EXECUTOR",
    "QueryRunner",
]

DEFAULT_TIMEOUT_S = 120.0
EXECUCAO_SO_NO_EXECUTOR = "a execução passa pelo executor em container"


class QueryRunner:
    """Interpreta a saída de um agente e recusa executá-lo no host.

    Attributes:
        timeout_seconds: Timeout em segundos aplicado quando o caso não declara o seu.
        api_key: Chave de API opcional para autenticação.
        MCP_TOOLS: Conjunto de tools do MCP novomodelo.
        NATIVE_TOOLS: Conjunto de tools nativas do agente.
    """

    MCP_TOOLS: ClassVar[frozenset[str]] = MCP_TOOLS
    NATIVE_TOOLS: ClassVar[frozenset[str]] = NATIVE_TOOLS

    def __init__(
        self,
        timeout_seconds: float | None = None,
        api_key: str | None = None,
        workspace_dir: str | Path | None = None,
    ) -> None:
        """Inicializa o runner.

        Args:
            timeout_seconds: Timeout forçado (s) para todos os casos. Se None,
                usa QUERY_TIMEOUT_S; sem ele, cada caso usa o próprio ``timeout_s``
                (cases.yaml) e DEFAULT_TIMEOUT_S só quando o caso não tem um.
            api_key: Chave de API opcional para autenticação.
            workspace_dir: Raiz do path guard do MCP (ver ``mcp_workspace``).
                Se None, vale a config global do usuário.
        """
        if timeout_seconds is None and os.environ.get("QUERY_TIMEOUT_S"):
            timeout_seconds = float(os.environ["QUERY_TIMEOUT_S"])
        self._forced_timeout = timeout_seconds
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else DEFAULT_TIMEOUT_S
        self.api_key = api_key
        self.workspace_dir = prepare_workspace(workspace_dir) if workspace_dir else None

    def execute(self, test_case: QueryTestCase) -> QueryResult:
        """Recusa: nenhum agente roda no host.

        Raises:
            RuntimeError: Sempre, com ``EXECUCAO_SO_NO_EXECUTOR``.
        """
        raise RuntimeError(EXECUCAO_SO_NO_EXECUTOR)

    def timeout_for(self, test_case: QueryTestCase) -> float:
        """Timeout aplicado a um caso: o forçado, senão o do caso, senão o fallback."""
        if self._forced_timeout is not None:
            return self._forced_timeout
        return test_case.timeout_s or self.timeout_seconds

    def cancel(self) -> None:
        """Sem processo de agente no host: nada a interromper."""

    def close(self) -> None:
        """Sem recursos do host a liberar."""

    def _parse_tool_calls(self, log_content: str) -> list[ToolCall]:
        """Extrai tool calls do log verbose.

        Extrair Tool_Calls do log verbose parseando padrões
        "Validating tool uses".

        Registrar todas as Tool_Calls para diagnóstico,
        mesmo as não esperadas.

        Parseia múltiplos formatos de log:

        1. Formato AssistantToolUse (Kiro CLI -vvv):
           "Validating tool uses tool_uses=[AssistantToolUse { tool_use_id: "toolu_...",
            name: "deck_list", input: {...} }]"

        2. Formato Tool call simples:
           "Tool call: deck_list({...})"

        3. Formato JSON:
           {"tool": "deck_list", "args": {...}}

        Args:
            log_content: Conteúdo do log stderr.

        Returns:
            Lista de ToolCall extraídas, incluindo todas as calls para diagnóstico.
        """
        tool_calls: list[ToolCall] = []
        seen_ids: set[str] = set()

        # Pattern 1: AssistantToolUse format (new Kiro format)
        # Match: AssistantToolUse { tool_use_id: "toolu_...", name: "tool_name", args: Object {...}, ... }
        assistant_pattern = re.compile(
            r"AssistantToolUse\s*\{\s*"
            r'(?:tool_use_)?id:\s*["\']([^"\']+)["\'],?\s*'
            r'name:\s*["\']([^"\']+)["\']',
            re.DOTALL | re.IGNORECASE,
        )

        for match in assistant_pattern.finditer(log_content):
            tool_id = match.group(1)
            tool_name = match.group(2)

            # Avoid duplicate entries by tool_use_id
            if tool_id in seen_ids:
                continue
            seen_ids.add(tool_id)

            # Try to extract args from the full match context
            # Look for args: Object {...} or args: {...} after this match
            args_match = re.search(
                rf"{re.escape(tool_id)}[^}}]*(?:args|input):\s*(?:Object\s*)?(\{{[^}}]*\}})",
                log_content,
            )
            args = self._parse_args(args_match.group(1)) if args_match else {}

            tool_calls.append(
                ToolCall(
                    name=tool_name,
                    args=args,
                    tool_id=tool_id,
                )
            )

        # Pattern 2: Simpler AssistantToolUse format (alternative structure)
        # Match lines like: name: "deck_list" followed by input
        simple_pattern = re.compile(
            r'name:\s*["\']([a-z_]+)["\'].*?'
            r"(?:input|args|arguments):\s*(\{[^}]*\})",
            re.DOTALL | re.IGNORECASE,
        )

        # Only use if no matches found with pattern 1
        if not tool_calls:
            for match in simple_pattern.finditer(log_content):
                tool_name = match.group(1)
                args_str = match.group(2)
                args = self._parse_args(args_str)
                tool_calls.append(
                    ToolCall(
                        name=tool_name,
                        args=args,
                        tool_id=None,
                    )
                )

        # Pattern 3: Tool call: tool_name({...})
        tool_call_pattern = re.compile(
            r"Tool\s+call:\s*([a-z_]+)\s*\((\{.*?\})\)",
            re.DOTALL | re.IGNORECASE,
        )

        for match in tool_call_pattern.finditer(log_content):
            tool_name = match.group(1)
            args_str = match.group(2)
            args = self._parse_args(args_str)

            # Check if we already have this tool (avoid duplicates)
            if any(tc.name == tool_name and tc.args == args for tc in tool_calls):
                continue

            tool_calls.append(
                ToolCall(
                    name=tool_name,
                    args=args,
                    tool_id=None,
                )
            )

        # Pattern 4: Invoke MCP tool pattern
        # "Invoking tool deck_list" or "Calling MCP tool: deck_list"
        invoke_pattern = re.compile(
            r"(?:Invoking|Calling)\s+(?:MCP\s+)?tool[:\s]+([a-z_]+)",
            re.IGNORECASE,
        )

        for match in invoke_pattern.finditer(log_content):
            tool_name = match.group(1)
            # Only add if not already present
            if not any(tc.name == tool_name for tc in tool_calls):
                tool_calls.append(
                    ToolCall(
                        name=tool_name,
                        args={},
                        tool_id=None,
                    )
                )

        # Pattern 5: Generic tool use from JSON-like output
        # "tool_use" or "tool_name" fields in JSON
        json_tool_pattern = re.compile(
            r'"(?:tool_name|tool|name)":\s*"([a-z_]+)"',
            re.IGNORECASE,
        )

        # Try to find tool names in JSON-like structures (fallback)
        if not tool_calls:
            for match in json_tool_pattern.finditer(log_content):
                tool_name = match.group(1)
                if tool_name and not any(tc.name == tool_name for tc in tool_calls):
                    tool_calls.append(
                        ToolCall(
                            name=tool_name,
                            args={},
                            tool_id=None,
                        )
                    )

        # Pattern 6: New Kiro CLI format (2024+)
        # "[tool] Running: @novomodelo/tool_name" or "[tool] Running: @server/tool_name"
        kiro_tool_pattern = re.compile(
            r"\[tool\]\s+Running:\s+@(?:novomodelo|[a-z-]+)/([a-z_]+)",
            re.IGNORECASE,
        )

        for match in kiro_tool_pattern.finditer(log_content):
            tool_name = match.group(1)
            # Only add if not already present
            if not any(tc.name == tool_name for tc in tool_calls):
                tool_calls.append(
                    ToolCall(
                        name=tool_name,
                        args={},
                        tool_id=None,
                    )
                )

        return tool_calls

    def _parse_args(self, args_str: str) -> dict[str, Any]:
        """Parseia argumentos de tool call de string para dict.

        Tenta interpretar como JSON, com fallbacks para formatos não-standard.

        Args:
            args_str: String contendo os argumentos (formato JSON ou similar).

        Returns:
            Dict com os argumentos parseados, ou dict vazio se falhar.
        """
        if not args_str or not args_str.strip():
            return {}

        # Clean up the string
        cleaned = args_str.strip()

        # Try standard JSON first
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # Try to fix common issues: single quotes instead of double
        try:
            fixed = cleaned.replace("'", '"')
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass

        # Try to extract key-value pairs manually
        # Format: {key: "value", key2: value2}
        try:
            result: dict[str, Any] = {}
            # Remove braces
            inner = cleaned.strip("{}")
            # Split by comma (basic)
            pairs = inner.split(",")
            for pair in pairs:
                if ":" in pair:
                    key, value = pair.split(":", 1)
                    key = key.strip().strip("\"'")
                    value = value.strip().strip("\"'")
                    # Try to convert to appropriate type
                    if value.lower() in ("true", "false"):
                        result[key] = value.lower() == "true"
                    elif value.isdigit():
                        result[key] = int(value)
                    else:
                        try:
                            result[key] = float(value)
                        except ValueError:
                            result[key] = value
            if result:
                return result
        except Exception:
            pass

        # Return empty dict if all parsing fails
        return {}

    def _extract_agent_response(self, stdout: str) -> str:
        """Extrai resposta final do agente do stdout.

        Tenta extrair a resposta do agente removendo elementos de formatação
        do Kiro CLI como prompts, spinners, e metadata.

        A resposta final geralmente aparece após os tool calls e pode estar
        em diferentes formatos dependendo da versão do Kiro CLI.

        Args:
            stdout: Saída padrão capturada do Kiro CLI.

        Returns:
            Resposta final do agente, limpa de elementos de formatação.
        """
        if not stdout:
            return ""

        response = stdout.strip()

        # Remove ANSI escape codes (cores, formatação)
        ansi_pattern = re.compile(r"\x1b\[[0-9;]*m")
        response = ansi_pattern.sub("", response)

        # Remove spinner/progress characters
        spinner_chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏●○◐◑◒◓◔◕"
        for char in spinner_chars:
            response = response.replace(char, "")

        # Remove common Kiro CLI prefixes/prompts
        cli_patterns = [
            r"^>\s*",  # Prompt markers
            r"^\[kiro\]\s*",  # Kiro prefix
            r"^\[agent\]\s*",  # Agent prefix
            r"^Thinking\.\.\.\s*",  # Thinking indicator
            r"^Processing\.\.\.\s*",  # Processing indicator
        ]
        for pattern in cli_patterns:
            response = re.sub(pattern, "", response, flags=re.MULTILINE | re.IGNORECASE)

        # Try to extract the final response block if there are markers
        # Look for common response delimiters
        response_markers = [
            r"(?:Final\s+)?[Rr]esponse:\s*(.*)",
            r"[Aa]ssistant:\s*(.*)",
            r"[Aa]gent:\s*(.*)",
        ]

        for marker in response_markers:
            match = re.search(marker, response, re.DOTALL)
            if match:
                extracted = match.group(1).strip()
                if extracted:
                    response = extracted
                    break

        # Remove trailing tool output markers
        tool_output_patterns = [
            r"\n---\s*$",
            r"\n\[end\]\s*$",
            r"\n\[done\]\s*$",
        ]
        for pattern in tool_output_patterns:
            response = re.sub(pattern, "", response, flags=re.IGNORECASE)

        # Clean up multiple newlines
        response = re.sub(r"\n{3,}", "\n\n", response)

        return response.strip()

    @classmethod
    def classify_tool(cls, tool_name: str) -> str:
        """Classifica uma tool como "mcp", "native", ou "unknown".

        Implements:
        - Identificar MCP_Tools pela lista conhecida de 37 tools
        - Identificar Native_Tools e classificar desconhecidas como native

        Args:
            tool_name: Nome da tool a classificar.

        Returns:
            "mcp" se é tool do novomodelo
            "native" se é tool conhecida do Kiro
            "unknown" se não está em nenhuma lista (tratada como native por segurança)
        """
        return classify_tool(tool_name)
