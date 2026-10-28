"""Os marcadores `executaveis_reais` e `rede` pulam por padrão e rodam com a opção."""

from pathlib import Path

import pytest

CONFTEST = (Path(__file__).parent / "conftest.py").read_text(encoding="utf-8")

TESTES = """
import pytest

def test_offline():
    pass

@pytest.mark.executaveis_reais
def test_executavel():
    pass

@pytest.mark.rede
def test_rede():
    pass

@pytest.mark.executaveis_reais
@pytest.mark.rede
def test_os_dois():
    pass
"""

INI = """
[pytest]
addopts = --strict-markers
markers =
    executaveis_reais: precisa do novomodelo e do novomodelo-bridge instalados
    rede: acessa a rede
"""


@pytest.fixture
def suite(pytester):
    pytester.makeconftest(CONFTEST.replace('pytest_plugins = ("pytester",)\n', ""))
    pytester.makeini(INI)
    pytester.makepyfile(TESTES)
    return pytester


@pytest.mark.parametrize(
    ("opcoes", "passam", "pulam"),
    [
        ([], 1, 3),
        (["--executaveis-reais"], 2, 2),
        (["--com-rede"], 2, 2),
        (["--executaveis-reais", "--com-rede"], 4, 0),
    ],
)
def test_opcoes_ligam_so_o_que_pedem(suite, opcoes, passam, pulam):
    suite.runpytest(*opcoes).assert_outcomes(passed=passam, skipped=pulam)


def test_pulado_mostra_a_opcao_que_falta(suite):
    resultado = suite.runpytest("-rs")
    resultado.stdout.fnmatch_lines(["*precisa de --executaveis-reais*", "*precisa de --com-rede*"])


def test_marcador_com_erro_de_digitacao_e_recusado(suite):
    suite.makepyfile(
        test_digitado="""
import pytest

@pytest.mark.executaveis_reias
def test_x():
    pass
"""
    )
    resultado = suite.runpytest()
    assert resultado.ret != 0
    resultado.stdout.fnmatch_lines(["*executaveis_reias*not found*"])
