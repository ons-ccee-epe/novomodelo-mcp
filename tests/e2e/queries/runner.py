"""Execução de queries via Kiro CLI.

Este módulo implementa o QueryRunner que executa queries em linguagem natural
via Kiro CLI e extrai informações do output para validação.

O fluxo de execução é:
1. Validar que Kiro CLI está instalado
2. Configurar log de respostas MCP (NOVOMODELO_MCP_RESPONSE_LOG)
3. Construir comando com flags apropriadas
4. Executar query com timeout
5. Parsear tool calls do log verbose
6. Ler envelopes MCP do arquivo de log de respostas
7. Extrair resposta do agente
8. Retornar QueryResult para validação
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, ClassVar

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
    "QueryRunner",
]


class QueryRunner:
    """Executa queries via Kiro CLI.

    O QueryRunner é responsável por:
    - Validar que o Kiro CLI está instalado
    - Configurar captura de respostas MCP via NOVOMODELO_MCP_RESPONSE_LOG
    - Executar queries em modo não-interativo
    - Parsear tool calls do log verbose
    - Ler envelopes MCP do arquivo de log de respostas
    - Extrair resposta do agente
    - Retornar QueryResult com métricas de execução

    Attributes:
        timeout_seconds: Timeout em segundos para execução da query.
        api_key: Chave de API opcional para autenticação.
        MCP_TOOLS: Conjunto de tools do MCP novomodelo (37 tools).
        NATIVE_TOOLS: Conjunto de tools nativas do Kiro.

    Example:
        >>> runner = QueryRunner(timeout_seconds=60.0)
        >>> result = runner.execute(test_case)
        >>> print(f"Tool calls: {len(result.tool_calls)}")
        >>> print(f"Latency: {result.latency_ms}ms")
        >>> if result.envelope:
        ...     print(f"MCP envelope: {result.envelope}")
    """

    # Reexpose constants from validator for backwards compatibility and design conformance
    MCP_TOOLS: ClassVar[frozenset[str]] = MCP_TOOLS
    NATIVE_TOOLS: ClassVar[frozenset[str]] = NATIVE_TOOLS

    def __init__(
        self,
        timeout_seconds: float | None = None,
        api_key: str | None = None,
        response_log_dir: str | None = None,
    ) -> None:
        """Inicializa o QueryRunner.

        Args:
            timeout_seconds: Timeout em segundos para execução da query.
                Se None, usa variável de ambiente QUERY_TIMEOUT_S ou padrão de 120s (Req 2.7).
            api_key: Chave de API opcional para autenticação.
                Se não fornecida, assume autenticação via kiro-cli login (Req 19.4).
            response_log_dir: Diretório para arquivos de log de respostas MCP.
                Se None, usa diretório temporário.

        Raises:
            RuntimeError: Se Kiro CLI não está instalado (Req 19.5).
        """
        if timeout_seconds is None:
            timeout_seconds = float(os.environ.get("QUERY_TIMEOUT_S", "120"))
        self.timeout_seconds = timeout_seconds
        self.api_key = api_key
        
        # Configurar diretório para logs de resposta MCP
        if response_log_dir:
            self._response_log_dir = Path(response_log_dir)
            self._response_log_dir.mkdir(parents=True, exist_ok=True)
        else:
            self._temp_dir = tempfile.mkdtemp(prefix="mcp_response_log_")
            self._response_log_dir = Path(self._temp_dir)
        
        self._validate_kiro_cli()

    def execute(self, test_case: QueryTestCase) -> QueryResult:
        """Executa uma query via Kiro CLI.

        Implements:
        - Req 2.1: Invocar kiro-cli chat --no-interactive --trust-all-tools -vvv
        - Req 2.2: Capturar stdout e stderr do Kiro CLI para parsing
        - Req 2.3: Garantir Session_Isolation iniciando sessão limpa
        - Req 2.5: Coletar tempo total de execução em milissegundos
        - NEW: Capturar envelopes MCP via NOVOMODELO_MCP_RESPONSE_LOG

        Args:
            test_case: Caso de teste a executar.

        Returns:
            QueryResult com tool_calls, resposta, envelope MCP e métricas.
        """
        # Check if there's a fixed log file configured
        # Priority: env var > mcp.json > fallback to temp file
        fixed_log_file = os.environ.get("NOVOMODELO_MCP_RESPONSE_LOG")
        if not fixed_log_file:
            # Try to read from mcp.json (Kiro's user-level config)
            fixed_log_file = self._read_log_path_from_mcp_json()
        
        if fixed_log_file:
            log_file = Path(fixed_log_file)
        else:
            # Fallback to unique log file per test (won't work if server already running)
            log_file = self._response_log_dir / f"mcp_responses_{test_case.id}_{int(time.time() * 1000)}.jsonl"
        
        # Record log file size before test to read only new entries after
        log_size_before = log_file.stat().st_size if log_file.exists() else 0
        
        # Build command (Req 2.1)
        cmd = self._build_command(test_case.query)
        
        # Prepare environment with MCP response logging enabled
        env = os.environ.copy()
        env["NOVOMODELO_MCP_RESPONSE_LOG"] = str(log_file)

        # Execute with subprocess and measure time (Req 2.2, 2.3, 2.5)
        start_time = time.perf_counter()
        try:
            process = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",  # Explicit UTF-8 encoding for Windows compatibility
                errors="replace",  # Handle any remaining encoding issues gracefully
                timeout=self.timeout_seconds,
                env=env,
            )
            status = "completed"
            stdout = process.stdout
            stderr = process.stderr
        except subprocess.TimeoutExpired as e:
            # Req 2.6: Reter dados parciais capturados em caso de timeout
            status = "timeout"
            stdout = e.stdout if e.stdout else ""
            stderr = e.stderr if e.stderr else ""
            # Ensure stdout/stderr are strings, not bytes
            # (TimeoutExpired may return bytes when encoding is specified)
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")

        end_time = time.perf_counter()
        latency_ms = (end_time - start_time) * 1000

        # Parse tool calls from stderr AND stdout (Kiro may output logs to either)
        # Combine both streams for parsing to ensure we capture tool calls
        combined_log = (stderr or "") + "\n" + (stdout or "")
        tool_calls = self._parse_tool_calls(combined_log)
        
        # Read MCP response envelopes from log file (only new entries)
        mcp_responses = self._read_mcp_response_log(log_file, offset=log_size_before)
        
        # Match tool calls with their MCP envelopes
        envelope = self._extract_primary_envelope(tool_calls, mcp_responses)

        # Extract agent response from stdout
        agent_response = self._extract_agent_response(stdout)

        return QueryResult(
            test_case=test_case,
            tool_calls=tool_calls,
            agent_response=agent_response,
            latency_ms=latency_ms,
            status=status,
            stdout=stdout,
            stderr=stderr,
            envelope=envelope,
        )
    
    def _read_mcp_response_log(self, log_file: Path, offset: int = 0) -> list[dict[str, Any]]:
        """Lê o arquivo de log de respostas MCP.
        
        Args:
            log_file: Caminho para o arquivo JSONL de log.
            offset: Posição em bytes a partir da qual ler (para ler só entradas novas).
            
        Returns:
            Lista de entradas de log, cada uma com tool, arguments, result, duration_ms.
        """
        if not log_file.exists():
            return []
        
        entries = []
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                if offset > 0:
                    f.seek(offset)
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
        except Exception:
            pass
        
        return entries
    
    def _extract_primary_envelope(
        self,
        tool_calls: list[ToolCall],
        mcp_responses: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Extrai o envelope MCP da tool principal.
        
        Encontra a primeira tool MCP chamada e retorna seu envelope de resposta.
        
        Args:
            tool_calls: Lista de tool calls detectadas no log.
            mcp_responses: Lista de respostas MCP do arquivo de log.
            
        Returns:
            Envelope MCP da tool principal, ou None se não encontrado.
        """
        if not mcp_responses:
            return None
        
        # Find the first MCP tool call
        for tc in tool_calls:
            if classify_tool(tc.name) == "mcp":
                # Find matching response in MCP log
                for response in mcp_responses:
                    if response.get("tool") == tc.name:
                        return {
                            "tool": response.get("tool"),
                            "arguments": response.get("arguments"),
                            "result": response.get("result"),
                            "duration_ms": response.get("duration_ms"),
                        }
        
        # If no match found, return the first MCP response (fallback)
        if mcp_responses:
            first = mcp_responses[0]
            return {
                "tool": first.get("tool"),
                "arguments": first.get("arguments"),
                "result": first.get("result"),
                "duration_ms": first.get("duration_ms"),
            }
        
        return None

    def _build_command(self, query: str) -> list[str]:
        """Constrói comando Kiro CLI.

        Args:
            query: Query em linguagem natural a ser executada.

        Returns:
            Lista de argumentos para subprocess (Req 2.1).
        """
        return [
            "kiro-cli",
            "chat",
            "--no-interactive",
            "--trust-all-tools",
            "-vvv",
            query,
        ]

    def _parse_tool_calls(self, log_content: str) -> list[ToolCall]:
        """Extrai tool calls do log verbose.

        Implements Req 2.4: Extrair Tool_Calls do log verbose parseando padrões
        "Validating tool uses".

        Implements Req 3.6: Registrar todas as Tool_Calls para diagnóstico,
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
        # Match: AssistantToolUse { id: "toolu_...", name: "tool_name", orig_name: "...", args: Object {...}, ... }
        assistant_pattern = re.compile(
            r'AssistantToolUse\s*\{\s*'
            r'id:\s*["\']([^"\']+)["\'],?\s*'
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
                rf'{re.escape(tool_id)}[^}}]*args:\s*(?:Object\s*)?(\{{[^}}]*\}})',
                log_content
            )
            args = self._parse_args(args_match.group(1)) if args_match else {}

            tool_calls.append(ToolCall(
                name=tool_name,
                args=args,
                tool_id=tool_id,
            ))

        # Pattern 2: Simpler AssistantToolUse format (alternative structure)
        # Match lines like: name: "deck_list" followed by input
        simple_pattern = re.compile(
            r'name:\s*["\']([a-z_]+)["\'].*?'
            r'(?:input|args|arguments):\s*(\{[^}]*\})',
            re.DOTALL | re.IGNORECASE,
        )

        # Only use if no matches found with pattern 1
        if not tool_calls:
            for match in simple_pattern.finditer(log_content):
                tool_name = match.group(1)
                args_str = match.group(2)
                args = self._parse_args(args_str)
                tool_calls.append(ToolCall(
                    name=tool_name,
                    args=args,
                    tool_id=None,
                ))

        # Pattern 3: Tool call: tool_name({...})
        tool_call_pattern = re.compile(
            r'Tool\s+call:\s*([a-z_]+)\s*\((\{.*?\})\)',
            re.DOTALL | re.IGNORECASE,
        )

        for match in tool_call_pattern.finditer(log_content):
            tool_name = match.group(1)
            args_str = match.group(2)
            args = self._parse_args(args_str)

            # Check if we already have this tool (avoid duplicates)
            if any(tc.name == tool_name and tc.args == args for tc in tool_calls):
                continue

            tool_calls.append(ToolCall(
                name=tool_name,
                args=args,
                tool_id=None,
            ))

        # Pattern 4: Invoke MCP tool pattern
        # "Invoking tool deck_list" or "Calling MCP tool: deck_list"
        invoke_pattern = re.compile(
            r'(?:Invoking|Calling)\s+(?:MCP\s+)?tool[:\s]+([a-z_]+)',
            re.IGNORECASE,
        )

        for match in invoke_pattern.finditer(log_content):
            tool_name = match.group(1)
            # Only add if not already present
            if not any(tc.name == tool_name for tc in tool_calls):
                tool_calls.append(ToolCall(
                    name=tool_name,
                    args={},
                    tool_id=None,
                ))

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
                    tool_calls.append(ToolCall(
                        name=tool_name,
                        args={},
                        tool_id=None,
                    ))

        # Pattern 6: New Kiro CLI format (2024+)
        # "[tool] Running: @novomodelo/tool_name" or "[tool] Running: @server/tool_name"
        kiro_tool_pattern = re.compile(
            r'\[tool\]\s+Running:\s+@(?:novomodelo|[a-z-]+)/([a-z_]+)',
            re.IGNORECASE,
        )

        for match in kiro_tool_pattern.finditer(log_content):
            tool_name = match.group(1)
            # Only add if not already present
            if not any(tc.name == tool_name for tc in tool_calls):
                tool_calls.append(ToolCall(
                    name=tool_name,
                    args={},
                    tool_id=None,
                ))

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
                    key = key.strip().strip('"\'')
                    value = value.strip().strip('"\'')
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
        ansi_pattern = re.compile(r'\x1b\[[0-9;]*m')
        response = ansi_pattern.sub("", response)

        # Remove spinner/progress characters
        spinner_chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏●○◐◑◒◓◔◕"
        for char in spinner_chars:
            response = response.replace(char, "")

        # Remove common Kiro CLI prefixes/prompts
        cli_patterns = [
            r'^>\s*',  # Prompt markers
            r'^\[kiro\]\s*',  # Kiro prefix
            r'^\[agent\]\s*',  # Agent prefix
            r'^Thinking\.\.\.\s*',  # Thinking indicator
            r'^Processing\.\.\.\s*',  # Processing indicator
        ]
        for pattern in cli_patterns:
            response = re.sub(pattern, "", response, flags=re.MULTILINE | re.IGNORECASE)

        # Try to extract the final response block if there are markers
        # Look for common response delimiters
        response_markers = [
            r'(?:Final\s+)?[Rr]esponse:\s*(.*)',
            r'[Aa]ssistant:\s*(.*)',
            r'[Aa]gent:\s*(.*)',
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
            r'\n---\s*$',
            r'\n\[end\]\s*$',
            r'\n\[done\]\s*$',
        ]
        for pattern in tool_output_patterns:
            response = re.sub(pattern, "", response, flags=re.IGNORECASE)

        # Clean up multiple newlines
        response = re.sub(r'\n{3,}', "\n\n", response)

        return response.strip()

    @classmethod
    def classify_tool(cls, tool_name: str) -> str:
        """Classifica uma tool como "mcp", "native", ou "unknown".

        Implements:
        - Req 3.3: Identificar MCP_Tools pela lista conhecida de 37 tools
        - Req 3.4: Identificar Native_Tools e classificar desconhecidas como native

        Args:
            tool_name: Nome da tool a classificar.

        Returns:
            "mcp" se é tool do novomodelo
            "native" se é tool conhecida do Kiro
            "unknown" se não está em nenhuma lista (tratada como native por segurança)
        """
        return classify_tool(tool_name)

    def _validate_kiro_cli(self) -> None:
        """Valida que Kiro CLI está instalado.

        Implements:
        - Req 19.5: THE Query_Runner SHALL validar que Kiro CLI está instalado
                    antes de executar testes

        Raises:
            RuntimeError: Se kiro-cli não está disponível no PATH.
        """
        if shutil.which("kiro-cli") is None:
            raise RuntimeError(
                "Kiro CLI not found. Please install it first or ensure it's in your PATH."
            )

    def _read_log_path_from_mcp_json(self) -> str | None:
        """Lê o caminho do log de respostas MCP do arquivo mcp.json do Kiro.
        
        O mcp.json pode estar em:
        - ~/.kiro/settings/mcp.json (user-level)
        - .kiro/settings/mcp.json (workspace-level)
        
        Procura em mcpServers.novomodelo.env.NOVOMODELO_MCP_RESPONSE_LOG
        
        Returns:
            Caminho do arquivo de log, ou None se não encontrado.
        """
        # Possíveis locais do mcp.json
        candidates = [
            Path.home() / ".kiro" / "settings" / "mcp.json",
            Path.cwd() / ".kiro" / "settings" / "mcp.json",
        ]
        
        for mcp_json_path in candidates:
            if not mcp_json_path.exists():
                continue
            
            try:
                with open(mcp_json_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                
                # Procurar em mcpServers.novomodelo.env
                servers = config.get("mcpServers", {})
                novomodelo = servers.get("novomodelo", {})
                env = novomodelo.get("env", {})
                log_path = env.get("NOVOMODELO_MCP_RESPONSE_LOG")
                
                if log_path:
                    return log_path
            except (json.JSONDecodeError, OSError):
                continue
        
        return None
