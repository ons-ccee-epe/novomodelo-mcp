"""Impressão digital das entradas do caso e comparação com a rodada registrada."""
from novomodelo_mcp.adapters import run_registry as R


def _caso(tmp_path):
    (tmp_path / "system").mkdir(parents=True)
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    (tmp_path / "system" / "hydros.json").write_text("[]", encoding="utf-8")
    (tmp_path / "config.json.bak").write_text("{}", encoding="utf-8")
    return tmp_path


def test_so_entradas_entram_e_saidas_de_rodada_ficam_de_fora(tmp_path):
    caso = _caso(tmp_path)
    sim = caso / "output-2" / "simulation"
    (sim / "hydros").mkdir(parents=True)
    (sim / "_SUCCESS").write_text("", encoding="utf-8")
    (sim / "hydros" / "x.parquet").write_bytes(b"PAR1")
    (caso / "output" / "training").mkdir(parents=True)
    (caso / "output" / "training" / "metadata.json").write_text("{}", encoding="utf-8")
    assert sorted(R.input_fingerprint(caso)) == ["config.json", "system/hydros.json"]


def test_compara_igual_mudou_e_sem_registro(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "state_dir", lambda settings: tmp_path / "state")
    caso = _caso(tmp_path / "caso")
    out = str(caso / "output")
    antes = R.input_fingerprint(caso)
    assert R.compare(None, output=out, entradas=antes, versao="0.19.0")["caso_igual"] is None
    R.record(None, output=out, case_dir=str(caso), entradas=antes, versao="0.19.0")
    assert R.compare(None, output=out, entradas=antes, versao="0.19.0")["caso_igual"] is True
    (caso / "system" / "hydros.json").write_text("[1]", encoding="utf-8")
    c = R.compare(None, output=out, entradas=R.input_fingerprint(caso), versao="0.19.0")
    assert c["caso_igual"] is False and c["alterados"] == ["system/hydros.json"]


def test_versao_limpa_do_texto_da_cli():
    assert R.plain_version("v0.19.0") == "0.19.0"
    assert R.plain_version("novomodelo   v0.19.1-rc.1") == "0.19.1-rc.1"
    assert R.plain_version(None) is None
