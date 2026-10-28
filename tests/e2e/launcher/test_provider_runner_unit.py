"""Testes unitários para o ProviderQueryRunner (parsing stream-json por provedor).

Prova que o dispatcher de parsing do ProviderQueryRunner:
  - kiro-cli: lê o stream-json ACP REAL (capturado de kiro-cli 2.33.0) e extrai
    tool calls (nome bare), envelope MCP e resposta final.
  - claude:   mantém o parsing Anthropic-style (regressão de comportamento).

O fixture ACP é uma cópia fiel e reduzida da amostra real salva em
tests/e2e/.agents/tasks/kiro-cli-streamjson/acp_sample.jsonl (mesmo schema de
eventos: runStarted / sessionUpdate(tool_call|tool_call_update|
agent_message_chunk) / runFinished). Embutimos o sample como constante para o
teste não depender do arquivo de notas.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from tests.e2e.launcher.provider_runner import ProviderQueryRunner
from tests.e2e.launcher.providers import ProviderInfo
from tests.e2e.queries.validator import MCP_TOOLS

# ---------------------------------------------------------------------------
# Fixtures de stream-json
# ---------------------------------------------------------------------------

# Amostra ACP real (kiro-cli 2.33.0), reduzida. Cada linha = um evento JSON.
# O envelope da tool vem em rawOutput.items[].Json.content[].text (string JSON).
ACP_SAMPLE = r"""{"type":"runStarted","data":{"payloadSchema":"acp","acpProtocolVersion":1,"engine":"v2"}}
{"type":"metadata","data":{"sessionId":"sess-1","contextUsagePercentage":4.0}}
{"type":"sessionUpdate","data":{"sessionId":"sess-1","update":{"sessionUpdate":"tool_call","toolCallId":"toolu_bdrk_01EFDtr2vKjDS4uC2oxaz6fC","title":"Running: @novomodelo/server_info","rawInput":{"__tool_use_purpose":"verificar versao"},"_meta":{"kiro":{"toolName":"server_info","mcpServerName":"novomodelo"}}}}}
{"type":"sessionUpdate","data":{"sessionId":"sess-1","update":{"sessionUpdate":"tool_call_update","toolCallId":"toolu_bdrk_01EFDtr2vKjDS4uC2oxaz6fC","kind":"other","status":"completed","title":"Running: @novomodelo/server_info","rawInput":{"__tool_use_purpose":"verificar versao"},"rawOutput":{"items":[{"Json":{"content":[{"type":"text","text":"{\"server\": \"novomodelo-mcp\", \"versao_mcp\": \"0.18.0.post1\"}"}],"isError":false}}]}}}}
{"type":"sessionUpdate","data":{"sessionId":"sess-1","update":{"sessionUpdate":"agent_message_chunk","content":{"type":"text","text":"A versao instalada "}}}}
{"type":"sessionUpdate","data":{"sessionId":"sess-1","update":{"sessionUpdate":"agent_message_chunk","content":{"type":"text","text":"e a 0.18.0."}}}}
{"type":"metadata","data":{"sessionId":"sess-1","contextUsagePercentage":8.0,"turnDurationMs":36048}}
{"type":"runFinished","data":{"sessionId":"sess-1","status":"success","stopReason":"end_turn","finalText":"A versao instalada do novomodelo e a 0.18.0.","finalTextTruncated":false}}
"""  # noqa: E501 - amostra bruta de log, a quebra alteraria o formato testado


# Amostra claude (stream-json Anthropic-style), reduzida — para regressão.
CLAUDE_SAMPLE = r"""{"type":"system","subtype":"init","session_id":"c-1"}
{"type":"assistant","message":{"content":[{"type":"tool_use","id":"toolu_claude_1","name":"mcp__novomodelo__solver_version","input":{"x":1}}]}}
{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"toolu_claude_1","content":[{"type":"text","text":"{\"status\": \"ok\", \"version\": \"0.18.0\"}"}]}]}}
{"type":"result","result":"A versao do solver e 0.18.0."}
"""  # noqa: E501 - amostra bruta de log, a quebra alteraria o formato testado


def _make_runner(provider_id: str) -> ProviderQueryRunner:
    """Instancia o runner para um provedor, mockando a validação do binário."""
    provider = ProviderInfo(
        id=provider_id,  # type: ignore[arg-type]
        label="Test",
        binary=provider_id,
        installed=True,
        path=provider_id,
    )
    with patch.object(ProviderQueryRunner, "_validate_kiro_cli"):
        return ProviderQueryRunner(provider)


@pytest.fixture
def kiro_runner() -> ProviderQueryRunner:
    return _make_runner("kiro-cli")


@pytest.fixture
def claude_runner() -> ProviderQueryRunner:
    return _make_runner("claude")


# ---------------------------------------------------------------------------
# kiro-cli (ACP)
# ---------------------------------------------------------------------------


class TestKiroAcpParsing:
    """Parsing do stream-json ACP do kiro-cli."""

    def test_parse_tool_calls_extracts_bare_name(self, kiro_runner):
        tool_calls = kiro_runner._parse_tool_calls(ACP_SAMPLE)
        assert len(tool_calls) == 1
        tc = tool_calls[0]
        # Nome bare, casa direto com MCP_TOOLS.
        assert tc.name == "server_info"
        assert tc.name in MCP_TOOLS
        assert tc.tool_id == "toolu_bdrk_01EFDtr2vKjDS4uC2oxaz6fC"
        # rawInput vira args.
        assert tc.args == {"__tool_use_purpose": "verificar versao"}

    def test_read_mcp_response_log_builds_envelope(self, kiro_runner):
        # Precisa parsear antes para popular self._kiro_log.
        kiro_runner._parse_tool_calls(ACP_SAMPLE)
        envelopes = kiro_runner._read_mcp_response_log(None)
        assert len(envelopes) == 1
        env = envelopes[0]
        assert env["tool"] == "server_info"
        # O envelope veio do rawOutput e foi desserializado de JSON.
        assert env["result"] == {
            "server": "novomodelo-mcp",
            "versao_mcp": "0.18.0.post1",
        }
        assert env["result"]  # não vazio
        assert set(env.keys()) == {"tool", "arguments", "result", "duration_ms"}

    def test_extract_agent_response_uses_final_text(self, kiro_runner):
        response = kiro_runner._extract_agent_response(ACP_SAMPLE)
        assert response == "A versao instalada do novomodelo e a 0.18.0."

    def test_extract_agent_response_falls_back_to_chunks(self, kiro_runner):
        # Sem runFinished.finalText, concatena os agent_message_chunk.
        no_final = "\n".join(
            line for line in ACP_SAMPLE.splitlines() if '"runFinished"' not in line
        )
        response = kiro_runner._extract_agent_response(no_final)
        assert response == "A versao instalada e a 0.18.0."

    def test_tool_name_fallback_from_title(self, kiro_runner):
        # Sem _meta.kiro.toolName, extrai do title "Running: @novomodelo/docs_list".
        line = (
            '{"type":"sessionUpdate","data":{"update":{"sessionUpdate":"tool_call",'
            '"toolCallId":"t1","title":"Running: @novomodelo/docs_list","rawInput":{}}}}'
        )
        tool_calls = kiro_runner._parse_tool_calls(line)
        assert len(tool_calls) == 1
        assert tool_calls[0].name == "docs_list"
        assert tool_calls[0].name in MCP_TOOLS


# ---------------------------------------------------------------------------
# claude (regressão de comportamento)
# ---------------------------------------------------------------------------


class TestClaudeRegression:
    """Garante que o parser claude (Anthropic-style) segue intacto."""

    def test_parse_tool_calls_strips_mcp_prefix(self, claude_runner):
        tool_calls = claude_runner._parse_tool_calls(CLAUDE_SAMPLE)
        assert len(tool_calls) == 1
        assert tool_calls[0].name == "solver_version"
        assert tool_calls[0].name in MCP_TOOLS
        assert tool_calls[0].tool_id == "toolu_claude_1"

    def test_read_mcp_response_log_from_stream(self, claude_runner):
        claude_runner._parse_tool_calls(CLAUDE_SAMPLE)
        envelopes = claude_runner._read_mcp_response_log(None)
        assert len(envelopes) == 1
        assert envelopes[0]["tool"] == "solver_version"
        assert envelopes[0]["result"] == {"status": "ok", "version": "0.18.0"}

    def test_extract_agent_response_from_result_event(self, claude_runner):
        response = claude_runner._extract_agent_response(CLAUDE_SAMPLE)
        assert response == "A versao do solver e 0.18.0."


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
