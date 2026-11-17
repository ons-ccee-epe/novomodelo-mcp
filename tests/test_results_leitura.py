"""Leituras de resultado sem Parquet: status, convergência e localização da rodada."""

import json
import tempfile
from pathlib import Path
from typing import Any

from novomodelo_mcp.adapters import results as R


def test_read_metadata_ok():
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "output"
        (out / "training").mkdir(parents=True)
        (out / "training" / "metadata.json").write_text(
            json.dumps(
                {
                    "status": "complete",
                    "bounds": {"final_lower_bound": 1.0, "final_upper_bound": 1.1},
                    "convergence": {"achieved": True, "final_gap_percent": 0.9},
                }
            ),
            encoding="utf-8",
        )
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
        json.dumps({"status": "complete"}), encoding="utf-8"
    )
    return pasta


def _caso_com_rodada(d):
    caso = Path(d) / "caso"
    _rodada(caso / "output")
    return caso


def _rodadas_acima(pasta: Path) -> dict[str, Any]:
    env = R.folder_above_runs(str(pasta))
    assert env is not None
    return env


def test_pasta_do_caso_e_recusada_apontando_a_rodada():
    with tempfile.TemporaryDirectory() as d:
        caso = _caso_com_rodada(d)
        env = R.read_metadata(str(caso))
        assert env["status"] == "error" and env["exit_code"] == 2, env
        assert env["suggested_output"] == str(caso / "output"), env


def test_rodada_com_qualquer_nome_e_mais_funda_e_achada():
    with tempfile.TemporaryDirectory() as d:
        rodada = _rodada(Path(d) / "estudo" / "caso-a" / "rodadas" / "teste 1")
        env = _rodadas_acima(Path(d) / "estudo")
        assert env["suggested_output"] == str(rodada), env


def test_varias_rodadas_sao_listadas_sem_sugerir_nenhuma():
    with tempfile.TemporaryDirectory() as d:
        caso = _caso_com_rodada(d)
        _rodada(caso / "output-teste")
        env = _rodadas_acima(caso)
        assert "suggested_output" not in env, env
        assert env["runs"] == [str(caso / "output"), str(caso / "output-teste")], env
        assert any("pergunte ao usuário" in m for m in env["diagnostics"]), env


def test_busca_nao_entra_dentro_de_uma_rodada():
    with tempfile.TemporaryDirectory() as d:
        caso = _caso_com_rodada(d)
        _rodada(caso / "output" / "simulation" / "copia")
        assert _rodadas_acima(caso)["runs"] == [str(caso / "output")]


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
