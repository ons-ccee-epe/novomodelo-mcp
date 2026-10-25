"""Um `job.json` corrompido (gravação interrompida, edição à mão) não trava os runs:
o job inválido é ignorado e `run_start`/`run_plan` seguem listando os demais."""
import dataclasses
import json

import pytest

from novomodelo_mcp.adapters import jobs
from novomodelo_mcp.config import load_settings


@pytest.fixture
def settings(tmp_path):
    return dataclasses.replace(load_settings(), state_dir=str(tmp_path))


@pytest.mark.parametrize("conteudo", ['{"status": "running"}', "[1, 2]", '"texto"',
                                      '{"started_at": "ontem"}', "{"])
def test_job_json_invalido_nao_trava_a_listagem(settings, conteudo):
    d = jobs.jobs_root(settings) / "20261024-000000-abcdef"
    d.mkdir()
    (d / "job.json").write_text(conteudo, encoding="utf-8")
    assert jobs.list_jobs(settings) == []
    assert jobs.running_jobs(settings) == []
    assert jobs.read_meta(settings, d.name) is None


def test_job_valido_continua_listado(settings):
    d = jobs.jobs_root(settings) / "20261024-000000-abcdef"
    d.mkdir()
    (d / "job.json").write_text(json.dumps({"started_at": 1.0, "argv": []}), encoding="utf-8")
    assert jobs.read_meta(settings, d.name)["started_at"] == 1.0
