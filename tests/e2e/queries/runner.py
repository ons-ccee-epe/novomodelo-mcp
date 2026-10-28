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
import signal
import subprocess
import tempfile
import threading
import time
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
    "QueryRunner",
]


_COLLECT_POLL_S = 0.5
DEFAULT_TIMEOUT_S = 120.0


def _kill_process_tree(process: subprocess.Popen[str]) -> None:
    """Mata o agente e os filhos dele (o servidor MCP sobe como filho do CLI).

    Matar só o pai deixaria o MCP órfão segurando os pipes, e o ``communicate``
    ficaria esperando.
    """
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            capture_output=True,
            check=False,
        )
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


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
        workspace_dir: str | Path | None = None,
    ) -> None:
        """Inicializa o QueryRunner.

        Args:
            timeout_seconds: Timeout forçado (s) para todos os casos. Se None,
                usa QUERY_TIMEOUT_S; sem ele, cada caso usa o próprio ``timeout_s``
                (cases.yaml) e DEFAULT_TIMEOUT_S só quando o caso não tem um.
            api_key: Chave de API opcional para autenticação.
                Se não fornecida, assume autenticação via kiro-cli login (Req 19.4).
            response_log_dir: Diretório para arquivos de log de respostas MCP.
                Se None, usa diretório temporário.
            workspace_dir: Raiz do path guard do MCP e cwd do agente
                (ver ``mcp_workspace``). Se None, vale a config global do usuário.

        Raises:
            RuntimeError: Se Kiro CLI não está instalado (Req 19.5), ou se
                workspace_dir é dado e o servidor novomodelo não está configurado.
        """
        if timeout_seconds is None and os.environ.get("QUERY_TIMEOUT_S"):
            timeout_seconds = float(os.environ["QUERY_TIMEOUT_S"])
        # Explícito (argumento ou QUERY_TIMEOUT_S) vale para todos os casos;
        # senão cada caso usa o seu timeout_s, e este é só o fallback.
        self._forced_timeout = timeout_seconds
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else DEFAULT_TIMEOUT_S
        self.api_key = api_key

        # Configurar diretório para logs de resposta MCP
        if response_log_dir:
            self._response_log_dir = Path(response_log_dir)
            self._response_log_dir.mkdir(parents=True, exist_ok=True)
        else:
            self._temp_dir = tempfile.mkdtemp(prefix="mcp_response_log_")
            self._owns_temp_dir = True
            self._response_log_dir = Path(self._temp_dir)

        self._process: subprocess.Popen[str] | None = None
        self._process_lock = threading.Lock()
        self._cancelled = False

        self._validate_kiro_cli()
        self.workspace_dir = prepare_workspace(workspace_dir) if workspace_dir else None

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
        log_file = self._response_log_file(test_case)

        # Record log file size before test to read only new entries after
        log_size_before = log_file.stat().st_size if log_file.exists() else 0

        # Build command (Req 2.1)
        cmd = self._build_command(test_case.query)

        # Prepare environment with MCP response logging enabled
        env = os.environ.copy()
        env["NOVOMODELO_MCP_RESPONSE_LOG"] = str(log_file)
        env.update(self._agent_env())

        # Execute with subprocess and measure time (Req 2.2, 2.3, 2.5)
        start_time = time.perf_counter()
        timeout = self.timeout_for(test_case)
        status, stdout, stderr = self._run_process(cmd, env, timeout)
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
            timeout_s=timeout,
        )

    def _response_log_file(self, test_case: QueryTestCase) -> Path:
        """Arquivo NOVOMODELO_MCP_RESPONSE_LOG do caso: env, depois mcp.json, depois um por caso."""
        fixed_log_file = os.environ.get("NOVOMODELO_MCP_RESPONSE_LOG")
        if not fixed_log_file:
            fixed_log_file = self._read_log_path_from_mcp_json()
        if fixed_log_file:
            return Path(fixed_log_file)
        # Um arquivo por caso não funciona se o servidor já estiver rodando com outro caminho.
        return (
            self._response_log_dir / f"mcp_responses_{test_case.id}_{int(time.time() * 1000)}.jsonl"
        )

    def _agent_env(self) -> dict[str, str]:
        """Variáveis extras para o processo do agente (o kiro-cli não precisa de nenhuma)."""
        return {}

    def timeout_for(self, test_case: QueryTestCase) -> float:
        """Timeout aplicado a um caso: o forçado, senão o do caso, senão o fallback."""
        if self._forced_timeout is not None:
            return self._forced_timeout
        return test_case.timeout_s or self.timeout_seconds

    def _run_process(
        self, cmd: list[str], env: dict[str, str], timeout: float
    ) -> tuple[str, str, str]:
        """Roda o agente e devolve (status, stdout, stderr).

        status: "completed", "timeout" (Req 2.6: saída parcial retida) ou
        "cancelled" (``cancel()`` chamado durante ou antes da execução).
        """
        with self._process_lock:
            if self._cancelled:
                return "cancelled", "", ""
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,  # headless: nunca ficar pendurado aguardando entrada/confirmacao
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                cwd=self.workspace_dir,
                start_new_session=os.name != "nt",
            )
            self._process = process
        try:
            return self._collect(process, timeout)
        finally:
            with self._process_lock:
                self._process = None

    def _collect(self, process: subprocess.Popen[str], timeout: float) -> tuple[str, str, str]:
        # Um neto criado durante o kill escapa do taskkill /T e segura os pipes;
        # com o pai já morto, desistir da saída em vez de esperar o neto.
        deadline = time.monotonic() + timeout
        timed_out = False
        while True:
            try:
                stdout, stderr = process.communicate(timeout=_COLLECT_POLL_S)
                break
            except subprocess.TimeoutExpired:
                if (self._cancelled or timed_out) and process.poll() is not None:
                    return ("timeout" if timed_out else "cancelled"), "", ""
                if not timed_out and time.monotonic() > deadline:
                    timed_out = True
                    _kill_process_tree(process)
        if timed_out:
            return "timeout", stdout or "", stderr or ""
        return ("cancelled" if self._cancelled else "completed"), stdout or "", stderr or ""

    def close(self) -> None:
        """Remove o diretório temporário de logs criado pelo runner, se houver."""
        if getattr(self, "_owns_temp_dir", False):
            shutil.rmtree(self._temp_dir, ignore_errors=True)

    def cancel(self) -> None:
        """Interrompe a query em andamento e recusa as próximas (definitivo)."""
        with self._process_lock:
            self._cancelled = True
            process = self._process
        if process is not None and process.poll() is None:
            _kill_process_tree(process)

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
            with open(log_file, encoding="utf-8") as f:
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
        """Constrói comando Kiro CLI (modo verbose legado).

        NOTA DE DESIGN — por que a base NAO delega a
        ``tests.e2e.launcher.providers.build_command`` (fonte única do comando):

        - O ``QueryRunner`` base é o caminho de compatibilidade: parseia o log
          *verbose* (``_parse_tool_calls`` com 6 padrões regex) e lê os envelopes
          do arquivo ``NOVOMODELO_MCP_RESPONSE_LOG`` (``_read_mcp_response_log``).
          Esse parser exige a saída verbose ``-vvv``, NÃO ``stream-json``.
        - ``build_command`` já emite ``--output-format stream-json`` para o
          kiro-cli; delegar aqui quebraria o parser verbose desta classe (o
          stream-json tem schema totalmente diferente) e o contrato de
          backward-compat da instanciação direta de ``QueryRunner``.
        - A unificação "fonte única" é atendida no caminho de produção: o
          ``ProviderQueryRunner`` (usado pela UI via ``service.py``) delega a
          ``providers.build_command`` em seu ``_build_command`` e faz o parsing
          stream-json por provedor. Esta duplicata é intencional e preservada.

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
                with open(mcp_json_path, encoding="utf-8") as f:
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
