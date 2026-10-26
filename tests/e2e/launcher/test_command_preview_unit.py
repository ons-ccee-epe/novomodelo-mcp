"""Testes do comando equivalente ao disparo (GET /api/command-preview)."""
from __future__ import annotations

import shlex
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402 - depois do importorskip

from tests.e2e.launcher import app as app_mod  # noqa: E402
from tests.e2e.launcher.command_preview import command_preview  # noqa: E402
from tests.e2e.launcher.providers import ProviderInfo, build_command  # noqa: E402
from tests.e2e.queries.models import ExpectedResult, QueryTestCase  # noqa: E402

LOCAL = "http://127.0.0.1:5175"
KIRO = ProviderInfo("kiro-cli", "Kiro CLI", "kiro-cli", True, "/opt/abs/kiro-cli")
CLAUDE = ProviderInfo("claude", "Claude Code", "claude", True, "/opt/abs/claude")


def _case(case_id: str, query: str = "pergunta do caso") -> QueryTestCase:
    return QueryTestCase(
        id=case_id,
        query=query,
        expected=ExpectedResult(uses_mcp=True, tool="server_info"),
    )


def test_kiro_full_suite() -> None:
    preview = command_preview(KIRO, None, None, [_case("a"), _case("b")])

    assert preview["terminal"] == "python -m tests.e2e.queries.run_queries"
    assert preview["terminal_note"] is None
    assert preview["conjunto"] == "todos"
    assert preview["total"] == 2
    assert "<pergunta>" in preview["agent"]
    assert preview["agent"].startswith("kiro-cli chat --no-interactive --trust-all-tools")


def test_kiro_tags_and_case() -> None:
    by_tags = command_preview(KIRO, ["docs", "bridge"], None, [_case("a"), _case("b")])
    assert by_tags["terminal"].endswith(" --tags docs bridge")

    by_case = command_preview(KIRO, None, "a", [_case("a", "qual a versão?")])
    assert by_case["terminal"].endswith(" --case a")
    assert by_case["conjunto"] == "pergunta:a"
    assert "qual a versão?" in by_case["agent"]


def test_claude_has_no_terminal_equivalent() -> None:
    preview = command_preview(CLAUDE, None, None, [_case("a"), _case("b")])

    assert preview["terminal"] is None
    assert "Claude Code" in preview["terminal_note"]
    assert "--mcp-config <config-mcp-temporaria>" in preview["agent"]
    assert not preview["agent"].startswith("/opt/abs")


def test_preview_matches_build_command() -> None:
    cases = [_case("a", "uma pergunta com 'aspas' e espaços")]
    preview = command_preview(CLAUDE, None, "a", cases)

    expected = build_command(
        replace(CLAUDE, path=None),
        cases[0].query,
        mcp_config_path=Path("<config-mcp-temporaria>"),
    )
    assert shlex.split(preview["agent"]) == expected


@pytest.fixture
def client() -> TestClient:
    return TestClient(app_mod.create_app(), base_url=LOCAL)


def test_route_returns_preview(client: TestClient) -> None:
    with patch.object(app_mod, "resolve_provider", return_value=KIRO):
        resp = client.get("/api/command-preview", params={"provider": "kiro-cli", "tags": "docs"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["terminal"].endswith(" --tags docs")
    assert body["total"] >= 1


def test_route_unknown_case_is_422(client: TestClient) -> None:
    with patch.object(app_mod, "resolve_provider", return_value=KIRO):
        resp = client.get("/api/command-preview", params={"case_id": "nao-existe-xyz"})

    assert resp.status_code == 422


def test_route_unknown_provider_is_422(client: TestClient) -> None:
    with patch.object(app_mod, "resolve_provider", side_effect=RuntimeError("sem provedor")):
        resp = client.get("/api/command-preview")

    assert resp.status_code == 422
    assert "sem provedor" in resp.json()["detail"]
