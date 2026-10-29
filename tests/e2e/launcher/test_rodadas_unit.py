"""Disparo e leitura das rodadas pelo launcher, sem container nem agente."""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tests.e2e.config import Config
from tests.e2e.launcher import app as app_mod
from tests.e2e.launcher import service as service_mod
from tests.e2e.launcher.service import (
    AMBIENTE_PERMITIDO,
    PASTA_LOGS,
    PASTA_WHEELS_ENV,
    ambiente_do_subprocesso,
)
from tests.e2e.resultado.armazenamento import gravar_manifesto, gravar_registro
from tests.e2e.resultado.modelos import Manifesto, Registro
from tests.e2e.rodada import ARQUIVO_BLOQUEIO

LOCAL = "http://127.0.0.1:5175"
HEADER = {"X-Launcher": "1"}
WHEEL = "novomodelo_mcp-0.19.0-py3-none-any.whl"


@pytest.fixture
def resultados(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    pasta = tmp_path / "resultados"
    pasta.mkdir()
    monkeypatch.setenv("NOVOMODELO_BATERIA_RESULTADOS", str(pasta))
    monkeypatch.delenv(PASTA_WHEELS_ENV, raising=False)
    return pasta


@pytest.fixture(autouse=True)
def sem_gitleaks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_mod, "varrer_segredos", lambda _pasta: service_mod.Varredura())


@pytest.fixture
def client(resultados: Path) -> TestClient:
    return TestClient(app_mod.create_app(), base_url=LOCAL)


def _processo(codigo: int = 0) -> SimpleNamespace:
    return SimpleNamespace(wait=lambda: codigo)


def _manifesto(nome: str) -> Manifesto:
    return Manifesto(
        rodada=nome,
        criado_em="2026-01-01T00:00:00Z",
        configs=("sem-mcp",),
        conjuntos=("tools",),
        agentes=("claude",),
        repeticoes=1,
        flags={"completa": False},
        versoes={
            "novomodelo": "0.0.0",
            "novomodelo-bridge": "0.0.0",
            "claude-code": "0.0.0",
            "kiro-cli": "0.0.0",
            "juiz-modelo": "m",
            "juiz-temperatura": "0",
        },
        commit_bateria="abc1234",
    )


def _registro(nome: str, estado: str = "passou") -> Registro:
    return Registro(
        rodada=nome,
        conjunto="tools",
        caso="docs-list-all",
        agente="claude",
        config="sem-mcp",
        repeticao=1,
        estado=estado,  # type: ignore[arg-type]
        motivo="",
        tools=(),
        duracao_s=1.0,
    )


def _gravar(pasta: Path, nome: str) -> Path:
    rodada = pasta / nome
    gravar_manifesto(rodada, _manifesto(nome))
    gravar_registro(rodada, _registro(nome))
    return rodada


def test_disparo_monta_comando_da_bateria_sem_shell(client: TestClient, resultados: Path) -> None:
    with patch.object(service_mod.subprocess, "Popen", return_value=_processo()) as popen:
        resp = client.post(
            "/api/rodadas",
            json={"rodada": "r1", "mcp": ["sem"], "conjuntos": ["tools"], "filtro": "docs-*"},
            headers=HEADER,
        )

    assert resp.status_code == 200
    comando = popen.call_args.args[0]
    assert comando == [
        sys.executable,
        "-m",
        "tests.e2e",
        "rodar",
        "--mcp",
        "sem",
        "--rodada",
        "r1",
        "--conjuntos",
        "tools",
        "--filtro=docs-*",
    ]
    opcoes = popen.call_args.kwargs
    assert opcoes["shell"] is False
    assert opcoes.get("start_new_session") is True or "creationflags" in opcoes
    assert (resultados / PASTA_LOGS / "r1.log").is_file()
    assert resp.json()["comando"] == (
        "python -m tests.e2e rodar --mcp sem --rodada r1 --conjuntos tools --filtro=docs-*"
    )


def test_disparo_sem_nome_gera_o_nome_da_rodada(client: TestClient) -> None:
    with patch.object(service_mod.subprocess, "Popen", return_value=_processo()) as popen:
        resp = client.post("/api/rodadas", json={"mcp": ["sem"]}, headers=HEADER)
    nome = resp.json()["rodada"]
    comando = popen.call_args.args[0]
    assert comando[comando.index("--rodada") + 1] == nome


def test_disparo_recusa_flag_fora_da_lista(client: TestClient) -> None:
    with patch.object(service_mod.subprocess, "Popen") as popen:
        for corpo in (
            {"mcp": ["sem"], "origem_mcp": ["x=y"]},
            {"mcp": ["sem"], "extra": "--trust"},
            {"mcp": ["sem --completa"]},
        ):
            resp = client.post("/api/rodadas", json=corpo, headers=HEADER)
            assert resp.status_code == 422, corpo
    popen.assert_not_called()


def test_disparo_recusa_wheel_fora_da_pasta_configurada(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pasta = tmp_path / "wheels"
    pasta.mkdir()
    fora = tmp_path / WHEEL
    fora.write_bytes(b"")
    monkeypatch.setenv(PASTA_WHEELS_ENV, str(pasta))
    with patch.object(service_mod.subprocess, "Popen") as popen:
        for valor in (str(fora), "../" + WHEEL, WHEEL):
            resp = client.post("/api/rodadas", json={"mcp": [valor]}, headers=HEADER)
            assert resp.status_code == 422, valor
    popen.assert_not_called()


def test_disparo_recusa_link_na_pasta_que_aponta_para_fora(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pasta = tmp_path / "wheels"
    pasta.mkdir()
    fora = tmp_path / WHEEL
    fora.write_bytes(b"")
    try:
        (pasta / "link.whl").symlink_to(fora)
    except OSError:
        pytest.skip("o sistema não deixa criar link simbólico")
    monkeypatch.setenv(PASTA_WHEELS_ENV, str(pasta))
    with patch.object(service_mod.subprocess, "Popen") as popen:
        resp = client.post("/api/rodadas", json={"mcp": ["link.whl"]}, headers=HEADER)
        assert resp.status_code == 422
    popen.assert_not_called()


def test_disparo_com_wheel_da_pasta_leva_o_caminho_resolvido(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / WHEEL).write_bytes(b"")
    monkeypatch.setenv(PASTA_WHEELS_ENV, str(tmp_path))
    with patch.object(service_mod.subprocess, "Popen", return_value=_processo()) as popen:
        resp = client.post("/api/rodadas", json={"mcp": [WHEEL]}, headers=HEADER)
    assert resp.status_code == 200
    comando = popen.call_args.args[0]
    assert comando[comando.index("--mcp") + 1] == str((tmp_path / WHEEL).resolve())
    assert str(tmp_path) not in resp.json()["comando"]


def test_segundo_disparo_e_409_enquanto_a_rodada_roda(client: TestClient) -> None:
    class Preso:
        def wait(self) -> int:
            import time

            time.sleep(0.3)
            return 0

    with patch.object(service_mod.subprocess, "Popen", return_value=Preso()):
        primeiro = client.post("/api/rodadas", json={"mcp": ["sem"]}, headers=HEADER)
        segundo = client.post("/api/rodadas", json={"mcp": ["sem"]}, headers=HEADER)
    assert (primeiro.status_code, segundo.status_code) == (200, 409)


def test_lista_rodadas_da_pasta_configurada(client: TestClient, resultados: Path) -> None:
    _gravar(resultados, "20260101T000000Z")
    _gravar(resultados, "20260102T000000Z")
    (resultados / "sem-manifesto").mkdir()
    (resultados / PASTA_LOGS).mkdir()

    resp = client.get("/api/rodadas")

    assert resp.status_code == 200
    nomes = [r["rodada"] for r in resp.json()["rodadas"]]
    assert nomes == ["20260102T000000Z", "20260101T000000Z"]
    primeira = resp.json()["rodadas"][0]
    assert primeira["configs"] == ["sem-mcp"] and primeira["bloqueada"] is False


def test_detalhe_traz_manifesto_registros_e_decisao_sem_base(
    client: TestClient, resultados: Path
) -> None:
    _gravar(resultados, "r1")

    corpo = client.get("/api/rodadas/r1").json()

    assert corpo["manifesto"]["rodada"] == "r1"
    assert [r["estado"] for r in corpo["registros"]] == ["passou"]
    assert corpo["decisoes"]["sem-mcp"]["veredito"] == "go"


def test_detalhe_devolve_a_decisao_do_go_no_go_quando_gravada(
    client: TestClient, resultados: Path
) -> None:
    pasta = _gravar(resultados, "r1")
    assert client.get("/api/rodadas/r1").json()["go_no_go"] is None

    (pasta / "decisao-go-no-go.json").write_text(
        json.dumps(
            {
                "schema_versao": 1,
                "veredito": "go",
                "alvo": "sem-mcp",
                "base": None,
                "bloqueios": [],
                "inconclusivos": [],
                "pulados": [],
                "sem_base": [],
                "ausentes": [],
            }
        ),
        encoding="utf-8",
    )
    assert client.get("/api/rodadas/r1").json()["go_no_go"]["veredito"] == "go"

    (pasta / "decisao-go-no-go.json").write_text(
        json.dumps({"schema_versao": 1, "veredito": "go"}), encoding="utf-8"
    )
    assert "erro" in client.get("/api/rodadas/r1").json()["go_no_go"]

    (pasta / "decisao-go-no-go.json").write_text(
        json.dumps({"schema_versao": 2, "veredito": "go"}), encoding="utf-8"
    )
    assert "schema_versao" in client.get("/api/rodadas/r1").json()["go_no_go"]["erro"]

    (pasta / "decisao-go-no-go.json").write_text("{", encoding="utf-8")
    assert "erro" in client.get("/api/rodadas/r1").json()["go_no_go"]


def test_rodada_bloqueada_por_segredo_nao_expoe_registros(
    client: TestClient, resultados: Path
) -> None:
    pasta = _gravar(resultados, "r1")
    (pasta / ARQUIVO_BLOQUEIO).write_text("achado", encoding="utf-8")

    corpo = client.get("/api/rodadas/r1").json()

    assert corpo["bloqueada"] is True
    assert corpo["registros"] == [] and corpo["decisoes"] == {}


@pytest.mark.parametrize("raiz", ["[]", '"texto"', "1"])
def test_manifesto_com_raiz_que_nao_e_objeto_vira_erro_tratado(
    client: TestClient, resultados: Path, raiz: str
) -> None:
    _gravar(resultados, "r1")
    pasta = resultados / "ruim"
    pasta.mkdir()
    (pasta / "manifesto.json").write_text(raiz, encoding="utf-8")

    resp = client.get("/api/rodadas")

    assert resp.status_code == 200
    itens = {r["rodada"]: r for r in resp.json()["rodadas"]}
    assert "erro" in itens["ruim"] and "erro" not in itens["r1"]
    assert client.get("/api/rodadas/ruim").status_code == 200


def test_rodada_que_quebra_a_leitura_e_pulada_na_lista(
    client: TestClient, resultados: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _gravar(resultados, "r1")
    _gravar(resultados, "r2")
    original = service_mod.RodadaService._resumo

    def resumo(self, pasta):
        if pasta.name == "r2":
            raise RuntimeError("leitura quebrou")
        return original(self, pasta)

    monkeypatch.setattr(service_mod.RodadaService, "_resumo", resumo)
    resp = client.get("/api/rodadas")
    assert resp.status_code == 200
    assert [r["rodada"] for r in resp.json()["rodadas"]] == ["r1"]


def test_manifesto_ilegivel_nao_derruba_a_lista(client: TestClient, resultados: Path) -> None:
    pasta = resultados / "ruim"
    pasta.mkdir()
    (pasta / "manifesto.json").write_text("{", encoding="utf-8")

    item = client.get("/api/rodadas").json()["rodadas"][0]

    assert item["rodada"] == "ruim" and "erro" in item
    assert str(resultados) not in json.dumps(item)


def test_rodada_inexistente_404(client: TestClient) -> None:
    assert client.get("/api/rodadas/nao-existe").status_code == 404


@pytest.mark.parametrize("nome", ["a%2Fb", "..%2F..%2Fetc", "%2E%2E", "a%5Cb", "a b"])
def test_id_de_rodada_com_barra_e_404_ou_recusa(client: TestClient, nome: str) -> None:
    assert client.get(f"/api/rodadas/{nome}").status_code in (404, 422)


def test_detalhe_recusa_nome_invalido_antes_de_virar_caminho(resultados: Path) -> None:
    service = service_mod.RodadaService(config=lambda: replace_resultados(resultados))
    with pytest.raises(ValueError):
        service.detalhe("../fora")


def replace_resultados(pasta: Path) -> Config:
    return replace(service_mod.carregar_config({}), resultados=pasta)


def test_filtro_nao_comeca_por_hifen_e_vai_como_valor_da_flag(client: TestClient) -> None:
    for filtro in ("--completa", "-x", ",a"):
        resp = client.post("/api/rodadas", json={"mcp": ["sem"], "filtro": filtro}, headers=HEADER)
        assert resp.status_code == 422, filtro


def test_trava_viva_da_rodada_pedida_e_409(client: TestClient, resultados: Path) -> None:
    pasta = resultados / "r1"
    pasta.mkdir()
    (pasta / ".trava").write_text(f"{os.getpid()} 2026-01-01T00:00:00+00:00\n", encoding="utf-8")
    with patch.object(service_mod.subprocess, "Popen") as popen:
        resp = client.post("/api/rodadas", json={"rodada": "r1", "mcp": ["sem"]}, headers=HEADER)
    assert resp.status_code == 409
    popen.assert_not_called()


def test_detalhe_mostra_em_andamento_pela_trava_e_nao_pela_memoria(
    client: TestClient, resultados: Path
) -> None:
    pasta = _gravar(resultados, "r1")
    assert client.get("/api/rodadas/r1").json()["em_andamento"] is False
    (pasta / ".trava").write_text(f"{os.getpid()} 2026-01-01T00:00:00+00:00\n", encoding="utf-8")
    assert client.get("/api/rodadas/r1").json()["em_andamento"] is True
    assert client.get("/api/rodadas").json()["rodadas"][0]["em_andamento"] is True


def test_subprocesso_recebe_so_o_ambiente_da_lista_branca(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TOKEN_QUALQUER", "valor-falso")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "valor-falso")
    monkeypatch.setenv("NOVOMODELO_BATERIA_MOTOR", "podman")
    with patch.object(service_mod.subprocess, "Popen", return_value=_processo()) as popen:
        client.post("/api/rodadas", json={"mcp": ["sem"]}, headers=HEADER)
    env = popen.call_args.kwargs["env"]
    assert "TOKEN_QUALQUER" not in env and "AWS_SECRET_ACCESS_KEY" not in env
    assert env["NOVOMODELO_BATERIA_MOTOR"] == "podman"
    assert set(env) <= set(AMBIENTE_PERMITIDO) | {"PYTHONUNBUFFERED"} | {
        k for k in env if k.startswith(("NOVOMODELO_", "LC_", "XDG_", "UV_", "CONTAINERS_"))
    }
    assert ambiente_do_subprocesso({"PATH": "/x", "SEGREDO": "y"}) == {
        "PATH": "/x",
        "PYTHONUNBUFFERED": "1",
    }


def test_espera_que_falha_encerra_a_arvore_varre_o_log_e_so_entao_libera_a_vaga(
    resultados: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Quebra:
        def wait(self) -> int:
            raise OSError("falhou")

    ordem: list[str] = []
    service = service_mod.RodadaService(config=lambda: replace_resultados(resultados))

    def varrer(_pasta):
        ordem.append("varrido" if service._gate.owner == "r9" else "varrido sem vaga")
        return service_mod.Varredura()

    monkeypatch.setattr(service_mod, "_encerrar_arvore", lambda p: ordem.append("encerrado"))
    monkeypatch.setattr(service_mod, "varrer_segredos", varrer)
    with patch.object(service_mod.subprocess, "Popen", return_value=Quebra()):
        service.disparar(service_mod.RodadaRequest(mcp=["sem"], rodada="r9"))
        for _ in range(100):
            if service._gate.owner is None:
                break
            time.sleep(0.02)
    assert ordem == ["encerrado", "varrido"]
    assert service._gate.owner is None
    assert service._disparo("r9")["codigo_saida"] is None
    assert service._disparo("r9")["log_bloqueado"] is False


def test_varredura_do_log_que_quebra_bloqueia_o_log_e_libera_a_vaga(
    resultados: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def quebra(_pasta):
        raise RuntimeError("gitleaks quebrou")

    monkeypatch.setattr(service_mod, "varrer_segredos", quebra)
    service = service_mod.RodadaService(config=lambda: replace_resultados(resultados))
    with patch.object(service_mod.subprocess, "Popen", return_value=_processo()):
        service.disparar(service_mod.RodadaRequest(mcp=["sem"], rodada="r9"))
        for _ in range(100):
            if service._gate.owner is None:
                break
            time.sleep(0.02)
    assert service._gate.owner is None
    assert service._disparo("r9")["log_bloqueado"] is True
    assert (
        (resultados / PASTA_LOGS / "r9.log").read_text(encoding="utf-8").startswith("log removido")
    )


def test_log_com_achado_do_gitleaks_e_apagado(resultados: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        service_mod, "varrer_segredos", lambda _p: service_mod.Varredura(("r9.log",))
    )
    service = service_mod.RodadaService(config=lambda: replace_resultados(resultados))
    with patch.object(service_mod.subprocess, "Popen", return_value=_processo()):
        service.disparar(service_mod.RodadaRequest(mcp=["sem"], rodada="r9"))
        for _ in range(100):
            if service._gate.owner is None:
                break
            time.sleep(0.02)
    log = (resultados / PASTA_LOGS / "r9.log").read_text(encoding="utf-8")
    assert log.startswith("log removido")
    assert service._disparo("r9")["log_bloqueado"] is True
