"""Testes unitários para o confinamento do MCP novomodelo ao workspace de fixtures."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests.e2e.queries import mcp_workspace
from tests.e2e.queries.mcp_workspace import (
    WORKSPACE_ENV,
    prepare_workspace,
    server_config_for_workspace,
)


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.chdir(tmp_path)
    return home


def _write_user_config(home: Path, server: dict) -> None:
    cfg = home / ".kiro" / "settings" / "mcp.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(json.dumps({"mcpServers": {"novomodelo": server}}), encoding="utf-8")


def test_workspace_override_keeps_rest_of_user_server(fake_home: Path, tmp_path: Path) -> None:
    _write_user_config(
        fake_home,
        {
            "command": "novomodelo-mcp",
            "args": ["--x"],
            "env": {WORKSPACE_ENV: "/pasta/do/usuario", "NOVOMODELO_MCP_RESPONSE_LOG": "log.jsonl"},
        },
    )
    fixtures = tmp_path / "fixtures"

    server = server_config_for_workspace(fixtures)

    assert server is not None
    assert server["env"][WORKSPACE_ENV] == str(fixtures.resolve())
    assert server["env"]["NOVOMODELO_MCP_RESPONSE_LOG"] == "log.jsonl"
    assert server["command"] == "novomodelo-mcp"
    assert server["args"] == ["--x"]


def test_override_does_not_mutate_user_config(fake_home: Path, tmp_path: Path) -> None:
    _write_user_config(fake_home, {"command": "novomodelo-mcp", "env": {WORKSPACE_ENV: "/u"}})

    prepare_workspace(tmp_path / "fixtures")

    user_cfg = json.loads(
        (fake_home / ".kiro" / "settings" / "mcp.json").read_text(encoding="utf-8")
    )
    assert user_cfg["mcpServers"]["novomodelo"]["env"][WORKSPACE_ENV] == "/u"


def test_prepare_workspace_writes_workspace_level_kiro_config(
    fake_home: Path, tmp_path: Path
) -> None:
    _write_user_config(fake_home, {"command": "novomodelo-mcp"})
    fixtures = tmp_path / "fixtures"

    root = prepare_workspace(fixtures)

    assert root == fixtures.resolve()
    written = json.loads((root / ".kiro" / "settings" / "mcp.json").read_text(encoding="utf-8"))
    assert written["mcpServers"]["novomodelo"]["env"][WORKSPACE_ENV] == str(root)


def _link_dir(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            pytest.skip("symlink de diretório indisponível neste sistema")
        # Symlink no Windows exige privilégio; junction não, e é o que as fixtures locais usam.
        import _winapi

        _winapi.CreateJunction(str(target), str(link))


def test_linked_fixture_target_becomes_explicit_root(
    fake_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mcp_workspace, "_REPO_ROOT", tmp_path.resolve())
    _write_user_config(fake_home, {"command": "novomodelo-mcp"})
    real_case = tmp_path / "real_cases" / "novomodelo-caso-reduzido"
    real_case.mkdir(parents=True)
    fixtures = tmp_path / "fixtures"
    (fixtures / "newave").mkdir(parents=True)
    _link_dir(fixtures / "newave" / "novomodelo-caso-reduzido", real_case)

    server = server_config_for_workspace(fixtures)

    assert server is not None
    roots = server["env"][WORKSPACE_ENV].split(os.pathsep)
    assert roots == [str(fixtures.resolve()), str(real_case.resolve())]


def test_link_pointing_outside_repo_is_not_a_root(
    fake_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    fixtures = repo / "fixtures"
    fixtures.mkdir(parents=True)
    outside = tmp_path / "fora_do_repo"
    outside.mkdir()
    monkeypatch.setattr(mcp_workspace, "_REPO_ROOT", repo.resolve())
    _write_user_config(fake_home, {"command": "novomodelo-mcp"})
    _link_dir(fixtures / "atalho", outside)

    server = server_config_for_workspace(fixtures)

    assert server is not None
    assert server["env"][WORKSPACE_ENV].split(os.pathsep) == [str(fixtures.resolve())]


def test_prepare_workspace_fails_without_novomodelo_server(fake_home: Path, tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="novomodelo"):
        prepare_workspace(tmp_path / "fixtures")
