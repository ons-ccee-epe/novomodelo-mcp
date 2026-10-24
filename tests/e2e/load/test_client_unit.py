"""Testes da classificação de resultados e do cliente MCP da carga (sessão falsa)."""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from tests.e2e.load import client as client_mod
from tests.e2e.load.client import McpStdioClient, classify_result


def _result(text: str, is_error: bool = False) -> SimpleNamespace:
    return SimpleNamespace(isError=is_error, content=[SimpleNamespace(text=text)])


class TestClassifyResult:
    def test_ok_envelope(self) -> None:
        assert classify_result(_result(json.dumps({"status": "ok"}))) == ("ok", None)

    def test_error_envelope_reports_the_first_diagnostic(self) -> None:
        envelope = {"status": "error", "exit_code": 2, "diagnostics": ["arquivo nao existe: x", "y"]}
        assert classify_result(_result(json.dumps(envelope))) == ("error", "arquivo nao existe: x")

    def test_error_envelope_without_diagnostics_uses_the_message(self) -> None:
        outcome, message = classify_result(_result(json.dumps({"status": "error", "message": "m"})))
        assert (outcome, message) == ("error", "m")

    def test_protocol_level_is_error(self) -> None:
        outcome, message = classify_result(_result("Tool nope not found", is_error=True))
        assert outcome == "error"
        assert "not found" in message

    def test_non_json_text_is_ok(self) -> None:
        assert classify_result(_result("texto livre")) == ("ok", None)

    def test_json_without_status_is_ok(self) -> None:
        assert classify_result(_result(json.dumps({"types": []}))) == ("ok", None)

    def test_empty_content_is_ok(self) -> None:
        assert classify_result(SimpleNamespace(isError=False, content=[])) == ("ok", None)

    def test_long_error_text_is_truncated(self) -> None:
        _outcome, message = classify_result(_result("x" * 1000, is_error=True))
        assert len(message) <= 200


class _Session:
    def __init__(self, behavior) -> None:
        self.behavior = behavior
        self.timeouts: list = []

    async def call_tool(self, tool, arguments, read_timeout_seconds=None):
        self.timeouts.append(read_timeout_seconds)
        return await self.behavior(tool, arguments)

    async def list_tools(self):
        annotations = SimpleNamespace(readOnlyHint=True, openWorldHint=False)
        return SimpleNamespace(tools=[SimpleNamespace(name="docs_list", annotations=annotations)])


class TestMcpStdioClient:
    def test_ok_call_carries_latency_and_passes_the_timeout_to_the_sdk(self) -> None:
        async def behavior(_tool, _args):
            await asyncio.sleep(0.02)
            return _result(json.dumps({"status": "ok"}))

        session = _Session(behavior)
        outcome = asyncio.run(McpStdioClient(session).call("docs_list", {}, timeout_s=7))

        assert outcome.outcome == "ok"
        assert outcome.broken is False
        assert outcome.latency_ms >= 20
        assert session.timeouts[0].total_seconds() == 7

    def test_error_envelope_is_an_error_but_keeps_the_session(self) -> None:
        async def behavior(_tool, _args):
            return _result(json.dumps({"status": "error", "diagnostics": ["falhou"]}))

        outcome = asyncio.run(McpStdioClient(_Session(behavior)).call("deck_list", {}, 5))
        assert (outcome.outcome, outcome.error, outcome.broken) == ("error", "falhou", False)

    def test_no_answer_in_time_is_a_timeout_and_breaks_the_session(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(client_mod, "_BACKSTOP_S", 0.0)

        async def behavior(_tool, _args):
            await asyncio.sleep(30)

        outcome = asyncio.run(McpStdioClient(_Session(behavior)).call("docs_list", {}, 0.1))
        assert outcome.outcome == "timeout"
        assert outcome.broken is True
        assert outcome.latency_ms < 5000

    def test_sdk_timeout_error_is_a_timeout(self) -> None:
        class McpError(Exception):
            error = SimpleNamespace(code=408)

        async def behavior(_tool, _args):
            raise McpError("Timed out while waiting for response")

        outcome = asyncio.run(McpStdioClient(_Session(behavior)).call("docs_list", {}, 5))
        assert (outcome.outcome, outcome.broken) == ("timeout", True)

    def test_connection_failure_is_an_error_and_breaks_the_session(self) -> None:
        async def behavior(_tool, _args):
            raise BrokenPipeError("servidor morreu")

        outcome = asyncio.run(McpStdioClient(_Session(behavior)).call("docs_list", {}, 5))
        assert outcome.outcome == "error"
        assert outcome.broken is True
        assert "BrokenPipeError" in outcome.error

    def test_list_tools_returns_the_read_only_hints(self) -> None:
        hints = asyncio.run(McpStdioClient(_Session(None)).list_tools())
        assert hints["docs_list"].read_only is True
        assert hints["docs_list"].open_world is False
