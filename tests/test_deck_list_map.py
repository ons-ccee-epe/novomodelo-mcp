"""`deck_list` como mapa do caso: entradas listadas, rodadas resumidas, teto.

Motivação (12/out): num caso real com 2 000 cenários, a versão antiga listava
18 053 arquivos (≈5,5 MB de resposta); só 28 eram o deck.
"""
import json

from novomodelo_mcp.adapters.deck_io import case_map

TYPES = {"config", "hydros", "stages"}


def _make_case(root, n_scenarios=50):
    (root / "system").mkdir(parents=True)
    (root / "config.json").write_text("{}")
    (root / "config.json.bak").write_text("{}")
    (root / "stages.json").write_text("{}")
    (root / "system" / "hydros.json").write_text("{}")
    (root / "scenarios").mkdir()
    (root / "scenarios" / "inflow_history.parquet").write_bytes(b"x")
    (root / "dashboard.html").write_text("<html/>")
    out = root / "output_variante"          # nome qualquer: o contrato é training/metadata.json
    (out / "training").mkdir(parents=True)
    (out / "training" / "metadata.json").write_text("{}")
    (out / "training" / "_SUCCESS").write_text("")
    for s in range(n_scenarios):
        part = out / "simulation" / "hydros" / f"scenario_id={s}"
        part.mkdir(parents=True)
        (part / "data.parquet").write_bytes(b"x")


def test_entradas_listadas_e_rodada_resumida(tmp_path):
    _make_case(tmp_path)
    m = case_map(str(tmp_path), TYPES, max_files=500)
    rels = {f["rel"] for f in m["files"]}
    assert rels == {"config.json", "stages.json", "system/hydros.json",
                    "scenarios/inflow_history.parquet"}
    assert {f["rel"]: f.get("schema") for f in m["files"]}["system/hydros.json"] == "hydros"
    assert len(m["runs"]) == 1
    run = m["runs"][0]
    assert run["rel"] == "output_variante"
    assert run["files"] == 50 + 2
    assert run["milestones"] == {"training": True, "simulation": False}
    assert run["simulation_entities"] == ["hydros"]
    assert set(m["others"]) == {"config.json.bak", "dashboard.html"}


def test_resposta_nao_cresce_com_os_cenarios(tmp_path):
    small, big = tmp_path / "pequeno", tmp_path / "grande"
    _make_case(small, n_scenarios=5)
    _make_case(big, n_scenarios=500)
    size = lambda p: len(json.dumps(case_map(str(p), TYPES, 500)))  # noqa: E731
    assert size(big) < size(small) * 1.2


def test_teto_de_entradas(tmp_path):
    _make_case(tmp_path)
    m = case_map(str(tmp_path), TYPES, max_files=2)
    assert len(m["files"]) == 2 and m["count"] == 4
    assert m["files_truncated"] is True


def test_pasta_da_propria_rodada(tmp_path):
    _make_case(tmp_path)
    m = case_map(str(tmp_path / "output_variante"), TYPES, max_files=500)
    assert m["files"] == [] and len(m["runs"]) == 1 and m["runs"][0]["rel"] == "."
