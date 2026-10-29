"""Gravação atômica e leitura validada de manifestos e registros."""

from __future__ import annotations

import json
import os
import re
import tempfile
from importlib import resources
from pathlib import Path
from typing import Any

import jsonschema

from novomodelo_mcp_e2e.resultado.modelos import (
    SCHEMA_VERSAO,
    Manifesto,
    Registro,
    VersaoDesconhecida,
)

NOME_MANIFESTO = "manifesto.json"
NOME_REGISTRO = "registro.json"
NOME_DECISAO = "decisao-go-no-go.json"
PADRAO_NOME = r"^(?!\.{1,2}(?![\s\S]))[A-Za-z0-9._-]+(?![\s\S])"


def _schema(nome: str) -> dict[str, Any]:
    texto = (
        resources.files("novomodelo_mcp_e2e.resultado")
        .joinpath("schemas", f"{nome}.schema.json")
        .read_text(encoding="utf-8")
    )
    return json.loads(texto)


def _validar(dados: dict[str, Any], nome: str) -> None:
    jsonschema.Draft202012Validator(_schema(nome)).validate(dados)


def _checar_versao(dados: dict[str, Any], arquivo: Path) -> None:
    versao = dados.get("schema_versao")
    if versao != SCHEMA_VERSAO:
        raise VersaoDesconhecida(
            f"{arquivo}: schema_versao {versao!r}, este leitor conhece {SCHEMA_VERSAO}"
        )


def _gravar_json(destino: Path, dados: dict[str, Any]) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    fd, temporario = tempfile.mkstemp(dir=destino.parent, prefix=f".{destino.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporario, destino)
    except BaseException:
        Path(temporario).unlink(missing_ok=True)
        raise
    return destino


def _ler_json(arquivo: Path) -> dict[str, Any]:
    """O objeto JSON do arquivo.

    Raises:
        ValueError: JSON inválido ou com raiz que não é objeto.
    """
    dados = json.loads(arquivo.read_text(encoding="utf-8"))
    if not isinstance(dados, dict):
        raise ValueError(f"{arquivo.name}: a raiz do JSON não é um objeto")
    return dados


def gravar_manifesto(pasta: Path, m: Manifesto) -> Path:
    dados = m.para_dict()
    _validar(dados, "manifesto")
    return _gravar_json(pasta / NOME_MANIFESTO, dados)


def ler_manifesto(pasta: Path) -> Manifesto:
    arquivo = pasta / NOME_MANIFESTO
    dados = _ler_json(arquivo)
    _checar_versao(dados, arquivo)
    _validar(dados, "manifesto")
    return Manifesto.de_dict(dados)


def caminho_execucao(pasta: Path, r: Registro) -> Path:
    for rotulo, valor in (("caso", r.caso), ("agente", r.agente), ("config", r.config)):
        if not re.search(PADRAO_NOME, valor):
            raise ValueError(f"{rotulo} {valor!r} não casa com {PADRAO_NOME}")
    return pasta / "execucoes" / r.conjunto / r.caso / r.agente / r.config / str(r.repeticao)


def gravar_registro(pasta: Path, r: Registro) -> Path:
    dados = r.para_dict()
    _validar(dados, "registro")
    return _gravar_json(caminho_execucao(pasta, r) / NOME_REGISTRO, dados)


def ler_registros(pasta: Path) -> list[Registro]:
    registros = []
    for arquivo in sorted((pasta / "execucoes").glob(f"*/*/*/*/*/{NOME_REGISTRO}")):
        dados = _ler_json(arquivo)
        _checar_versao(dados, arquivo)
        _validar(dados, "registro")
        registros.append(Registro.de_dict(dados))
    return registros


def gravar_decisao(pasta: Path, dados: dict[str, Any]) -> Path:
    """Grava a decisão do go-no-go depois de validá-la contra o schema."""
    dados = json.loads(json.dumps(dados))
    _validar(dados, "decisao")
    return _gravar_json(pasta / NOME_DECISAO, dados)


def ler_decisao(pasta: Path) -> dict[str, Any] | None:
    """A decisão gravada na rodada; `None` se o go-no-go ainda não rodou."""
    arquivo = pasta / NOME_DECISAO
    if not arquivo.is_file():
        return None
    dados = _ler_json(arquivo)
    _checar_versao(dados, arquivo)
    _validar(dados, "decisao")
    return dados
