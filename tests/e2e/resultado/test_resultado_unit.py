"""Formato de resultado: modelos, armazenamento atômico, schemas versionados e JUnit."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path

import jsonschema
import pytest

from tests.e2e.resultado import armazenamento
from tests.e2e.resultado.armazenamento import (
    caminho_execucao,
    gravar_manifesto,
    gravar_registro,
    ler_manifesto,
    ler_registros,
)
from tests.e2e.resultado.junit import escrever_junit
from tests.e2e.resultado.modelos import (
    ChamadaTool,
    Manifesto,
    Registro,
    VersaoDesconhecida,
)


def _registro(**mudancas: object) -> Registro:
    base = Registro(
        rodada="r1",
        conjunto="tools",
        caso="docs-list-all",
        agente="claude",
        config="padrao",
        repeticao=1,
        estado="passou",
        motivo="",
        tools=(
            ChamadaTool("docs_list", True, 0.5),
            ChamadaTool("docs_read", None, None),
        ),
        duracao_s=12.5,
    )
    return replace(base, **mudancas)


def _manifesto() -> Manifesto:
    return Manifesto(
        rodada="r1",
        criado_em="2026-01-01T00:00:00Z",
        configs=("padrao", "sem-docs"),
        conjuntos=("deterministica", "tools"),
        agentes=("claude", "kiro"),
        repeticoes=3,
        flags={"completa": True},
        versoes={
            "mcp:padrao": "1.0.0",
            "mcp:sem-docs": "1.0.0",
            "novomodelo": "1.0.0",
            "novomodelo-bridge": "1.0.0",
            "claude-code": "1.0.0",
            "kiro-cli": "1.0.0",
            "juiz-modelo": "modelo-falso",
            "juiz-temperatura": "0",
        },
        commit_bateria="abc1234",
    )


def test_registro_ida_e_volta(tmp_path: Path) -> None:
    r = _registro()
    caminho = gravar_registro(tmp_path, r)
    assert caminho == caminho_execucao(tmp_path, r) / "registro.json"
    assert caminho_execucao(tmp_path, r) == (
        tmp_path / "execucoes" / "tools" / "docs-list-all" / "claude" / "padrao" / "1"
    )
    assert ler_registros(tmp_path) == [r]


def test_manifesto_ida_e_volta(tmp_path: Path) -> None:
    m = _manifesto()
    assert gravar_manifesto(tmp_path, m) == tmp_path / "manifesto.json"
    assert ler_manifesto(tmp_path) == m


def test_ler_recusa_versao_desconhecida(tmp_path: Path) -> None:
    gravar_manifesto(tmp_path, _manifesto())
    gravar_registro(tmp_path, _registro())
    for arquivo in (
        tmp_path / "manifesto.json",
        caminho_execucao(tmp_path, _registro()) / "registro.json",
    ):
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
        dados["schema_versao"] = 2
        arquivo.write_text(json.dumps(dados), encoding="utf-8")
    with pytest.raises(VersaoDesconhecida):
        ler_manifesto(tmp_path)
    with pytest.raises(VersaoDesconhecida):
        ler_registros(tmp_path)


def test_registro_invalido_pelo_schema(tmp_path: Path) -> None:
    with pytest.raises(jsonschema.ValidationError):
        gravar_registro(tmp_path, _registro(estado="ok"))
    assert not list(tmp_path.rglob("registro.json"))


def test_ler_ignora_execucao_sem_registro(tmp_path: Path) -> None:
    gravar_registro(tmp_path, _registro())
    (tmp_path / "execucoes" / "tools" / "outro" / "claude" / "padrao" / "1").mkdir(parents=True)
    assert len(ler_registros(tmp_path)) == 1


def test_gravacao_atomica_nao_deixa_parcial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def falha(*_args: object, **_kwargs: object) -> None:
        raise OSError("falha simulada")

    monkeypatch.setattr(armazenamento.os, "replace", falha)
    r = _registro()
    with pytest.raises(OSError, match="falha simulada"):
        gravar_registro(tmp_path, r)
    assert not list(tmp_path.rglob("registro.json"))
    assert list(caminho_execucao(tmp_path, r).iterdir()) == []


def test_gravacao_substitui_registro_existente(tmp_path: Path) -> None:
    gravar_registro(tmp_path, _registro(estado="falhou", motivo="x"))
    gravar_registro(tmp_path, _registro())
    assert [r.estado for r in ler_registros(tmp_path)] == ["passou"]


def test_junit_mapeia_os_quatro_estados(tmp_path: Path) -> None:
    registros = [
        _registro(caso="a", estado="passou"),
        _registro(caso="b", estado="falhou", motivo="resposta errada"),
        _registro(caso="c", estado="erro_infra", motivo="container caiu"),
        _registro(caso="d", estado="pulado", motivo="sem rede", repeticao=2),
    ]
    destino = escrever_junit(registros, tmp_path / "junit.xml")
    casos = ET.parse(destino).getroot().findall(".//testcase")
    assert [c.get("name") for c in casos] == ["a[1]", "b[1]", "c[1]", "d[2]"]
    assert {c.get("classname") for c in casos} == {"tools.claude.padrao"}
    filhos = [[f.tag for f in c] for c in casos]
    assert filhos == [[], ["failure"], ["error"], ["skipped"]]
    assert casos[1].find("failure").get("message") == "resposta errada"
