"""`sync_bundled`: páginas resolvidas (sem `_impl`), manifesto, índice FTS5 e `--check`."""

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from novomodelo_mcp.adapters import reference as REF

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "sync_bundled.py"
BUNDLED = ROOT / "src" / "novomodelo_mcp" / "_bundled"

PAGINA = """---
title: SDDP Algorithm
description: How training works.
---

import { Tabs, TabItem } from '@astrojs/starlight/components';
import { Content as SddpConfigure } from './_impl/_sddp.configure.mdx';
import ValueFunctionPlot from "../../../components/ValueFunctionPlot.astro";

Intro text about SDDP.

<ValueFunctionPlot />

{/* capture: comentario que nao deve ficar */}

## 3.2 Backward Pass

The backward pass builds cuts.

```python
import polars as pl
# nao e titulo
```

<Tabs>
  <TabItem label="Configure"><SddpConfigure /></TabItem>
</Tabs>

## `training.parallelism`

Other section.
"""

IMPL = """---
title: oculto
---
Scheduler knob lives in `config.json`.

### Scheduler Configuration

Use `by_node`.
"""

INDEX = """---
title: Home
description: Start.
---

<CardGrid>
  <LinkCard
    title="Getting started"
    href="/getting-started/"
    description="Install."
  />
</CardGrid>
"""

GLOSSARY = """---
title: Glossary
description: Terms.
---

## Hydro

| English | Portuguese | Definition |
| ------- | ---------- | ---------- |
| Inflow  | Afluência / Vazão natural | Water arriving. |
| Head    | Queda | Height. |
| Energy contract | - | No PT. |
"""


def _fixture(tmp_path: Path) -> Path:
    src = tmp_path / "docs-repo"
    docs = src / "src" / "content" / "docs"
    (docs / "math" / "_impl").mkdir(parents=True)
    (docs / "reference").mkdir()
    (docs / "pt-br").mkdir()
    (docs / "pt-br" / ".gitkeep").write_text("", encoding="utf-8")
    (docs / "math" / "sddp-algorithm.mdx").write_text(PAGINA, encoding="utf-8")
    (docs / "math" / "_impl" / "_sddp.configure.mdx").write_text(IMPL, encoding="utf-8")
    (docs / "index.mdx").write_text(INDEX, encoding="utf-8")
    (docs / "reference" / "glossary.md").write_text(GLOSSARY, encoding="utf-8")
    (src / "public" / "schemas").mkdir(parents=True)
    (src / "public" / "schemas" / "config.schema.json").write_text(
        '{"type": "object"}', encoding="utf-8"
    )
    (src / "versions.json").write_text(
        json.dumps(
            {"latest": {"label": "latest", "base": "/", "novomodelo": "v0.18.0"}, "versions": []}
        ),
        encoding="utf-8",
    )
    return src


def _sync(src: Path, dest: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--source", str(src), "--dest", str(dest), *extra],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


@pytest.fixture
def synced(tmp_path):
    src, dest = _fixture(tmp_path), tmp_path / "bundled"
    proc = _sync(src, dest)
    assert proc.returncode == 0, proc.stderr
    return src, dest


def test_impl_incluido_no_lugar_do_componente_e_fora_da_lista(synced):
    _, dest = synced
    page = (dest / "docs" / "math" / "sddp-algorithm.mdx").read_text(encoding="utf-8")
    assert "Scheduler knob lives in" in page and "<SddpConfigure" not in page
    assert not (dest / "docs" / "math" / "_impl").exists()
    assert not (dest / "docs" / "pt-br").exists()
    assert "title: SDDP Algorithm" in page


def test_import_em_bloco_de_codigo_fica_e_import_mdx_sai(synced):
    _, dest = synced
    page = (dest / "docs" / "math" / "sddp-algorithm.mdx").read_text(encoding="utf-8")
    assert "import polars as pl" in page
    assert "@astrojs/starlight" not in page and "ValueFunctionPlot" not in page


def test_nenhum_componente_mdx_sobra(synced):
    _, dest = synced
    for p in (dest / "docs").rglob("*.md*"):
        text = p.read_text(encoding="utf-8")
        for tag in ("<Tabs", "<TabItem", "<CardGrid", "<LinkCard", "{/*"):
            assert tag not in text, (p, tag)
    assert "**Configure**" in (dest / "docs" / "math" / "sddp-algorithm.mdx").read_text(
        encoding="utf-8"
    )
    assert "[Getting started](/getting-started/)" in (dest / "docs" / "index.mdx").read_text(
        encoding="utf-8"
    )


def test_manifesto_e_uma_linha_por_secao(synced):
    _, dest = synced
    man = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
    assert man["docs_versao"] == "0.18.0" and man["paginas"] == 3
    assert {"docs_commit", "gerado_em", "secoes"} <= set(man)
    con = sqlite3.connect(dest / "docs_index.sqlite")
    rows = con.execute(
        "SELECT pagina, titulo, ancora FROM secoes WHERE pagina = 'math/sddp-algorithm'"
    ).fetchall()
    assert [r[2] for r in rows] == [
        "",
        "32-backward-pass",
        "scheduler-configuration",
        "trainingparallelism",
    ]
    assert man["secoes"] == con.execute("SELECT count(*) FROM secoes").fetchone()[0]


def test_glossario_no_indice(synced):
    _, dest = synced
    con = sqlite3.connect(dest / "docs_index.sqlite")
    pares = set(con.execute("SELECT pt, en FROM glossario").fetchall())
    assert {("afluencia", "Inflow"), ("vazao natural", "Inflow"), ("queda", "Head")} <= pares
    assert not any(en == "Energy contract" for _, en in pares)


def test_check_igual_sai_zero_e_pagina_mudada_sai_diferente(synced):
    src, dest = synced
    assert _sync(src, dest, "--check").returncode == 0
    page = src / "src" / "content" / "docs" / "math" / "sddp-algorithm.mdx"
    page.write_text(page.read_text(encoding="utf-8") + "\nNovo parágrafo.\n", encoding="utf-8")
    proc = _sync(src, dest, "--check")
    assert proc.returncode != 0 and "sddp-algorithm" in (proc.stdout + proc.stderr)


def test_indice_do_script_e_o_de_memoria_tem_as_mesmas_secoes(synced):
    src, dest = synced
    raw = src / "src" / "content" / "docs"
    script = sqlite3.connect(dest / "docs_index.sqlite")
    memory = REF.build_docs_index(raw, ":memory:")
    query = "SELECT pagina, titulo, ancora FROM secoes ORDER BY pagina, rowid"
    assert script.execute(query).fetchall() == memory.execute(query).fetchall()
    resolved = REF.build_docs_index(dest / "docs", ":memory:")
    assert script.execute(query).fetchall() == resolved.execute(query).fetchall()


def test_slug_no_formato_do_site():
    assert REF.slugify("3.2 Backward Pass") == "32-backward-pass"
    assert (
        REF.slugify("`training.parallelism` — Backward-Pass Scheduler")
        == "trainingparallelism--backward-pass-scheduler"
    )
    assert REF.slugify("2 Conditional Value-at-Risk (CVaR)") == "2-conditional-value-at-risk-cvar"


def test_bundled_do_repositorio_tem_manifesto_e_indice_pequeno():
    man = json.loads((BUNDLED / "manifest.json").read_text(encoding="utf-8"))
    assert man["docs_versao"] and man["docs_commit"]
    assert (BUNDLED / "docs_index.sqlite").stat().st_size < 5 * 1024 * 1024
    assert not (BUNDLED / "docs" / "math" / "_impl").exists()


def test_docs_embutidas_na_versao_do_mcp():
    import novomodelo_mcp

    man = json.loads((BUNDLED / "manifest.json").read_text(encoding="utf-8"))
    menor = lambda v: tuple(v.split(".")[:2])  # noqa: E731
    assert menor(man["docs_versao"]) == menor(novomodelo_mcp.__version__), (
        "docs embutidas de outra versão: rode scripts/sync_bundled.py com as docs da versão do MCP"
    )


def test_docs_embutidas_trazem_a_truncagem_do_larroyd(monkeypatch):
    from novomodelo_mcp.config import load_settings

    monkeypatch.delenv("NOVOMODELO_MCP_DOCS_DIR", raising=False)
    hits = REF.search_docs(load_settings(), "Relation to Larroyd", k=5)
    assert any(
        h["pagina"] == "math/inflow-nonnegativity"
        and h["titulo"].startswith("6.2 Relation to Larroyd")
        for h in hits["resultados"]
    )
