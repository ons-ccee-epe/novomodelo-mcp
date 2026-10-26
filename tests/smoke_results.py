#!/usr/bin/env python3
"""Smoke test das leituras de resultado (stdlib puro; partes com Parquet ficam
para o ambiente com Polars). Roda: python3 tests/smoke_results.py"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from novomodelo_mcp.adapters import results as R  # noqa: E402


def test_read_metadata_ok():
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "output"
        (out / "training").mkdir(parents=True)
        (out / "training" / "metadata.json").write_text(json.dumps({
            "status": "complete",
            "bounds": {"final_lower_bound": 1.0, "final_upper_bound": 1.1},
            "convergence": {"achieved": True, "final_gap_percent": 0.9},
        }), encoding="utf-8")
        env = R.read_metadata(str(out))
        assert env["status"] == "ok", env
        assert env["simulation_ran"] is False, env
        assert env["training"]["status"] == "complete", env


def test_read_metadata_missing():
    with tempfile.TemporaryDirectory() as d:
        env = R.read_metadata(d)
        assert env["status"] == "error", env


def _rodada(pasta):
    (pasta / "training").mkdir(parents=True)
    (pasta / "training" / "metadata.json").write_text(
        json.dumps({"status": "complete"}), encoding="utf-8")
    return pasta


def _caso_com_rodada(d):
    caso = Path(d) / "caso"
    _rodada(caso / "output")
    return caso


def test_pasta_do_caso_e_recusada_apontando_a_rodada():
    with tempfile.TemporaryDirectory() as d:
        caso = _caso_com_rodada(d)
        env = R.read_metadata(str(caso))
        assert env["status"] == "error" and env["exit_code"] == 2, env
        assert env["output_sugerido"] == str(caso / "output"), env


def test_rodada_com_qualquer_nome_e_mais_funda_e_achada():
    with tempfile.TemporaryDirectory() as d:
        rodada = _rodada(Path(d) / "estudo" / "caso-a" / "rodadas" / "teste 1")
        env = R.folder_above_runs(str(Path(d) / "estudo"))
        assert env["output_sugerido"] == str(rodada), env


def test_varias_rodadas_sao_listadas_sem_sugerir_nenhuma():
    with tempfile.TemporaryDirectory() as d:
        caso = _caso_com_rodada(d)
        _rodada(caso / "output-teste")
        env = R.folder_above_runs(str(caso))
        assert "output_sugerido" not in env, env
        assert env["rodadas"] == [str(caso / "output"), str(caso / "output-teste")], env
        assert any("pergunte ao usuário" in m for m in env["diagnostics"]), env


def test_busca_nao_entra_dentro_de_uma_rodada():
    with tempfile.TemporaryDirectory() as d:
        caso = _caso_com_rodada(d)
        _rodada(caso / "output" / "simulation" / "copia")
        assert R.folder_above_runs(str(caso))["rodadas"] == [str(caso / "output")]


def test_pasta_da_rodada_nao_e_recusada():
    with tempfile.TemporaryDirectory() as d:
        caso = _caso_com_rodada(d)
        assert R.folder_above_runs(str(caso / "output")) is None
        assert R.read_metadata(str(caso / "output"))["status"] == "ok"


def test_pasta_sem_rodada_nenhuma_segue_o_erro_de_cada_tool():
    with tempfile.TemporaryDirectory() as d:
        assert R.folder_above_runs(d) is None
        assert R.folder_above_runs(str(Path(d) / "nao-existe")) is None


def test_list_entities_empty():
    with tempfile.TemporaryDirectory() as d:
        assert R.list_entities(d) == []


def main():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t(); print(f"  PASS {t.__name__}")
        except AssertionError as e:
            failed += 1; print(f"  FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passaram")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
