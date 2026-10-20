"""Testes unitários para o QueryRunner.

Este módulo testa:
- _parse_tool_calls() parsing de logs do Kiro CLI
- _parse_args() conversão de argumentos
- _extract_agent_response() extração de resposta
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from tests.e2e.queries.models import ToolCall
from tests.e2e.queries.runner import QueryRunner


class TestParseToolCalls:
    """Testes para _parse_tool_calls()."""

    @pytest.fixture
    def runner(self):
        """Cria runner mockando validação do Kiro CLI."""
        with patch.object(QueryRunner, "_validate_kiro_cli"):
            return QueryRunner()

    def test_parse_assistant_tool_use_format(self, runner: QueryRunner):
        """Parseia formato AssistantToolUse completo."""
        log = '''
        Validating tool uses tool_uses=[AssistantToolUse { tool_use_id: "toolu_bdrk_123abc", name: "deck_list", input: {"case_dir": "/path/to/case"} }]
        '''
        tool_calls = runner._parse_tool_calls(log)

        assert len(tool_calls) == 1
        assert tool_calls[0].name == "deck_list"
        assert tool_calls[0].tool_id == "toolu_bdrk_123abc"
        assert tool_calls[0].args == {"case_dir": "/path/to/case"}

    def test_parse_multiple_tool_calls(self, runner: QueryRunner):
        """Parseia múltiplas tool calls no mesmo log."""
        log = '''
        Validating tool uses tool_uses=[AssistantToolUse { tool_use_id: "toolu_1", name: "deck_list", input: {} }]
        Some other log line
        Validating tool uses tool_uses=[AssistantToolUse { tool_use_id: "toolu_2", name: "docs_search", input: {"query": "test"} }]
        '''
        tool_calls = runner._parse_tool_calls(log)

        assert len(tool_calls) == 2
        names = {tc.name for tc in tool_calls}
        assert names == {"deck_list", "docs_search"}

    def test_parse_tool_call_simple_format(self, runner: QueryRunner):
        """Parseia formato Tool call: simples."""
        log = '''
        Tool call: bridge_check_newave({"path": "/case"})
        '''
        tool_calls = runner._parse_tool_calls(log)

        assert len(tool_calls) == 1
        assert tool_calls[0].name == "bridge_check_newave"
        assert tool_calls[0].args == {"path": "/case"}

    def test_parse_invoking_tool_format(self, runner: QueryRunner):
        """Parseia formato Invoking tool."""
        log = '''
        Invoking tool deck_read_parquet
        '''
        tool_calls = runner._parse_tool_calls(log)

        assert len(tool_calls) == 1
        assert tool_calls[0].name == "deck_read_parquet"
        assert tool_calls[0].args == {}

    def test_parse_calling_mcp_tool_format(self, runner: QueryRunner):
        """Parseia formato Calling MCP tool."""
        log = '''
        Calling MCP tool: schema_list
        '''
        tool_calls = runner._parse_tool_calls(log)

        assert len(tool_calls) == 1
        assert tool_calls[0].name == "schema_list"

    def test_parse_empty_log(self, runner: QueryRunner):
        """Log vazio retorna lista vazia."""
        tool_calls = runner._parse_tool_calls("")
        assert tool_calls == []

    def test_parse_no_tool_calls(self, runner: QueryRunner):
        """Log sem tool calls retorna lista vazia."""
        log = "Some random log output without any tool calls"
        tool_calls = runner._parse_tool_calls(log)
        assert tool_calls == []

    def test_avoid_duplicate_tool_ids(self, runner: QueryRunner):
        """Evita duplicatas com mesmo tool_use_id."""
        log = '''
        Validating tool uses tool_uses=[AssistantToolUse { tool_use_id: "toolu_same", name: "deck_list", input: {} }]
        Validating tool uses tool_uses=[AssistantToolUse { tool_use_id: "toolu_same", name: "deck_list", input: {} }]
        '''
        tool_calls = runner._parse_tool_calls(log)

        assert len(tool_calls) == 1

    def test_parse_json_format_fallback(self, runner: QueryRunner):
        """Parseia formato JSON como fallback."""
        log = '''
        {"tool_name": "results_query", "some": "data"}
        '''
        tool_calls = runner._parse_tool_calls(log)

        assert len(tool_calls) == 1
        assert tool_calls[0].name == "results_query"


class TestParseArgs:
    """Testes para _parse_args()."""

    @pytest.fixture
    def runner(self):
        """Cria runner mockando validação do Kiro CLI."""
        with patch.object(QueryRunner, "_validate_kiro_cli"):
            return QueryRunner()

    def test_parse_valid_json(self, runner: QueryRunner):
        """Parseia JSON válido."""
        args = runner._parse_args('{"key": "value", "num": 42}')
        assert args == {"key": "value", "num": 42}

    def test_parse_empty_json(self, runner: QueryRunner):
        """Parseia JSON vazio."""
        args = runner._parse_args("{}")
        assert args == {}

    def test_parse_empty_string(self, runner: QueryRunner):
        """String vazia retorna dict vazio."""
        args = runner._parse_args("")
        assert args == {}

    def test_parse_single_quotes(self, runner: QueryRunner):
        """Trata single quotes como JSON."""
        args = runner._parse_args("{'key': 'value'}")
        assert args == {"key": "value"}

    def test_parse_invalid_returns_empty(self, runner: QueryRunner):
        """String inválida retorna dict vazio."""
        args = runner._parse_args("not valid json at all")
        assert args == {}

    def test_parse_boolean_values(self, runner: QueryRunner):
        """Parseia valores booleanos."""
        args = runner._parse_args('{"enabled": true, "disabled": false}')
        assert args == {"enabled": True, "disabled": False}


class TestExtractAgentResponse:
    """Testes para _extract_agent_response()."""

    @pytest.fixture
    def runner(self):
        """Cria runner mockando validação do Kiro CLI."""
        with patch.object(QueryRunner, "_validate_kiro_cli"):
            return QueryRunner()

    def test_extract_simple_response(self, runner: QueryRunner):
        """Extrai resposta simples."""
        stdout = "Here is the answer to your question."
        response = runner._extract_agent_response(stdout)
        assert response == "Here is the answer to your question."

    def test_extract_empty_response(self, runner: QueryRunner):
        """String vazia retorna vazia."""
        response = runner._extract_agent_response("")
        assert response == ""

    def test_remove_ansi_codes(self, runner: QueryRunner):
        """Remove ANSI escape codes."""
        stdout = "\x1b[32mGreen text\x1b[0m and normal"
        response = runner._extract_agent_response(stdout)
        assert response == "Green text and normal"

    def test_remove_spinner_chars(self, runner: QueryRunner):
        """Remove caracteres de spinner."""
        stdout = "⠋Loading...⠙ Done!"
        response = runner._extract_agent_response(stdout)
        assert "⠋" not in response
        assert "⠙" not in response
        assert "Done!" in response

    def test_remove_kiro_prefix(self, runner: QueryRunner):
        """Remove prefixo [kiro]."""
        stdout = "[kiro] Here is the response"
        response = runner._extract_agent_response(stdout)
        assert "[kiro]" not in response
        assert "response" in response

    def test_extract_after_assistant_marker(self, runner: QueryRunner):
        """Extrai texto após marcador Assistant:."""
        stdout = "Some preamble\nAssistant: Here is my response"
        response = runner._extract_agent_response(stdout)
        assert "Here is my response" in response

    def test_remove_thinking_indicator(self, runner: QueryRunner):
        """Remove indicador Thinking..."""
        stdout = "Thinking...\nHere is the actual response"
        response = runner._extract_agent_response(stdout)
        assert "Thinking" not in response

    def test_clean_multiple_newlines(self, runner: QueryRunner):
        """Limpa múltiplas newlines consecutivas."""
        stdout = "First line\n\n\n\nSecond line"
        response = runner._extract_agent_response(stdout)
        assert "\n\n\n" not in response


class TestClassifyTool:
    """Testes para classify_tool() no QueryRunner."""

    def test_classify_mcp_tools(self):
        """Tools MCP são classificadas corretamente."""
        assert QueryRunner.classify_tool("deck_list") == "mcp"
        assert QueryRunner.classify_tool("bridge_check_newave") == "mcp"
        assert QueryRunner.classify_tool("docs_search") == "mcp"

    def test_classify_native_tools(self):
        """Tools nativas são classificadas corretamente."""
        assert QueryRunner.classify_tool("read_file") == "native"
        assert QueryRunner.classify_tool("list_directory") == "native"

    def test_classify_unknown_tools(self):
        """Tools desconhecidas retornam 'unknown'."""
        assert QueryRunner.classify_tool("some_unknown_tool") == "unknown"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
