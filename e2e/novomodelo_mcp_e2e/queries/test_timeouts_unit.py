"""Testes da resolução de timeouts: caso > grupo > default, override e timeout por tool."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from novomodelo_mcp_e2e.queries import mcp_workspace
from novomodelo_mcp_e2e.queries.loader import CasesLoader
from novomodelo_mcp_e2e.queries.models import ExpectedResult, QueryTestCase
from novomodelo_mcp_e2e.queries.runner import DEFAULT_TIMEOUT_S, QueryRunner

CASES_YAML = """
defaults:
  timeout_s: 300
  timeout_s_by_group:
    bridge: 900
cases:
- id: convert
  query: q
  expected: {uses_mcp: true, tool: bridge_convert_newave}
- id: deck
  query: q
  expected: {uses_mcp: true, tool: deck_list}
- id: proprio
  query: q
  timeout_s: 42
  expected: {uses_mcp: true, tool: bridge_check_newave}
- id: tools-lista
  query: q
  expected: {uses_mcp: true, tools: [bridge_compare_newave, deck_list]}
"""


def _load(tmp_path: Path, text: str) -> dict[str, QueryTestCase]:
    path = tmp_path / "cases.yaml"
    path.write_text(text, encoding="utf-8")
    return {c.id: c for c in CasesLoader(path, tmp_path).load()}


def test_timeout_precedence_case_then_group_then_default(tmp_path: Path) -> None:
    cases = _load(tmp_path, CASES_YAML)
    assert cases["convert"].timeout_s == 900
    assert cases["deck"].timeout_s == 300
    assert cases["proprio"].timeout_s == 42
    assert cases["tools-lista"].timeout_s == 900  # grupo da primeira tool aceita


def test_legacy_list_format_still_loads_without_timeouts(tmp_path: Path) -> None:
    cases = _load(
        tmp_path,
        "- id: a\n  query: q\n  expected: {uses_mcp: true, tool: deck_list}\n",
    )
    assert cases["a"].timeout_s is None


def test_invalid_defaults_are_rejected(tmp_path: Path) -> None:
    from novomodelo_mcp_e2e.queries.loader import CasesLoaderError

    with pytest.raises(CasesLoaderError, match="defaults"):
        _load(tmp_path, "defaults: {timeout_s: -1}\ncases: []\n")


def _case(timeout_s: float | None) -> QueryTestCase:
    return QueryTestCase(
        id="c1",
        query="q",
        expected=ExpectedResult(uses_mcp=True, tool="deck_list"),
        timeout_s=timeout_s,
    )


def _runner(timeout_seconds: float | None = None) -> QueryRunner:
    return QueryRunner(timeout_seconds=timeout_seconds)


def test_runner_uses_case_timeout_unless_forced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QUERY_TIMEOUT_S", raising=False)
    assert _runner().timeout_for(_case(900)) == 900
    assert _runner().timeout_for(_case(None)) == DEFAULT_TIMEOUT_S
    assert _runner(timeout_seconds=30).timeout_for(_case(900)) == 30


def test_env_var_forces_timeout_for_every_case(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QUERY_TIMEOUT_S", "45")
    assert _runner().timeout_for(_case(900)) == 45


def test_tool_timeout_follows_mcp_cli_timeout_plus_margin() -> None:
    assert mcp_workspace.tool_timeout_ms({"env": {}}) == 960_000
    assert mcp_workspace.tool_timeout_ms({"env": {"NOVOMODELO_MCP_TIMEOUT": "1200"}}) == 1_260_000


def test_workspace_config_carries_kiro_tool_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    cfg = home / ".kiro" / "settings" / "mcp.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(json.dumps({"mcpServers": {"novomodelo": {"command": "x"}}}), encoding="utf-8")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    root = mcp_workspace.prepare_workspace(tmp_path / "fixtures")

    written = json.loads((root / ".kiro" / "settings" / "mcp.json").read_text(encoding="utf-8"))
    assert written["mcpServers"]["novomodelo"]["timeout"] == 960_000
