"""Formato de resultado: modelos, armazenamento atômico, schemas versionados e JUnit."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import fields, replace
from pathlib import Path
from typing import get_args

import jsonschema
import pytest

from tests.e2e.resultado import armazenamento
from tests.e2e.resultado.armazenamento import (
    PADRAO_NOME,
    caminho_execucao,
    gravar_manifesto,
    gravar_registro,
    ler_manifesto,
    ler_registros,
)
from tests.e2e.resultado.junit import escrever_junit
from tests.e2e.resultado.modelos import (
    SCHEMA_VERSAO,
    ChamadaTool,
    Conjunto,
    Estado,
    Manifesto,
    Metricas,
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


@pytest.mark.parametrize("nome", ["../x", "/etc", "a/b", "a\\b", "..", ".", "", "a\n"])
@pytest.mark.parametrize("campo", ["caso", "agente", "config"])
def test_caminho_execucao_recusa_nome_que_escapa(tmp_path: Path, campo: str, nome: str) -> None:
    with pytest.raises(ValueError, match=campo):
        caminho_execucao(tmp_path, _registro(**{campo: nome}))
    assert not list(tmp_path.iterdir())


def test_deterministica_com_hifen_passa(tmp_path: Path) -> None:
    r = _registro(conjunto="deterministica", agente="-", config="-")
    gravar_registro(tmp_path, r)
    assert ler_registros(tmp_path) == [r]


@pytest.mark.parametrize("campo", ["caso", "agente", "config"])
@pytest.mark.parametrize("nome", ["a/b", "..", "", "a\\b", "a\n"])
def test_schema_recusa_nome_invalido(campo: str, nome: str) -> None:
    dados = _registro().para_dict()
    dados[campo] = nome
    schema = json.loads(
        (Path(__file__).parent / "schemas" / "registro.schema.json").read_text(encoding="utf-8")
    )
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(dados)


def test_junit_motivo_com_caractere_de_controle_gera_xml_valido(tmp_path: Path) -> None:
    r = _registro(estado="falhou", motivo="saida\x00ruim\x1b[0m fim")
    destino = escrever_junit([r], tmp_path / "junit.xml")
    falha = ET.parse(destino).getroot().find(".//failure")
    assert falha is not None
    assert "\x00" not in falha.get("message")


def test_schema_versao_bate_com_os_schemas() -> None:
    pasta = Path(__file__).parent / "schemas"
    for nome in ("registro", "manifesto"):
        schema = json.loads((pasta / f"{nome}.schema.json").read_text(encoding="utf-8"))
        assert schema["properties"]["schema_versao"]["const"] == SCHEMA_VERSAO


def test_padrao_de_nome_igual_no_schema_e_no_codigo() -> None:
    schema = json.loads(
        (Path(__file__).parent / "schemas" / "registro.schema.json").read_text(encoding="utf-8")
    )
    for campo in ("caso", "agente", "config"):
        assert schema["properties"][campo]["pattern"] == PADRAO_NOME


_METRICAS = Metricas(
    acerto_tool=True,
    contornos=1,
    aprovacoes=2,
    rigidez=0,
    erros_envelope=1,
    t_primeira_tool=3.5,
    t_total=12.5,
    tokens_entrada=1200,
    tokens_saida=300,
    resposta_correta=False,
    interrupcoes=2,
    t_primeira_interrupcao=10.0,
    maior_trecho_sem_interrupcao=42.5,
    indice_autonomia=0.75,
    comandos_terminal=4,
    nota_juiz=2,
)


def test_registro_com_metricas_ida_e_volta(tmp_path: Path) -> None:
    r = _registro(metricas=_METRICAS)
    gravar_registro(tmp_path, r)
    assert ler_registros(tmp_path) == [r]
    gravado = json.loads((caminho_execucao(tmp_path, r) / "registro.json").read_text("utf-8"))
    assert gravado["metricas"]["nota_juiz"] == 2


def test_registro_sem_metricas_e_valido_com_tudo_nulo(tmp_path: Path) -> None:
    r = _registro()
    assert r.metricas == Metricas()
    gravar_registro(tmp_path, r)
    gravado = json.loads((caminho_execucao(tmp_path, r) / "registro.json").read_text("utf-8"))
    assert set(gravado["metricas"].values()) == {None}
    assert ler_registros(tmp_path) == [r]


@pytest.mark.parametrize(
    "mudanca",
    [
        {"nota_juiz": 3},
        {"nota_juiz": -1},
        {"indice_autonomia": 1.5},
        {"tokens_entrada": -1},
        {"t_total": -0.5},
        {"campo_desconhecido": 1},
    ],
)
def test_schema_recusa_metricas_invalidas(tmp_path: Path, mudanca: dict) -> None:
    dados = _registro(metricas=_METRICAS).para_dict()
    dados["metricas"].update(mudanca)
    with pytest.raises(jsonschema.ValidationError):
        armazenamento._validar(dados, "registro")


def test_schema_exige_metricas_no_json_gravado() -> None:
    dados = _registro().para_dict()
    del dados["metricas"]
    with pytest.raises(jsonschema.ValidationError):
        armazenamento._validar(dados, "registro")


def _decisao() -> dict:
    return {
        "schema_versao": 1,
        "alvo": "mcp",
        "base": None,
        "veredito": "go",
        "bloqueios": [],
        "inconclusivos": [],
        "pulados": [],
        "sem_base": [],
        "ausentes": [],
    }


def test_decisao_ida_e_volta_e_sem_arquivo_e_none(tmp_path: Path) -> None:
    from tests.e2e.resultado.armazenamento import gravar_decisao, ler_decisao

    assert ler_decisao(tmp_path) is None
    gravar_decisao(tmp_path, _decisao())
    assert ler_decisao(tmp_path) == _decisao()


def test_decisao_recusa_schema_invalido_e_versao_desconhecida(tmp_path: Path) -> None:
    from tests.e2e.resultado.armazenamento import gravar_decisao, ler_decisao
    from tests.e2e.resultado.modelos import VersaoDesconhecida

    with pytest.raises(jsonschema.ValidationError):
        gravar_decisao(tmp_path, {**_decisao(), "veredito": "talvez"})
    (tmp_path / "decisao-go-no-go.json").write_text(
        json.dumps({**_decisao(), "schema_versao": 2}), encoding="utf-8"
    )
    with pytest.raises(VersaoDesconhecida):
        ler_decisao(tmp_path)


def _schema(nome: str) -> dict:
    return json.loads(
        (Path(armazenamento.__file__).parent / "schemas" / f"{nome}.schema.json").read_text(
            encoding="utf-8"
        )
    )


def _campos(classe) -> list[str]:
    return sorted(f.name for f in fields(classe))


@pytest.mark.parametrize(
    "classe, caminho",
    [
        (Registro, ("registro",)),
        (ChamadaTool, ("registro", "tools", "items")),
        (Metricas, ("registro", "metricas")),
        (Manifesto, ("manifesto",)),
    ],
)
def test_campos_das_dataclasses_sao_os_do_schema(classe, caminho):
    no = _schema(caminho[0])
    for chave in caminho[1:]:
        no = no["properties"][chave] if chave != "items" else no["items"]
    assert _campos(classe) == sorted(no["properties"])
    assert _campos(classe) == sorted(no["required"])
    assert no["additionalProperties"] is False


def test_enums_dos_modelos_sao_os_do_schema():
    registro = _schema("registro")["properties"]
    assert list(get_args(Estado)) == registro["estado"]["enum"]
    assert list(get_args(Conjunto)) == registro["conjunto"]["enum"]
    assert (
        list(get_args(Conjunto)) == _schema("manifesto")["properties"]["conjuntos"]["items"]["enum"]
    )


@pytest.mark.parametrize("raiz", ["[]", '"texto"', "1", "null"])
def test_json_com_raiz_que_nao_e_objeto_vira_value_error(tmp_path, raiz):
    gravar_registro(tmp_path, _registro())
    (tmp_path / "manifesto.json").write_text(raiz, encoding="utf-8")
    with pytest.raises(ValueError, match="raiz do JSON"):
        ler_manifesto(tmp_path)
    [registro] = tmp_path.glob("execucoes/*/*/*/*/*/registro.json")
    registro.write_text(raiz, encoding="utf-8")
    with pytest.raises(ValueError, match="raiz do JSON"):
        ler_registros(tmp_path)
    (tmp_path / armazenamento.NOME_DECISAO).write_text(raiz, encoding="utf-8")
    with pytest.raises(ValueError, match="raiz do JSON"):
        armazenamento.ler_decisao(tmp_path)
