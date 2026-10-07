"""Teste de propriedade da guarda de workspace fail-closed na Schema_Export_Tool.

Offline: a CLI `cobre` falsa é alcançada via `COBRE_BIN` (`monkeypatch.setenv`),
espelhando `test_cobre_meta.py` e `test_adapters.py`. Nenhum teste exige o
binário real nem faz requisição de rede; todo acesso ao FS fica em diretórios
temporários.

Reutiliza o padrão `_CaptureMCP` e o lançador `fake_cobre_bin` de
`test_cobre_meta.py`: a tool registrada é uma função Python comum, invocada como
o servidor faria após o despacho stdio.
"""

import os
import stat
import sys
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

import cobre_mcp.tools.cobre_meta as cobre_meta
from cobre_mcp.config import load_settings
from cobre_mcp.tools.cobre_meta import register_cobre_meta

FAKE = Path(__file__).resolve().parent / "fake_cobre.py"

# Segmentos de caminho sem separadores, `..`, `.` ou NUL: a propriedade exercita
# a decisão da guarda sobre o caminho resolvido, não a travessia por `..` (o
# `resolve()` já a neutraliza e é coberto à parte).
_SEGMENT = st.text(
    alphabet=st.characters(min_codepoint=0x61, max_codepoint=0x7A),
    min_size=1,
    max_size=8,
)
_SEGMENTS = st.lists(_SEGMENT, min_size=1, max_size=4)


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


def _write_launcher(tmp_path: Path) -> str:
    """Lançador executável do `cobre` falso, confinado a um diretório temporário."""
    if os.name == "nt":
        launcher = tmp_path / "cobre.cmd"
        launcher.write_text(f'@"{sys.executable}" "{FAKE}" %*\r\n', encoding="utf-8")
    else:
        launcher = tmp_path / "cobre"
        launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" "$@"\n')
        launcher.chmod(launcher.stat().st_mode | stat.S_IEXEC)
    return str(launcher)


@pytest.fixture
def fake_cobre_bin(tmp_path):
    """Lançador do `cobre` falso a apontar em `COBRE_BIN` (ver `test_cobre_meta.py`)."""
    return _write_launcher(tmp_path)


# Feature: schema-export-version-tools, Property 1: Guarda de workspace é fail-closed na Schema_Export_Tool
@settings(max_examples=200, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(inside=_SEGMENTS, outside=_SEGMENTS)
def test_workspace_guard_is_fail_closed(monkeypatch, tmp_path_factory, inside, outside):
    """Dentro de R ⇒ aceito (prossegue à CLI); fora de R ⇒ recusa com 13 sem tocar o FS.

    O transporte `run_cobre` é substituído por um sentinela que apenas registra
    que foi alcançado: prova "aceito = prossegue para a CLI" para 200 inputs sem
    pagar o custo de iniciar o interpretador por exemplo. O caminho fim-a-fim até
    a CLI `cobre` falsa real é coberto por `test_guard_accept_reaches_fake_cli`.

    Validates: Requirements 1.6, 5.2
    """
    base = tmp_path_factory.mktemp("guard")
    root = base / "workspace"
    root.mkdir()
    monkeypatch.setenv("COBRE_MCP_WORKSPACE", str(root))

    reached: list[list[str]] = []

    def spy_run_cobre(subargv, **kwargs):
        reached.append(subargv)
        return {"status": "ok", "exit_code": 0}

    monkeypatch.setattr(cobre_meta, "run_cobre", spy_run_cobre)
    tool = _schema_export_tool(load_settings())

    inside_dir = str(root.joinpath(*inside))
    env_in = tool(output_dir=inside_dir)
    assert env_in["status"] == "ok"
    assert env_in["exit_code"] == 0
    assert env_in["artifacts"]["schemas"] == inside_dir
    assert reached and reached[-1][:2] == ["schema", "export"]

    outside_dir = str(base.joinpath("outside", *outside))
    # O destino fora de R não existe em disco: provar a recusa sem acesso ao FS.
    assert not Path(outside_dir).exists()
    before = len(reached)
    env_out = tool(output_dir=outside_dir)
    assert env_out["status"] == "error"
    assert env_out["exit_code"] == 13
    # A recusa precede qualquer transporte: a CLI nunca é alcançada.
    assert len(reached) == before


def test_guard_accept_reaches_fake_cli(monkeypatch, tmp_path, fake_cobre_bin):
    """Caminho dentro do workspace alcança a CLI `cobre` falsa real via `COBRE_BIN`.

    Validates: Requirements 1.6, 5.2
    """
    root = tmp_path / "workspace"
    root.mkdir()
    monkeypatch.setenv("COBRE_MCP_WORKSPACE", str(root))
    monkeypatch.setenv("COBRE_BIN", fake_cobre_bin)

    inside_dir = str(root / "schemas")
    env = _schema_export_tool(load_settings())(output_dir=inside_dir)
    assert env["status"] == "ok"
    assert env["exit_code"] == 0
    assert env["artifacts"]["schemas"] == inside_dir
    non_flag = [a for a in env["argv"] if not a.startswith("--")]
    assert non_flag[:2] == ["schema", "export"]


def test_guard_refuses_outside_before_reaching_fake_cli(monkeypatch, tmp_path, fake_cobre_bin):
    """Caminho fora do workspace é recusado com 13 antes de alcançar a CLI falsa.

    Validates: Requirements 1.6, 5.2
    """
    root = tmp_path / "workspace"
    root.mkdir()
    monkeypatch.setenv("COBRE_MCP_WORKSPACE", str(root))
    monkeypatch.setenv("COBRE_BIN", fake_cobre_bin)

    outside_dir = str(tmp_path / "outside" / "schemas")
    assert not Path(outside_dir).exists()
    env = _schema_export_tool(load_settings())(output_dir=outside_dir)
    assert env["status"] == "error"
    assert env["exit_code"] == 13
    assert "argv" not in env


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
