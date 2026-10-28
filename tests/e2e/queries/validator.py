"""Validação de resultados de queries contra expectativas do TestCase.

Este módulo implementa o QueryValidator que valida se as tool calls e respostas
atendem às expectativas definidas nos casos de teste.

O fluxo de validação verifica:
1. uses_mcp - MCP foi usado quando esperado?
2. tool/tools - Tool correta foi chamada?
3. did_not_use - Tools proibidas não foram usadas?
4. status - Status do envelope está correto?
5. content - Campos do envelope estão corretos?
6. validation - Citações e keywords estão presentes?
7. error_contains - Mensagem de erro contém substring?
"""

from __future__ import annotations

import re
from typing import Any, ClassVar

from tests.e2e.queries.models import (
    QueryResult,
    QueryTestCase,
    ToolCall,
    ValidationCheck,
    ValidationResult,
    ValidationSpec,
)

__all__ = [
    "QueryValidator",
    "MCP_TOOLS",
    "NATIVE_TOOLS",
    "classify_tool",
    "get_nested",
    "values_match",
]

# =============================================================================
# Tool Classification Constants
# =============================================================================

# Tools do MCP novomodelo (37 tools)
MCP_TOOLS: frozenset[str] = frozenset(
    {
        # Pre-run / bridge validation
        "bridge_check_newave",
        "bridge_check_decomp",
        "bridge_convert_newave",
        "bridge_convert_decomp",
        "case_validate",
        "case_summary",
        "case_init",
        # Post-run / bridge comparison
        "bridge_compare_newave",
        "bridge_compare_decomp",
        "bridge_dashboard",
        # Deck operations
        "deck_list",
        "deck_read_json",
        "deck_read_parquet",
        "deck_describe_parquet",
        "deck_edit_json",
        "deck_edit_parquet",
        "deck_sql",
        # Results
        "results_status",
        "results_convergence",
        "results_query",
        "results_list_entities",
        "results_policy",
        "results_stochastic",
        # Reference / docs
        "docs_list",
        "docs_search",
        "docs_read",
        # Schema
        "schema_list",
        "schema_get",
        "schema_export",
        # Run
        "run_plan",
        "run_apply",
        "run_start",
        "run_status",
        "run_logs",
        "run_cancel",
        # Meta
        "server_info",
        "solver_version",
        "instalar_novomodelo",
    }
)

# Tools nativas do Kiro (conhecidas)
NATIVE_TOOLS: frozenset[str] = frozenset(
    {
        "read_file",
        "list_directory",
        "glob",
        "grep_search",
        "fs_write",
        "fs_append",
        "str_replace",
        "execute_pwsh",
        "web_fetch",
        "remote_web_search",
    }
)


# =============================================================================
# Matchers (reaproveitados de eval/validator.py)
# =============================================================================


class _Missing:
    """Sentinel para campo ausente."""

    pass


_MISSING = _Missing()


def get_nested(obj: Any, path: str) -> Any:
    """Acessa campo por caminho aninhado.

    Suporta:
    - Campos simples: "status"
    - Campos aninhados: "summary.total"
    - Índices de lista: "items[0].name" ou "items.0.name"

    Args:
        obj: Objeto dict/list para navegar
        path: Caminho no formato "field.subfield" ou "items[0].name"

    Returns:
        O valor encontrado ou _MISSING se não existir.
    """
    # Normaliza: "items[0]" -> "items.0"
    normalized = path.replace("[", ".").replace("]", "")
    parts = [p for p in normalized.split(".") if p]

    current = obj
    for part in parts:
        if part.isdigit():
            # Acesso por índice
            idx = int(part)
            if not isinstance(current, (list, tuple)):
                return _MISSING
            if idx < 0 or idx >= len(current):
                return _MISSING
            current = current[idx]
        else:
            # Acesso por chave
            if not isinstance(current, dict):
                return _MISSING
            if part not in current:
                return _MISSING
            current = current[part]

    return current


def values_match(expected: Any, actual: Any) -> bool:
    """Compara valores com suporte a matchers especiais.

    Matchers suportados:
    - "__any__": aceita qualquer valor não-None
    - "__nonempty__": aceita string/lista/dict não-vazia
    - "__contains__:texto": verifica se contém substring
    - "__gt__:N": maior que N (numérico)
    - "__gte__:N": maior ou igual a N
    - "__lt__:N": menor que N
    - "__lte__:N": menor ou igual a N
    - "__matches__:regex": verifica match de regex

    Args:
        expected: Valor esperado (pode ser matcher especial)
        actual: Valor obtido

    Returns:
        True se os valores são equivalentes
    """
    if expected == "__any__":
        return actual is not None

    if expected == "__nonempty__":
        if actual is None:
            return False
        if isinstance(actual, (str, list, dict)):
            return len(actual) > 0
        return True

    if isinstance(expected, str):
        if expected.startswith("__contains__:"):
            substring = expected[13:]
            return isinstance(actual, str) and substring in actual

        if expected.startswith("__gt__:"):
            threshold = float(expected[7:])
            return isinstance(actual, (int, float)) and actual > threshold

        if expected.startswith("__gte__:"):
            threshold = float(expected[8:])
            return isinstance(actual, (int, float)) and actual >= threshold

        if expected.startswith("__lt__:"):
            threshold = float(expected[7:])
            return isinstance(actual, (int, float)) and actual < threshold

        if expected.startswith("__lte__:"):
            threshold = float(expected[8:])
            return isinstance(actual, (int, float)) and actual <= threshold

        if expected.startswith("__matches__:"):
            pattern = expected[12:]
            return isinstance(actual, str) and re.search(pattern, actual) is not None

    # Comparação direta
    return expected == actual


# =============================================================================
# Tool Classification
# =============================================================================


def classify_tool(tool_name: str) -> str:
    """Classifica uma tool como "mcp", "native", ou "unknown".

    Args:
        tool_name: Nome da tool

    Returns:
        "mcp" se é tool do novomodelo
        "native" se é tool conhecida do Kiro
        "unknown" se não está em nenhuma lista (tratada como native por segurança)
    """
    if tool_name in MCP_TOOLS:
        return "mcp"
    if tool_name in NATIVE_TOOLS:
        return "native"
    return "unknown"  # Tratada como native por segurança (Req 3.4)


# =============================================================================
# QueryValidator
# =============================================================================


class QueryValidator:
    """Valida resultados de queries contra expectativas.

    O QueryValidator implementa o fluxo de validação completo:
    1. uses_mcp - Verifica se MCP foi usado quando esperado
    2. tool/tools - Verifica se a tool correta foi chamada
    3. did_not_use - Verifica que tools proibidas não foram usadas
    4. status - Verifica status do envelope
    5. content - Verifica campos do envelope
    6. validation - Verifica citações e keywords
    7. error_contains - Verifica substring na mensagem de erro

    Example:
        >>> validator = QueryValidator()
        >>> result = validator.validate(test_case, query_result)
        >>> if result.valid:
        ...     print("All checks passed!")
        ... else:
        ...     print(f"Failed: {result.failure_reason}")
    """

    MCP_TOOLS: ClassVar[frozenset[str]] = MCP_TOOLS
    NATIVE_TOOLS: ClassVar[frozenset[str]] = NATIVE_TOOLS

    def validate(
        self,
        test_case: QueryTestCase,
        result: QueryResult,
    ) -> ValidationResult:
        """Valida resultado de query contra expectativas.

        Realiza validações na ordem:
        1. uses_mcp - MCP foi usado?
        2. tool/tools - Tool correta foi chamada?
        3. did_not_use - Tools proibidas não foram usadas?
        4. status - Status do envelope está correto?
        5. content - Campos do envelope estão corretos?
        6. validation - Citações e keywords estão presentes?
        7. error_contains - Mensagem de erro contém substring?

        Args:
            test_case: Caso de teste com expectativas
            result: Resultado da execução

        Returns:
            ValidationResult com status e detalhes
        """
        # Handle timeout/error status from runner
        if result.status == "timeout":
            return ValidationResult(
                valid=False,
                status="timeout",
                checks=[],
                failure_reason="Query execution timed out",
                details={"latency_ms": result.latency_ms},
            )

        if result.status == "error":
            return ValidationResult(
                valid=False,
                status="fail",
                checks=[],
                failure_reason=f"Query execution error: {(result.stderr or 'unknown')[:200]}",
                details={"stderr": result.stderr},
            )

        expected = test_case.expected
        checks: list[ValidationCheck] = []
        all_passed = True
        mcp_check_passed = False
        tool_check_passed = False

        # 1. Check uses_mcp (Req 3.1, 3.2, 3.3, 3.4)
        check_mcp = self._check_uses_mcp(result.tool_calls, expected.uses_mcp)
        checks.append(check_mcp)
        mcp_check_passed = check_mcp.passed
        if not check_mcp.passed:
            all_passed = False

        # 2. Check tool/tools (Req 4.1, 4.2, 4.3, 4.4, 4.5)
        if expected.tool is not None or expected.tools is not None:
            check_tool = self._check_correct_tool(
                result.tool_calls,
                expected.tool,
                expected.tools,
            )
            checks.append(check_tool)
            tool_check_passed = check_tool.passed
            if not check_tool.passed:
                all_passed = False

        # 3. Check did_not_use (Req 3.5)
        if expected.did_not_use is not None:
            check_forbidden = self._check_did_not_use(
                result.tool_calls,
                expected.did_not_use,
            )
            checks.append(check_forbidden)
            if not check_forbidden.passed:
                all_passed = False

        # Extract the MCP result envelope for status/content checks
        # The envelope structure is: {tool, arguments, result, duration_ms}
        # We want to validate against the "result" field which is the actual MCP response
        mcp_result = None
        if result.envelope and "result" in result.envelope:
            mcp_result = result.envelope.get("result")

        # 4. Check status (Req 5.1)
        if expected.status is not None:
            check_status = self._check_status(mcp_result, expected.status)
            checks.append(check_status)
            if not check_status.passed:
                all_passed = False

        # 5. Check content (Req 5.2-5.8)
        if expected.content is not None:
            check_content = self._check_content(mcp_result, expected.content)
            checks.append(check_content)
            if not check_content.passed:
                all_passed = False

        # 6. Check validation (Req 6.1-6.4)
        if expected.validation is not None:
            check_validation = self._check_validation(
                result.agent_response,
                expected.validation,
            )
            checks.append(check_validation)
            if not check_validation.passed:
                all_passed = False

        # 7. Check error_contains (Req 7.3)
        if expected.error_contains is not None:
            check_error = self._check_error_contains(
                mcp_result,
                expected.error_contains,
            )
            checks.append(check_error)
            if not check_error.passed:
                all_passed = False

        # Determine failure reason
        failure_reason = None
        if not all_passed:
            failed_checks = [c for c in checks if not c.passed]
            if failed_checks:
                failure_reason = failed_checks[0].message

        # Determine status: pass, partial, or fail
        # partial = MCP was used correctly but other validations failed
        if all_passed:
            status = "pass"
        elif mcp_check_passed and tool_check_passed:
            status = "partial"  # MCP ok, but content/validation failed
        else:
            status = "fail"

        return ValidationResult(
            valid=all_passed,
            status=status,
            checks=checks,
            failure_reason=failure_reason,
            details={
                "total_tool_calls": len(result.tool_calls),
                "mcp_calls": [
                    tc.name for tc in result.tool_calls if classify_tool(tc.name) == "mcp"
                ],
                "has_envelope": result.envelope is not None,
                "envelope_tool": result.envelope.get("tool") if result.envelope else None,
            },
        )

    def _check_uses_mcp(
        self,
        tool_calls: list[ToolCall],
        expected: bool,
    ) -> ValidationCheck:
        """Verifica se MCP foi usado quando deveria.

        Implements:
        - Req 3.1: WHEN expected.uses_mcp é true, verificar que pelo menos uma MCP_Tool foi chamada
        - Req 3.2: WHEN expected.uses_mcp é true, falhar se apenas Native_Tools foram usadas
        - Req 3.3: Identificar MCP_Tools pela lista conhecida de 37 tools
        - Req 3.4: Identificar Native_Tools e classificar desconhecidas como Native por padrão

        Args:
            tool_calls: Lista de tool calls registradas
            expected: Se MCP deveria ter sido usado (True/False)

        Returns:
            ValidationCheck com resultado da verificação
        """
        mcp_calls = [tc for tc in tool_calls if classify_tool(tc.name) == "mcp"]

        if expected:
            # Esperamos que MCP tenha sido usado
            passed = len(mcp_calls) > 0
            if mcp_calls:
                actual: Any = [tc.name for tc in mcp_calls]
                message = f"MCP usado: {', '.join(tc.name for tc in mcp_calls)}"
            else:
                # Nenhuma MCP tool foi chamada - reportar o que foi usado
                if tool_calls:
                    actual = [tc.name for tc in tool_calls]
                    message = f"MCP NÃO foi usado, usou: {', '.join(tc.name for tc in tool_calls)}"
                else:
                    actual = "nenhuma tool chamada"
                    message = "MCP NÃO foi usado, nenhuma tool foi chamada"
        else:
            # Esperamos que MCP NÃO tenha sido usado
            passed = len(mcp_calls) == 0
            if mcp_calls:
                actual = [tc.name for tc in mcp_calls]
                message = f"MCP foi usado inesperadamente: {', '.join(tc.name for tc in mcp_calls)}"
            else:
                actual = "nenhuma MCP tool"
                message = "MCP não foi usado (conforme esperado)"

        return ValidationCheck(
            name="uses_mcp",
            passed=passed,
            expected=expected,
            actual=actual,
            message=message,
        )

    def _check_correct_tool(
        self,
        tool_calls: list[ToolCall],
        expected_tool: str | None,
        expected_tools: list[str] | None,
    ) -> ValidationCheck:
        """Verifica se a tool correta foi chamada.

        Implements:
        - Req 4.1: WHEN expected.tool é definido, verificar que essa tool foi chamada
        - Req 4.2: WHEN expected.tools é lista, aceitar se qualquer uma foi chamada
        - Req 4.3: Reportar qual tool foi chamada em vez da esperada
        - Req 4.4: Suportar validação por order-independent set membership
        - Req 4.5: Falhar com mensagem explicativa se nenhuma tool foi chamada

        Args:
            tool_calls: Lista de tool calls registradas
            expected_tool: Tool específica esperada (ou None)
            expected_tools: Lista de tools aceitáveis (ou None)

        Returns:
            ValidationCheck com resultado da verificação
        """
        called_names = {tc.name for tc in tool_calls}

        # Determine expected set
        if expected_tool is not None:
            expected_set = {expected_tool}
            expected_display = expected_tool
        elif expected_tools is not None:
            expected_set = set(expected_tools)
            expected_display = f"qualquer de: {', '.join(sorted(expected_tools))}"
        else:
            # Não deveria acontecer, mas tratamos defensivamente
            return ValidationCheck(
                name="correct_tool",
                passed=True,
                expected=None,
                actual=list(called_names),
                message="Nenhuma tool esperada definida",
            )

        # Check if any expected tool was called (Req 4.4: order-independent set membership)
        matches = called_names & expected_set
        passed = len(matches) > 0

        if passed:
            actual: Any = list(matches)
            message = f"Tool correta chamada: {', '.join(sorted(matches))}"
        else:
            # Req 4.3: Reportar qual tool foi chamada em vez da esperada
            # Req 4.5: Falhar com mensagem explicativa se nenhuma tool foi chamada
            if called_names:
                actual = list(called_names)
                usadas = ", ".join(sorted(called_names))
                message = f"Tool esperada '{expected_display}' não foi chamada, usou: {usadas}"
            else:
                actual = "nenhuma"
                message = f"Nenhuma tool foi chamada, esperava: {expected_display}"

        return ValidationCheck(
            name="correct_tool",
            passed=passed,
            expected=expected_display,
            actual=actual,
            message=message,
        )

    def _check_did_not_use(
        self,
        tool_calls: list[ToolCall],
        forbidden: list[str],
    ) -> ValidationCheck:
        """Verifica que tools proibidas não foram usadas.

        Implements:
        - Req 3.5: WHEN expected.did_not_use é definido, falhar se qualquer tool listada foi chamada

        Args:
            tool_calls: Lista de tool calls registradas
            forbidden: Lista de tools que NÃO devem ter sido usadas

        Returns:
            ValidationCheck com resultado da verificação
        """
        called_names = {tc.name for tc in tool_calls}
        violations = called_names & set(forbidden)

        passed = len(violations) == 0

        if passed:
            actual: Any = "OK"
            message = f"Nenhuma tool proibida usada (proibidas: {', '.join(sorted(forbidden))})"
        else:
            actual = list(violations)
            message = f"Usou tools proibidas: {', '.join(sorted(violations))}"

        return ValidationCheck(
            name="did_not_use",
            passed=passed,
            expected=f"não usar: {', '.join(sorted(forbidden))}",
            actual=actual,
            message=message,
        )

    def _check_status(
        self,
        mcp_result: dict[str, Any] | None,
        expected_status: str,
    ) -> ValidationCheck:
        """Verifica status do resultado MCP.

        Implements:
        - Req 5.1: WHEN expected.status é definido, verificar o status do Envelope

        Args:
            mcp_result: Resultado da tool MCP (pode ser None)
            expected_status: Status esperado ("ok" ou "error")

        Returns:
            ValidationCheck com resultado da verificação
        """
        if mcp_result is None:
            return ValidationCheck(
                name="status",
                passed=False,
                expected=expected_status,
                actual="nenhum envelope MCP",
                message=(
                    "Nenhum envelope MCP disponível para verificar status "
                    "(ative NOVOMODELO_MCP_RESPONSE_LOG)"
                ),
            )

        actual_status = mcp_result.get("status")
        passed = actual_status == expected_status

        if passed:
            message = f"Status correto: {actual_status}"
        else:
            message = f"Status incorreto: esperado '{expected_status}', obtido '{actual_status}'"

        return ValidationCheck(
            name="status",
            passed=passed,
            expected=expected_status,
            actual=actual_status,
            message=message,
        )

    def _check_content(
        self,
        mcp_result: dict[str, Any] | None,
        expected_content: dict[str, Any],
    ) -> ValidationCheck:
        """Verifica campos do resultado MCP usando matchers.

        Implements:
        - Req 5.2: Validar campos aninhados usando notação de caminho
        - Req 5.3-5.7: Suportar matchers especiais
        - Req 5.8: Falhar com caminho do campo faltante

        Args:
            mcp_result: Resultado da tool MCP (pode ser None)
            expected_content: Dict de path -> expected value/matcher

        Returns:
            ValidationCheck com resultado da verificação
        """
        if mcp_result is None:
            return ValidationCheck(
                name="content",
                passed=False,
                expected=expected_content,
                actual="nenhum envelope MCP",
                message=(
                    "Nenhum envelope MCP disponível para verificar conteúdo "
                    "(ative NOVOMODELO_MCP_RESPONSE_LOG)"
                ),
            )

        # Check each expected field
        failures: list[str] = []
        for path, expected_value in expected_content.items():
            actual_value = get_nested(mcp_result, path)

            if actual_value is _MISSING:
                failures.append(f"campo ausente: '{path}'")
                continue

            if not values_match(expected_value, actual_value):
                failures.append(
                    f"campo '{path}': esperado {expected_value!r}, obtido {actual_value!r}"
                )

        passed = len(failures) == 0

        if passed:
            message = "Todos os campos do envelope estão corretos"
            actual: Any = "OK"
        else:
            message = f"Falhas no conteúdo: {'; '.join(failures)}"
            actual = failures

        return ValidationCheck(
            name="content",
            passed=passed,
            expected=expected_content,
            actual=actual,
            message=message,
        )

    def _check_validation(
        self,
        agent_response: str,
        validation_spec: ValidationSpec,
    ) -> ValidationCheck:
        """Verifica citações e keywords na resposta.

        Implements:
        - Req 6.1: WHEN cites_section_pattern é definido, verificar citação com regex
        - Req 6.2: WHEN response_contains é definido, verificar keywords
        - Req 6.3: Extrair citações no formato página#seção
        - Req 6.4: Aceitar citações em qualquer formato página#seção

        Args:
            agent_response: Resposta final do agente
            validation_spec: Especificação de validações

        Returns:
            ValidationCheck com resultado da verificação
        """
        failures: list[str] = []

        # Check citation pattern (Req 6.1, 6.3, 6.4)
        if validation_spec.cites_section_pattern is not None:
            pattern = validation_spec.cites_section_pattern
            if not re.search(pattern, agent_response):
                failures.append(f"citação não encontrada (padrão: {pattern})")

        # Check keywords (Req 6.2)
        if validation_spec.response_contains is not None:
            for keyword in validation_spec.response_contains:
                if keyword.lower() not in agent_response.lower():
                    failures.append(f"keyword ausente: '{keyword}'")

        passed = len(failures) == 0

        if passed:
            message = "Todas as validações de resposta passaram"
            actual: Any = "OK"
        else:
            message = f"Falhas na validação: {'; '.join(failures)}"
            actual = failures

        expected_desc: list[str] = []
        if validation_spec.cites_section_pattern:
            expected_desc.append(f"cites_pattern: {validation_spec.cites_section_pattern}")
        if validation_spec.response_contains:
            expected_desc.append(f"contains: {validation_spec.response_contains}")

        return ValidationCheck(
            name="validation",
            passed=passed,
            expected="; ".join(expected_desc) if expected_desc else "validation spec",
            actual=actual,
            message=message,
        )

    def _check_error_contains(
        self,
        mcp_result: dict[str, Any] | None,
        expected_substring: str,
    ) -> ValidationCheck:
        """Verifica substring na mensagem de erro.

        Implements:
        - Req 7.3: WHEN expected.error_contains é definido, verificar substring na mensagem

        Args:
            mcp_result: Resultado da tool MCP (pode ser None)
            expected_substring: Substring esperada na mensagem de erro

        Returns:
            ValidationCheck com resultado da verificação
        """
        if mcp_result is None:
            return ValidationCheck(
                name="error_contains",
                passed=False,
                expected=f"erro contendo: '{expected_substring}'",
                actual="nenhum envelope MCP",
                message=(
                    "Nenhum envelope MCP disponível para verificar erro "
                    "(ative NOVOMODELO_MCP_RESPONSE_LOG)"
                ),
            )

        # Look for error message in common locations
        error_message = (
            mcp_result.get("error")
            or mcp_result.get("message")
            or mcp_result.get("error_message")
            or str(mcp_result.get("content", ""))
        )

        passed = expected_substring in error_message

        if passed:
            message = f"Erro contém substring esperada: '{expected_substring}'"
            actual: Any = error_message[:100] + "..." if len(error_message) > 100 else error_message
        else:
            message = f"Erro não contém substring '{expected_substring}'"
            actual = error_message[:200] if error_message else "nenhuma mensagem de erro"

        return ValidationCheck(
            name="error_contains",
            passed=passed,
            expected=f"erro contendo: '{expected_substring}'",
            actual=actual,
            message=message,
        )
