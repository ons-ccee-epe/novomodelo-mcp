"""Changelogs do novomodelo e do bridge nas docs embutidas, lidos por seção de versão."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from novomodelo_mcp.adapters import reference as REF

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "sync_bundled.py"
BUNDLED = ROOT / "src" / "novomodelo_mcp" / "_bundled"

_spec = importlib.util.spec_from_file_location("sync_bundled", SCRIPT)
assert _spec is not None and _spec.loader is not None
SB = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(SB)

ANTIGO = bytes.fromhex("436f627265").decode()

CHANGELOG = f"""# Changelog

All notable changes are documented here.

## [Unreleased]

## [0.19.0] - 2026-10-20

### Changed

- **BREAKING:** the default cut selection is `level1`.
- `truncation` no longer produces an infeasible LP.

### Fixed

- A resumed run places its cuts at their slot.

## [0.18.0] - 2026-10-07

First release under the new name.

## [{ANTIGO} 0.18.0] - 2026-10-07

### Added

- Old history.

## [0.17.0] - 2026-10-01

- Older.
"""


def _clone(tmp_path: Path, nome: str, texto: str = CHANGELOG) -> Path:
    repo = tmp_path / nome
    repo.mkdir()
    (repo / "CHANGELOG.md").write_text(texto, encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", "add", "."],
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "commit",
            "-q",
            "-m",
            "x",
        ],
        check=True,
    )
    return repo


def _docs(tmp_path: Path) -> Path:
    src = tmp_path / "docs-repo"
    if src.exists():
        return src
    docs = src / "src" / "content" / "docs"
    docs.mkdir(parents=True)
    (docs / "index.mdx").write_text(
        "---\ntitle: Home\n---\n\n## Start\n\nText.\n", encoding="utf-8"
    )
    (src / "public" / "schemas").mkdir(parents=True)
    (src / "versions.json").write_text(
        json.dumps({"latest": {"novomodelo": "v0.19.0"}}), encoding="utf-8"
    )
    return src


def _sync(tmp_path: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--source",
            str(_docs(tmp_path)),
            "--dest",
            str(tmp_path / "bundled"),
            *extra,
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


def test_pagina_so_da_0_18_em_diante():
    pagina = SB.changelog_page("novomodelo", CHANGELOG)
    assert [s["title"] for s in REF.section_list(pagina)] == [
        "0.19.0",
        "Changed",
        "Fixed",
        "0.18.0",
    ]
    assert ANTIGO not in pagina and "Unreleased" not in pagina and "0.17.0" not in pagina


def _secao_0_19_0() -> dict[str, Any]:
    sec = REF.find_section(SB.changelog_page("novomodelo", CHANGELOG), "0.19.0")
    assert sec is not None
    return sec


def test_secao_pela_versao():
    sec = _secao_0_19_0()
    assert sec["text"].startswith("## 0.19.0\n\nReleased 2026-10-20.")
    assert "0.18.0" not in sec["text"]


def test_corpo_preservado():
    sec = _secao_0_19_0()["text"]
    assert "### Changed\n\n- **BREAKING:** the default cut selection is `level1`." in sec
    assert "### Fixed\n\n- A resumed run places its cuts at their slot." in sec


def test_sync_com_changelog_grava_manifesto_e_indice(tmp_path):
    nm = _clone(tmp_path, "nm")
    proc = _sync(tmp_path, "--changelog", f"novomodelo={nm}")
    assert proc.returncode == 0, proc.stderr
    dest = tmp_path / "bundled"
    assert (dest / "docs" / "changelog" / "novomodelo.mdx").is_file()
    manifest = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
    entrada = manifest["changelogs"]["novomodelo"]
    assert entrada["versoes"] == ["0.19.0", "0.18.0"] and len(entrada["commit"]) == 40
    con = REF.sqlite3.connect(str(dest / "docs_index.sqlite"))
    paginas = {r[0] for r in con.execute("SELECT pagina FROM changelog")}
    assert paginas == {"changelog/novomodelo"}
    assert not con.execute("SELECT 1 FROM secoes WHERE pagina LIKE 'changelog/%'").fetchone()


def test_check_com_changelog_mudado_diverge(tmp_path):
    nm = _clone(tmp_path, "nm")
    assert _sync(tmp_path, "--changelog", f"novomodelo={nm}").returncode == 0
    (nm / "CHANGELOG.md").write_text(CHANGELOG.replace("infeasible", "unbounded"), encoding="utf-8")
    proc = _sync(tmp_path, "--changelog", f"novomodelo={nm}", "--check")
    assert proc.returncode == 1 and "changelog/novomodelo.mdx" in proc.stdout


def test_produto_desconhecido_e_recusado(tmp_path):
    proc = _sync(tmp_path, "--changelog", f"outro={tmp_path}")
    assert proc.returncode == 2


@pytest.mark.parametrize("produto", ["novomodelo", "novomodelo-bridge"])
def test_cada_secao_cabe_no_teto(produto):
    texto = (BUNDLED / "docs" / "changelog" / f"{produto}.mdx").read_text(encoding="utf-8")
    secoes = [s for s in REF.split_sections(f"changelog/{produto}", texto)]
    assert secoes
    for s in secoes:
        assert len(s["texto"].encode("utf-8")) <= 50 * 1024, s["titulo"]


def test_instrucoes_apontam_o_changelog():
    from novomodelo_mcp.server import SERVER_INSTRUCTIONS

    assert "`changelog/novomodelo`" in SERVER_INSTRUCTIONS
    assert "`changelog/novomodelo-bridge`" in SERVER_INSTRUCTIONS
    assert 'docs_read(page, "<versão>")' in SERVER_INSTRUCTIONS


def _busca(consulta: str, k: int = 10) -> list[str]:
    from novomodelo_mcp.config import load_settings

    return [h["page"] for h in REF.search_docs(load_settings(), consulta, k)["results"]]


@pytest.mark.parametrize(
    "consulta", ["inflow non-negativity", "negative inflow", "CVaR", "cut selection level1"]
)
def test_busca_sem_intencao_de_versao_nao_traz_changelog(consulta):
    assert not [p for p in _busca(consulta) if p.startswith("changelog/")]


@pytest.mark.parametrize(
    "consulta", ["what changed in 0.19.0", "changelog cut selection", "breaking changes release"]
)
def test_busca_sobre_versao_traz_changelog(consulta):
    assert any(p.startswith("changelog/") for p in _busca(consulta, 5))


@pytest.mark.parametrize(
    "workflow", sorted((ROOT / ".github" / "workflows").glob("*.yml")), ids=lambda p: p.name
)
def test_conferencia_das_docs_nos_workflows_passa_os_changelogs(workflow):
    """Um `sync_bundled --check` sem os changelogs do manifesto acusa as páginas como sobra."""
    produtos = json.loads((BUNDLED / "manifest.json").read_text(encoding="utf-8"))["changelogs"]
    texto = workflow.read_text(encoding="utf-8")
    for chamada in texto.split("sync_bundled.py")[1:]:
        trecho = chamada.split("\n\n", 1)[0]
        if "--check" not in trecho:
            continue
        for produto in produtos:
            assert f"--changelog {produto}=" in trecho, (
                f"{workflow.name}: falta --changelog {produto}"
            )
