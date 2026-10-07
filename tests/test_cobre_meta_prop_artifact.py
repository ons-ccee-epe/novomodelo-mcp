"""Teste de propriedade da Schema_Export_Tool: destino vira artefato, não conteúdo.

Property 2 do design `schema-export-version-tools`. Toda a suíte é offline: a CLI
`cobre` falsa é alcançada via `COBRE_BIN` (`monkeypatch.setenv`), espelhando o
padrão de `test_cobre_meta.py`. Nenhum teste exige o binário real nem faz
requisição de rede.

A CLI falsa (`fake_cobre.py`) ecoa um envelope `status=ok` com `exit_code` 0 e
nunca embute o conteúdo dos schemas; isso é o que a propriedade exige para
afirmar que o envelope carrega apenas o CAMINHO do destino, não os arquivos.
"""

import os
import stat
import sys
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from cobre_mcp.config import load_settings
from cobre_mcp.tools.cobre_meta import register_cobre_meta

FAKE = Path(__file__).resolve().parent / "fake_cobre.py"

# Chaves que, se presentes no envelope, denunciariam conteúdo de schema embutido
# em vez do caminho do destino (o relé fino registra só o artefato).
_SCHEMA_CONTENT_KEYS = frozenset({"schemas", "schema", "content", "contents", "files"})

# Segmento de caminho seguro: sem separadores, sem `..`, sem vazio; mantém o
# destino confinado sob a raiz temporária gerada em COBRE_MCP_WORKSPACE.
_segment = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_-"),
    min_size=1,
    max_size=12,
).filter(lambda s: s not in (".", ".."))


class _CaptureMCP:
    """`mcp` falso cujo `tool()` captura a função registrada, para chamá-la direto."""

    def __init__(self):
        self.tools = {}

    def tool(self, *args, **kwargs):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


def _schema_export_tool(settings):
    mcp = _CaptureMCP()
    register_cobre_meta(mcp, settings)
    return mcp.tools["cobre_schema_export"]


@pytest.fixture
def fake_cobre_bin(tmp_path):
    """Lançador executável do `cobre` falso, confinado a um diretório temporário.

    Portátil: em Windows gera um `.cmd`; em POSIX, um shell script. Ambos
    repassam o argv ao script falso via o interpretador corrente.
    """
    if os.name == "nt":
        launcher = tmp_path / "cobre.cmd"
        launcher.write_text(f'@"{sys.executable}" "{FAKE}" %*\r\n', encoding="utf-8")
    else:
        launcher = tmp_path / "cobre"
        launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" "$@"\n')
        launcher.chmod(launcher.stat().st_mode | stat.S_IEXEC)
    return str(launcher)


# Feature: schema-export-version-tools, Property 2: Destino de export é registrado como artefato, nunca como conteúdo
# Validates: Requirements 1.7
# deadline=None: cada exemplo gera um subprocesso da CLI falsa; a latência é do spawn
# externo (lenta em `.cmd` no Windows), não do relé sob teste — o prazo mediria o processo.
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(segments=st.lists(_segment, min_size=1, max_size=4))
def test_destination_is_artifact_not_content(monkeypatch, tmp_path, fake_cobre_bin, segments):
    root = tmp_path.resolve()
    monkeypatch.setenv("COBRE_MCP_WORKSPACE", str(root))
    monkeypatch.setenv("COBRE_BIN", fake_cobre_bin)

    output_dir = str(root.joinpath(*segments))
    env = _schema_export_tool(load_settings())(output_dir=output_dir)

    assert env["status"] == "ok"
    assert env["exit_code"] == 0
    assert env.get("artifacts", {}).get("schemas") == output_dir
    assert not (_SCHEMA_CONTENT_KEYS & set(env.keys()))
