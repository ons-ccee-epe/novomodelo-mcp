"""As notas do release do GitHub saem da seção `## [X.Y.Z]` do CHANGELOG.md, e o
release.yml as confere antes de publicar."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "notas_da_release.py"

_spec = importlib.util.spec_from_file_location("sync_bundled", ROOT / "scripts" / "sync_bundled.py")
assert _spec and _spec.loader
sync_bundled = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sync_bundled)

CHANGELOG = """# Changelog

Texto de abertura.

## [Unreleased]

### Fixed

- Ainda não saiu.

## [0.21.0] - 2026-11-20

### Changed

#### Teto das respostas

- **BREAKING:** as tabelas do bridge cabem no teto.

### Fixed

- O `docs_read` abre o link.

## [0.20.0] - 2026-11-04

### Changed

- Da versão anterior.
"""


def _notas(tmp_path, versao, texto=CHANGELOG):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(texto, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(SCRIPT), versao, "--changelog", str(changelog)],
        capture_output=True,
        encoding="utf-8",
        timeout=60,
    )


def test_notas_sao_a_instalacao_e_a_secao_da_versao(tmp_path):
    r = _notas(tmp_path, "0.21.0")
    assert r.returncode == 0, r.stderr
    instalacao, secao = r.stdout.split("\n\n", 1)
    assert "uv tool install novomodelo-mcp==0.21.0" in instalacao
    assert secao.strip() == (
        "### Changed\n\n#### Teto das respostas\n\n"
        "- **BREAKING:** as tabelas do bridge cabem no teto.\n\n"
        "### Fixed\n\n- O `docs_read` abre o link."
    )


@pytest.mark.parametrize(
    ("versao", "texto"),
    [
        ("0.22.0", CHANGELOG),
        ("0.21.0", "## [0.21.0] - 2026-11-20\n\n## [0.20.0] - 2026-11-04\n\n- x\n"),
    ],
    ids=["sem a secao", "secao vazia"],
)
def test_sem_mudancas_da_versao_nao_ha_notas(tmp_path, versao, texto):
    r = _notas(tmp_path, versao, texto)
    assert r.returncode == 1 and r.stdout == "" and f"## [{versao}]" in r.stderr


def test_o_changelog_do_repositorio_da_as_notas_da_versao_mais_recente():
    texto = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    versao = sync_bundled.changelog_versions(texto, "0.0.0")[0]
    r = subprocess.run(
        [sys.executable, str(SCRIPT), versao],
        capture_output=True,
        encoding="utf-8",
        timeout=60,
    )
    assert r.returncode == 0, r.stderr
    assert sync_bundled.version_section(texto, versao) in r.stdout


def test_release_confere_as_notas_antes_do_pypi_e_publica_com_elas():
    texto = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    build = texto.split("\n  build:", 1)[1].split("\n  instalacao:", 1)[0]
    publicar = texto.split("\n  publicar:", 1)[1]
    assert "scripts/notas_da_release.py" in build
    assert "--notes-file" in publicar and "--notes " not in publicar
