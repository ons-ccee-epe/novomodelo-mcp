"""Comando equivalente do disparo de rodada e a varredura contra comandos inseguros."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.e2e.launcher import app as app_mod
from tests.e2e.launcher.command_preview import command_preview
from tests.e2e.launcher.service import RodadaRequest, argumentos_do_rodar

LOCAL = "http://127.0.0.1:5175"
WHEEL = "novomodelo_mcp-0.19.0-py3-none-any.whl"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app_mod.create_app(), base_url=LOCAL)


def test_preview_mostra_o_comando_do_rodar_sem_caminho_do_host() -> None:
    req = RodadaRequest(mcp=["sem", WHEEL], conjuntos=["tools"], filtro="docs-*", repeticoes=2)
    preview = command_preview(req)
    assert preview["comando"] == (
        f"python -m tests.e2e rodar --mcp sem {WHEEL} --conjuntos tools "
        "--filtro=docs-* --repeticoes 2"
    )
    assert "/" not in preview["comando"]


def test_preview_bate_com_os_argumentos_do_disparo() -> None:
    req = RodadaRequest(mcp=["sem"], agentes=["kiro"], completa=True, max_minutos=0)
    reais = argumentos_do_rodar(req, wheel=lambda nome: nome)
    assert command_preview(req)["argumentos"] == reais
    assert reais == ["--mcp", "sem", "--agentes", "kiro", "--completa", "--max-minutos", "0"]


def test_rota_devolve_o_comando(client: TestClient) -> None:
    resp = client.get(
        "/api/command-preview",
        params={"mcp": ["sem"], "conjuntos": "tools,usuario", "completa": "true"},
    )
    assert resp.status_code == 200
    assert resp.json()["comando"] == (
        "python -m tests.e2e rodar --mcp sem --conjuntos tools,usuario --completa"
    )


@pytest.mark.parametrize("params", [{"filtro": "a b"}, {"conjuntos": "x"}, {"repeticoes": "0"}])
def test_rota_recusa_valor_fora_da_lista(client: TestClient, params: dict) -> None:
    assert client.get("/api/command-preview", params=params).status_code == 422


_E2E = Path(__file__).resolve().parents[1]
_PASTAS_IGNORADAS = {"node_modules", "dist", "__pycache__", "executor"}
_SUFIXOS = {".py", ".ts", ".tsx", ".js", ".mjs", ".json", ".yaml", ".yml", ".toml", ".sh", ".md"}
_SEM_PERMISSAO = ("--trust-all" + "-tools", "--dangerously-skip" + "-permissions")


def test_nenhum_comando_inseguro_fora_do_executor() -> None:
    achados = [
        f"{arquivo.relative_to(_E2E).as_posix()}: {flag}"
        for arquivo in sorted(_E2E.rglob("*"))
        if arquivo.suffix in _SUFIXOS
        and arquivo.is_file()
        and not _PASTAS_IGNORADAS.intersection(arquivo.relative_to(_E2E).parts)
        for flag in _SEM_PERMISSAO
        if flag in arquivo.read_text(encoding="utf-8", errors="replace")
    ]

    assert achados == []
