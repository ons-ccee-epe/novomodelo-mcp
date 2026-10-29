"""Testes unitários para o QueryValidator.

Este módulo testa:
- MCP_TOOLS e NATIVE_TOOLS constants
- classify_tool() function
- get_nested() e values_match() matchers
- QueryValidator._check_uses_mcp()
- QueryValidator._check_correct_tool()
- QueryValidator._check_did_not_use()
"""

from __future__ import annotations

import pytest

from novomodelo_mcp_e2e.queries.models import (
    ExpectedResult,
    QueryResult,
    QueryTestCase,
    ToolCall,
)
from novomodelo_mcp_e2e.queries.validator import (
    MCP_TOOLS,
    NATIVE_TOOLS,
    QueryValidator,
    classify_tool,
    get_nested,
    values_match,
)


class TestConstants:
    """Testes para MCP_TOOLS e NATIVE_TOOLS."""

    def test_mcp_tools_count(self):
        """Verifica que temos 37 MCP tools."""
        # Note: We have 38 because 'install_novomodelo' was added
        assert len(MCP_TOOLS) >= 37

    def test_mcp_tools_contains_expected(self):
        """Verifica tools MCP conhecidas."""
        expected_tools = [
            "bridge_check_newave",
            "bridge_check_decomp",
            "deck_list",
            "deck_read_parquet",
            "docs_search",
            "docs_read",
            "results_query",
            "schema_list",
            "run_start",
            "server_info",
        ]
        for tool in expected_tools:
            assert tool in MCP_TOOLS, f"{tool} should be in MCP_TOOLS"

    def test_native_tools_contains_expected(self):
        """Verifica tools nativas conhecidas."""
        expected_native = [
            "read_file",
            "list_directory",
            "glob",
            "grep_search",
            "fs_write",
        ]
        for tool in expected_native:
            assert tool in NATIVE_TOOLS, f"{tool} should be in NATIVE_TOOLS"

    def test_no_overlap(self):
        """Verifica que MCP e Native não têm overlap."""
        overlap = MCP_TOOLS & NATIVE_TOOLS
        assert len(overlap) == 0, f"Overlap found: {overlap}"


class TestClassifyTool:
    """Testes para classify_tool()."""

    def test_classify_mcp_tool(self):
        """MCP tools retornam 'mcp'."""
        assert classify_tool("deck_list") == "mcp"
        assert classify_tool("bridge_check_newave") == "mcp"
        assert classify_tool("docs_search") == "mcp"

    def test_classify_native_tool(self):
        """Native tools retornam 'native'."""
        assert classify_tool("read_file") == "native"
        assert classify_tool("list_directory") == "native"
        assert classify_tool("fs_write") == "native"

    def test_classify_unknown_tool(self):
        """Unknown tools retornam 'unknown'."""
        assert classify_tool("some_unknown_tool") == "unknown"
        assert classify_tool("") == "unknown"


class TestGetNested:
    """Testes para get_nested()."""

    def test_simple_field(self):
        """Acessa campo simples."""
        obj = {"status": "ok"}
        assert get_nested(obj, "status") == "ok"

    def test_nested_field(self):
        """Acessa campo aninhado."""
        obj = {"summary": {"total": 42}}
        assert get_nested(obj, "summary.total") == 42

    def test_array_index(self):
        """Acessa índice de array."""
        obj = {"items": [{"name": "first"}, {"name": "second"}]}
        assert get_nested(obj, "items[0].name") == "first"
        assert get_nested(obj, "items.1.name") == "second"

    def test_missing_field(self):
        """Campo ausente retorna _MISSING."""
        obj = {"status": "ok"}
        result = get_nested(obj, "missing")
        assert result.__class__.__name__ == "_Missing"

    def test_missing_nested(self):
        """Campo aninhado ausente retorna _MISSING."""
        obj = {"summary": {}}
        result = get_nested(obj, "summary.missing")
        assert result.__class__.__name__ == "_Missing"


class TestValuesMatch:
    """Testes para values_match() matchers."""

    def test_exact_match(self):
        """Comparação exata funciona."""
        assert values_match("ok", "ok")
        assert not values_match("ok", "error")
        assert values_match(42, 42)

    def test_any_matcher(self):
        """__any__ aceita qualquer valor não-None."""
        assert values_match("__any__", "anything")
        assert values_match("__any__", 42)
        assert values_match("__any__", [1, 2, 3])
        assert not values_match("__any__", None)

    def test_nonempty_matcher(self):
        """__nonempty__ verifica não-vazio."""
        assert values_match("__nonempty__", "text")
        assert values_match("__nonempty__", [1])
        assert values_match("__nonempty__", {"key": "value"})
        assert not values_match("__nonempty__", "")
        assert not values_match("__nonempty__", [])
        assert not values_match("__nonempty__", {})
        assert not values_match("__nonempty__", None)

    def test_contains_matcher(self):
        """__contains__ verifica substring."""
        assert values_match("__contains__:error", "An error occurred")
        assert values_match("__contains__:success", "Operation was a success")
        assert not values_match("__contains__:error", "All good")

    def test_numeric_matchers(self):
        """Matchers numéricos funcionam."""
        assert values_match("__gt__:10", 15)
        assert not values_match("__gt__:10", 10)
        assert not values_match("__gt__:10", 5)

        assert values_match("__gte__:10", 15)
        assert values_match("__gte__:10", 10)
        assert not values_match("__gte__:10", 5)

        assert values_match("__lt__:10", 5)
        assert not values_match("__lt__:10", 10)
        assert not values_match("__lt__:10", 15)

        assert values_match("__lte__:10", 5)
        assert values_match("__lte__:10", 10)
        assert not values_match("__lte__:10", 15)

    def test_matches_matcher(self):
        """__matches__ verifica regex."""
        assert values_match(r"__matches__:page\d+#section", "page123#section")
        assert not values_match(r"__matches__:page\d+#section", "no match here")


class TestCheckUsesMcp:
    """Testes para _check_uses_mcp()."""

    def test_mcp_expected_and_used(self):
        """MCP esperado e usado -> passa."""
        validator = QueryValidator()
        tool_calls = [ToolCall(name="deck_list", args={})]
        check = validator._check_uses_mcp(tool_calls, expected=True)
        assert check.passed
        assert check.name == "uses_mcp"
        assert "MCP usado" in check.message

    def test_mcp_expected_but_native_used(self):
        """MCP esperado mas Native usado -> falha."""
        validator = QueryValidator()
        tool_calls = [ToolCall(name="read_file", args={})]
        check = validator._check_uses_mcp(tool_calls, expected=True)
        assert not check.passed
        assert "MCP NÃO foi usado" in check.message
        assert "read_file" in check.message

    def test_mcp_expected_but_no_tools(self):
        """MCP esperado mas nenhuma tool chamada -> falha."""
        validator = QueryValidator()
        tool_calls = []
        check = validator._check_uses_mcp(tool_calls, expected=True)
        assert not check.passed
        assert "nenhuma tool foi chamada" in check.message

    def test_mcp_not_expected_and_not_used(self):
        """MCP não esperado e não usado -> passa."""
        validator = QueryValidator()
        tool_calls = [ToolCall(name="read_file", args={})]
        check = validator._check_uses_mcp(tool_calls, expected=False)
        assert check.passed


class TestCheckCorrectTool:
    """Testes para _check_correct_tool()."""

    def test_single_tool_correct(self):
        """Tool única esperada e chamada -> passa."""
        validator = QueryValidator()
        tool_calls = [ToolCall(name="deck_list", args={})]
        check = validator._check_correct_tool(
            tool_calls,
            expected_tool="deck_list",
            expected_tools=None,
        )
        assert check.passed
        assert "Tool correta chamada" in check.message

    def test_single_tool_wrong(self):
        """Tool única esperada mas outra chamada -> falha."""
        validator = QueryValidator()
        tool_calls = [ToolCall(name="deck_read_parquet", args={})]
        check = validator._check_correct_tool(
            tool_calls,
            expected_tool="deck_list",
            expected_tools=None,
        )
        assert not check.passed
        assert "deck_list" in check.message
        assert "deck_read_parquet" in check.message

    def test_tools_list_any_correct(self):
        """Lista de tools e uma foi chamada -> passa."""
        validator = QueryValidator()
        tool_calls = [ToolCall(name="docs_read", args={})]
        check = validator._check_correct_tool(
            tool_calls,
            expected_tool=None,
            expected_tools=["docs_search", "docs_read"],
        )
        assert check.passed

    def test_tools_list_none_called(self):
        """Lista de tools mas nenhuma chamada -> falha."""
        validator = QueryValidator()
        tool_calls = [ToolCall(name="read_file", args={})]
        check = validator._check_correct_tool(
            tool_calls,
            expected_tool=None,
            expected_tools=["docs_search", "docs_read"],
        )
        assert not check.passed
        assert "não foi chamada" in check.message

    def test_no_tools_called(self):
        """Nenhuma tool chamada -> falha com mensagem explicativa."""
        validator = QueryValidator()
        tool_calls = []
        check = validator._check_correct_tool(
            tool_calls,
            expected_tool="deck_list",
            expected_tools=None,
        )
        assert not check.passed
        assert "Nenhuma tool foi chamada" in check.message

    def test_order_independent_matching(self):
        """Validação order-independent."""
        validator = QueryValidator()
        tool_calls = [
            ToolCall(name="read_file", args={}),
            ToolCall(name="deck_list", args={}),
            ToolCall(name="docs_search", args={}),
        ]
        check = validator._check_correct_tool(
            tool_calls,
            expected_tool="deck_list",
            expected_tools=None,
        )
        assert check.passed  # deck_list was called, even if not first


class TestCheckDidNotUse:
    """Testes para _check_did_not_use()."""

    def test_no_forbidden_used(self):
        """Nenhuma tool proibida usada -> passa."""
        validator = QueryValidator()
        tool_calls = [ToolCall(name="deck_list", args={})]
        check = validator._check_did_not_use(
            tool_calls,
            forbidden=["read_file", "list_directory"],
        )
        assert check.passed
        assert "Nenhuma tool proibida" in check.message

    def test_forbidden_used(self):
        """Tool proibida usada -> falha."""
        validator = QueryValidator()
        tool_calls = [
            ToolCall(name="deck_list", args={}),
            ToolCall(name="read_file", args={}),
        ]
        check = validator._check_did_not_use(
            tool_calls,
            forbidden=["read_file", "list_directory"],
        )
        assert not check.passed
        assert "read_file" in check.message
        assert "Usou tools proibidas" in check.message


class TestValidateIntegration:
    """Testes de integração para validate()."""

    def _make_test_case(
        self,
        uses_mcp: bool = True,
        tool: str | None = None,
        tools: list[str] | None = None,
        did_not_use: list[str] | None = None,
    ) -> QueryTestCase:
        """Helper para criar test cases."""
        return QueryTestCase(
            id="test-case",
            query="Test query",
            expected=ExpectedResult(
                uses_mcp=uses_mcp,
                tool=tool,
                tools=tools,
                did_not_use=did_not_use,
            ),
        )

    def _make_result(
        self,
        tool_calls: list[ToolCall],
        status: str = "completed",
    ) -> QueryResult:
        """Helper para criar query results."""
        test_case = self._make_test_case()
        return QueryResult(
            test_case=test_case,
            tool_calls=tool_calls,
            agent_response="Test response",
            latency_ms=100.0,
            status=status,
            stdout="",
            stderr="",
        )

    def test_validate_pass(self):
        """Validação passa quando tudo está correto."""
        test_case = self._make_test_case(
            uses_mcp=True,
            tool="deck_list",
        )
        result = self._make_result([ToolCall(name="deck_list", args={})])

        validator = QueryValidator()
        validation = validator.validate(test_case, result)

        assert validation.valid
        assert validation.status == "pass"
        assert validation.failure_reason is None

    def test_validate_fail_no_mcp(self):
        """Validação falha quando MCP não foi usado."""
        test_case = self._make_test_case(
            uses_mcp=True,
            tool="deck_list",
        )
        result = self._make_result([ToolCall(name="read_file", args={})])

        validator = QueryValidator()
        validation = validator.validate(test_case, result)

        assert not validation.valid
        assert validation.status == "fail"
        assert validation.failure_reason is not None
        assert "MCP NÃO foi usado" in validation.failure_reason

    def test_validate_fail_wrong_tool(self):
        """Validação falha quando tool errada foi usada."""
        test_case = self._make_test_case(
            uses_mcp=True,
            tool="deck_list",
        )
        result = self._make_result([ToolCall(name="deck_read_parquet", args={})])

        validator = QueryValidator()
        validation = validator.validate(test_case, result)

        assert not validation.valid
        # First failure is uses_mcp (passes because deck_read_parquet is MCP)
        # Second failure should be correct_tool
        assert validation.status == "fail"

    def test_validate_timeout(self):
        """Validação retorna timeout quando status é timeout."""
        test_case = self._make_test_case(uses_mcp=True)
        result = self._make_result([], status="timeout")

        validator = QueryValidator()
        validation = validator.validate(test_case, result)

        assert not validation.valid
        assert validation.status == "timeout"
        assert validation.failure_reason is not None
        assert "timed out" in validation.failure_reason.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
